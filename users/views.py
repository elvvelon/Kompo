import logging

from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from hardware.serializers import ErrorResponseSerializer
from .serializers import (
    CurrentUserResponseSerializer,
    LogoutRequestSerializer,
    RegisterResponseSerializer,
    RegistrationSerializer,
)

logger = logging.getLogger(__name__)


class RegisterAPIView(APIView):
    permission_classes = (AllowAny,)

    @extend_schema(
        tags=['Users & Authentication'],
        summary='Register a new user account',
        description=(
            'Register a new user account with strong password validation and immediately '
            'receive JWT `access` and `refresh` tokens.'
        ),
        request=RegistrationSerializer,
        responses={
            201: OpenApiResponse(
                response=RegisterResponseSerializer,
                description='User account created and JWT tokens issued.',
            ),
            400: OpenApiResponse(
                description='Validation error (e.g. duplicate username/email, weak password, or password mismatch).',
            ),
        },
        examples=[
            OpenApiExample(
                'RegisterUserRequest',
                summary='Register user request payload',
                request_only=True,
                value={
                    'username': 'vvelon_builder',
                    'first_name': 'Danylo',
                    'last_name': 'Maister',
                    'email': 'vvelon@example.com',
                    'password': 'StrongPassword123!',
                    'password_confirmation': 'StrongPassword123!',
                },
            ),
        ],
    )
    def post(self, request):
        serializer = RegistrationSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning(
                "User registration failed for username='%s': invalid fields=%s",
                request.data.get('username', '<unknown>'),
                list(serializer.errors.keys()),
            )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        logger.info(
            "User registered successfully: user_id=%s, username='%s'",
            user.id,
            user.username,
        )

        return Response(
            {
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name
                },
                'access': str(refresh.access_token),
                'refresh': str(refresh)
            },
            status=status.HTTP_201_CREATED
        )


class LogoutAPIView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        tags=['Users & Authentication'],
        summary='Logout user and blacklist refresh token',
        description='Invalidate and blacklist the provided JWT `refresh` token for the authenticated user.',
        request=LogoutRequestSerializer,
        responses={
            200: OpenApiResponse(description='Refresh token blacklisted successfully.'),
            400: OpenApiResponse(description='Missing, invalid, or already blacklisted refresh token.'),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description='Authentication credentials were not provided or are invalid.',
            ),
        },
    )
    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            logger.warning(
                'Logout failed for user_id=%s: refresh token was not provided',
                request.user.id,
            )
            return Response(status=status.HTTP_400_BAD_REQUEST)

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            logger.warning(
                'Logout failed for user_id=%s: invalid or expired refresh token',
                request.user.id,
            )
            return Response(status=status.HTTP_400_BAD_REQUEST)

        logger.info('User logged out successfully: user_id=%s', request.user.id)
        return Response(status=status.HTTP_200_OK)


class CurrentUserAPIView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        tags=['Users & Authentication'],
        summary='Get current authenticated user profile',
        description='Retrieve the currently authenticated user profile details and administrator (`is_staff`) status.',
        responses={
            200: OpenApiResponse(
                response=CurrentUserResponseSerializer,
                description='Authenticated user profile details.',
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description='Authentication credentials were not provided or are invalid.',
            ),
        },
    )
    def get(self, request):
        user = request.user
        logger.debug("Retrieved profile for user_id=%s (username='%s')", user.id, user.username)
        return Response(
            {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'is_staff': user.is_staff
            },
            status=status.HTTP_200_OK
        )

