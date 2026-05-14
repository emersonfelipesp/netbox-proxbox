"""Read-only plan summary view for NetBox -> Proxmox intent branches."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views import View
from utilities.views import ConditionalLoginRequiredMixin

from netbox_proxbox.intent.diff_classify import classify_diff
from netbox_proxbox.intent.plan_client import PlanClientError, call_plan_endpoint
from netbox_proxbox.models import ProxboxPluginSettings

_VM_MODEL = "virtualmachine"


def _maybe_restrict(queryset: Any, user: Any) -> Any:
    restrict = getattr(queryset, "restrict", None)
    if not callable(restrict):
        return queryset
    try:
        return restrict(user, "view")
    except TypeError:
        return restrict(user)


def _branch_custom_fields(branch: Any) -> dict[str, Any]:
    data = getattr(branch, "custom_field_data", None)
    return data if isinstance(data, dict) else {}


def _branch_flag(branch: Any, field_name: str) -> bool:
    return _branch_custom_fields(branch).get(field_name) is True


def _intent_enabled() -> bool:
    settings_obj = ProxboxPluginSettings.objects.first()
    return bool(settings_obj and settings_obj.netbox_to_proxmox_enabled)


def _changediff_rows(branch: Any) -> list[Any]:
    manager = getattr(branch, "changediff_set", None)
    if manager is None:
        return []
    rows = manager.filter(object_type__model=_VM_MODEL)
    order_by = getattr(rows, "order_by", None)
    if callable(order_by):
        rows = order_by("pk")
    return list(rows)


def _row_name(row: Any) -> str:
    vm = getattr(row, "object", None)
    for value in (
        getattr(vm, "name", None),
        getattr(row, "object_repr", None),
        getattr(row, "object_id", None),
    ):
        if value not in (None, ""):
            return str(value)
    return ""


def _row_netbox_id(row: Any) -> Any:
    return getattr(row, "object_id", None)


def _row_plan_diff(row: Any) -> dict[str, Any]:
    try:
        op, kind = classify_diff(row)
    except Exception:  # pragma: no cover - defensive display fallback
        op = str(getattr(row, "action", "") or "update").lower()
        kind = "qemu"
    return {
        "changediff_id": getattr(row, "pk", None),
        "op": op,
        "kind": kind,
        "netbox_id": _row_netbox_id(row),
        "name": _row_name(row),
    }


def _not_evaluated_verdicts(
    diffs: list[dict[str, Any]], *, verdict: str, reason: str, message: str
) -> list[dict[str, Any]]:
    return [
        {
            **diff,
            "verdict": verdict,
            "reason": reason,
            "message": message,
        }
        for diff in diffs
    ]


class IntentPlanSummaryView(ConditionalLoginRequiredMixin, View):
    """Render a per-VM intent verdict table for a netbox-branching branch."""

    template_name = "netbox_proxbox/plan_summary.html"

    def get(self, request: HttpRequest, branch_id: int) -> HttpResponse:
        context: dict[str, Any] = {
            "object": None,
            "branch": None,
            "branch_id": branch_id,
            "diffs": [],
            "verdicts": [],
            "permitted": None,
            "summary": "",
            "error": "",
            "apply_to_proxmox": False,
            "apply_destroy_confirmed": False,
            "intent_enabled": False,
        }

        try:
            from netbox_branching.models import Branch
        except ImportError:
            context["error"] = "netbox-branching is not installed."
            return render(request, self.template_name, context)

        try:
            branch = _maybe_restrict(Branch.objects.all(), request.user).filter(
                pk=branch_id
            ).first()
        except Exception as exc:  # pragma: no cover - defensive
            context["error"] = f"Could not load branch {branch_id}: {exc}"
            return render(request, self.template_name, context)

        if branch is None:
            context["error"] = f"Branch {branch_id} was not found."
            return render(request, self.template_name, context)

        rows = _changediff_rows(branch)
        diffs = [_row_plan_diff(row) for row in rows]
        intent_enabled = _intent_enabled()
        apply_to_proxmox = _branch_flag(branch, "apply_to_proxmox")
        apply_destroy_confirmed = _branch_flag(branch, "apply_destroy_confirmed")

        context.update(
            {
                "object": branch,
                "branch": branch,
                "diffs": diffs,
                "intent_enabled": intent_enabled,
                "apply_to_proxmox": apply_to_proxmox,
                "apply_destroy_confirmed": apply_destroy_confirmed,
            }
        )

        if not diffs:
            context["permitted"] = True
            context["summary"] = "No VirtualMachine ChangeDiffs exist on this branch."
            return render(request, self.template_name, context)

        if not intent_enabled:
            context["permitted"] = True
            context["summary"] = "Intent master flag is disabled."
            context["verdicts"] = _not_evaluated_verdicts(
                diffs,
                verdict="skipped",
                reason="intent_disabled",
                message="NetBox -> Proxmox intent is disabled in plugin settings.",
            )
            return render(request, self.template_name, context)

        if not apply_to_proxmox:
            context["permitted"] = True
            context["summary"] = "Branch is not opted in for Proxmox apply."
            context["verdicts"] = _not_evaluated_verdicts(
                diffs,
                verdict="skipped",
                reason="branch_not_opted_in",
                message="Branch custom field apply_to_proxmox is not true.",
            )
            return render(request, self.template_name, context)

        if any(diff["op"] == "delete" for diff in diffs) and not apply_destroy_confirmed:
            context["permitted"] = False
            context["summary"] = "DELETE diffs require apply_destroy_confirmed=True."
            context["verdicts"] = _not_evaluated_verdicts(
                diffs,
                verdict="blocked",
                reason="destroy_not_confirmed",
                message=(
                    "Branch contains DELETE diffs but apply_destroy_confirmed is not true."
                ),
            )
            return render(request, self.template_name, context)

        payload = {
            "branch_id": getattr(branch, "pk", branch_id),
            "actor": getattr(request.user, "username", None),
            "diffs": [
                {
                    "op": diff["op"],
                    "kind": diff["kind"],
                    "netbox_id": diff["netbox_id"],
                    "name": diff["name"] or None,
                }
                for diff in diffs
            ],
        }
        try:
            result = call_plan_endpoint(payload)
        except PlanClientError as exc:
            context["permitted"] = False
            context["summary"] = f"Plan endpoint unavailable: {exc}"
            context["verdicts"] = _not_evaluated_verdicts(
                diffs,
                verdict="blocked",
                reason="plan_endpoint_error",
                message=str(exc),
            )
            return render(request, self.template_name, context)

        context["permitted"] = result.permitted
        context["summary"] = result.summary
        context["verdicts"] = result.verdicts
        return render(request, self.template_name, context)
