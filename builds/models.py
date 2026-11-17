from django.contrib.auth.models import User
from django.db import models
from django.db.models import Q

from hardware.models import Component


class Build(models.Model):
    title = models.CharField(max_length=200, default='Draft Build')
    is_completed = models.BooleanField(default=False)
    is_compatible = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_public = models.BooleanField(default=False)
    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_power_watts = models.PositiveIntegerField(default=0)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='builds')

    class Meta:
        ordering = ('-created_at', '-id')
        constraints = [
            models.UniqueConstraint(
                fields=('user',),
                condition=Q(is_completed=False),
                name='unique_draft_build_per_user',
            ),
            models.CheckConstraint(
                condition=Q(is_completed=True) | Q(is_public=False),
                name='draft_build_cannot_be_public'
            )
        ]
        indexes = [
            models.Index(fields=('is_public', 'is_completed', '-created_at'))
        ]

    def __str__(self):
        status_label = 'Completed' if self.is_completed else 'Draft'
        return f'{self.title} ({self.user.username} - {status_label})'


class BuildItem(models.Model):
    build = models.ForeignKey(Build, on_delete=models.CASCADE, related_name='items')
    component = models.ForeignKey(Component, on_delete=models.CASCADE, related_name='build_items')
    quantity = models.PositiveIntegerField(default=1)
    price_at_moment = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ('id',)
        constraints = [
            models.UniqueConstraint(
                fields=('build', 'component'),
                name='unique_component_per_build',
            ),
        ]

    def __str__(self):
        return f'{self.quantity}x {self.component.name} (Build #{self.build_id})'