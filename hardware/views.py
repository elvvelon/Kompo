from django.db.models import Q
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .exceptions import build_error_response
from .models import Category, Component, Manufacturer
from .serializers import (
    CategoryDetailSerializer,
    CategoryListSerializer,
    ComponentDetailSerializer,
    ComponentListSerializer,
    ManufacturerDetailSerializer,
    ManufacturerListSerializer,
)


class BaseDetailAPIView(APIView):
    model = None
    queryset = None

    @classmethod
    def _get_object(cls, pk: int):
        qs = cls.queryset if cls.queryset is not None else cls.model.objects.all()
        try:
            return qs.get(pk=pk)
        except cls.model.DoesNotExist:
            return None

    @classmethod
    def _not_found(cls, pk: int) -> Response:
        model_name = cls.model._meta.verbose_name.title()
        return build_error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message=f"{model_name} with id={pk} was not found.",
            details={"id": pk},
        )


class ComponentListCreateAPIView(APIView):
    """
    GET /api/components  - List components with search, filtering, and sorting.
    POST /api/components - Create a new component.
    """

    SORT_FIELDS_MAP = {
        "price": "price",
        "popularity": "popularity_score",
        "power_watts": "power_watts",
        "category": "category__name",
    }

    def get(self, request):
        queryset = Component.objects.prefetch_related("manufacturer", "category").all()

        search = request.query_params.get("search", "")
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(sku=search))

        category_id = request.query_params.get("category_id")
        if category_id is not None and category_id != "":
            try:
                queryset = queryset.filter(category_id=int(category_id))
            except ValueError:
                return build_error_response(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    code="invalid_query_parameter",
                    message="Query parameter 'category_id' must be a valid integer.",
                    details={"category_id": category_id}
                )

        manufacturer_id = request.query_params.get("manufacturer_id")
        if manufacturer_id is not None and manufacturer_id != "":
            try:
                queryset = queryset.filter(manufacturer_id=int(manufacturer_id))
            except ValueError:
                return build_error_response(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    code="invalid_query_param",
                    message="Query parameter 'manufacturer_id' must be a valid integer.",
                    details={"manufacturer_id": manufacturer_id}
                )

        sort_by = request.query_params.get("sort_by")
        order = request.query_params.get("order", "asc").lower()

        if order not in ("asc", "desc"):
            return build_error_response(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="invalid_query_param",
                message="Query parameter 'order' must be 'asc' or 'desc'.",
                details={"order": order, "allowed_values": ["asc", "desc"]}
            )

        if sort_by:
            if sort_by not in self.SORT_FIELDS_MAP:
                return build_error_response(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    code="invalid_query_param",
                    message=(
                        f"Invalid 'sort_by' value '{sort_by}'. "
                        f"Allowed values: {', '.join(self.SORT_FIELDS_MAP.keys())}."
                    ),
                    details={
                        "sort_by": sort_by,
                        "allowed_values": list(self.SORT_FIELDS_MAP.keys()),
                    }
                )
            orm_field = self.SORT_FIELDS_MAP[sort_by]
        else:
            orm_field = "id"

        if order == "desc":
            orm_field = f"-{orm_field}"
        queryset = queryset.order_by(orm_field)

        serializer = ComponentListSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = ComponentDetailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ComponentDetailAPIView(BaseDetailAPIView):
    """
    GET /api/components/{id}    - Retrieve full details of a component.
    PUT /api/components/{id}    - Update a component.
    PATCH /api/components/{id}  - Partially update a component.
    DELETE /api/components/{id} - Delete a component.
    """
    model = Component
    queryset = Component.objects.select_related("manufacturer", "category")

    def get(self, request, pk: int):
        component = self._get_object(pk)
        if component is None:
            return self._not_found(pk)
        serializer = ComponentDetailSerializer(component)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk: int):
        component = self._get_object(pk)
        if component is None:
            return self._not_found(pk)
        serializer = ComponentDetailSerializer(component, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, pk: int):
        component = self._get_object(pk)
        if component is None:
            return self._not_found(pk)
        serializer = ComponentDetailSerializer(component, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk: int):
        component = self._get_object(pk)
        if component is None:
            return self._not_found(pk)
        component.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ManufacturerListCreateAPIView(APIView):
    """
    GET /api/manufacturers  - List all manufacturers.
    POST /api/manufacturers - Create a new manufacturer.
    """

    def get(self, request):
        manufacturers = Manufacturer.objects.all().order_by("id")
        serializer = ManufacturerListSerializer(manufacturers, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = ManufacturerDetailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ManufacturerDetailAPIView(BaseDetailAPIView):
    """
    GET /api/manufacturers/{id}    - Retrieve manufacturer details & its components.
    PUT /api/manufacturers/{id}    - Update a manufacturer.
    PATCH /api/manufacturers/{id}  - Partially update a manufacturer.
    DELETE /api/manufacturers/{id} - Delete a manufacturer (blocked with 409 if it has components).
    """
    model = Manufacturer
    queryset = Manufacturer.objects.prefetch_related("components__category")

    def get(self, request, pk: int):
        manufacturer = self._get_object(pk)
        if manufacturer is None:
            return self._not_found(pk)
        serializer = ManufacturerDetailSerializer(manufacturer)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk: int):
        manufacturer = self._get_object(pk)
        if manufacturer is None:
            return self._not_found(pk)
        serializer = ManufacturerDetailSerializer(manufacturer, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, pk: int):
        manufacturer = self._get_object(pk)
        if manufacturer is None:
            return self._not_found(pk)
        serializer = ManufacturerDetailSerializer(
            manufacturer, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk: int):
        manufacturer = self._get_object(pk)
        if manufacturer is None:
            return self._not_found(pk)

        components_count = manufacturer.components.count()
        if components_count > 0:
            return build_error_response(
                status_code=status.HTTP_409_CONFLICT,
                code="conflict",
                message=(
                    f"Cannot delete manufacturer '{manufacturer.name}' because "
                    f"{components_count} component(s) are associated with it. "
                    f"Please delete or reassign those components first."
                ),
                details={
                    "manufacturer_id": manufacturer.id,
                    "manufacturer_name": manufacturer.name,
                    "components_count": components_count,
                },
            )

        manufacturer.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CategoryListCreateAPIView(APIView):
    """
    GET /api/categories  - List all hardware categories.
    POST /api/categories - Create a new hardware category.
    """

    def get(self, request):
        categories = Category.objects.all().order_by("id")
        serializer = CategoryListSerializer(categories, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = CategoryDetailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        category = serializer.save()
        return Response(
            CategoryListSerializer(category).data,
            status=status.HTTP_201_CREATED,
        )


class CategoryDetailAPIView(BaseDetailAPIView):
    """
    GET /api/categories/{id}    - Retrieve category details & its components.
    PUT /api/categories/{id}    - Update a category.
    PATCH /api/categories/{id}  - Partially update a category.
    DELETE /api/categories/{id} - Delete a category (blocked with 409 if it has components).
    """
    model = Category
    queryset = Category.objects.prefetch_related("components__manufacturer")

    def get(self, request, pk: int):
        category = self._get_object(pk)
        if category is None:
            return self._not_found(pk)
        serializer = CategoryDetailSerializer(category)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, pk: int):
        category = self._get_object(pk)
        if category is None:
            return self._not_found(pk)
        serializer = CategoryDetailSerializer(category, data=request.data)
        serializer.is_valid(raise_exception=True)
        category = serializer.save()
        return Response(
            CategoryDetailSerializer(category).data,
            status=status.HTTP_200_OK,
        )

    def patch(self, request, pk: int):
        category = self._get_object(pk)
        if category is None:
            return self._not_found(pk)
        serializer = CategoryDetailSerializer(
            category, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        category = serializer.save()
        return Response(
            CategoryDetailSerializer(category).data,
            status=status.HTTP_200_OK,
        )

    def delete(self, request, pk: int):
        category = self._get_object(pk)
        if category is None:
            return self._not_found(pk)

        components_count = category.components.count()
        if components_count > 0:
            return build_error_response(
                status_code=status.HTTP_409_CONFLICT,
                code="conflict",
                message=(
                    f"Cannot delete category '{category.name}' because "
                    f"{components_count} component(s) belong to it. "
                    f"Please delete or move those components to another category first."
                ),
                details={
                    "category_id": category.id,
                    "category_name": category.name,
                    "components_count": components_count,
                },
            )

        category.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
