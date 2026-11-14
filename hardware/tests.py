from decimal import Decimal
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from .models import Manufacturer, Category, Component


class HardwareAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

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

    def test_list_components_and_filters(self):
        response = self.client.get("/api/components?search=7800X3D&sort_by=price&order=asc")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "AMD Ryzen 7 7800X3D")
        self.assertEqual(response.data[0]["manufacturer"]["name"], "AMD")
        self.assertEqual(response.data[0]["category"]["name"], "Processors")

    def test_invalid_sort_by_returns_400_unified_error(self):
        response = self.client.get("/api/components?sort_by=invalid_field")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)
        self.assertEqual(response.data["error"]["status_code"], 400)
        self.assertEqual(response.data["error"]["code"], "invalid_query_param")

    def test_create_update_delete_component(self):
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
        update_res = self.client.put(f"/api/components/{comp_id}", update_payload, format="json")
        self.assertEqual(update_res.status_code, status.HTTP_200_OK)
        self.assertEqual(update_res.json()["price"], 199.99)

        delete_res = self.client.delete(f"/api/components/{comp_id}")
        self.assertEqual(delete_res.status_code, status.HTTP_204_NO_CONTENT)

    def test_component_validation_error_400(self):
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
        for url in ("/api/components/9999", "/api/manufacturers/9999", "/api/categories/9999"):
            res = self.client.get(url)
            self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
            self.assertEqual(res.data["error"]["status_code"], 404)
            self.assertEqual(res.data["error"]["code"], "not_found")

    def test_delete_manufacturer_with_components_returns_409(self):
        res = self.client.delete(f"/api/manufacturers/{self.amd.id}")
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res.data["error"]["status_code"], 409)
        self.assertEqual(res.data["error"]["code"], "conflict")
        self.assertEqual(res.data["error"]["details"]["components_count"], 1)

    def test_delete_empty_manufacturer_returns_204(self):
        res = self.client.delete(f"/api/manufacturers/{self.empty_manufacturer.id}")
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)

    def test_delete_category_with_components_returns_409(self):
        res = self.client.delete(f"/api/categories/{self.cpu_category.id}")
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res.data["error"]["status_code"], 409)
        self.assertEqual(res.data["error"]["code"], "conflict")
        self.assertEqual(res.data["error"]["details"]["components_count"], 1)

    def test_delete_empty_category_returns_204(self):
        res = self.client.delete(f"/api/categories/{self.empty_category.id}")
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
