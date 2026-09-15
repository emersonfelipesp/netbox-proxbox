"""Helpers to drive netbox-branching Branch lifecycle from ProxboxSyncJob.

The branching plugin is optional; importers must tolerate ImportError.
All Branch lifecycle calls are made in-process (no REST round-trip) so a
single RQ worker can complete provisioning, sync, and merge without
deadlocking on its own queue.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from enum import Enum
import logging
import time
from typing import Any

from netbox_proxbox.models import ProxboxPluginSettings

logger = logging.getLogger("netbox_proxbox.branch_lifecycle")


class BranchingDecisionState(str, Enum):
    """The three safe outcomes of resolving branch-isolated sync settings."""

    ENABLED = "enabled"
    DISABLED = "disabled"
    CONFIGURED_BUT_UNAVAILABLE = "configured_but_unavailable"


@dataclass(frozen=True)
class BranchingDecision:
    """Resolved branch-isolation state and its supporting detail."""

    state: BranchingDecisionState
    settings: dict[str, str] | None = None
    reason: str | None = None
    configured: bool | None = None


class BranchingUnavailableError(RuntimeError):
    """Branch isolation was configured but could not be provided safely."""


class ActiveBranchRequiredError(RuntimeError):
    """An enabled request lacked an active READY branch schema."""


ACTIVE_BRANCH_REQUIRED_MESSAGE = (
    "Proxbox sync refused: branch isolation is enabled, but this request has no "
    "active READY branch schema; activate a branch or disable branch isolation."
)


def _exception_reason(prefix: str, exc: Exception) -> str:
    """Return a concise human-readable reason without losing the exception type."""
    detail = str(exc).strip()
    suffix = f": {detail}" if detail else ""
    return f"{prefix} ({type(exc).__name__}{suffix})"


def _branching_failure_message(decision: BranchingDecision) -> str:
    """Build the actionable refusal shared by every sync entry point."""
    detail = decision.reason or "no usable netbox-branching runtime was detected"
    if decision.configured is not True:
        return (
            "Proxbox sync refused: branching_enabled could not be read, so branch "
            f"isolation cannot be safely ruled out ({detail}). Restore access to "
            "ProxboxPluginSettings, then install and enable a netbox-branching "
            "release compatible with this NetBox version, or set "
            "branching_enabled=False to explicitly allow sync on main."
        )
    return (
        "Proxbox sync refused: branch isolation is configured with "
        f"branching_enabled=True, but netbox-branching is unavailable ({detail}). "
        "Install and enable a netbox-branching release compatible with this NetBox "
        "version, or set branching_enabled=False to explicitly allow sync on main."
    )


def _branching_unavailable_reason() -> str | None:
    """Return why the branching app cannot be used, or ``None`` when ready."""
    try:
        from django.apps import apps  # noqa: PLC0415

        installed = apps.is_installed("netbox_branching")
    except Exception as exc:
        return _exception_reason("the Django app registry could not be checked", exc)
    if not installed:
        return (
            "the `netbox_branching` Django app is not loaded; it may be missing, "
            "disabled, or skipped because its NetBox version range is incompatible"
        )
    try:
        import netbox_branching  # noqa: F401, PLC0415
    except Exception as exc:
        return _exception_reason(
            "the loaded `netbox_branching` app could not import", exc
        )
    return None


def is_branching_available() -> bool:
    """True only when netbox-branching is a *loaded Django app*.

    Importability is not the question, and treating it as one is unsafe on
    NetBox 4.7. ``netboxlabs-netbox-branching`` declares ``max_version =
    "4.6.99"``, and ``netbox/settings.py`` handles an out-of-range plugin by
    catching ``IncompatiblePluginError``, warning, and **skipping** it. The
    package therefore remains perfectly importable on 4.7 while its app is
    absent from ``INSTALLED_APPS`` and its models and schemas do not exist.

    An import check reports "available" in exactly that state, so callers would
    go on to create branches against an engine that is not running. Requiring
    the app registry to know about it is what makes the answer true.

    Returns False rather than raising if the registry cannot be consulted.
    :func:`resolve_branching_decision` combines that result with the persisted
    operator setting and decides whether syncing on ``main`` is safe.
    """
    return _branching_unavailable_reason() is None


def get_active_branch_schema_id() -> str | None:
    """Return the ``schema_id`` of the active READY netbox-branching Branch.

    Reads ``netbox_branching.contextvars.active_branch`` — the canonical
    process-local indicator of "the user is browsing on a branch right
    now". Returns ``None`` when branching is not installed, no branch is active,
    the branch is not freshly READY, or its schema identifier is unusable. The
    detection is best-effort and never raises. Sync entry points must call
    :func:`require_branch_isolation_or_raise` first so an unavailable configured
    boundary cannot be mistaken for "stay on main".
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
    try:
        from netbox_branching.choices import BranchStatusChoices  # noqa: PLC0415

        if (
            _refreshed_branch_status(branch, "request sync")
            != BranchStatusChoices.READY
        ):
            return None
        return _require_branch_schema_id(branch)
    except Exception:
        return None


def resolve_branching_decision() -> BranchingDecision:
    """Resolve branch isolation without treating uncertainty as permission."""
    try:
        settings_obj = ProxboxPluginSettings.get_solo()
    except Exception as exc:
        logger.exception("Could not load ProxboxPluginSettings")
        return BranchingDecision(
            BranchingDecisionState.CONFIGURED_BUT_UNAVAILABLE,
            reason=_exception_reason(
                "Proxbox plugin settings could not be loaded", exc
            ),
        )
    if not getattr(settings_obj, "branching_enabled", False):
        return BranchingDecision(BranchingDecisionState.DISABLED, configured=False)
    reason = _branching_unavailable_reason()
    if reason is not None:
        return BranchingDecision(
            BranchingDecisionState.CONFIGURED_BUT_UNAVAILABLE,
            reason=reason,
            configured=True,
        )
    settings = {
        "prefix": getattr(settings_obj, "branch_name_prefix", "") or "proxbox-sync",
        "on_conflict": getattr(settings_obj, "branch_on_conflict", "") or "fail",
    }
    return BranchingDecision(
        BranchingDecisionState.ENABLED,
        settings=settings,
        configured=True,
    )


def require_branch_isolation_or_raise() -> BranchingDecision:
    """Return the resolved isolation decision or refuse an unsafe main sync."""
    decision = resolve_branching_decision()
    if decision.state is BranchingDecisionState.CONFIGURED_BUT_UNAVAILABLE:
        raise BranchingUnavailableError(_branching_failure_message(decision))
    return decision


def require_active_branch_schema_id(decision: BranchingDecision) -> str | None:
    """Require an active READY schema for an enabled request mutation."""
    if decision.state is BranchingDecisionState.DISABLED:
        return None
    schema_id = get_active_branch_schema_id()
    if schema_id is None:
        raise ActiveBranchRequiredError(ACTIVE_BRANCH_REQUIRED_MESSAGE)
    return schema_id


def branching_enabled_settings() -> dict[str, str] | None:
    """Compatibility wrapper returning settings only when branching is enabled."""
    decision = require_branch_isolation_or_raise()
    if decision.state is BranchingDecisionState.DISABLED:
        return None
    return decision.settings


def _left_open_message(branch: Any, detail: str) -> str:
    """Name a branch lifecycle failure and its safe operator disposition."""
    name = getattr(branch, "name", "<unknown>")
    return f"Branch {name} {detail}; branch left open for operator inspection."


def _refreshed_branch_status(branch: Any, action: str) -> object:
    """Refresh lifecycle state or fail without trusting a stale model instance."""
    try:
        branch.refresh_from_db()
    except Exception as exc:
        detail = _exception_reason(f"could not be refreshed before {action}", exc)
        raise BranchingUnavailableError(_left_open_message(branch, detail)) from exc
    return getattr(branch, "status", None)


def _require_branch_ready(branch: Any, action: str) -> None:
    """Require a freshly-read READY branch immediately before a write context."""
    from netbox_branching.choices import BranchStatusChoices  # noqa: PLC0415

    status = _refreshed_branch_status(branch, action)
    if status != BranchStatusChoices.READY:
        detail = f"is not READY before {action} (status={status})"
        raise BranchingUnavailableError(_left_open_message(branch, detail))
    _require_branch_schema_id(branch)


@contextmanager
def activate_sync_branch(branch: Any | None):
    """Activate a freshly verified branch and restore the prior context."""
    if branch is None:
        yield
        return
    try:
        from netbox_branching.utilities import activate_branch  # noqa: PLC0415
    except Exception as exc:
        detail = _exception_reason("activation could not import", exc)
        raise BranchingUnavailableError(_left_open_message(branch, detail)) from exc
    _require_branch_ready(branch, "activation")
    stack = ExitStack()
    try:
        stack.enter_context(activate_branch(branch))
    except Exception as exc:
        stack.close()
        detail = _exception_reason("activation failed", exc)
        raise BranchingUnavailableError(_left_open_message(branch, detail)) from exc
    with stack:
        yield


def _require_branch_schema_id(branch: Any) -> str:
    """Return a non-empty provisioned schema identifier or fail closed."""
    schema_id = getattr(branch, "schema_id", None)
    if not isinstance(schema_id, str) or not schema_id.strip():
        name = getattr(branch, "name", "<unknown>")
        raise BranchingUnavailableError(
            f"Branch {name} reached READY without a usable schema_id; "
            "branch isolation cannot be guaranteed, so the branch was left open "
            "for operator inspection."
        )
    return schema_id


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
            _require_branch_schema_id(branch)
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


def _branch_has_unmerged_changes(branch: Any) -> bool:
    """Use the branching lifecycle's own query to identify a no-change return."""
    return branch.get_unmerged_changes().exists()


def merge_branch(
    *,
    branch: Any,
    user: Any | None,
    on_conflict: str,
) -> tuple[bool, str, str | None]:
    """Apply branch policy and verify merge or a safe no-change return.

    Returns ``(merged, message, disposition)``. When conflicts exist and policy
    is ``fail``, the branch is left in READY for operator inspection. When the
    policy is ``acknowledge``, the merge is attempted despite conflicts; the
    underlying merge strategy decides the outcome. A successful merge must
    refresh to MERGED. The v1.2.0-beta1 no-change return remains READY and is
    left open with the ``no_changes_left_open`` disposition.
    """
    from netbox_branching.choices import BranchStatusChoices  # noqa: PLC0415

    if branch_has_conflicts(branch):
        if on_conflict != "acknowledge":
            return (
                False,
                _left_open_message(
                    branch,
                    "has unresolved conflicts and branch_on_conflict=fail",
                ),
                None,
            )
        logger.warning(
            "Merging %s despite conflicts (branch_on_conflict=acknowledge)",
            branch.name,
        )

    try:
        _require_branch_ready(branch, "merge")
        branch.merge(user=user)
    except BranchingUnavailableError as exc:
        return False, str(exc), None
    except Exception as exc:  # pragma: no cover - merge_strategies vary
        logger.exception("Branch merge raised for %s", branch.name)
        return False, _left_open_message(branch, f"merge failed: {exc}"), None
    try:
        status = _refreshed_branch_status(branch, "merge verification")
        if status == BranchStatusChoices.MERGED:
            return True, f"Branch {branch.name} merged.", None
        if status != BranchStatusChoices.READY:
            detail = f"did not reach MERGED after merge (status={status})"
            return False, _left_open_message(branch, detail), None
        if _branch_has_unmerged_changes(branch):
            detail = "remained READY after merge with unmerged changes"
            return False, _left_open_message(branch, detail), None
    except BranchingUnavailableError as exc:
        return False, str(exc), None
    except Exception as exc:  # pragma: no cover - lifecycle backends vary
        logger.exception("Branch merge verification failed for %s", branch.name)
        return False, _left_open_message(branch, f"verification failed: {exc}"), None
    branch_id = getattr(branch, "pk", getattr(branch, "id", None))
    return (
        True,
        f"Branch {branch.name} (id={branch_id}) had no changes; branch left open. "
        "Archive it through the netbox-branching UI.",
        "no_changes_left_open",
    )
