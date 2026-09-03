"""Fail-closed resolution of plugin-owned per-branch intent gates."""

from __future__ import annotations

from typing import Any, NamedTuple


class BranchIntentFlags(NamedTuple):
    """Effective safety-gate values for one branch."""

    apply_to_proxmox: bool
    apply_destroy_confirmed: bool


FALSE_BRANCH_INTENT = BranchIntentFlags(
    apply_to_proxmox=False,
    apply_destroy_confirmed=False,
)


def resolve_branch_reference(branch_id: Any, branch_schema_id: Any) -> Any | None:
    """Resolve an exact soft branch reference without ever raising."""
    try:
        from netbox_proxbox.services.branch_lifecycle import is_branching_available

        if not is_branching_available():
            return None
        if branch_id is None or not branch_schema_id:
            return None

        from netbox_branching.models import Branch

        return Branch.objects.filter(
            pk=branch_id,
            schema_id=str(branch_schema_id),
        ).first()
    except Exception:
        return None


def resolve_branch_intent_flags(branch: Any) -> BranchIntentFlags:
    """Return both effective branch gates, defaulting both to false on failure."""
    try:
        branch_id = getattr(branch, "pk", None)
        branch_schema_id = getattr(branch, "schema_id", None)
        if resolve_branch_reference(branch_id, branch_schema_id) is None:
            return FALSE_BRANCH_INTENT

        from netbox_proxbox.models import ProxboxBranchIntent

        intent = ProxboxBranchIntent.objects.filter(
            branch_id=branch_id,
            branch_schema_id=str(branch_schema_id),
        ).first()
        if intent is None:
            return FALSE_BRANCH_INTENT
        return BranchIntentFlags(
            apply_to_proxmox=getattr(intent, "apply_to_proxmox", False) is True,
            apply_destroy_confirmed=(
                getattr(intent, "apply_destroy_confirmed", False) is True
            ),
        )
    except Exception:
        return FALSE_BRANCH_INTENT
