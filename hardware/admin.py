from django.contrib import admin
from hardware.models import Manufacturer, Category, Component


@admin.register(Manufacturer)
class ManufacturerAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "country", "founded_year")
    search_fields = ("name", "country")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "slug", "max_per_build", "is_periphery")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "slug")


@admin.register(Component)
class ComponentAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "sku", "price", "power_watts", "popularity_score", "manufacturer", "category")
    list_filter = ("category", "manufacturer")
    search_fields = ("name", "sku")
