"""netbox-branching lifecycle helpers for netbox-ceph sync jobs.

These thin wrappers delegate the Branch provision/merge mechanics to
``netbox_proxbox.services.branch_lifecycle`` so the two plugins share one
implementation of the in-process branching contract. Only the policy
toggle (branching_enabled / prefix / on_conflict) is sourced locally from
``CephPluginSettings`` instead of ``ProxboxPluginSettings``.

Branching is optional. When the netbox-branching plugin is not installed
or branching is disabled in plugin settings, ``branching_enabled_settings``
returns ``None`` and the caller stays on ``main``.
"""

from __future__ import annotations

import logging

# Reuse the mechanics from netbox_proxbox so there is one implementation
# of branch provisioning, conflict detection, and merge behavior.
from netbox_proxbox.services.branch_lifecycle import (
    branch_has_conflicts,
    create_and_provision_branch,
    get_active_branch_schema_id,
    is_branching_available,
    merge_branch,
)

from netbox_ceph.models import CephPluginSettings

logger = logging.getLogger("netbox_ceph.branch_lifecycle")

__all__ = (
    "branch_has_conflicts",
    "branching_enabled_settings",
    "create_and_provision_branch",
    "get_active_branch_schema_id",
    "is_branching_available",
    "merge_branch",
)


def branching_enabled_settings() -> dict[str, str] | None:
    """Return Ceph branching config, or ``None`` when disabled/unavailable."""
    if not is_branching_available():
        return None
    try:
        settings_obj = CephPluginSettings.get_solo()
    except Exception:
        logger.exception("Could not load CephPluginSettings")
        return None
    if not getattr(settings_obj, "branching_enabled", False):
        return None
    return {
        "prefix": getattr(settings_obj, "branch_name_prefix", "") or "ceph-sync",
        "on_conflict": getattr(settings_obj, "branch_on_conflict", "") or "fail",
    }
