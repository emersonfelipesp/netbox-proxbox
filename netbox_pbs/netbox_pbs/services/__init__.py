"""Service layer for netbox-pbs.

Contains backend HTTP transport (``http_client``) and netbox-branching
lifecycle helpers (``branch_lifecycle``). Both modules are designed so the
plugin can boot even when the optional ``netbox-branching`` and
``netbox-proxbox`` plugins are absent: every cross-plugin import is
guarded.
"""

from netbox_pbs.services.branch_lifecycle import (
    branch_has_conflicts,
    branching_enabled_settings,
    create_and_provision_branch,
    get_active_branch_schema_id,
    is_branching_available,
    merge_branch,
)
from netbox_pbs.services.http_client import (
    PBS_STAGES_FULL,
    PBSStageResult,
    run_pbs_sync_stage,
)

__all__ = (
    "PBS_STAGES_FULL",
    "PBSStageResult",
    "branch_has_conflicts",
    "branching_enabled_settings",
    "create_and_provision_branch",
    "get_active_branch_schema_id",
    "is_branching_available",
    "merge_branch",
    "run_pbs_sync_stage",
)
