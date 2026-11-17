from django.contrib import admin

from .models import Build, BuildItem


class BuildItemInline(admin.TabularInline):
    model = BuildItem
    extra = 0
    readonly_fields = ('price_at_moment',)


@admin.register(Build)
class BuildAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'title',
        'user',
        'is_completed',
        'is_compatible',
        'is_public',
        'total_price',
        'total_power_watts',
        'created_at',
    )
    list_filter = ('is_completed', 'is_compatible', 'is_public')
    search_fields = ('title', 'user__username', 'user__email')
    inlines = (BuildItemInline,)


@admin.register(BuildItem)
class BuildItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'build', 'component', 'quantity', 'price_at_moment')
    list_filter = ('component__category',)
    search_fields = ('build__title', 'component__name', 'component__sku')
