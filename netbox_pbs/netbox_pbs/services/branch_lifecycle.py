"""Helpers to drive netbox-branching Branch lifecycle from PBSSyncJob.

Mirrors ``netbox_proxbox.services.branch_lifecycle`` so the PBS plugin can
participate in the same branch-create / sync / merge cycle without taking a
hard dependency on netbox-proxbox. The branching plugin itself is optional;
all imports tolerate ``ImportError``. Lifecycle calls are made in-process
(no REST round-trip) so a single RQ worker can complete provisioning, sync,
and merge without deadlocking on its own queue.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from netbox_pbs.models import PBSPluginSettings

logger = logging.getLogger("netbox_pbs.branch_lifecycle")


def is_branching_available() -> bool:
    try:
        import netbox_branching  # noqa: F401, PLC0415
    except Exception:
        return False
    return True


def get_active_branch_schema_id() -> str | None:
    """Return the ``schema_id`` of the currently-active netbox-branching Branch.

    Reads ``netbox_branching.contextvars.active_branch`` — the canonical
    process-local indicator of "the user is browsing on a branch right
    now". Returns ``None`` when branching is not installed, when no branch
    is active in this context, or when the branch object lacks the expected
    attributes. The detection is best-effort and never raises: the caller
    (sync-now views, etc.) treats ``None`` as "stay on main".
    """
    try:
        from netbox_branching.contextvars import active_branch  # noqa: PLC0415
    except Exception:
        return None
    try:
        branch = active_branch.get()
    except Exception:
        return None
    if branch is None:
        return None
    schema_id = getattr(branch, "schema_id", None)
    if not schema_id:
        return None
    return str(schema_id)


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


def create_and_provision_branch(
    *,
    name: str,
    user: Any | None,
    ready_timeout_seconds: int = 60,
) -> Any:
    """Create a Branch row, run provision() synchronously, return the Branch.

    Raises if branching is not installed, if the schema_id cannot be allocated,
    or if provision() raises.
    """
    from netbox_branching.choices import BranchStatusChoices  # noqa: PLC0415
    from netbox_branching.models import Branch  # noqa: PLC0415

    branch = Branch(name=name)
    branch.save(provision=False)
    try:
        branch.provision(user=user)
    except Exception:
        logger.exception("Branch provision failed for %s", name)
        raise

    deadline = time.monotonic() + ready_timeout_seconds
    while True:
        branch.refresh_from_db()
        if branch.status == BranchStatusChoices.READY:
            return branch
        if branch.status == BranchStatusChoices.FAILED:
            raise RuntimeError(
                f"Branch {branch.name} entered FAILED status during provisioning"
            )
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"Branch {branch.name} did not reach READY within "
                f"{ready_timeout_seconds}s (status={branch.status})"
            )
        time.sleep(0.5)


def branch_has_conflicts(branch: Any) -> bool:
    """True when ChangeDiff rows for this branch contain unresolved conflicts."""
    from netbox_branching.models import ChangeDiff  # noqa: PLC0415

    return ChangeDiff.objects.filter(branch=branch, conflicts__isnull=False).exists()


def merge_branch(
    *,
    branch: Any,
    user: Any | None,
    on_conflict: str,
) -> tuple[bool, str]:
    """Apply branch policy and call branch.merge() in-process.

    Returns (merged, message). When conflicts exist and policy is ``fail``,
    the branch is left in READY for operator inspection and (False, detail)
    is returned. When the policy is ``acknowledge``, the merge is attempted
    despite conflicts; the underlying merge_strategy decides the outcome.
    """
    if branch_has_conflicts(branch):
        if on_conflict != "acknowledge":
            return False, (
                f"Branch {branch.name} has unresolved conflicts and "
                "branch_on_conflict=fail; leaving branch open."
            )
        logger.warning(
            "Merging %s despite conflicts (branch_on_conflict=acknowledge)",
            branch.name,
        )

    try:
        branch.merge(user=user)
    except Exception as exc:
        logger.exception("Branch merge raised for %s", branch.name)
        return False, f"merge failed: {exc}"
    return True, f"Branch {branch.name} merged."
