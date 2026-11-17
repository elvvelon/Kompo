import logging

from django.db import transaction
from django.db.models import Q, Sum
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from hardware.exceptions import build_error_response
from hardware.serializers import ErrorResponseSerializer
from .models import Build, BuildItem
from .serializers import (
    BuildCheckoutSerializer,
    BuildItemCreateSerializer,
    BuildItemUpdateSerializer,
    BuildSerializer,
    BuildUpdateSerializer,
)
from .services import recalculate_build

logger = logging.getLogger(__name__)


def get_or_create_workbench(user) -> Build:
    build, created = Build.objects.get_or_create(
        user=user,
        is_completed=False,
        defaults={'title': 'Draft Build'},
    )
    if created:
        logger.info(
            'Initialized new draft workbench build id=%s for user_id=%s',
            build.id,
            user.id,
        )
    return build


class CurrentBuildAPIView(APIView):
    """
    GET /api/builds/current - Retrieve the user's active unfinished build (workbench).
    """

    permission_classes = (IsAuthenticated,)

    @extend_schema(
        tags=['Builds & Workbench'],
        summary='Get current active workbench build',
        description=(
            'Retrieve (or automatically initialize) the authenticated user\'s active draft '
            'workbench build (`is_completed = false`) with live pricing, power estimation, '
            'recommended PSU wattage, and real-time compatibility validation.'
        ),
        responses={
            200: OpenApiResponse(
                response=BuildSerializer,
                description='Active draft workbench build.',
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description='Authentication credentials were not provided or are invalid.',
            ),
        },
    )
    def get(self, request):
        build = get_or_create_workbench(request.user)
        issues = recalculate_build(build)
        logger.debug(
            'Retrieved active workbench build id=%s for user_id=%s',
            build.id,
            request.user.id,
        )
        serializer = BuildSerializer(build, context={'compatibility_issues': issues})
        return Response(serializer.data, status=status.HTTP_200_OK)


class CurrentBuildItemCreateAPIView(APIView):
    """
    POST /api/builds/current/items - Add a component to the current workbench build.
    """

    permission_classes = (IsAuthenticated,)

    @extend_schema(
        tags=['Builds & Workbench'],
        summary='Add a component to the current workbench',
        description=(
            'Add a hardware component (or increment its quantity if already present) in the '
            'authenticated user\'s active workbench build. Enforces `category.max_per_build` '
            'quantity limits and recalculates compatibility.'
        ),
        request=BuildItemCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=BuildSerializer,
                description='Component added to workbench and build recalculated.',
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description='Validation error or category `max_per_build` quota exceeded.',
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description='Authentication credentials were not provided.',
            ),
        },
        examples=[
            OpenApiExample(
                'AddWorkbenchItemRequest',
                summary='Add RAM module to workbench',
                request_only=True,
                value={'component_id': 105, 'quantity': 2},
            ),
        ],
    )
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
                logger.warning(
                    "Max per build exceeded on add: user_id=%s, build_id=%s, category='%s' (current=%d, requested=%d, max=%d)",
                    request.user.id,
                    build.id,
                    component.category.name,
                    existing_category_qty,
                    quantity,
                    max_allowed,
                )
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

        logger.info(
            'Added component id=%s (qty=%d) to workbench build id=%s for user_id=%s',
            component.id,
            quantity,
            build.id,
            request.user.id,
        )
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
        logger.warning('Workbench build item id=%s was not found.', item_id)
        return build_error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code='not_found',
            message=f'Build item with id={item_id} was not found in the current workbench.',
            details={'item_id': item_id},
        )

    @extend_schema(
        tags=['Builds & Workbench'],
        summary='Update workbench item quantity',
        description=(
            'Set a new quantity for a specific component item in the active workbench '
            'while validating `category.max_per_build` limits.'
        ),
        parameters=[
            OpenApiParameter(
                name='item_id',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description='Unique integer ID of the build item in the workbench.',
            )
        ],
        request=BuildItemUpdateSerializer,
        responses={
            200: OpenApiResponse(
                response=BuildSerializer,
                description='Item quantity updated and build recalculated.',
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description='Invalid quantity or `max_per_build` limit exceeded.',
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description='Authentication credentials were not provided.',
            ),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                description='Build item not found in the user\'s active workbench.',
            ),
        },
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
                logger.warning(
                    "Max per build exceeded on update: user_id=%s, item_id=%s, category='%s' (other=%d, requested=%d, max=%d)",
                    request.user.id,
                    item.id,
                    item.component.category.name,
                    other_category_qty,
                    new_quantity,
                    max_allowed,
                )
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

        logger.info(
            'Updated workbench item id=%s quantity=%d in build id=%s for user_id=%s',
            item.id,
            new_quantity,
            item.build_id,
            request.user.id,
        )
        serializer = BuildSerializer(item.build, context={'compatibility_issues': issues})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=['Builds & Workbench'],
        summary='Replace workbench item quantity',
        description='Set a new quantity for a specific component item in the active workbench.',
        parameters=[
            OpenApiParameter(
                name='item_id',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description='Unique integer ID of the build item in the workbench.',
            )
        ],
        request=BuildItemUpdateSerializer,
        responses={
            200: OpenApiResponse(
                response=BuildSerializer,
                description='Item quantity updated and build recalculated.',
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description='Invalid quantity or `max_per_build` limit exceeded.',
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description='Authentication credentials were not provided.',
            ),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                description='Build item not found in the user\'s active workbench.',
            ),
        },
    )
    def put(self, request, item_id: int):
        return self.patch(request, item_id)

    @extend_schema(
        tags=['Builds & Workbench'],
        summary='Remove item from current workbench',
        description='Remove a component item from the active workbench and recalculate build totals and compatibility.',
        parameters=[
            OpenApiParameter(
                name='item_id',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description='Unique integer ID of the build item in the workbench.',
            )
        ],
        responses={
            204: OpenApiResponse(description='Build item removed from workbench.'),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description='Authentication credentials were not provided.',
            ),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                description='Build item not found in the user\'s active workbench.',
            ),
        },
    )
    def delete(self, request, item_id: int):
        item = self._get_item(request.user, item_id)
        if item is None:
            return self._not_found(item_id)

        with transaction.atomic():
            build = item.build
            item.delete()
            recalculate_build(build)

        logger.info(
            'Removed item id=%s from workbench build id=%s for user_id=%s',
            item_id,
            build.id,
            request.user.id,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class CurrentBuildCheckoutAPIView(APIView):
    """
    POST /api/builds/current/checkout - Finalize and save the current workbench build.
    """

    permission_classes = (IsAuthenticated,)

    @extend_schema(
        tags=['Builds & Workbench'],
        summary='Checkout and finalize current workbench build',
        description=(
            'Finalize the current non-empty draft workbench build (`is_completed = true`), '
            'locking component prices (`price_at_moment`) and optionally assigning a custom '
            '`title` and publishing it (`is_public = true`).'
        ),
        request=BuildCheckoutSerializer,
        responses={
            200: OpenApiResponse(
                response=BuildSerializer,
                description='Workbench build finalized and saved to user history.',
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description='Workbench build is empty (`empty_build`) or validation error.',
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description='Authentication credentials were not provided.',
            ),
        },
        examples=[
            OpenApiExample(
                'CheckoutBuildRequest',
                summary='Finalize and publish workbench build',
                request_only=True,
                value={'title': 'ML & 1440p Gaming Rig', 'is_public': True},
            ),
        ],
    )
    def post(self, request):
        input_serializer = BuildCheckoutSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            build = Build.objects.filter(user=request.user, is_completed=False).first()
            if build is None or not build.items.exists():
                logger.warning(
                    'Checkout rejected for user_id=%s: workbench build is empty',
                    request.user.id,
                )
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

        logger.info(
            "Build id=%s checked out by user_id=%s (title='%s', is_public=%s, total_price=%s)",
            build.id,
            request.user.id,
            build.title,
            build.is_public,
            build.total_price,
        )
        serializer = BuildSerializer(build, context={'compatibility_issues': issues})
        return Response(serializer.data, status=status.HTTP_200_OK)


class BuildListAPIView(APIView):
    """
    GET /api/builds - Retrieve the authenticated user's history of completed PC builds.
    """

    permission_classes = (IsAuthenticated,)

    @extend_schema(
        operation_id='builds_list',
        tags=['Builds & Workbench'],
        summary='List user\'s completed PC builds',
        description='Retrieve the authenticated user\'s history of finalized PC builds (`is_completed = true`), ordered newest first.',
        responses={
            200: OpenApiResponse(
                response=BuildSerializer(many=True),
                description='List of completed builds owned by the user.',
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description='Authentication credentials were not provided.',
            ),
        },
    )
    def get(self, request):
        builds = (
            Build.objects.filter(user=request.user, is_completed=True)
            .select_related('user')
            .prefetch_related('items__component__category', 'items__component__manufacturer')
            .order_by('-created_at', '-id')
        )
        logger.debug('Listing completed builds for user_id=%s', request.user.id)
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

    @extend_schema(
        operation_id='builds_public_list',
        tags=['Builds & Workbench'],
        summary='List public community PC builds',
        description=(
            'Browse all community-published completed PC builds (`is_public = true` and '
            '`is_completed = true`). Supports search by build title or author username, '
            'filtering by compatibility status, and sorting.'
        ),
        parameters=[
            OpenApiParameter(
                name='search',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description='Case-insensitive search by build title or author username.',
            ),
            OpenApiParameter(
                name='is_compatible',
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                required=False,
                description='Filter public builds by hardware compatibility status (`true` or `false`).',
            ),
            OpenApiParameter(
                name='sort_by',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                enum=['created_at', 'price', 'total_price', 'power_watts', 'total_power_watts'],
                description='Field to sort public builds by (default: `created_at`).',
            ),
            OpenApiParameter(
                name='order',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                enum=['asc', 'desc'],
                description='Sort direction: `asc` or `desc` (default: `desc`).',
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=BuildSerializer(many=True),
                description='List of public completed PC builds.',
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description='Invalid query parameter value.',
            ),
        },
    )
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
                logger.warning("Invalid is_compatible query parameter: '%s'", is_compatible_param)
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
            logger.warning("Invalid order query parameter on public builds: '%s'", order)
            return build_error_response(
                status_code=status.HTTP_400_BAD_REQUEST,
                code='invalid_query_param',
                message="Query parameter 'order' must be 'asc' or 'desc'.",
                details={'order': order, 'allowed_values': ['asc', 'desc']},
            )

        if sort_by:
            if sort_by not in self.SORT_FIELDS_MAP:
                logger.warning("Invalid sort_by query parameter on public builds: '%s'", sort_by)
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

        logger.debug(
            "Listing public builds (search='%s', is_compatible=%s, sort_by=%s, order=%s)",
            search,
            is_compatible_param,
            sort_by,
            order,
        )
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
        logger.warning('Build with id=%s was not found or is not accessible.', pk)
        return build_error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code='not_found',
            message=f'Build with id={pk} was not found.',
            details={'id': pk},
        )

    @staticmethod
    def _unauthorized() -> Response:
        logger.warning('Unauthorized access attempt to build detail endpoint.')
        return build_error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code='not_authenticated',
            message='Authentication credentials were not provided.',
            details={},
        )

    @extend_schema(
        tags=['Builds & Workbench'],
        summary='Get PC build details by ID',
        description=(
            'Retrieve full details of a PC build by ID. Publicly accessible without '
            'authentication if `is_public = true` and `is_completed = true`; otherwise '
            'accessible only to the build owner or staff.'
        ),
        parameters=[
            OpenApiParameter(
                name='id',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description='Unique integer ID of the build.',
            )
        ],
        responses={
            200: OpenApiResponse(
                response=BuildSerializer,
                description='Build details retrieved successfully.',
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description='Unauthenticated request to a non-public build.',
            ),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                description='Build not found or private to another user.',
            ),
        },
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

        logger.debug('Retrieved build details for id=%s', build.id)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=['Builds & Workbench'],
        summary='Update build title or visibility',
        description=(
            'Update a build\'s `title` or public visibility (`is_public`). Only the build '
            'owner or staff can update a build. Draft builds (`is_completed = false`) cannot '
            'be made public.'
        ),
        parameters=[
            OpenApiParameter(
                name='id',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description='Unique integer ID of the build.',
            )
        ],
        request=BuildUpdateSerializer,
        responses={
            200: OpenApiResponse(
                response=BuildSerializer,
                description='Build updated successfully.',
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description='Validation error or attempt to publish a draft build.',
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description='Authentication credentials were not provided.',
            ),
            403: OpenApiResponse(
                response=ErrorResponseSerializer,
                description='User does not have permission to modify another user\'s build.',
            ),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                description='Build not found.',
            ),
        },
    )
    def patch(self, request, pk: int):
        if not request.user or not request.user.is_authenticated:
            return self._unauthorized()

        build = self._get_build(pk)
        if build is None:
            return self._not_found(pk)

        if build.user_id != request.user.id and not request.user.is_staff:
            if build.is_public:
                logger.warning(
                    'Permission denied: user_id=%s attempted to modify build id=%s owned by user_id=%s',
                    request.user.id,
                    build.id,
                    build.user_id,
                )
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
            logger.warning(
                'Rejected attempt to publish draft build id=%s by user_id=%s',
                build.id,
                request.user.id,
            )
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
        logger.info(
            "Build id=%s updated by user_id=%s (title='%s', is_public=%s)",
            build.id,
            request.user.id,
            build.title,
            build.is_public,
        )
        serializer = BuildSerializer(build)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=['Builds & Workbench'],
        summary='Delete a PC build',
        description='Permanently delete a PC build. Accessible only to the build owner or staff.',
        parameters=[
            OpenApiParameter(
                name='id',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description='Unique integer ID of the build.',
            )
        ],
        responses={
            204: OpenApiResponse(description='Build deleted successfully.'),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description='Authentication credentials were not provided.',
            ),
            403: OpenApiResponse(
                response=ErrorResponseSerializer,
                description='User does not have permission to delete another user\'s build.',
            ),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                description='Build not found.',
            ),
        },
    )
    def delete(self, request, pk: int):
        if not request.user or not request.user.is_authenticated:
            return self._unauthorized()

        build = self._get_build(pk)
        if build is None:
            return self._not_found(pk)

        if build.user_id != request.user.id and not request.user.is_staff:
            if build.is_public:
                logger.warning(
                    'Permission denied: user_id=%s attempted to delete build id=%s owned by user_id=%s',
                    request.user.id,
                    build.id,
                    build.user_id,
                )
                return build_error_response(
                    status_code=status.HTTP_403_FORBIDDEN,
                    code='permission_denied',
                    message="You do not have permission to delete another user's build.",
                    details={'id': pk},
                )
            return self._not_found(pk)

        build.delete()
        logger.info('Build id=%s deleted by user_id=%s', pk, request.user.id)
        return Response(status=status.HTTP_204_NO_CONTENT)

