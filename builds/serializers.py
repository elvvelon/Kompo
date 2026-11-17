from django.contrib.auth.models import User
from rest_framework import serializers

from hardware.models import Component
from .models import Build, BuildItem
from .services import calculate_recommended_psu_watts, evaluate_build_compatibility


class BuildAuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username')


class BuildComponentNestedSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        coerce_to_string=False,
        read_only=True,
    )

    class Meta:
        model = Component
        fields = (
            'id',
            'name',
            'category_name',
            'price',
            'power_watts',
        )


class BuildItemSerializer(serializers.ModelSerializer):
    item_id = serializers.IntegerField(source='id', read_only=True)
    price_at_moment = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        coerce_to_string=False,
        read_only=True,
    )
    component = BuildComponentNestedSerializer(read_only=True)

    class Meta:
        model = BuildItem
        fields = (
            'item_id',
            'quantity',
            'price_at_moment',
            'component',
        )


class BuildSerializer(serializers.ModelSerializer):
    user = BuildAuthorSerializer(read_only=True)
    total_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        coerce_to_string=False,
        read_only=True,
    )
    recommended_psu_watts = serializers.SerializerMethodField()
    compatibility_issues = serializers.SerializerMethodField()
    items = BuildItemSerializer(many=True, read_only=True)

    class Meta:
        model = Build
        fields = (
            'id',
            'title',
            'user',
            'is_completed',
            'is_compatible',
            'is_public',
            'compatibility_issues',
            'total_price',
            'total_power_watts',
            'recommended_psu_watts',
            'created_at',
            'updated_at',
            'items',
        )

    def get_recommended_psu_watts(self, obj: Build) -> int:
        return calculate_recommended_psu_watts(obj.total_power_watts)

    def get_compatibility_issues(self, obj: Build) -> list[str]:
        cached_issues = self.context.get('compatibility_issues')
        if cached_issues is not None and self.instance is obj:
            return cached_issues
        items = list(
            obj.items.select_related('component__category', 'component__manufacturer').all()
        )
        return evaluate_build_compatibility(items, obj.total_power_watts)


class BuildItemCreateSerializer(serializers.Serializer):
    component_id = serializers.PrimaryKeyRelatedField(
        queryset=Component.objects.select_related('category', 'manufacturer').all(),
        source='component',
        error_messages={
            'required': 'Component ID is required.',
            'does_not_exist': 'Component with ID {pk_value} not found.',
            'incorrect_type': 'Component ID must be a valid integer.',
        },
    )
    quantity = serializers.IntegerField(
        min_value=1,
        default=1,
        error_messages={
            'min_value': 'Quantity must be at least 1.',
            'invalid': 'Quantity must be a valid integer.',
        },
    )


class BuildItemUpdateSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(
        min_value=1,
        required=True,
        error_messages={
            'required': 'Quantity is required.',
            'min_value': 'Quantity must be at least 1.',
            'invalid': 'Quantity must be a valid integer.',
        },
    )


class BuildCheckoutSerializer(serializers.Serializer):
    title = serializers.CharField(
        max_length=200,
        required=False,
        allow_blank=False,
    )
    is_public = serializers.BooleanField(required=False, default=False)

    def validate_title(self, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise serializers.ValidationError('Build title cannot be empty.')
        return stripped


class BuildUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(
        max_length=200,
        required=False,
        allow_blank=False,
    )
    is_public = serializers.BooleanField(required=False)

    def validate_title(self, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise serializers.ValidationError('Build title cannot be empty.')
        return stripped