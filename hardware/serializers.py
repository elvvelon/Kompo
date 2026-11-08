from datetime import date
from decimal import Decimal

from rest_framework import serializers
from .models import Component, Category, Manufacturer
from django.db import models
from typing import Type


def validate_str(
        model: Type[models.Model],
        serializer: serializers.ModelSerializer,
        field_name: str,
        value: str
) -> str:
    stripped = value.strip()
    model_name = model._meta.verbose_name.title()
    if not stripped:
        raise serializers.ValidationError(f"{model_name} {field_name} cannot be empty.")
    lookup = f"{field_name.lower()}__iexact"
    qs = model.objects.filter(**{lookup: stripped})
    if serializer.instance is not None:
        qs = qs.exclude(pk=serializer.instance.id)
    if qs.exists():
        raise serializers.ValidationError(f"{model_name} with {field_name} '{stripped}' already exists.")
    return stripped

# --- MANUFACTURER ---

class ManufacturerListSerializer(serializers.ModelSerializer):
    """
    List of all manufacturers
    """
    class Meta:
        model = Manufacturer
        fields = ("id", "name", "country", "founded_year", "logo_url")


class ManufacturerComponentNestedSerializer(serializers.ModelSerializer):
    """
    List of all components of specific manufacturer
    """
    category_name = serializers.CharField(source="category.name", read_only=True)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False)

    class Meta:
        model = Component
        fields = ("id", "name", "price", "category_name")


class ManufacturerDetailSerializer(serializers.ModelSerializer):
    """
    Full information about manufacturer
    """
    components = ManufacturerComponentNestedSerializer(many=True, read_only=True)

    class Meta:
        model = Manufacturer
        fields = ("id", "name", "country", "founded_year", "description", "logo_url", "components")

    def validate_name(self, name: str) -> str:
        return validate_str(Manufacturer, self, "name", name)

    def validate_founded_year(self, founded_year: int) -> int:
        current_year = date.today().year
        if not 1800 < founded_year <= current_year:
            raise serializers.ValidationError("Invalid founded year.")
        return founded_year

# --- CATEGORY ---

class CategoryListSerializer(serializers.ModelSerializer):
    """
    List of all categories
    """
    class Meta:
        model = Category
        fields = ("id", "name", "slug", "description", "max_per_build", "is_periphery")


class CategoryComponentNestedSerializer(serializers.ModelSerializer):
    """
    List of all components of specific category
    """
    manufacturer_name = serializers.CharField(source="manufacturer.name", read_only=True)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False)

    class Meta:
        model = Component
        fields = ("id", "name", "price", "manufacturer_name")


class CategoryDetailSerializer(serializers.ModelSerializer):
    """
    Full information about category
    """
    components = CategoryComponentNestedSerializer(many=True, read_only=True)

    class Meta:
        model = Category
        fields = ("id", "name", "slug", "description", "max_per_build", "is_periphery", "components")

    def validate_name(self, name: str) -> str:
        return validate_str(Category, self, "name", name)

    def validate_max_per_build(self, value: int) -> int:
        if not 0 < value < 32:
            raise serializers.ValidationError("Invalid value for max per build.")
        return value


# --- COMPONENTS ---

# Helping Serializers
class ComponentManufacturerSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Manufacturer
        fields = ("id", "name")

class ComponentCategorySummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name", "max_per_build")


class ComponentListSerializer(serializers.ModelSerializer):
    """
    List of all components
    """
    price = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False)
    manufacturer = ComponentManufacturerSummarySerializer(read_only=True)
    category = ComponentCategorySummarySerializer(read_only=True)

    class Meta:
        model = Component
        fields = (
            "id",
            "name",
            "sku",
            "price",
            "power_watts",
            "popularity_score",
            "description",
            "specifications",
            "image_url",
            "manufacturer",
            "category"
        )


class ComponentDetailSerializer(serializers.ModelSerializer):
    """
    Full information about component
    """
    price = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False)
    manufacturer = ComponentManufacturerSummarySerializer(read_only=True)
    category = ComponentCategorySummarySerializer(read_only=True)
    manufacturer_id = serializers.PrimaryKeyRelatedField(
        queryset=Manufacturer.objects.all(),
        source="manufacturer",
        write_only=True,
        error_messages={
            "required": "Manufacturer ID is required.",
            "does_not_exist": "Manufacturer with ID {pk_value} not found.",
            "invalid": "Manufacturer with ID {pk_value} not found."
        }
    )
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        source="category",
        write_only=True,
        error_messages={
            "required": "Category ID is required.",
            "does_not_exist": "Category with ID {pk_value} not found.",
            "invalid": "Category with ID {pk_value} not found."
        }
    )

    class Meta:
        model = Component
        fields = (
            "id",
            "name",
            "sku",
            "price",
            "power_watts",
            "popularity_score",
            "description",
            "specifications",
            "image_url",
            "manufacturer",
            "category",
            "manufacturer_id",
            "category_id"
        )

    def validate_sku(self, value: str) -> str:
        return validate_str(Component, self, "SKU", value)

    def validate_price(self, price: Decimal) -> Decimal:
        if price < 0:
            raise serializers.ValidationError("Price must be greater than zero.")
        return price

    def validate_power_watts(self, value: float) -> float:
        if not 0 < value < 3000:
            raise serializers.ValidationError("power_watts must be between 0 and 3000.")
        return value

    def validate_popularity_score(self, value: int) -> int:
        if not 0 <= value <= 5:
            raise serializers.ValidationError("popularity_score must be between 0 and 5.")
        return value

    def validate_specs(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("specifications must be a JSON object.")
        return value