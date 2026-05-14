"""Signal receivers for optional NetBox branching integration."""

from __future__ import annotations

import logging
from typing import Any

from django.dispatch import receiver

logger = logging.getLogger(__name__)

try:
    from netbox_branching.signals import post_merge
    from netbox_branching.models import Branch
except ImportError:
    post_merge = None
    Branch = None
    logger.info("netbox_branching not available; post_merge receiver disabled.")


_VM_MODEL = "virtualmachine"


def _custom_field_enabled(obj: Any, field_name: str) -> bool:
    cf = getattr(obj, "custom_field_data", None) or {}
    if not isinstance(cf, dict):
        return False
    return cf.get(field_name) is True


def _virtualmachine_changediffs(branch: Any) -> Any:
    changediff_qs = getattr(branch, "changediff_set", None)
    if changediff_qs is None:
        return None
    return changediff_qs.filter(object_type__model=_VM_MODEL)


if post_merge is not None:

    @receiver(post_merge, sender=Branch)
    def handle_branch_merged(sender: Any, branch: Any, user: Any, **kwargs: Any) -> None:
        """Queue the dry-run Proxmox apply executor after eligible branch merges."""
        try:
            from netbox_proxbox.intent.apply_job import ProxmoxApplyJob  # noqa: PLC0415
            from netbox_proxbox.models.plugin_settings import (  # noqa: PLC0415
                ProxboxPluginSettings,
            )

            settings_obj = ProxboxPluginSettings.objects.first()
            if not (
                settings_obj
                and getattr(settings_obj, "netbox_to_proxmox_enabled", False)
            ):
                logger.debug("Intent post_merge ignored: master flag disabled.")
                return

            if not _custom_field_enabled(branch, "apply_to_proxmox"):
                logger.debug("Intent post_merge ignored: branch is not opted in.")
                return

            vm_diffs = _virtualmachine_changediffs(branch)
            if vm_diffs is None or not vm_diffs.exists():
                logger.info(
                    "Intent post_merge ignored for branch %s: no VM ChangeDiff rows.",
                    getattr(branch, "pk", None),
                )
                return

            job = ProxmoxApplyJob.enqueue(branch=branch, user=user)
            logger.info(
                "Queued ProxmoxApplyJob for branch %s as NetBox Job %s.",
                getattr(branch, "pk", None),
                getattr(job, "pk", None),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Failed to handle netbox_branching post_merge for branch %s: %s",
                getattr(branch, "pk", None),
                exc,
            )
            return
