from django.urls import path, re_path
from .views import (
    CategoryDetailAPIView,
    CategoryListCreateAPIView,
    ComponentDetailAPIView,
    ComponentListCreateAPIView,
    ManufacturerDetailAPIView,
    ManufacturerListCreateAPIView,
)

urlpatterns = [
    re_path(
        r"^components/?$",
        ComponentListCreateAPIView.as_view(),
        name="component-list-create",
    ),
    re_path(
        r"^components/(?P<pk>\d+)/?$",
        ComponentDetailAPIView.as_view(),
        name="component-detail",
    ),
    re_path(
        r"^manufacturers/?$",
        ManufacturerListCreateAPIView.as_view(),
        name="manufacturer-list-create",
    ),
    re_path(
        r"^manufacturers/(?P<pk>\d+)/?$",
        ManufacturerDetailAPIView.as_view(),
        name="manufacturer-detail",
    ),
    re_path(
        r"^categories/?$",
        CategoryListCreateAPIView.as_view(),
        name="category-list-create",
    ),
    re_path(
        r"^categories/(?P<pk>\d+)/?$",
        CategoryDetailAPIView.as_view(),
        name="category-detail",
    ),
]
