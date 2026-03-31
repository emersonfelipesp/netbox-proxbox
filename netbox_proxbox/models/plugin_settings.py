"""Persistent plugin-level settings for ProxBox behavior toggles."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox.models import NetBoxModel


class ProxboxPluginSettings(NetBoxModel):
    """Singleton-style settings row used by plugin UI and sync jobs."""

    singleton_key = models.CharField(
        max_length=32,
        unique=True,
        default="default",
        editable=False,
    )
    use_guest_agent_interface_name = models.BooleanField(
        default=True,
        verbose_name=_("Use guest agent interface name"),
        help_text=_(
            "When enabled, VM interface names use QEMU guest-agent names when available "
            "(for example ens18) instead of generic Proxmox labels (for example net0/nic0)."
        ),
    )

    class Meta:
        verbose_name = _("Proxbox plugin settings")
        verbose_name_plural = _("Proxbox plugin settings")

    def __str__(self) -> str:
        return "Proxbox plugin settings"

    def save(self, *args, **kwargs):
        self.singleton_key = "default"
        return super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_proxbox:settings")

    @classmethod
    def get_solo(cls) -> "ProxboxPluginSettings":
        obj, _ = cls.objects.get_or_create(singleton_key="default")
        return obj
