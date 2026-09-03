"""Best-effort writes to apply-managed ``ProxmoxVMIntent`` stamp fields."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def stamp_intent_state(vm, state: str, run_uuid: str | None = None) -> None:
    """Update an existing intent stamp without ever failing the apply job."""
    try:
        from netbox_proxbox.models import ProxmoxVMIntent

        defaults = {"intent_state": state}
        if run_uuid is not None:
            defaults["last_apply_run_id"] = run_uuid
        ProxmoxVMIntent.objects.filter(virtual_machine=vm).update(**defaults)
    except Exception:  # noqa: BLE001
        logger.exception(
            "Failed to stamp Proxbox intent state on VM %s.",
            getattr(vm, "pk", None),
        )


__all__ = ("stamp_intent_state",)
