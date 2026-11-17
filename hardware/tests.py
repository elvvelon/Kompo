from decimal import Decimal
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Category, Component, Manufacturer


class HardwareAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.admin_user = User.objects.create_user(
            username="admin_hw",
            email="admin@kompo.com",
            password="StrongPassword123!",
            is_staff=True,
        )
        self.regular_user = User.objects.create_user(
            username="user_hw",
            email="user@kompo.com",
            password="StrongPassword123!",
            is_staff=False,
        )

        self.admin_token = str(RefreshToken.for_user(self.admin_user).access_token)
        self.user_token = str(RefreshToken.for_user(self.regular_user).access_token)

        self.amd = Manufacturer.objects.create(
            name="AMD",
            country="USA",
            founded_year=1969,
            description="Semiconductor manufacturer.",
            logo_url="https://example.com/logos/amd.png",
        )
        self.empty_manufacturer = Manufacturer.objects.create(
            name="Noctua",
            country="Austria",
            founded_year=2005,
            description="Premium cooling solutions.",
            logo_url="https://example.com/logos/noctua.png",
        )

        self.cpu_category = Category.objects.create(
            name="Processors",
            slug="cpus",
            description="Central processing units.",
            max_per_build=1,
            is_periphery=False,
        )
        self.empty_category = Category.objects.create(
            name="Coolers",
            slug="coolers",
            description="CPU coolers.",
            max_per_build=1,
            is_periphery=False,
        )

        self.cpu = Component.objects.create(
            name="AMD Ryzen 7 7800X3D",
            sku="100-100000910WOF",
            price=Decimal("420.00"),
            power_watts=120,
            popularity_score=5,
            description="8-core gaming CPU.",
            specifications={"socket": "AM5", "cores": 8},
            image_url="https://example.com/images/r7.jpg",
            manufacturer=self.amd,
            category=self.cpu_category,
        )

    def authenticate_admin(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.admin_token}")

    def authenticate_regular_user(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.user_token}")

    def clear_authentication(self):
        self.client.credentials()

    def test_list_components_and_filters_public_access(self):
        self.clear_authentication()
        response = self.client.get(
            f"/api/components?search=7800X3D&category_id={self.cpu_category.id}"
            f"&manufacturer_id={self.amd.id}&sort_by=price&order=asc"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "AMD Ryzen 7 7800X3D")
        self.assertEqual(response.data[0]["manufacturer"]["name"], "AMD")
        self.assertEqual(response.data[0]["category"]["name"], "Processors")

    def test_invalid_query_params_return_400_unified_error(self):
        for query in (
            "sort_by=invalid_field",
            "order=sideways",
            "category_id=abc",
            "manufacturer_id=xyz",
        ):
            res = self.client.get(f"/api/components?{query}")
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("error", res.data)
            self.assertEqual(res.data["error"]["status_code"], 400)

    def test_write_endpoints_require_admin_permissions(self):
        payload = {
            "name": "AMD Ryzen 5 7600X",
            "sku": "100-100000593WOF",
            "price": 229.00,
            "power_watts": 105,
            "popularity_score": 4,
            "manufacturer_id": self.amd.id,
            "category_id": self.cpu_category.id,
        }

        # Unauthenticated -> 401
        self.clear_authentication()
        unauth_res = self.client.post("/api/components", payload, format="json")
        self.assertEqual(unauth_res.status_code, status.HTTP_401_UNAUTHORIZED)

        # Non-staff user -> 403
        self.authenticate_regular_user()
        forbidden_res = self.client.post("/api/components", payload, format="json")
        self.assertEqual(forbidden_res.status_code, status.HTTP_403_FORBIDDEN)

        forbidden_del = self.client.delete(f"/api/components/{self.cpu.id}")
        self.assertEqual(forbidden_del.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_create_update_patch_and_delete_component(self):
        self.authenticate_admin()
        payload = {
            "name": "AMD Ryzen 5 7600X",
            "sku": "100-100000593WOF",
            "price": 229.00,
            "power_watts": 105,
            "popularity_score": 4,
            "description": "6-core AM5 processor.",
            "specifications": {"socket": "AM5", "cores": 6},
            "image_url": "https://example.com/images/r5.jpg",
            "manufacturer_id": self.amd.id,
            "category_id": self.cpu_category.id,
        }
        create_res = self.client.post("/api/components", payload, format="json")
        self.assertEqual(create_res.status_code, status.HTTP_201_CREATED)
        comp_id = create_res.data["id"]

        update_payload = dict(payload, price=199.99)
        update_res = self.client.put(
            f"/api/components/{comp_id}", update_payload, format="json"
        )
        self.assertEqual(update_res.status_code, status.HTTP_200_OK)
        self.assertEqual(update_res.json()["price"], 199.99)

        patch_res = self.client.patch(
            f"/api/components/{comp_id}", {"popularity_score": 5}, format="json"
        )
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_res.data["popularity_score"], 5)

        delete_res = self.client.delete(f"/api/components/{comp_id}")
        self.assertEqual(delete_res.status_code, status.HTTP_204_NO_CONTENT)

    def test_component_validation_error_400(self):
        self.authenticate_admin()
        payload = {
            "name": "Invalid Price CPU",
            "sku": "INV-001",
            "price": -10.00,
            "power_watts": 65,
            "manufacturer_id": self.amd.id,
            "category_id": self.cpu_category.id,
        }
        res = self.client.post("/api/components", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", res.data)
        self.assertEqual(res.data["error"]["status_code"], 400)
        self.assertIn("price", res.data["error"]["details"])

    def test_not_found_404_unified_error(self):
        for url in (
            "/api/components/9999",
            "/api/manufacturers/9999",
            "/api/categories/9999",
        ):
            res = self.client.get(url)
            self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
            self.assertEqual(res.data["error"]["status_code"], 404)
            self.assertEqual(res.data["error"]["code"], "not_found")

    def test_manufacturer_crud_and_conflict_on_delete(self):
        # Public GET list and detail
        list_res = self.client.get("/api/manufacturers")
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_res.data), 2)

        detail_res = self.client.get(f"/api/manufacturers/{self.amd.id}")
        self.assertEqual(detail_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(detail_res.data["components"]), 1)

        # Admin create, update, and delete
        self.authenticate_admin()
        create_res = self.client.post(
            "/api/manufacturers",
            {
                "name": "Corsair",
                "country": "USA",
                "founded_year": 1994,
                "description": "Gaming peripherals and memory.",
                "logo_url": "https://example.com/logos/corsair.png",
            },
            format="json",
        )
        self.assertEqual(create_res.status_code, status.HTTP_201_CREATED)

        # Delete manufacturer with existing components -> 409 Conflict
        conflict_res = self.client.delete(f"/api/manufacturers/{self.amd.id}")
        self.assertEqual(conflict_res.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(conflict_res.data["error"]["status_code"], 409)
        self.assertEqual(conflict_res.data["error"]["code"], "conflict")
        self.assertEqual(conflict_res.data["error"]["details"]["components_count"], 1)

        # Delete empty manufacturer -> 204 No Content
        empty_del_res = self.client.delete(
            f"/api/manufacturers/{self.empty_manufacturer.id}"
        )
        self.assertEqual(empty_del_res.status_code, status.HTTP_204_NO_CONTENT)

    def test_category_crud_and_conflict_on_delete(self):
        # Public GET list and detail
        list_res = self.client.get("/api/categories")
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_res.data), 2)

        detail_res = self.client.get(f"/api/categories/{self.cpu_category.id}")
        self.assertEqual(detail_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(detail_res.data["components"]), 1)

        # Admin create and delete
        self.authenticate_admin()
        create_res = self.client.post(
            "/api/categories",
            {
                "name": "Motherboards",
                "slug": "motherboards",
                "description": "Main system boards.",
                "max_per_build": 1,
                "is_periphery": False,
            },
            format="json",
        )
        self.assertEqual(create_res.status_code, status.HTTP_201_CREATED)

        # Delete category with existing components -> 409 Conflict
        conflict_res = self.client.delete(f"/api/categories/{self.cpu_category.id}")
        self.assertEqual(conflict_res.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(conflict_res.data["error"]["status_code"], 409)
        self.assertEqual(conflict_res.data["error"]["code"], "conflict")
        self.assertEqual(conflict_res.data["error"]["details"]["components_count"], 1)

        # Delete empty category -> 204 No Content
        empty_del_res = self.client.delete(f"/api/categories/{self.empty_category.id}")
        self.assertEqual(empty_del_res.status_code, status.HTTP_204_NO_CONTENT)
