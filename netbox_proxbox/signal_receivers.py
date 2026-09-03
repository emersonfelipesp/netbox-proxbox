"""Signal receivers for optional NetBox branching integration."""

from __future__ import annotations

import logging
from typing import Any

from django.apps import apps
from django.dispatch import receiver

logger = logging.getLogger(__name__)

if apps.is_installed("netbox_branching"):
    # An explicitly enabled companion is part of the configured application.
    # Let import failures abort startup instead of silently disabling the merge
    # receiver and creating a partially configured write path.
    from netbox_branching.models import Branch
    from netbox_branching.signals import post_merge
else:
    post_merge = None
    Branch = None
    logger.info("netbox_branching is not enabled; post_merge receiver disabled.")


def _branch_opted_in(branch: Any) -> bool:
    """Read the branch opt-in through the shared fail-closed resolver."""
    from netbox_proxbox.services.branch_intent import resolve_branch_intent_flags

    return resolve_branch_intent_flags(branch).apply_to_proxmox


def _mergeable_virtual_machines(branch: Any) -> list:
    """VM operations this branch changes, through either diff stream.

    This must use the same union the validator and the apply job use. Gating on
    the core virtual-machine stream alone makes an intent-only branch a silent
    no-op: it has no virtualmachine ChangeDiff, so the job is never queued, the
    merge still reports success, and Proxmox is never touched.

    A deleted core VM remains mergeable with a ``None`` object because its
    originating ChangeDiff carries the deletion identity for the apply job.
    """
    if getattr(branch, "changediff_set", None) is None:
        return []
    from netbox_proxbox.intent.diff_union import (  # noqa: PLC0415
        virtual_machine_diff_union,
    )

    return virtual_machine_diff_union(branch)


if post_merge is not None:

    @receiver(post_merge, sender=Branch)
    def handle_branch_merged(
        sender: Any, branch: Any, user: Any, **kwargs: Any
    ) -> None:
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

            if not _branch_opted_in(branch):
                logger.debug("Intent post_merge ignored: branch is not opted in.")
                return

            if not _mergeable_virtual_machines(branch):
                logger.info(
                    "Intent post_merge ignored for branch %s: no virtual-machine "
                    "or intent ChangeDiff rows.",
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
