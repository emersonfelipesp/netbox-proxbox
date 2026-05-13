"""Branch-lifecycle shim that delegates to ``netbox_proxbox``.

netbox-pbs hard-depends on netbox-proxbox (declared in ``PBSConfig.required_plugins``),
so the branching primitives — ``is_branching_available``, ``get_active_branch_schema_id``,
``create_and_provision_branch``, ``branch_has_conflicts``, ``merge_branch`` — are
re-exported directly from ``netbox_proxbox.services.branch_lifecycle``. The only
PBS-specific function is ``branching_enabled_settings()``, which reads from
``PBSPluginSettings.get_solo()`` (the PBS plugin owns its own settings row) so
PBS sync can be branched independently of Proxmox sync.
"""

from __future__ import annotations

import logging

from netbox_proxbox.services.branch_lifecycle import (
    branch_has_conflicts,
    create_and_provision_branch,
    get_active_branch_schema_id,
    is_branching_available,
    merge_branch,
)

from netbox_pbs.models import PBSPluginSettings

__all__ = (
    "branch_has_conflicts",
    "branching_enabled_settings",
    "create_and_provision_branch",
    "get_active_branch_schema_id",
    "is_branching_available",
    "merge_branch",
)

logger = logging.getLogger("netbox_pbs.branch_lifecycle")


def branching_enabled_settings() -> dict[str, str] | None:
    """Return branching config from PBSPluginSettings, or None when disabled."""
    if not is_branching_available():
        return None
    try:
        settings_obj = PBSPluginSettings.get_solo()
    except Exception:
        logger.exception("Could not load PBSPluginSettings")
        return None
    if not getattr(settings_obj, "branching_enabled", False):
        return None
    return {
        "prefix": getattr(settings_obj, "branch_name_prefix", "") or "pbs-sync",
        "on_conflict": getattr(settings_obj, "branch_on_conflict", "") or "fail",
    }
