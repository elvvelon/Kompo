from decimal import Decimal
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from hardware.models import Category, Component, Manufacturer
from .models import Build, BuildItem


class BuildsAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.user = User.objects.create_user(
            username='builder_alex',
            email='alex@example.com',
            password='StrongPassword123!',
        )
        self.other_user = User.objects.create_user(
            username='other_builder',
            email='other@example.com',
            password='StrongPassword123!',
        )

        refresh = RefreshToken.for_user(self.user)
        self.access_token = str(refresh.access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.access_token}')

        # Manufacturers
        self.amd = Manufacturer.objects.create(
            name='AMD',
            country='USA',
            founded_year=1969,
        )
        self.intel = Manufacturer.objects.create(
            name='Intel',
            country='USA',
            founded_year=1968,
        )
        self.asus = Manufacturer.objects.create(
            name='ASUS',
            country='Taiwan',
            founded_year=1989,
        )
        self.kingston = Manufacturer.objects.create(
            name='Kingston',
            country='USA',
            founded_year=1987,
        )
        self.bequiet = Manufacturer.objects.create(
            name='Be Quiet!',
            country='Germany',
            founded_year=2001,
        )

        # Categories
        self.cpu_cat = Category.objects.create(
            name='Processors',
            slug='cpus',
            max_per_build=1,
            is_periphery=False,
        )
        self.mb_cat = Category.objects.create(
            name='Motherboards',
            slug='motherboards',
            max_per_build=1,
            is_periphery=False,
        )
        self.ram_cat = Category.objects.create(
            name='Memory (RAM)',
            slug='ram',
            max_per_build=4,
            is_periphery=False,
        )
        self.case_cat = Category.objects.create(
            name='PC Cases',
            slug='cases',
            max_per_build=1,
            is_periphery=False,
        )
        self.cooler_cat = Category.objects.create(
            name='Coolers',
            slug='coolers',
            max_per_build=1,
            is_periphery=False,
        )
        self.psu_cat = Category.objects.create(
            name='Power Supplies',
            slug='power-supplies',
            max_per_build=1,
            is_periphery=False,
        )

        # Components
        self.cpu_am5 = Component.objects.create(
            name='AMD Ryzen 7 7800X3D',
            sku='CPU-AM5-7800X3D',
            price=Decimal('420.00'),
            power_watts=120,
            popularity_score=5,
            specifications={'socket': 'AM5', 'cores': 8, 'threads': 16},
            manufacturer=self.amd,
            category=self.cpu_cat,
        )
        self.cpu_lga1700 = Component.objects.create(
            name='Intel Core i7-14700K',
            sku='CPU-LGA1700-14700K',
            price=Decimal('390.00'),
            power_watts=250,
            popularity_score=4,
            specifications={'socket': 'LGA1700', 'cores': 20},
            manufacturer=self.intel,
            category=self.cpu_cat,
        )
        self.mb_am5_ddr5_atx = Component.objects.create(
            name='ASUS TUF GAMING B650-PLUS',
            sku='MB-AM5-B650',
            price=Decimal('210.00'),
            power_watts=45,
            popularity_score=4,
            specifications={
                'socket': 'AM5',
                'memory_type': 'DDR5',
                'form_factor': 'ATX',
                'memory_slots': 4,
            },
            manufacturer=self.asus,
            category=self.mb_cat,
        )
        self.ram_ddr5 = Component.objects.create(
            name='Kingston FURY Beast 16GB DDR5',
            sku='RAM-DDR5-16G',
            price=Decimal('60.00'),
            power_watts=5,
            popularity_score=5,
            specifications={'memory_type': 'DDR5', 'capacity_gb': 16},
            manufacturer=self.kingston,
            category=self.ram_cat,
        )
        self.ram_ddr4 = Component.objects.create(
            name='Kingston FURY Beast 16GB DDR4',
            sku='RAM-DDR4-16G',
            price=Decimal('40.00'),
            power_watts=5,
            popularity_score=4,
            specifications={'memory_type': 'DDR4', 'capacity_gb': 16},
            manufacturer=self.kingston,
            category=self.ram_cat,
        )
        self.case_itx_only = Component.objects.create(
            name='Compact Mini-ITX Case',
            sku='CASE-ITX-01',
            price=Decimal('95.00'),
            power_watts=0,
            popularity_score=3,
            specifications={'supported_form_factors': ['Mini-ITX']},
            manufacturer=self.bequiet,
            category=self.case_cat,
        )
        self.cooler_am4_only = Component.objects.create(
            name='Legacy AM4 Cooler',
            sku='COOL-AM4-01',
            price=Decimal('35.00'),
            power_watts=5,
            popularity_score=2,
            specifications={'supported_sockets': ['AM4', 'LGA1200']},
            manufacturer=self.bequiet,
            category=self.cooler_cat,
        )
        self.psu_weak = Component.objects.create(
            name='Office PSU 150W',
            sku='PSU-150W',
            price=Decimal('30.00'),
            power_watts=0,
            popularity_score=1,
            specifications={'wattage': 150},
            manufacturer=self.bequiet,
            category=self.psu_cat,
        )
        self.psu_850w = Component.objects.create(
            name='Be Quiet! Pure Power 12 M 850W',
            sku='PSU-850W',
            price=Decimal('135.00'),
            power_watts=0,
            popularity_score=5,
            specifications={'wattage': 850},
            manufacturer=self.bequiet,
            category=self.psu_cat,
        )

    def test_unauthenticated_access_returns_401(self):
        self.client.credentials()
        res = self.client.get('/api/builds/current')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_current_build_initializes_empty_workbench(self):
        res = self.client.get('/api/builds/current')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['title'], 'Draft Build')
        self.assertFalse(res.data['is_completed'])
        self.assertTrue(res.data['is_compatible'])
        self.assertEqual(res.data['compatibility_issues'], [])
        self.assertEqual(res.data['total_price'], 0.0)
        self.assertEqual(res.data['total_power_watts'], 0)
        self.assertEqual(res.data['recommended_psu_watts'], 0)
        self.assertEqual(res.data['items'], [])

    def test_add_update_and_delete_workbench_items(self):
        # Add CPU
        res_cpu = self.client.post(
            '/api/builds/current/items',
            {'component_id': self.cpu_am5.id, 'quantity': 1},
            format='json',
        )
        self.assertEqual(res_cpu.status_code, status.HTTP_201_CREATED)

        # Add Motherboard
        res_mb = self.client.post(
            '/api/builds/current/items',
            {'component_id': self.mb_am5_ddr5_atx.id, 'quantity': 1},
            format='json',
        )
        self.assertEqual(res_mb.status_code, status.HTTP_201_CREATED)
        self.assertTrue(res_mb.data['is_compatible'])
        self.assertEqual(res_mb.data['total_price'], 630.00)
        self.assertEqual(res_mb.data['total_power_watts'], 165)
        self.assertEqual(res_mb.data['recommended_psu_watts'], 250)
        self.assertEqual(len(res_mb.data['items']), 2)

        # Add RAM (quantity=2)
        res_ram = self.client.post(
            '/api/builds/current/items',
            {'component_id': self.ram_ddr5.id, 'quantity': 2},
            format='json',
        )
        self.assertEqual(res_ram.status_code, status.HTTP_201_CREATED)
        ram_item_id = next(
            i['item_id']
            for i in res_ram.data['items']
            if i['component']['id'] == self.ram_ddr5.id
        )

        # Patch RAM quantity to 4
        res_patch = self.client.patch(
            f'/api/builds/current/items/{ram_item_id}',
            {'quantity': 4},
            format='json',
        )
        self.assertEqual(res_patch.status_code, status.HTTP_200_OK)
        self.assertEqual(res_patch.data['total_price'], 630.00 + 60.00 * 4)

        # Exceed max_per_build on PATCH (RAM max_per_build=4)
        res_patch_exceed = self.client.patch(
            f'/api/builds/current/items/{ram_item_id}',
            {'quantity': 5},
            format='json',
        )
        self.assertEqual(res_patch_exceed.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            res_patch_exceed.data['error']['code'], 'max_per_build_exceeded'
        )

        # Delete RAM item
        res_del = self.client.delete(f'/api/builds/current/items/{ram_item_id}')
        self.assertEqual(res_del.status_code, status.HTTP_204_NO_CONTENT)

        res_current = self.client.get('/api/builds/current')
        self.assertEqual(len(res_current.data['items']), 2)
        self.assertEqual(res_current.data['total_price'], 630.00)

    def test_exceed_max_per_build_on_post_returns_400(self):
        self.client.post(
            '/api/builds/current/items',
            {'component_id': self.cpu_am5.id, 'quantity': 1},
            format='json',
        )
        # Attempting to add a second CPU when max_per_build=1
        res = self.client.post(
            '/api/builds/current/items',
            {'component_id': self.cpu_lga1700.id, 'quantity': 1},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data['error']['code'], 'max_per_build_exceeded')

    def test_compatibility_engine_detects_all_hardware_conflicts(self):
        # 1. Add LGA1700 CPU + AM5 ATX DDR5 Motherboard -> Socket conflict
        self.client.post(
            '/api/builds/current/items',
            {'component_id': self.cpu_lga1700.id, 'quantity': 1},
            format='json',
        )
        self.client.post(
            '/api/builds/current/items',
            {'component_id': self.mb_am5_ddr5_atx.id, 'quantity': 1},
            format='json',
        )
        # 2. Add DDR4 RAM -> Memory type conflict with DDR5 motherboard
        self.client.post(
            '/api/builds/current/items',
            {'component_id': self.ram_ddr4.id, 'quantity': 1},
            format='json',
        )
        # 3. Add Mini-ITX only Case -> Form factor conflict with ATX motherboard
        self.client.post(
            '/api/builds/current/items',
            {'component_id': self.case_itx_only.id, 'quantity': 1},
            format='json',
        )
        # 4. Add AM4 Cooler -> Cooler socket conflict with LGA1700 CPU
        self.client.post(
            '/api/builds/current/items',
            {'component_id': self.cooler_am4_only.id, 'quantity': 1},
            format='json',
        )
        # 5. Add 150W PSU -> Insufficient headroom for ~305W build
        res = self.client.post(
            '/api/builds/current/items',
            {'component_id': self.psu_weak.id, 'quantity': 1},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertFalse(res.data['is_compatible'])
        self.assertEqual(len(res.data['compatibility_issues']), 5)

    def test_checkout_build_and_history_endpoints(self):
        # Checkout empty build should fail with 400
        empty_res = self.client.post(
            '/api/builds/current/checkout',
            {'title': 'Empty Rig'},
            format='json',
        )
        self.assertEqual(empty_res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(empty_res.data['error']['code'], 'empty_build')

        # Add compatible components and checkout
        self.client.post(
            '/api/builds/current/items',
            {'component_id': self.cpu_am5.id, 'quantity': 1},
            format='json',
        )
        self.client.post(
            '/api/builds/current/items',
            {'component_id': self.mb_am5_ddr5_atx.id, 'quantity': 1},
            format='json',
        )
        self.client.post(
            '/api/builds/current/items',
            {'component_id': self.psu_850w.id, 'quantity': 1},
            format='json',
        )

        checkout_res = self.client.post(
            '/api/builds/current/checkout',
            {'title': 'ML & 1440p Gaming Rig'},
            format='json',
        )
        self.assertEqual(checkout_res.status_code, status.HTTP_200_OK)
        self.assertTrue(checkout_res.data['is_completed'])
        self.assertTrue(checkout_res.data['is_compatible'])
        self.assertEqual(checkout_res.data['title'], 'ML & 1440p Gaming Rig')
        completed_build_id = checkout_res.data['id']

        # History list (GET /api/builds) should contain the completed build
        list_res = self.client.get('/api/builds')
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_res.data), 1)
        self.assertEqual(list_res.data[0]['id'], completed_build_id)

        # Detail view (GET /api/builds/{id})
        detail_res = self.client.get(f'/api/builds/{completed_build_id}')
        self.assertEqual(detail_res.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_res.data['title'], 'ML & 1440p Gaming Rig')

        # After checkout, GET /api/builds/current creates a fresh draft build
        new_draft_res = self.client.get('/api/builds/current')
        self.assertEqual(new_draft_res.status_code, status.HTTP_200_OK)
        self.assertNotEqual(new_draft_res.data['id'], completed_build_id)
        self.assertFalse(new_draft_res.data['is_completed'])
        self.assertEqual(new_draft_res.data['items'], [])

    def test_private_build_of_another_user_returns_404(self):
        other_build = Build.objects.create(
            user=self.other_user,
            title='Private Build',
            is_completed=True,
            is_public=False,
        )
        res = self.client.get(f'/api/builds/{other_build.id}')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


    def test_public_builds_list_filtering_sorting_and_anonymous_access(self):
        b1 = Build.objects.create(
            user=self.user,
            title="Budget AM5 Workstation",
            is_completed=True,
            is_public=True,
            is_compatible=True,
            total_price=Decimal("750.00"),
            total_power_watts=220,
        )
        b2 = Build.objects.create(
            user=self.other_user,
            title="Extreme 4K Gaming Rig",
            is_completed=True,
            is_public=True,
            is_compatible=False,
            total_price=Decimal("2400.00"),
            total_power_watts=650,
        )
        # Private build should not appear in public list
        Build.objects.create(
            user=self.other_user,
            title="Secret Prototype",
            is_completed=True,
            is_public=False,
            total_price=Decimal("1200.00"),
        )

        # Unauthenticated guest can browse public builds
        self.client.credentials()
        res = self.client.get("/api/builds/public")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 2)

        # Search by title or username
        search_res = self.client.get("/api/builds/public?search=Workstation")
        self.assertEqual(len(search_res.data), 1)
        self.assertEqual(search_res.data[0]["id"], b1.id)

        # Filter by is_compatible=true
        compat_res = self.client.get("/api/builds/public?is_compatible=true")
        self.assertEqual(len(compat_res.data), 1)
        self.assertEqual(compat_res.data[0]["id"], b1.id)

        # Sort by price ascending
        sort_res = self.client.get("/api/builds/public?sort_by=price&order=asc")
        self.assertEqual(sort_res.status_code, status.HTTP_200_OK)
        self.assertEqual([b["id"] for b in sort_res.data], [b1.id, b2.id])

        # Unauthenticated guest can view a single public build by ID
        detail_res = self.client.get(f"/api/builds/{b2.id}")
        self.assertEqual(detail_res.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_res.data["title"], "Extreme 4K Gaming Rig")
        self.assertEqual(detail_res.data["user"]["username"], "other_builder")

    def test_update_build_visibility_and_draft_public_protection(self):
        # Create draft build for self.user
        draft_res = self.client.get("/api/builds/current")
        draft_id = draft_res.data["id"]

        # Draft build cannot be made public
        bad_patch = self.client.patch(
            f"/api/builds/{draft_id}",
            {"is_public": True},
            format="json",
        )
        self.assertEqual(bad_patch.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            bad_patch.data["error"]["code"], "draft_build_cannot_be_public"
        )

        # Completed build can be toggled to public by its owner
        completed = Build.objects.create(
            user=self.user,
            title="My Completed Rig",
            is_completed=True,
            is_public=False,
        )
        ok_patch = self.client.patch(
            f"/api/builds/{completed.id}",
            {"is_public": True, "title": "Published Rig"},
            format="json",
        )
        self.assertEqual(ok_patch.status_code, status.HTTP_200_OK)
        self.assertTrue(ok_patch.data["is_public"])
        self.assertEqual(ok_patch.data["title"], "Published Rig")

        # Another user cannot modify or delete someone else's public build (403)
        other_build = Build.objects.create(
            user=self.other_user,
            title="Other User Public Build",
            is_completed=True,
            is_public=True,
        )
        forbidden_patch = self.client.patch(
            f"/api/builds/{other_build.id}",
            {"title": "Hacked Title"},
            format="json",
        )
        self.assertEqual(forbidden_patch.status_code, status.HTTP_403_FORBIDDEN)

        forbidden_del = self.client.delete(f"/api/builds/{other_build.id}")
        self.assertEqual(forbidden_del.status_code, status.HTTP_403_FORBIDDEN)
