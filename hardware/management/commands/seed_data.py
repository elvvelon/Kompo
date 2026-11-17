from decimal import Decimal
from django.core.management.base import BaseCommand
from hardware.models import Category, Component, Manufacturer


class Command(BaseCommand):
    help = "Seed the database with initial manufacturers, categories, and PC components."

    def handle(self, *args, **options):
        manufacturers_data = [
            {
                "name": "AMD",
                "country": "USA",
                "founded_year": 1969,
                "description": "Semiconductor company developing processors and graphics technologies.",
                "logo_url": "https://upload.wikimedia.org/wikipedia/commons/7/7c/AMD_Logo.svg",
            },
            {
                "name": "NVIDIA",
                "country": "USA",
                "founded_year": 1993,
                "description": "Leader in GPU computing, gaming graphics cards, and AI hardware.",
                "logo_url": "https://upload.wikimedia.org/wikipedia/commons/2/21/Nvidia_logo.svg",
            },
            {
                "name": "ASUS",
                "country": "Taiwan",
                "founded_year": 1989,
                "description": "Multinational computer and phone hardware and electronics company.",
                "logo_url": "https://upload.wikimedia.org/wikipedia/commons/2/2e/ASUS_Logo.svg",
            },
            {
                "name": "Kingston",
                "country": "USA",
                "founded_year": 1987,
                "description": "World leader in memory products and solid-state storage solutions.",
                "logo_url": "https://example.com/logos/kingston.png",
            },
            {
                "name": "Be Quiet!",
                "country": "Germany",
                "founded_year": 2001,
                "description": "Manufacturer of quiet power supplies, cases, and cooling solutions.",
                "logo_url": "https://example.com/logos/bequiet.png",
            },
        ]

        manufacturers = {}
        for m_data in manufacturers_data:
            obj, _ = Manufacturer.objects.update_or_create(
                name=m_data["name"],
                defaults=m_data,
            )
            manufacturers[obj.name] = obj

        categories_data = [
            {
                "name": "Processors",
                "slug": "cpus",
                "description": "Central processing units.",
                "max_per_build": 1,
                "is_periphery": False,
            },
            {
                "name": "Motherboards",
                "slug": "motherboards",
                "description": "Main printed circuit boards connecting all PC components.",
                "max_per_build": 1,
                "is_periphery": False,
            },
            {
                "name": "Memory (RAM)",
                "slug": "ram",
                "description": "System volatile memory modules.",
                "max_per_build": 4,
                "is_periphery": False,
            },
            {
                "name": "Graphics Cards",
                "slug": "gpus",
                "description": "Dedicated graphics processing units for gaming and ML workloads.",
                "max_per_build": 2,
                "is_periphery": False,
            },
            {
                "name": "Power Supplies",
                "slug": "power-supplies",
                "description": "Power supply units for internal components.",
                "max_per_build": 1,
                "is_periphery": False,
            },
            {
                "name": "Monitors",
                "slug": "monitors",
                "description": "External displays for gaming and professional productivity.",
                "max_per_build": 3,
                "is_periphery": True,
            },
        ]

        categories = {}
        for c_data in categories_data:
            obj, _ = Category.objects.update_or_create(
                slug=c_data["slug"],
                defaults=c_data,
            )
            categories[obj.slug] = obj

        components_data = [
            {
                "name": "AMD Ryzen 7 7800X3D",
                "sku": "100-100000910WOF",
                "price": Decimal("420.00"),
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
                "manufacturer": manufacturers["AMD"],
                "category": categories["cpus"],
            },
            {
                "name": "AMD Ryzen 5 7600X",
                "sku": "100-100000593WOF",
                "price": Decimal("229.00"),
                "power_watts": 105,
                "popularity_score": 5,
                "description": "6-core, 12-thread AM5 processor for mainstream gaming builds.",
                "specifications": {
                    "socket": "AM5",
                    "cores": 6,
                    "threads": 12,
                    "base_clock_ghz": 4.7,
                },
                "image_url": "https://example.com/images/r5-7600x.jpg",
                "manufacturer": manufacturers["AMD"],
                "category": categories["cpus"],
            },
            {
                "name": "ASUS TUF GAMING B650-PLUS",
                "sku": "90MB1BZ0-M0EAY0",
                "price": Decimal("210.00"),
                "power_watts": 45,
                "popularity_score": 4,
                "description": "AMD B650 ATX motherboard with DDR5 support and PCIe 5.0 M.2.",
                "specifications": {
                    "socket": "AM5",
                    "memory_type": "DDR5",
                    "form_factor": "ATX",
                    "memory_slots": 4,
                },
                "image_url": "https://example.com/images/b650-plus.jpg",
                "manufacturer": manufacturers["ASUS"],
                "category": categories["motherboards"],
            },
            {
                "name": "NVIDIA GeForce RTX 4070 Ti Super",
                "sku": "NV-RTX4070TIS-16G",
                "price": Decimal("840.00"),
                "power_watts": 285,
                "popularity_score": 5,
                "description": "16GB GDDR6X graphics card ideal for 1440p/4K gaming and PyTorch AI workloads.",
                "specifications": {
                    "vram_gb": 16,
                    "memory_type": "GDDR6X",
                    "boost_clock_mhz": 2610,
                },
                "image_url": "https://example.com/images/rtx-4070-ti-super.jpg",
                "manufacturer": manufacturers["NVIDIA"],
                "category": categories["gpus"],
            },
            {
                "name": "Kingston FURY Beast 32GB (2x16GB) DDR5-6000",
                "sku": "KF560C36BBEK2-32",
                "price": Decimal("115.00"),
                "power_watts": 10,
                "popularity_score": 5,
                "description": "High-performance DDR5 memory kit with AMD EXPO support.",
                "specifications": {
                    "memory_type": "DDR5",
                    "capacity_gb": 32,
                    "speed_mhz": 6000,
                    "modules": 2,
                },
                "image_url": "https://example.com/images/fury-beast-ddr5.jpg",
                "manufacturer": manufacturers["Kingston"],
                "category": categories["ram"],
            },
            {
                "name": "Be Quiet! Pure Power 12 M 850W",
                "sku": "BN344",
                "price": Decimal("135.00"),
                "power_watts": 0,
                "popularity_score": 3,
                "description": "ATX 3.0 80 Plus Gold modular power supply with whisper-quiet 120mm fan.",
                "specifications": {
                    "wattage": 850,
                    "efficiency_rating": "80 Plus Gold",
                    "modular": True,
                },
                "image_url": "https://example.com/images/pure-power-12m-850w.jpg",
                "manufacturer": manufacturers["Be Quiet!"],
                "category": categories["power-supplies"],
            },
        ]

        for comp_data in components_data:
            Component.objects.update_or_create(
                sku=comp_data["sku"],
                defaults=comp_data,
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {Manufacturer.objects.count()} manufacturers, "
                f"{Category.objects.count()} categories, and "
                f"{Component.objects.count()} components."
            )
        )
