from django.db import models

class Manufacturer(models.Model):
    name = models.CharField(max_length=100, unique=True)
    country = models.CharField(max_length=100)
    founded_year = models.PositiveSmallIntegerField()
    description = models.TextField(blank=True)
    logo_url = models.URLField(blank=True)

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    max_per_build = models.PositiveIntegerField(default=1)
    is_periphery = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name


class Component(models.Model):
    name = models.CharField(max_length=150)
    sku = models.CharField(max_length=100, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    power_watts = models.PositiveIntegerField(default=0)
    popularity_score = models.PositiveIntegerField(default=0)
    description = models.TextField(blank=True)
    specifications = models.JSONField(default=dict, blank=True)
    image_url = models.URLField(blank=True)
    manufacturer = models.ForeignKey(
        Manufacturer,
        on_delete=models.CASCADE,
        related_name="components",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="components",
    )

    def __str__(self):
        return f"{self.name} ({self.sku})"