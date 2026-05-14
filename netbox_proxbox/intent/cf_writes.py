"""Best-effort custom-field writes for intent apply state."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def stamp_intent_state(vm, state: str, run_uuid: str | None = None) -> None:
    """Stamp a VM with its latest intent apply state without failing the job."""
    try:
        cf = getattr(vm, "custom_field_data", None)
        if not isinstance(cf, dict):
            cf = {}
            vm.custom_field_data = cf

        cf["proxbox_intent_state"] = state
        if run_uuid is not None:
            cf["proxbox_last_apply_run_id"] = run_uuid
        vm.save()
    except Exception:  # noqa: BLE001
        logger.exception(
            "Failed to stamp Proxbox intent state on VM %s.",
            getattr(vm, "pk", None),
        )
