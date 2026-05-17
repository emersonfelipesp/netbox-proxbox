"""Singleton settings model for the netbox-packer plugin."""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel


class PackerPluginSettings(NetBoxModel):
    """Singleton-style settings row for image factory feature gates."""

    singleton_key = models.CharField(
        max_length=32,
        primary_key=True,
        default="default",
        editable=False,
    )
    image_factory_enabled = models.BooleanField(
        default=False,
        verbose_name=_("Image factory enabled"),
    )
    image_factory_max_concurrent_builds = models.PositiveIntegerField(
        default=1,
        verbose_name=_("Maximum concurrent image builds"),
    )
    image_factory_default_job_timeout = models.PositiveIntegerField(
        default=14400,
        verbose_name=_("Default image build job timeout"),
        help_text=_("Default Packer image build timeout in seconds."),
    )
    image_factory_allow_iso_builds = models.BooleanField(
        default=False,
        verbose_name=_("Allow ISO image builds"),
    )
    image_factory_allow_custom_variables = models.BooleanField(
        default=False,
        verbose_name=_("Allow custom Packer variables"),
    )

    class Meta:
        verbose_name = _("Packer plugin settings")
        verbose_name_plural = _("Packer plugin settings")

    def __str__(self) -> str:
        return "Packer plugin settings"

    def save(self, *args: object, **kwargs: object) -> None:
        self.singleton_key = "default"
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls) -> "PackerPluginSettings":
        obj, _created = cls.objects.get_or_create(singleton_key="default")
        return obj
