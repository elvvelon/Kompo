import logging

from django.db.models import Q
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .exceptions import build_error_response
from .serializers import *
from users.permissions import IsAdminOrReadOnly

logger = logging.getLogger(__name__)


class BaseDetailAPIView(APIView):
    model = None
    queryset = None
    permission_classes = (IsAdminOrReadOnly,)

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
        logger.warning("%s with id=%s was not found.", model_name, pk)
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

    permission_classes = (IsAdminOrReadOnly,)

    SORT_FIELDS_MAP = {
        "price": "price",
        "popularity": "popularity_score",
        "power_watts": "power_watts",
        "category": "category__name",
    }

    @extend_schema(
        operation_id="components_list",
        tags=["Components"],
        summary="List hardware components",
        description=(
            "Retrieve a list of hardware and peripheral components from the catalog. "
            "Supports case-insensitive search by component name or exact SKU, filtering by "
            "category or manufacturer ID, and sorting by price, popularity, power consumption, or category."
        ),
        parameters=[
            OpenApiParameter(
                name="search",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Case-insensitive partial match on component name or exact match on SKU.",
            ),
            OpenApiParameter(
                name="category_id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filter components by hardware category ID.",
            ),
            OpenApiParameter(
                name="manufacturer_id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filter components by manufacturer ID.",
            ),
            OpenApiParameter(
                name="sort_by",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                enum=["price", "popularity", "power_watts", "category"],
                description="Field to sort components by (default: id).",
            ),
            OpenApiParameter(
                name="order",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                enum=["asc", "desc"],
                description="Sort order direction: 'asc' (default) or 'desc'.",
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=ComponentListSerializer(many=True),
                description="List of hardware components matching the query criteria.",
                examples=[
                    OpenApiExample(
                        "ComponentsListExample",
                        summary="Sample component list response",
                        value=[
                            {
                                "id": 101,
                                "name": "AMD Ryzen 7 7800X3D",
                                "sku": "100-100000910WOF",
                                "price": 420.0,
                                "power_watts": 120,
                                "popularity_score": 5,
                                "description": "8-core, 16-thread desktop processor with 3D V-Cache technology.",
                                "specifications": {
                                    "socket": "AM5",
                                    "cores": 8,
                                    "threads": 16,
                                    "base_clock_ghz": 4.2,
                                },
                                "image_url": "https://example.com/images/r7-7800x3d.jpg",
                                "manufacturer": {"id": 1, "name": "AMD"},
                                "category": {"id": 1, "name": "Processors", "max_per_build": 1},
                            }
                        ],
                    )
                ],
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Invalid query parameter value or format.",
            ),
        },
    )
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
                logger.warning("Invalid category_id query parameter: '%s'", category_id)
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
                logger.warning("Invalid manufacturer_id query parameter: '%s'", manufacturer_id)
                return build_error_response(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    code="invalid_query_param",
                    message="Query parameter 'manufacturer_id' must be a valid integer.",
                    details={"manufacturer_id": manufacturer_id}
                )

        sort_by = request.query_params.get("sort_by")
        order = request.query_params.get("order", "asc").lower()

        if order not in ("asc", "desc"):
            logger.warning("Invalid order query parameter: '%s'", order)
            return build_error_response(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="invalid_query_param",
                message="Query parameter 'order' must be 'asc' or 'desc'.",
                details={"order": order, "allowed_values": ["asc", "desc"]}
            )

        if sort_by:
            if sort_by not in self.SORT_FIELDS_MAP:
                logger.warning("Invalid sort_by query parameter: '%s'", sort_by)
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

        logger.debug(
            "Listing components (search='%s', category_id=%s, manufacturer_id=%s, sort_by=%s, order=%s)",
            search,
            category_id,
            manufacturer_id,
            sort_by,
            order,
        )
        serializer = ComponentListSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Components"],
        summary="Create a new component",
        description=(
            "Create a new hardware or peripheral component in the catalog. "
            "Requires administrator privileges (`is_staff = true`)."
        ),
        request=ComponentDetailSerializer,
        responses={
            201: OpenApiResponse(
                response=ComponentDetailSerializer,
                description="Component created successfully.",
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Validation error in component data.",
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Authentication credentials were not provided or are invalid.",
            ),
            403: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="User does not have staff permissions.",
            ),
        },
        examples=[
            OpenApiExample(
                "CreateComponentRequest",
                summary="Create motherboard component request",
                request_only=True,
                value={
                    "name": "ASUS TUF GAMING B650-PLUS",
                    "sku": "90MB1BZ0-M0EAY0",
                    "price": 210.0,
                    "power_watts": 45,
                    "popularity_score": 4,
                    "description": "AMD B650 ATX motherboard with DDR5 support.",
                    "specifications": {
                        "socket": "AM5",
                        "memory_type": "DDR5",
                        "form_factor": "ATX",
                        "memory_slots": 4,
                    },
                    "image_url": "https://example.com/images/b650-plus.jpg",
                    "manufacturer_id": 3,
                    "category_id": 2,
                },
            ),
        ],
    )
    def post(self, request):
        serializer = ComponentDetailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        component = serializer.save()
        logger.info(
            "Component created: id=%s, sku='%s', name='%s' by user_id=%s",
            component.id,
            component.sku,
            component.name,
            request.user.id,
        )
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

    @extend_schema(
        tags=["Components"],
        summary="Get component details by ID",
        description="Retrieve full technical specifications, manufacturer info, and category details of a single component.",
        parameters=[
            OpenApiParameter(
                name="id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description="Unique integer ID of the component.",
            )
        ],
        responses={
            200: OpenApiResponse(
                response=ComponentDetailSerializer,
                description="Component details retrieved successfully.",
            ),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Component with the specified ID was not found.",
            ),
        },
    )
    def get(self, request, pk: int):
        component = self._get_object(pk)
        if component is None:
            return self._not_found(pk)
        logger.debug("Retrieved component details for id=%s (sku='%s')", component.id, component.sku)
        serializer = ComponentDetailSerializer(component)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Components"],
        summary="Replace component details",
        description="Fully update an existing component by ID. Requires administrator privileges (`is_staff = true`).",
        parameters=[
            OpenApiParameter(
                name="id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description="Unique integer ID of the component.",
            )
        ],
        request=ComponentDetailSerializer,
        responses={
            200: OpenApiResponse(
                response=ComponentDetailSerializer,
                description="Component updated successfully.",
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Validation error in request body.",
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Authentication credentials were not provided.",
            ),
            403: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="User does not have staff permissions.",
            ),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Component not found.",
            ),
        },
    )
    def put(self, request, pk: int):
        component = self._get_object(pk)
        if component is None:
            return self._not_found(pk)
        serializer = ComponentDetailSerializer(component, data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        logger.info(
            "Component updated (PUT): id=%s, sku='%s' by user_id=%s",
            updated.id,
            updated.sku,
            request.user.id,
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Components"],
        summary="Partially update component details",
        description="Partially update fields of an existing component by ID. Requires administrator privileges (`is_staff = true`).",
        parameters=[
            OpenApiParameter(
                name="id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description="Unique integer ID of the component.",
            )
        ],
        request=ComponentDetailSerializer,
        responses={
            200: OpenApiResponse(
                response=ComponentDetailSerializer,
                description="Component partially updated successfully.",
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Validation error in request body.",
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Authentication credentials were not provided.",
            ),
            403: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="User does not have staff permissions.",
            ),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Component not found.",
            ),
        },
    )
    def patch(self, request, pk: int):
        component = self._get_object(pk)
        if component is None:
            return self._not_found(pk)
        serializer = ComponentDetailSerializer(component, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        logger.info(
            "Component updated (PATCH): id=%s, sku='%s' by user_id=%s",
            updated.id,
            updated.sku,
            request.user.id,
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Components"],
        summary="Delete a component",
        description="Permanently delete a component from the catalog. Requires administrator privileges (`is_staff = true`).",
        parameters=[
            OpenApiParameter(
                name="id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description="Unique integer ID of the component.",
            )
        ],
        responses={
            204: OpenApiResponse(description="Component deleted successfully."),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Authentication credentials were not provided.",
            ),
            403: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="User does not have staff permissions.",
            ),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Component not found.",
            ),
        },
    )
    def delete(self, request, pk: int):
        component = self._get_object(pk)
        if component is None:
            return self._not_found(pk)
        comp_sku = component.sku
        component.delete()
        logger.info(
            "Component deleted: id=%s, sku='%s' by user_id=%s",
            pk,
            comp_sku,
            request.user.id,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class ManufacturerListCreateAPIView(APIView):
    """
    GET /api/manufacturers  - List all manufacturers.
    POST /api/manufacturers - Create a new manufacturer.
    """
    permission_classes = (IsAdminOrReadOnly,)

    @extend_schema(
        operation_id="manufacturers_list",
        tags=["Manufacturers"],
        summary="List all manufacturers",
        description="Retrieve a list of all hardware manufacturers available in the directory.",
        responses={
            200: OpenApiResponse(
                response=ManufacturerListSerializer(many=True),
                description="List of manufacturers.",
            ),
        },
    )
    def get(self, request):
        manufacturers = Manufacturer.objects.all().order_by("id")
        logger.debug("Listing all manufacturers")
        serializer = ManufacturerListSerializer(manufacturers, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Manufacturers"],
        summary="Create a new manufacturer",
        description="Add a new hardware brand to the directory. Requires administrator privileges (`is_staff = true`).",
        request=ManufacturerDetailSerializer,
        responses={
            201: OpenApiResponse(
                response=ManufacturerDetailSerializer,
                description="Manufacturer created successfully.",
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Validation error in request body.",
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Authentication credentials were not provided.",
            ),
            403: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="User does not have staff permissions.",
            ),
        },
    )
    def post(self, request):
        serializer = ManufacturerDetailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        manufacturer = serializer.save()
        logger.info(
            "Manufacturer created: id=%s, name='%s' by user_id=%s",
            manufacturer.id,
            manufacturer.name,
            request.user.id,
        )
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

    @extend_schema(
        tags=["Manufacturers"],
        summary="Get manufacturer details by ID",
        description="Retrieve full brand information along with all components produced by this manufacturer.",
        parameters=[
            OpenApiParameter(
                name="id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description="Unique integer ID of the manufacturer.",
            )
        ],
        responses={
            200: OpenApiResponse(
                response=ManufacturerDetailSerializer,
                description="Manufacturer details retrieved successfully.",
            ),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Manufacturer not found.",
            ),
        },
    )
    def get(self, request, pk: int):
        manufacturer = self._get_object(pk)
        if manufacturer is None:
            return self._not_found(pk)
        logger.debug("Retrieved manufacturer details for id=%s (name='%s')", manufacturer.id, manufacturer.name)
        serializer = ManufacturerDetailSerializer(manufacturer)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Manufacturers"],
        summary="Replace manufacturer details",
        description="Fully update manufacturer details by ID. Requires administrator privileges (`is_staff = true`).",
        parameters=[
            OpenApiParameter(
                name="id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description="Unique integer ID of the manufacturer.",
            )
        ],
        request=ManufacturerDetailSerializer,
        responses={
            200: OpenApiResponse(
                response=ManufacturerDetailSerializer,
                description="Manufacturer updated successfully.",
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Validation error in request body.",
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Authentication credentials were not provided.",
            ),
            403: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="User does not have staff permissions.",
            ),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Manufacturer not found.",
            ),
        },
    )
    def put(self, request, pk: int):
        manufacturer = self._get_object(pk)
        if manufacturer is None:
            return self._not_found(pk)
        serializer = ManufacturerDetailSerializer(manufacturer, data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        logger.info(
            "Manufacturer updated (PUT): id=%s, name='%s' by user_id=%s",
            updated.id,
            updated.name,
            request.user.id,
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Manufacturers"],
        summary="Partially update manufacturer details",
        description="Partially update manufacturer fields by ID. Requires administrator privileges (`is_staff = true`).",
        parameters=[
            OpenApiParameter(
                name="id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description="Unique integer ID of the manufacturer.",
            )
        ],
        request=ManufacturerDetailSerializer,
        responses={
            200: OpenApiResponse(
                response=ManufacturerDetailSerializer,
                description="Manufacturer partially updated successfully.",
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Validation error in request body.",
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Authentication credentials were not provided.",
            ),
            403: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="User does not have staff permissions.",
            ),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Manufacturer not found.",
            ),
        },
    )
    def patch(self, request, pk: int):
        manufacturer = self._get_object(pk)
        if manufacturer is None:
            return self._not_found(pk)
        serializer = ManufacturerDetailSerializer(
            manufacturer, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        logger.info(
            "Manufacturer updated (PATCH): id=%s, name='%s' by user_id=%s",
            updated.id,
            updated.name,
            request.user.id,
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Manufacturers"],
        summary="Delete a manufacturer",
        description=(
            "Delete a manufacturer by ID. Returns `409 Conflict` if any components are still "
            "associated with this manufacturer. Requires administrator privileges (`is_staff = true`)."
        ),
        parameters=[
            OpenApiParameter(
                name="id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description="Unique integer ID of the manufacturer.",
            )
        ],
        responses={
            204: OpenApiResponse(description="Manufacturer deleted successfully."),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Authentication credentials were not provided.",
            ),
            403: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="User does not have staff permissions.",
            ),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Manufacturer not found.",
            ),
            409: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Cannot delete manufacturer because components are still linked to it.",
            ),
        },
    )
    def delete(self, request, pk: int):
        manufacturer = self._get_object(pk)
        if manufacturer is None:
            return self._not_found(pk)

        components_count = manufacturer.components.count()
        if components_count > 0:
            logger.warning(
                "Conflict deleting manufacturer id=%s ('%s'): %d component(s) still associated",
                manufacturer.id,
                manufacturer.name,
                components_count,
            )
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

        manuf_name = manufacturer.name
        manufacturer.delete()
        logger.info(
            "Manufacturer deleted: id=%s, name='%s' by user_id=%s",
            pk,
            manuf_name,
            request.user.id,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class CategoryListCreateAPIView(APIView):
    """
    GET /api/categories  - List all hardware categories.
    POST /api/categories - Create a new hardware category.
    """
    permission_classes = (IsAdminOrReadOnly,)

    @extend_schema(
        operation_id="categories_list",
        tags=["Categories"],
        summary="List all hardware categories",
        description="Retrieve all equipment and peripheral categories along with their per-build quantity quotas (`max_per_build`).",
        responses={
            200: OpenApiResponse(
                response=CategoryListSerializer(many=True),
                description="List of hardware categories.",
            ),
        },
    )
    def get(self, request):
        categories = Category.objects.all().order_by("id")
        logger.debug("Listing all hardware categories")
        serializer = CategoryListSerializer(categories, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Categories"],
        summary="Create a new hardware category",
        description="Create a new hardware or peripheral category. Requires administrator privileges (`is_staff = true`).",
        request=CategoryDetailSerializer,
        responses={
            201: OpenApiResponse(
                response=CategoryListSerializer,
                description="Category created successfully.",
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Validation error in request body.",
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Authentication credentials were not provided.",
            ),
            403: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="User does not have staff permissions.",
            ),
        },
    )
    def post(self, request):
        serializer = CategoryDetailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        category = serializer.save()
        logger.info(
            "Category created: id=%s, slug='%s', name='%s' by user_id=%s",
            category.id,
            category.slug,
            category.name,
            request.user.id,
        )
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

    @extend_schema(
        tags=["Categories"],
        summary="Get category details by ID",
        description="Retrieve category details, build quota, and all components belonging to this category.",
        parameters=[
            OpenApiParameter(
                name="id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description="Unique integer ID of the category.",
            )
        ],
        responses={
            200: OpenApiResponse(
                response=CategoryDetailSerializer,
                description="Category details retrieved successfully.",
            ),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Category not found.",
            ),
        },
    )
    def get(self, request, pk: int):
        category = self._get_object(pk)
        if category is None:
            return self._not_found(pk)
        logger.debug("Retrieved category details for id=%s (slug='%s')", category.id, category.slug)
        serializer = CategoryDetailSerializer(category)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Categories"],
        summary="Replace category details",
        description="Fully update a hardware category by ID. Requires administrator privileges (`is_staff = true`).",
        parameters=[
            OpenApiParameter(
                name="id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description="Unique integer ID of the category.",
            )
        ],
        request=CategoryDetailSerializer,
        responses={
            200: OpenApiResponse(
                response=CategoryDetailSerializer,
                description="Category updated successfully.",
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Validation error in request body.",
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Authentication credentials were not provided.",
            ),
            403: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="User does not have staff permissions.",
            ),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Category not found.",
            ),
        },
    )
    def put(self, request, pk: int):
        category = self._get_object(pk)
        if category is None:
            return self._not_found(pk)
        serializer = CategoryDetailSerializer(category, data=request.data)
        serializer.is_valid(raise_exception=True)
        category = serializer.save()
        logger.info(
            "Category updated (PUT): id=%s, slug='%s' by user_id=%s",
            category.id,
            category.slug,
            request.user.id,
        )
        return Response(
            CategoryDetailSerializer(category).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["Categories"],
        summary="Partially update category details",
        description="Partially update a hardware category by ID. Requires administrator privileges (`is_staff = true`).",
        parameters=[
            OpenApiParameter(
                name="id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description="Unique integer ID of the category.",
            )
        ],
        request=CategoryDetailSerializer,
        responses={
            200: OpenApiResponse(
                response=CategoryDetailSerializer,
                description="Category partially updated successfully.",
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Validation error in request body.",
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Authentication credentials were not provided.",
            ),
            403: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="User does not have staff permissions.",
            ),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Category not found.",
            ),
        },
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
        logger.info(
            "Category updated (PATCH): id=%s, slug='%s' by user_id=%s",
            category.id,
            category.slug,
            request.user.id,
        )
        return Response(
            CategoryDetailSerializer(category).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["Categories"],
        summary="Delete a category",
        description=(
            "Delete a category by ID. Returns `409 Conflict` if any components still belong "
            "to this category. Requires administrator privileges (`is_staff = true`)."
        ),
        parameters=[
            OpenApiParameter(
                name="id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description="Unique integer ID of the category.",
            )
        ],
        responses={
            204: OpenApiResponse(description="Category deleted successfully."),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Authentication credentials were not provided.",
            ),
            403: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="User does not have staff permissions.",
            ),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Category not found.",
            ),
            409: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Cannot delete category because components still belong to it.",
            ),
        },
    )
    def delete(self, request, pk: int):
        category = self._get_object(pk)
        if category is None:
            return self._not_found(pk)

        components_count = category.components.count()
        if components_count > 0:
            logger.warning(
                "Conflict deleting category id=%s ('%s'): %d component(s) still belong to it",
                category.id,
                category.name,
                components_count,
            )
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

        cat_name = category.name
        category.delete()
        logger.info(
            "Category deleted: id=%s, name='%s' by user_id=%s",
            pk,
            cat_name,
            request.user.id,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

