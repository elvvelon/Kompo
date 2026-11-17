from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from .permissions import IsAdminOrReadOnly
from .serializers import RegistrationSerializer


class UsersAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.register_url = "/api/users/register/"
        self.me_url = "/api/users/me/"
        self.refresh_url = "/api/users/token/refresh/"

        self.user_data = {
            "username": "vvelon_builder",
            "first_name": "Danylo",
            "last_name": "Maister",
            "email": "vvelon@example.com",
            "password": "StrongPassword123!",
            "password_confirmation": "StrongPassword123!",
        }

    def test_register_user_success_and_returns_jwt_tokens(self):
        response = self.client.post(self.register_url, self.user_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("user", response.data)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

        self.assertEqual(response.data["user"]["username"], "vvelon_builder")
        self.assertEqual(response.data["user"]["email"], "vvelon@example.com")
        self.assertNotIn("password", response.data["user"])

        user = User.objects.get(username="vvelon_builder")
        self.assertNotEqual(user.password, self.user_data["password"])
        self.assertTrue(user.check_password(self.user_data["password"]))

    def test_register_password_mismatch_returns_400(self):
        payload = {**self.user_data, "password_confirmation": "DifferentPass123!"}
        response = self.client.post(self.register_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("non_field_errors", response.data)
        self.assertEqual(User.objects.count(), 0)

    def test_register_duplicate_username_and_email_returns_400(self):
        User.objects.create_user(
            username="vvelon_builder",
            email="vvelon@example.com",
            password="StrongPassword123!",
        )

        response = self.client.post(self.register_url, self.user_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", response.data)
        self.assertIn("email", response.data)

    def test_register_weak_password_returns_400(self):
        payload = {
            **self.user_data,
            "password": "password123",
            "password_confirmation": "password123",
        }
        response = self.client.post(self.register_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

    def test_register_blank_username_returns_400(self):
        payload = {**self.user_data, "username": "   "}
        response = self.client.post(self.register_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", response.data)

    def test_current_user_me_requires_authentication(self):
        response = self.client.get(self.me_url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("error", response.data)
        self.assertEqual(response.data["error"]["status_code"], 401)

    def test_current_user_me_returns_profile_data(self):
        user = User.objects.create_user(
            username="pc_enthusiast",
            email="pc@example.com",
            password="StrongPassword123!",
            first_name="Gordon",
            last_name="Freeman",
            is_staff=True,
        )
        refresh = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

        response = self.client.get(self.me_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {
                "id": user.id,
                "username": "pc_enthusiast",
                "email": "pc@example.com",
                "first_name": "Gordon",
                "last_name": "Freeman",
                "is_staff": True,
            },
        )

    def test_token_refresh_rotates_and_blacklists_old_token(self):
        user = User.objects.create_user(
            username="rotator",
            email="rotator@example.com",
            password="StrongPassword123!",
        )
        refresh = RefreshToken.for_user(user)
        old_refresh_str = str(refresh)

        response = self.client.post(
            self.refresh_url, {"refresh": old_refresh_str}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

        reuse_response = self.client.post(
            self.refresh_url, {"refresh": old_refresh_str}, format="json"
        )
        self.assertEqual(reuse_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_and_logout_blacklist_flow(self):
        user = User.objects.create_user(
            username="login_user",
            email="login@example.com",
            password="StrongPassword123!",
        )
        login_res = self.client.post(
            "/api/users/login/",
            {"username": "login_user", "password": "StrongPassword123!"},
            format="json",
        )
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)
        access_token = login_res.data["access"]
        refresh_token = login_res.data["refresh"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

        # Missing refresh token -> 400
        missing_res = self.client.post("/api/users/logout/", {}, format="json")
        self.assertEqual(missing_res.status_code, status.HTTP_400_BAD_REQUEST)

        # Invalid refresh token -> 400
        invalid_res = self.client.post(
            "/api/users/logout/", {"refresh": "invalid.token.str"}, format="json"
        )
        self.assertEqual(invalid_res.status_code, status.HTTP_400_BAD_REQUEST)

        # Valid refresh token -> 200 OK and blacklists token
        logout_res = self.client.post(
            "/api/users/logout/", {"refresh": refresh_token}, format="json"
        )
        self.assertEqual(logout_res.status_code, status.HTTP_200_OK)

        # Reusing blacklisted refresh token on logout -> 400
        repeat_res = self.client.post(
            "/api/users/logout/", {"refresh": refresh_token}, format="json"
        )
        self.assertEqual(repeat_res.status_code, status.HTTP_400_BAD_REQUEST)



class RegistrationSerializerUnitTest(TestCase):
    def test_serializer_creates_user_with_hashed_password(self):
        data = {
            "username": "unit_user",
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane@example.com",
            "password": "ComplexPassword987!",
            "password_confirmation": "ComplexPassword987!",
        }
        serializer = RegistrationSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

        user = serializer.save()
        self.assertEqual(user.username, "unit_user")
        self.assertEqual(user.email, "jane@example.com")
        self.assertTrue(user.check_password("ComplexPassword987!"))


class IsAdminOrReadOnlyPermissionTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.permission = IsAdminOrReadOnly()
        self.regular_user = User.objects.create_user(
            username="regular", password="StrongPassword123!", is_staff=False
        )
        self.admin_user = User.objects.create_user(
            username="admin", password="StrongPassword123!", is_staff=True
        )

    def test_safe_methods_allowed_for_anonymous_and_regular_users(self):
        request = self.factory.get("/api/components/1")
        request.user = self.regular_user
        self.assertTrue(
            self.permission.has_object_permission(request, None, obj=object())
        )

    def test_write_methods_denied_for_non_staff_user(self):
        request = self.factory.delete("/api/components/1")
        request.user = self.regular_user
        self.assertFalse(
            self.permission.has_object_permission(request, None, obj=object())
        )

    def test_write_methods_allowed_for_staff_user(self):
        request = self.factory.delete("/api/components/1")
        request.user = self.admin_user
        self.assertTrue(
            self.permission.has_object_permission(request, None, obj=object())
        )