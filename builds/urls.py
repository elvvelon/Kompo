from django.urls import path

from .views import (
    BuildDetailAPIView,
    BuildListAPIView,
    CurrentBuildAPIView,
    CurrentBuildCheckoutAPIView,
    CurrentBuildItemCreateAPIView,
    CurrentBuildItemDetailAPIView,
    PublicBuildListAPIView
)

urlpatterns = [
    path('builds', BuildListAPIView.as_view(), name='build-list'),
    path('builds/public', PublicBuildListAPIView.as_view(), name='build-public-list'),
    path('builds/current', CurrentBuildAPIView.as_view(), name='build-current'),
    path(
        'builds/current/items',
        CurrentBuildItemCreateAPIView.as_view(),
        name='build-current-item-create',
    ),
    path(
        'builds/current/items/<int:item_id>',
        CurrentBuildItemDetailAPIView.as_view(),
        name='build-current-item-detail',
    ),
    path(
        'builds/current/checkout',
        CurrentBuildCheckoutAPIView.as_view(),
        name='build-current-checkout',
    ),
    path('builds/<int:pk>', BuildDetailAPIView.as_view(), name='build-detail'),
]
