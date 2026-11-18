from django.db import transaction
from django.db.models import Q, Sum
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from hardware.exceptions import build_error_response
from .models import Build, BuildItem
from .serializers import (
    BuildCheckoutSerializer,
    BuildItemCreateSerializer,
    BuildItemUpdateSerializer,
    BuildSerializer,
    BuildUpdateSerializer,
)
from .services import recalculate_build


def get_or_create_workbench(user) -> Build:
    build, _ = Build.objects.get_or_create(
        user=user,
        is_completed=False,
        defaults={'title': 'Draft Build'},
    )
    return build


class CurrentBuildAPIView(APIView):
    """
    GET /api/builds/current - Retrieve the user's active unfinished build (workbench).
    """

    permission_classes = (IsAuthenticated,)

    def get(self, request):
        build = get_or_create_workbench(request.user)
        issues = recalculate_build(build)
        serializer = BuildSerializer(build, context={'compatibility_issues': issues})
        return Response(serializer.data, status=status.HTTP_200_OK)


class CurrentBuildItemCreateAPIView(APIView):
    """
    POST /api/builds/current/items - Add a component to the current workbench build.
    """

    permission_classes = (IsAuthenticated,)

    def post(self, request):
        input_serializer = BuildItemCreateSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        component = input_serializer.validated_data['component']
        quantity = input_serializer.validated_data['quantity']

        with transaction.atomic():
            build = get_or_create_workbench(request.user)

            existing_category_qty = (
                build.items.filter(component__category_id=component.category_id)
                .aggregate(total=Sum('quantity'))['total']
                or 0
            )
            max_allowed = component.category.max_per_build

            if existing_category_qty + quantity > max_allowed:
                return build_error_response(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    code='max_per_build_exceeded',
                    message=(
                        f"Cannot add {quantity} item(s) of category '{component.category.name}'. "
                        f"Maximum allowed per build is {max_allowed} "
                        f"(currently in build: {existing_category_qty})."
                    ),
                    details={
                        'category_id': component.category_id,
                        'category_name': component.category.name,
                        'max_per_build': max_allowed,
                        'current_quantity': existing_category_qty,
                        'requested_quantity': quantity,
                    },
                )

            item, created = BuildItem.objects.get_or_create(
                build=build,
                component=component,
                defaults={
                    'quantity': quantity,
                    'price_at_moment': component.price,
                },
            )
            if not created:
                item.quantity += quantity
                item.price_at_moment = component.price
                item.save(update_fields=['quantity', 'price_at_moment'])

            issues = recalculate_build(build)

        serializer = BuildSerializer(build, context={'compatibility_issues': issues})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class CurrentBuildItemDetailAPIView(APIView):
    """
    PATCH /api/builds/current/items/{item_id}  - Update component quantity in workbench.
    DELETE /api/builds/current/items/{item_id} - Remove component from workbench.
    """

    permission_classes = (IsAuthenticated,)

    @staticmethod
    def _get_item(user, item_id: int) -> BuildItem | None:
        return (
            BuildItem.objects.select_related('build', 'component__category')
            .filter(pk=item_id, build__user=user, build__is_completed=False)
            .first()
        )

    @staticmethod
    def _not_found(item_id: int) -> Response:
        return build_error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code='not_found',
            message=f'Build item with id={item_id} was not found in the current workbench.',
            details={'item_id': item_id},
        )

    def patch(self, request, item_id: int):
        item = self._get_item(request.user, item_id)
        if item is None:
            return self._not_found(item_id)

        input_serializer = BuildItemUpdateSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        new_quantity = input_serializer.validated_data['quantity']

        with transaction.atomic():
            other_category_qty = (
                item.build.items.filter(component__category_id=item.component.category_id)
                .exclude(pk=item.pk)
                .aggregate(total=Sum('quantity'))['total']
                or 0
            )
            max_allowed = item.component.category.max_per_build

            if other_category_qty + new_quantity > max_allowed:
                return build_error_response(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    code='max_per_build_exceeded',
                    message=(
                        f"Cannot set quantity to {new_quantity} for category "
                        f"'{item.component.category.name}'. "
                        f"Maximum allowed per build is {max_allowed}."
                    ),
                    details={
                        'category_id': item.component.category_id,
                        'category_name': item.component.category.name,
                        'max_per_build': max_allowed,
                        'other_items_quantity': other_category_qty,
                        'requested_quantity': new_quantity,
                    },
                )

            item.quantity = new_quantity
            item.price_at_moment = item.component.price
            item.save(update_fields=['quantity', 'price_at_moment'])

            issues = recalculate_build(item.build)

        serializer = BuildSerializer(item.build, context={'compatibility_issues': issues})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, item_id: int):
        return self.patch(request, item_id)

    def delete(self, request, item_id: int):
        item = self._get_item(request.user, item_id)
        if item is None:
            return self._not_found(item_id)

        with transaction.atomic():
            build = item.build
            item.delete()
            recalculate_build(build)

        return Response(status=status.HTTP_204_NO_CONTENT)


class CurrentBuildCheckoutAPIView(APIView):
    """
    POST /api/builds/current/checkout - Finalize and save the current workbench build.
    """

    permission_classes = (IsAuthenticated,)

    def post(self, request):
        input_serializer = BuildCheckoutSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            build = Build.objects.filter(user=request.user, is_completed=False).first()
            if build is None or not build.items.exists():
                return build_error_response(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    code='empty_build',
                    message='Cannot checkout an empty workbench build. Add at least one component first.',
                    details={},
                )

            title = input_serializer.validated_data.get('title')
            if title:
                build.title = title

            if 'is_public' in input_serializer.validated_data:
                build.is_public = input_serializer.validated_data['is_public']

            issues = recalculate_build(build, save=False)
            build.is_completed = True
            build.save(
                update_fields=[
                    'title',
                    'is_completed',
                    'is_compatible',
                    'is_public',
                    'total_price',
                    'total_power_watts',
                    'updated_at',
                ]
            )

        serializer = BuildSerializer(build, context={'compatibility_issues': issues})
        return Response(serializer.data, status=status.HTTP_200_OK)


class BuildListAPIView(APIView):
    """
    GET /api/builds - Retrieve the authenticated user's history of completed PC builds.
    """

    permission_classes = (IsAuthenticated,)

    def get(self, request):
        builds = (
            Build.objects.filter(user=request.user, is_completed=True)
            .select_related('user')
            .prefetch_related('items__component__category', 'items__component__manufacturer')
            .order_by('-created_at', '-id')
        )
        serializer = BuildSerializer(builds, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class PublicBuildListAPIView(APIView):
    """
    GET /api/builds/public - Retrieve all public completed PC builds with optional
    search, compatibility filtering, and sorting.
    """

    permission_classes = (AllowAny,)

    SORT_FIELDS_MAP = {
        'created_at': 'created_at',
        'price': 'total_price',
        'total_price': 'total_price',
        'power_watts': 'total_power_watts',
        'total_power_watts': 'total_power_watts',
    }

    def get(self, request):
        queryset = (
            Build.objects.filter(is_public=True, is_completed=True)
            .select_related('user')
            .prefetch_related('items__component__category', 'items__component__manufacturer')
        )

        search = request.query_params.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | Q(user__username__icontains=search)
            )

        is_compatible_param = request.query_params.get('is_compatible')
        if is_compatible_param is not None and is_compatible_param != '':
            lowered = is_compatible_param.lower()
            if lowered in ('true', '1'):
                queryset = queryset.filter(is_compatible=True)
            elif lowered in ('false', '0'):
                queryset = queryset.filter(is_compatible=False)
            else:
                return build_error_response(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    code='invalid_query_param',
                    message="Query parameter 'is_compatible' must be 'true' or 'false'.",
                    details={
                        'is_compatible': is_compatible_param,
                        'allowed_values': ['true', 'false'],
                    },
                )

        sort_by = request.query_params.get('sort_by')
        order = request.query_params.get('order', 'desc').lower()

        if order not in ('asc', 'desc'):
            return build_error_response(
                status_code=status.HTTP_400_BAD_REQUEST,
                code='invalid_query_param',
                message="Query parameter 'order' must be 'asc' or 'desc'.",
                details={'order': order, 'allowed_values': ['asc', 'desc']},
            )

        if sort_by:
            if sort_by not in self.SORT_FIELDS_MAP:
                return build_error_response(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    code='invalid_query_param',
                    message=(
                        f"Invalid 'sort_by' value '{sort_by}'. "
                        f"Allowed values: {', '.join(self.SORT_FIELDS_MAP.keys())}."
                    ),
                    details={
                        'sort_by': sort_by,
                        'allowed_values': list(self.SORT_FIELDS_MAP.keys()),
                    },
                )
            orm_field = self.SORT_FIELDS_MAP[sort_by]
        else:
            orm_field = 'created_at'

        if order == 'desc':
            queryset = queryset.order_by(f'-{orm_field}', '-id')
        else:
            queryset = queryset.order_by(orm_field, 'id')

        serializer = BuildSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class BuildDetailAPIView(APIView):
    """
    GET /api/builds/{id}    - Retrieve detailed information about a specific build
                              (accessible to anyone if public & completed, or to its owner).
    PATCH /api/builds/{id}  - Update build title or visibility (is_public) by its owner.
    DELETE /api/builds/{id} - Delete a build by its owner.
    """

    permission_classes = (AllowAny,)

    @staticmethod
    def _get_build(pk: int) -> Build | None:
        return (
            Build.objects.select_related('user')
            .prefetch_related(
                'items__component__category', 'items__component__manufacturer'
            )
            .filter(pk=pk)
            .first()
        )

    @staticmethod
    def _not_found(pk: int) -> Response:
        return build_error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code='not_found',
            message=f'Build with id={pk} was not found.',
            details={'id': pk},
        )

    @staticmethod
    def _unauthorized() -> Response:
        return build_error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code='not_authenticated',
            message='Authentication credentials were not provided.',
            details={},
        )

    def get(self, request, pk: int):
        build = self._get_build(pk)
        if build is None:
            return self._not_found(pk)

        is_owner_or_staff = (
            request.user
            and request.user.is_authenticated
            and (build.user_id == request.user.id or request.user.is_staff)
        )

        if not (build.is_public and build.is_completed) and not is_owner_or_staff:
            if not request.user or not request.user.is_authenticated:
                return self._unauthorized()
            return self._not_found(pk)

        if not build.is_completed:
            issues = recalculate_build(build)
            serializer = BuildSerializer(build, context={'compatibility_issues': issues})
        else:
            serializer = BuildSerializer(build)

        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, pk: int):
        if not request.user or not request.user.is_authenticated:
            return self._unauthorized()

        build = self._get_build(pk)
        if build is None:
            return self._not_found(pk)

        if build.user_id != request.user.id and not request.user.is_staff:
            if build.is_public:
                return build_error_response(
                    status_code=status.HTTP_403_FORBIDDEN,
                    code='permission_denied',
                    message="You do not have permission to modify another user's build.",
                    details={'id': pk},
                )
            return self._not_found(pk)

        input_serializer = BuildUpdateSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        wants_public = input_serializer.validated_data.get('is_public')
        if wants_public is True and not build.is_completed:
            return build_error_response(
                status_code=status.HTTP_400_BAD_REQUEST,
                code='draft_build_cannot_be_public',
                message='A draft build cannot be made public until it is completed.',
                details={'id': build.id, 'is_completed': False},
            )

        update_fields = ['updated_at']
        if 'title' in input_serializer.validated_data:
            build.title = input_serializer.validated_data['title']
            update_fields.append('title')
        if 'is_public' in input_serializer.validated_data:
            build.is_public = input_serializer.validated_data['is_public']
            update_fields.append('is_public')

        build.save(update_fields=update_fields)
        serializer = BuildSerializer(build)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk: int):
        if not request.user or not request.user.is_authenticated:
            return self._unauthorized()

        build = self._get_build(pk)
        if build is None:
            return self._not_found(pk)

        if build.user_id != request.user.id and not request.user.is_staff:
            if build.is_public:
                return build_error_response(
                    status_code=status.HTTP_403_FORBIDDEN,
                    code='permission_denied',
                    message="You do not have permission to delete another user's build.",
                    details={'id': pk},
                )
            return self._not_found(pk)

        build.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
