"""Explicit per-user authorization for protected credential disclosure."""

from django.conf import settings
from django.db import models
from django.urls import reverse
from netbox.models import NetBoxModel


class ProxboxSensitiveDataAccess(NetBoxModel):
    """Default-off grant, managed exclusively through superuser-only surfaces."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="proxbox_sensitive_data_access",
    )
    can_access_sensitive_data = models.BooleanField(
        default=False,
        help_text=(
            "Allow sensitive credential disclosure within existing object and provider "
            "permissions. Only an active superuser may change this grant."
        ),
    )

    class Meta:
        ordering = ("user_id",)
        verbose_name = "Proxbox sensitive data access"
        verbose_name_plural = "Proxbox sensitive data access grants"

    def __str__(self) -> str:
        """Identify the grant without resolving or disclosing credentials."""
        return f"Sensitive data access for user {self.user_id}"

    def get_absolute_url(self) -> str:
        """Return the protected grant administration API detail URL."""
        return reverse(
            "plugins-api:netbox_proxbox-api:proxboxsensitivedataaccess-detail",
            args=[self.pk],
        )
