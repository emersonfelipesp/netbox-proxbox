"""TTL cleanup for pending DeletionRequest records."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

from netbox_proxbox.intent.proxmox_tags import untag_pending_deletion
from netbox_proxbox.models import DeletionRequest, ProxboxPluginSettings
from netbox_proxbox.services.backend_context import get_fastapi_request_context

__all__ = ("auto_reject_expired_deletion_requests",)

logger = logging.getLogger(__name__)


def _ttl_days() -> int:
    settings_obj = ProxboxPluginSettings.get_solo()
    return int(getattr(settings_obj, "intent_deletion_request_ttl_days", 7) or 7)


def auto_reject_expired_deletion_requests() -> int:
    """Reject expired pending DeletionRequests and untag Proxmox best-effort."""
    ttl_days = _ttl_days()
    cutoff = timezone.now() - timedelta(days=ttl_days)
    queryset = DeletionRequest.objects.filter(
        state="pending",
        requested_at__lt=cutoff,
    )
    endpoint = get_fastapi_request_context()
    rejected = 0

    for deletion_request in queryset:
        deletion_request.state = DeletionRequest.State.REJECTED
        deletion_request.reject_reason = "TTL"
        deletion_request.save(update_fields=["state", "reject_reason"])
        rejected += 1

        if endpoint is None:
            continue
        try:
            untag_pending_deletion(
                endpoint,
                vmid=deletion_request.vmid,
                node=deletion_request.node,
                kind=deletion_request.kind,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to remove pending-deletion tag for DeletionRequest %s: %s",
                deletion_request.pk,
                exc,
            )

    return rejected
