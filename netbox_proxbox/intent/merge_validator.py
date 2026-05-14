"""``netbox_branching`` merge_validator for the NetBox -> Proxmox intent path.

Sub-PR D (#381) introduces ``validate_proxmox_intent(branch, user)``.
The hook runs on the netbox-branching plugin side just before a merge
commits. It is registered via NetBox's ``PLUGINS_CONFIG`` (see the
``proxbox_install_merge_validator`` management command for the
snippet) and returns a ``BranchActionIndicator``.

The validator is intentionally permissive when the intent path is
opt-out:

* If the master flag ``netbox_to_proxmox_enabled`` is False, the merge
  is permitted unconditionally (the reflection path is unaffected).
* If the branch does not opt in via ``cf.apply_to_proxmox=True``, the
  merge is permitted unconditionally.

When the intent path is engaged, the validator:

1. Collects the VirtualMachine ChangeDiff rows on the branch.
2. Calls ``POST /intent/plan`` on proxbox-api with the classified
   diffs.
3. Enforces the DELETE-without-``apply_destroy_confirmed`` block at
   the plugin layer (Safety Model invariant 3 — see
   ``netbox-proxbox/CLAUDE.md``).
4. Returns ``BranchActionIndicator(permitted, message)`` based on the
   backend's ``permitted`` flag plus the local DELETE check.

Per-op probes (node online, storage capacity, VMID availability,
cloud-init YAML well-formedness) live in proxbox-api Sub-PRs F/G/K
and ship as additional verdicts in the same response shape.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from netbox_proxbox.intent.plan_client import (
    PlanClientError,
    PlanClientResult,
    call_plan_endpoint,
)

if TYPE_CHECKING:  # pragma: no cover - import only for type hints
    from netbox_branching.models import Branch
    from netbox_branching.utilities import BranchActionIndicator
    from users.models import User

logger = logging.getLogger(__name__)


# The kinds we currently classify. Sub-PR K may add ``lxc`` once the
# LXC apply dispatchers land in proxbox-api; for now both CREATE and
# UPDATE diffs default to ``virtualmachine``.
_VM_MODEL = "virtualmachine"


def _plugin_settings() -> Any:
    try:
        from netbox_proxbox.models.plugin_settings import ProxboxPluginSettings
    except Exception:  # pragma: no cover - defensive
        return None

    return ProxboxPluginSettings.objects.first()


def _indicator(permitted: bool, message: str = "") -> "BranchActionIndicator":
    """Build a ``BranchActionIndicator`` lazily.

    Importing ``netbox_branching`` at module level would couple the
    plugin to a hard dependency; the netbox-branching plugin is
    operator-installable but not a pyproject dep here.
    """
    from netbox_branching.utilities import BranchActionIndicator

    return BranchActionIndicator(permitted=permitted, message=message)


def _is_intent_enabled() -> bool:
    """Master flag check — read fresh from ProxboxPluginSettings."""
    settings_obj = _plugin_settings()
    if settings_obj is None:
        return False
    return bool(getattr(settings_obj, "netbox_to_proxmox_enabled", False))


def _warn_plaintext_password_enabled() -> bool:
    settings_obj = _plugin_settings()
    if settings_obj is None:
        return True
    return bool(getattr(settings_obj, "intent_warn_plaintext_password", True))


def _branch_opted_in(branch: Any) -> bool:
    """Per-branch opt-in via the ``apply_to_proxmox`` custom field."""
    cf = getattr(branch, "custom_field_data", None) or {}
    if not isinstance(cf, dict):
        return False
    return bool(cf.get("apply_to_proxmox", False))


def _branch_destroy_confirmed(branch: Any) -> bool:
    """Per-branch DELETE four-eyes confirmation."""
    cf = getattr(branch, "custom_field_data", None) or {}
    if not isinstance(cf, dict):
        return False
    return bool(cf.get("apply_destroy_confirmed", False))


def _classify_vm_diffs(branch: Any) -> list[dict[str, Any]]:
    """Walk the VM ChangeDiff rows on the branch into intent payloads.

    Returns a list of ``{"op": ..., "kind": ..., "netbox_id": ..., "name": ...}``
    dicts matching proxbox-api's ``IntentDiff`` schema.
    """
    diffs: list[dict[str, Any]] = []

    changediff_qs = getattr(branch, "changediff_set", None)
    if changediff_qs is None:
        return diffs

    rows = changediff_qs.filter(object_type__model=_VM_MODEL)
    for row in rows:
        action = getattr(row, "action", None)
        if action not in {"create", "update", "delete"}:
            continue
        diffs.append(
            {
                "op": action,
                "kind": _VM_MODEL,
                "netbox_id": getattr(row, "object_id", None),
                "name": getattr(row, "object_repr", "") or None,
            }
        )

    return diffs


def _custom_fields_from_data(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    for key in ("custom_field_data", "custom_fields"):
        cf = data.get(key)
        if isinstance(cf, dict):
            return cf
    return {}


def _custom_fields_from_row(row: Any) -> dict[str, Any]:
    vm = getattr(row, "object", None)
    cf = getattr(vm, "custom_field_data", None)
    if isinstance(cf, dict):
        return cf

    for attr in ("postchange_data", "prechange_data"):
        cf = _custom_fields_from_data(getattr(row, attr, None))
        if cf:
            return cf
    return {}


def _contains_plaintext_password(user_data: Any) -> bool:
    return "password:" in str(user_data or "").lower()


def _row_vm_name(row: Any) -> str:
    vm = getattr(row, "object", None)
    for value in (
        getattr(vm, "name", None),
        getattr(row, "object_repr", None),
        getattr(row, "object_id", None),
    ):
        if value not in (None, ""):
            return str(value)
    return "unknown"


def _plaintext_password_warnings(branch: Any) -> list[dict[str, str]]:
    if not _warn_plaintext_password_enabled():
        return []

    changediff_qs = getattr(branch, "changediff_set", None)
    if changediff_qs is None:
        return []

    warnings: list[dict[str, str]] = []
    rows = changediff_qs.filter(object_type__model=_VM_MODEL)
    for row in rows:
        if getattr(row, "action", None) == "delete":
            continue
        user_data = _custom_fields_from_row(row).get("cloud_init_user_data")
        if not _contains_plaintext_password(user_data):
            continue
        warnings.append(
            {
                "vm": _row_vm_name(row),
                "level": "warn",
                "code": "plaintext_password_warning",
                "message": "cloud_init_user_data contains a plaintext password line",
            }
        )
    return warnings


def _has_delete(diffs: list[dict[str, Any]]) -> bool:
    return any(d.get("op") == "delete" for d in diffs)


def _format_remote_failure(result: PlanClientResult) -> str:
    """Build an operator-facing error from a non-permitting plan response."""
    blockers = [v for v in result.verdicts if v.get("verdict") == "blocked"]
    if blockers:
        bullet = "; ".join(
            f"{v.get('reason', 'blocked')}: {v.get('message', '').strip()}"
            for v in blockers
        )
        return f"proxbox-api blocked the merge: {bullet}"
    if result.summary:
        return f"proxbox-api refused the merge: {result.summary}"
    return "proxbox-api refused the merge."


def _format_success(result: PlanClientResult) -> str:
    warnings = [
        f"{v.get('vm', 'unknown')}: {v.get('message', '').strip()}"
        for v in result.verdicts
        if v.get("level") == "warn" and v.get("code") == "plaintext_password_warning"
    ]
    if not warnings:
        return result.summary or ""

    warning_text = "; ".join(warnings)
    if result.summary:
        return f"{result.summary} Warnings: {warning_text}"
    return f"Warnings: {warning_text}"


def validate_proxmox_intent(
    branch: "Branch", user: "User | None" = None
) -> "BranchActionIndicator":
    """``merge_validators`` entry point.

    Signature matches what netbox-branching invokes (see
    ``netbox_branching.models.branches.Branch.can_merge`` —
    validators are called with ``(branch, user)``).
    """
    # Fast path: intent path opt-out for the whole instance.
    if not _is_intent_enabled():
        return _indicator(True)

    # Fast path: branch not flagged for Proxmox apply.
    if not _branch_opted_in(branch):
        return _indicator(True)

    diffs = _classify_vm_diffs(branch)
    if not diffs:
        return _indicator(
            True,
            "No VM diffs on branch; Proxmox merge will be a no-op.",
        )

    # Local Safety Model invariant 3: DELETE diffs require the
    # per-branch ``apply_destroy_confirmed`` toggle BEFORE any
    # backend probe. Surface this at plan time so the operator can
    # fix it without round-tripping proxbox-api.
    if _has_delete(diffs) and not _branch_destroy_confirmed(branch):
        return _indicator(
            False,
            (
                "Branch contains DELETE diffs but apply_destroy_confirmed=False. "
                "Toggle the branch CF (and grant authorize_deletion_request to a "
                "separate user) before merging."
            ),
        )

    local_warnings = _plaintext_password_warnings(branch)
    payload: dict[str, Any] = {
        "branch_id": getattr(branch, "pk", None),
        "actor": getattr(user, "username", None) if user else None,
        "diffs": diffs,
    }

    try:
        result = call_plan_endpoint(payload)
    except PlanClientError as exc:
        logger.warning("intent.plan call failed: %s", exc)
        return _indicator(
            False,
            f"Could not validate merge against proxbox-api: {exc}",
        )

    if local_warnings:
        result.verdicts.extend(local_warnings)
        if isinstance(result.raw, dict):
            result.raw["verdicts"] = result.verdicts

    if not result.permitted:
        return _indicator(False, _format_remote_failure(result))

    return _indicator(True, _format_success(result))
