"""Store netbox-rpc systemctl service monitoring results for Proxmox endpoints."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel


SERVICE_COLLECTION_TRIGGER_SCHEDULED = "scheduled"
SERVICE_COLLECTION_TRIGGER_ON_DEMAND = "on_demand"
SERVICE_COLLECTION_TRIGGER_CHOICES = (
    (SERVICE_COLLECTION_TRIGGER_SCHEDULED, _("Scheduled")),
    (SERVICE_COLLECTION_TRIGGER_ON_DEMAND, _("On demand")),
)

SERVICE_COLLECTION_STATUS_PENDING = "pending"
SERVICE_COLLECTION_STATUS_SUCCEEDED = "succeeded"
SERVICE_COLLECTION_STATUS_FAILED = "failed"
SERVICE_COLLECTION_STATUS_CHOICES = (
    (SERVICE_COLLECTION_STATUS_PENDING, _("Pending")),
    (SERVICE_COLLECTION_STATUS_SUCCEEDED, _("Succeeded")),
    (SERVICE_COLLECTION_STATUS_FAILED, _("Failed")),
)


class ProxmoxServiceCollection(NetBoxModel):
    """One queued or completed systemctl service collection for an endpoint."""

    endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.CASCADE,
        related_name="service_collections",
        verbose_name=_("Proxmox endpoint"),
    )
    collected_at = models.DateTimeField(
        default=timezone.now,
        verbose_name=_("Collected at"),
    )
    reachable = models.BooleanField(
        default=False,
        verbose_name=_("Reachable"),
    )
    trigger = models.CharField(
        max_length=16,
        choices=SERVICE_COLLECTION_TRIGGER_CHOICES,
        default=SERVICE_COLLECTION_TRIGGER_SCHEDULED,
        verbose_name=_("Trigger"),
    )
    duration_ms = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Duration (ms)"),
    )
    error_message = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Error message"),
    )
    rpc_execution_id = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name=_("RPC execution ID"),
    )
    status = models.CharField(
        max_length=16,
        choices=SERVICE_COLLECTION_STATUS_CHOICES,
        default=SERVICE_COLLECTION_STATUS_PENDING,
        db_index=True,
        verbose_name=_("Status"),
    )

    class Meta:
        verbose_name = _("Proxmox service collection")
        verbose_name_plural = _("Proxmox service collections")
        ordering = ("-collected_at", "-pk")

    def __str__(self) -> str:
        return f"{self.endpoint} service collection {self.pk}"

    def get_absolute_url(self) -> str:
        """Return the endpoint Services tab where this collection is surfaced."""
        return reverse(
            "plugins:netbox_proxbox:proxmoxendpoint_services",
            args=[self.endpoint_id],
        )


class ProxmoxServiceSample(NetBoxModel):
    """Raw service row from a completed collection."""

    collection = models.ForeignKey(
        to="netbox_proxbox.ProxmoxServiceCollection",
        on_delete=models.CASCADE,
        related_name="samples",
        verbose_name=_("Service collection"),
    )
    unit = models.CharField(max_length=255, db_index=True, verbose_name=_("Unit"))
    service_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("Systemd ID"),
    )
    load_state = models.CharField(max_length=64, blank=True, default="")
    active_state = models.CharField(max_length=64, blank=True, default="")
    sub_state = models.CharField(max_length=64, blank=True, default="")
    result = models.CharField(max_length=64, blank=True, default="")
    main_pid = models.PositiveIntegerField(null=True, blank=True)
    exec_main_code = models.IntegerField(null=True, blank=True)
    exec_main_status = models.IntegerField(null=True, blank=True)
    n_restarts = models.PositiveIntegerField(null=True, blank=True)
    active_enter_timestamp = models.CharField(max_length=128, blank=True, default="")
    unit_file_state = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        verbose_name = _("Proxmox service sample")
        verbose_name_plural = _("Proxmox service samples")
        ordering = ("collection", "unit")
        unique_together = (("collection", "unit"),)

    def __str__(self) -> str:
        return f"{self.collection.endpoint} {self.unit}"

    def get_absolute_url(self) -> str:
        """Return the endpoint Services tab where this sample is surfaced."""
        return reverse(
            "plugins:netbox_proxbox:proxmoxendpoint_services",
            args=[self.collection.endpoint_id],
        )


class ProxmoxServiceStatus(NetBoxModel):
    """Latest projected state for one service unit on one endpoint."""

    endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.CASCADE,
        related_name="service_statuses",
        verbose_name=_("Proxmox endpoint"),
    )
    unit = models.CharField(max_length=255, db_index=True, verbose_name=_("Unit"))
    service_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("Systemd ID"),
    )
    load_state = models.CharField(max_length=64, blank=True, default="")
    active_state = models.CharField(max_length=64, blank=True, default="")
    sub_state = models.CharField(max_length=64, blank=True, default="")
    result = models.CharField(max_length=64, blank=True, default="")
    main_pid = models.PositiveIntegerField(null=True, blank=True)
    exec_main_code = models.IntegerField(null=True, blank=True)
    exec_main_status = models.IntegerField(null=True, blank=True)
    n_restarts = models.PositiveIntegerField(null=True, blank=True)
    active_enter_timestamp = models.CharField(max_length=128, blank=True, default="")
    unit_file_state = models.CharField(max_length=64, blank=True, default="")
    last_seen_at = models.DateTimeField(verbose_name=_("Last seen at"))
    is_healthy = models.BooleanField(default=False, verbose_name=_("Healthy"))
    expected_active = models.BooleanField(
        default=True,
        verbose_name=_("Expected active"),
    )

    class Meta:
        verbose_name = _("Proxmox service status")
        verbose_name_plural = _("Proxmox service statuses")
        ordering = ("endpoint", "unit")
        unique_together = (("endpoint", "unit"),)

    def __str__(self) -> str:
        return f"{self.endpoint} {self.unit}"

    def get_absolute_url(self) -> str:
        """Return the endpoint Services tab where this status is surfaced."""
        return reverse(
            "plugins:netbox_proxbox:proxmoxendpoint_services",
            args=[self.endpoint_id],
        )
