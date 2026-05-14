"""``DeletionRequest`` model for the NetBox→Proxmox safe-delete flow."""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from extras.managers import NetBoxTaggableManager
from taggit.managers import TaggableManager

from netbox.models import NetBoxModel


class DeletionRequest(NetBoxModel):
    """Represents a pending Proxmox DELETE awaiting four-eyes authorization.

    The ``authorize_deletion_request`` permission stays distinct from the
    ``intent_delete_*`` permissions on ``ProxmoxApplyJob``. The two permissions
    stay independent by design — four-eyes requires that the user who
    *requests* a delete cannot be the user who *approves* it.
    """

    class State(models.TextChoices):
        PENDING = "pending", _("Pending")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")
        EXECUTING = "executing", _("Executing")
        SUCCEEDED = "succeeded", _("Succeeded")
        FAILED = "failed", _("Failed")

    # Override inherited ``tags`` to avoid a ``Tag.deletionrequest_set`` reverse
    # accessor clash with ``netbox_nms.DeletionRequest`` (Django fields.E304).
    tags = TaggableManager(
        through="extras.TaggedItem",
        ordering=("weight", "name"),
        manager=NetBoxTaggableManager,
        related_name="netbox_proxbox_deletionrequest_set",
    )

    branch = models.ForeignKey(
        "netbox_branching.Branch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="proxbox_deletion_requests_requested",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    authorizer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="proxbox_deletion_requests_authorized",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    state = models.CharField(
        max_length=16,
        choices=State.choices,
        default=State.PENDING,
    )
    vmid = models.IntegerField(null=True, blank=True)
    node = models.CharField(max_length=64, blank=True, default="")
    kind = models.CharField(
        max_length=8,
        choices=(("qemu", "qemu"), ("lxc", "lxc")),
        default="qemu",
    )
    metadata_snapshot = models.JSONField(default=dict, blank=True)
    reject_reason = models.CharField(max_length=255, blank=True, default="")
    executor_run_uuid = models.UUIDField(null=True, blank=True)
    requested_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)

    name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Name"),
        help_text=_("Optional human-readable label for the deletion request."),
    )

    class Meta:
        ordering = ("-pk",)
        verbose_name = _("Deletion Request")
        verbose_name_plural = _("Deletion Requests")
        permissions = (
            (
                "authorize_deletion_request",
                "Can authorize (approve/reject) a Proxmox DeletionRequest",
            ),
        )

    def __str__(self) -> str:
        return self.name or f"DeletionRequest #{self.pk}"

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_proxbox:deletionrequest", args=[self.pk])

    def clean(self) -> None:
        super().clean()
        if self.authorizer_id is None or self.authorizer_id != self.requested_by_id:
            return

        from netbox_proxbox.models.plugin_settings import (  # noqa: PLC0415
            ProxboxPluginSettings,
        )

        settings_obj = ProxboxPluginSettings.get_solo()
        if not settings_obj.intent_apply_authorization_self_approve_allowed:
            raise ValidationError(
                "Self-approval blocked: a different authorized user must approve this request."
            )
