from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import *

urlpatterns = [
    path('login/', TokenObtainPairView.as_view(), name='auth-login'),
    path('logout/', LogoutAPIView.as_view(), name='auth-logout'),
    path('register/', RegisterAPIView.as_view(), name='auth-register'),
    path('me/', CurrentUserAPIView.as_view(), name='auth-me'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh')
]