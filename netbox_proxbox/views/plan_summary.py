"""Read-only plan summary view for NetBox -> Proxmox intent branches."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views import View
from utilities.views import ConditionalLoginRequiredMixin

from netbox_proxbox.intent.diff_classify import classify_diff
from netbox_proxbox.intent.diff_union import (
    virtual_machine_diff_id,
    virtual_machine_diff_name,
    virtual_machine_diff_union,
)
from netbox_proxbox.intent.plan_client import PlanClientError, call_plan_endpoint
from netbox_proxbox.models import ProxboxPluginSettings


def _maybe_restrict(queryset: Any, user: Any) -> Any:
    restrict = getattr(queryset, "restrict", None)
    if not callable(restrict):
        return queryset
    try:
        return restrict(user, "view")
    except TypeError:
        return restrict(user)


def _branch_intent_flags(branch: Any) -> Any:
    """Read both branch gates through the shared fail-closed resolver."""
    from netbox_proxbox.services.branch_intent import resolve_branch_intent_flags

    return resolve_branch_intent_flags(branch)


def _intent_enabled() -> bool:
    settings_obj = ProxboxPluginSettings.objects.first()
    return bool(settings_obj and settings_obj.netbox_to_proxmox_enabled)


def _vm_name(vm: Any) -> str:
    for value in (getattr(vm, "name", None), getattr(vm, "pk", None)):
        if value not in (None, ""):
            return str(value)
    return ""


def _vm_plan_diff(vm: Any, requested_op: str, row: Any) -> dict[str, Any]:
    try:
        op, kind = classify_diff(vm, requested_op, row)
    except Exception:  # pragma: no cover - defensive display fallback
        op = str(requested_op or "update").lower()
        kind = "qemu"
    return {
        "changediff_id": getattr(row, "pk", None),
        "op": op,
        "kind": kind,
        "netbox_id": virtual_machine_diff_id(vm, row),
        "name": virtual_machine_diff_name(vm, row),
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
            branch = (
                _maybe_restrict(Branch.objects.all(), request.user)
                .filter(pk=branch_id)
                .first()
            )
        except Exception as exc:  # pragma: no cover - defensive
            context["error"] = f"Could not load branch {branch_id}: {exc}"
            return render(request, self.template_name, context)

        if branch is None:
            context["error"] = f"Branch {branch_id} was not found."
            return render(request, self.template_name, context)

        diffs = [
            _vm_plan_diff(vm, op, row)
            for vm, op, row in virtual_machine_diff_union(branch)
        ]
        intent_enabled = _intent_enabled()
        branch_intent = _branch_intent_flags(branch)
        apply_to_proxmox = branch_intent.apply_to_proxmox
        apply_destroy_confirmed = branch_intent.apply_destroy_confirmed

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
                message="Branch intent setting apply_to_proxmox is not true.",
            )
            return render(request, self.template_name, context)

        if (
            any(diff["op"] == "delete" for diff in diffs)
            and not apply_destroy_confirmed
        ):
            context["permitted"] = False
            context["summary"] = "DELETE diffs require apply_destroy_confirmed=True."
            context["verdicts"] = _not_evaluated_verdicts(
                diffs,
                verdict="blocked",
                reason="destroy_not_confirmed",
                message=(
                    "Branch intent setting apply_destroy_confirmed is not true for "
                    "a branch containing DELETE diffs."
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
