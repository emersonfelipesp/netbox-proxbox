"""Plugin-side backend-proxy views for operational verbs (issue #376).

Trust boundary (operational-verbs.md §2.3):

  Browser ─ POST ─▶ this view (gated by ``core.run_proxmox_action``)
                  │
                  └─ HTTP POST ▶ proxbox-api ``/proxmox/{vm_type}/{vmid}/{verb}``
                                  (gated by ``ProxmoxEndpoint.allow_writes``)

Each view:

1. Requires ``core.run_proxmox_action`` via
   ``ContentTypePermissionRequiredMixin`` (returns 403 otherwise).
2. Resolves the VM's ``(endpoint_id, vmid, vm_type)`` triple. If any
   piece is missing, surfaces a Django message and redirects back to
   the VM detail page — never reaches proxbox-api.
3. Generates a fresh ``uuid4`` ``Idempotency-Key`` per request (§4.1).
4. POSTs to proxbox-api with the resolved ``endpoint_id`` query param.
   The backend's ``allow_writes`` check completes the trust boundary;
   a 403 ``endpoint_writes_disabled`` is surfaced as a Django message.

Migrate has an extra GET (target-node picker). The picker renders
regardless of ``allow_writes`` because the operator must be able to
see why a button is disabled; only the POST triggers a write.
"""

from __future__ import annotations

import uuid
from typing import ClassVar

import requests
from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.utils.translation import gettext_lazy as _
from django.views import View
from utilities.views import (
    ContentTypePermissionRequiredMixin,
    TokenConditionalLoginRequiredMixin,
    register_model_view,
)
from virtualization.models import VirtualMachine

from netbox_proxbox.models import ProxmoxNode
from netbox_proxbox.services._endpoint_errors import translate_request_exception
from netbox_proxbox.services.backend_context import get_fastapi_request_context
from netbox_proxbox.utils import resolve_vm_type
from netbox_proxbox.views.proxbox_access import permission_run_proxmox_action

__all__ = (
    "OperationalMigrateView",
    "OperationalSnapshotView",
    "OperationalStartView",
    "OperationalStopView",
    "resolve_vm_endpoint_context",
)

_BACKEND_TIMEOUT_S = 30


def resolve_vm_endpoint_context(
    vm: VirtualMachine,
) -> tuple[int, int, str] | None:
    """Return ``(endpoint_id, vmid, vm_type)`` if the VM is fully addressable.

    Returns ``None`` when any piece is missing — the caller should hide
    the button or surface a message rather than POSTing an invalid call
    to proxbox-api.
    """
    cluster = getattr(vm, "cluster", None)
    if cluster is None:
        return None
    proxmox_cluster = cluster.proxmox_cluster_tracking.first()
    if proxmox_cluster is None or proxmox_cluster.endpoint_id is None:
        return None
    endpoint = getattr(proxmox_cluster, "endpoint", None)
    if endpoint is not None and not bool(getattr(endpoint, "enabled", True)):
        return None
    cf = getattr(vm, "custom_field_data", None) or {}
    raw_vmid = cf.get("proxmox_vm_id") or cf.get("cf_proxmox_vm_id")
    try:
        vmid = int(raw_vmid) if raw_vmid is not None else None
    except (TypeError, ValueError):
        return None
    if vmid is None:
        return None
    return (int(proxmox_cluster.endpoint_id), vmid, resolve_vm_type(vm))


class _OperationalVerbView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """Shared dispatch path for the four operational verbs."""

    verb: ClassVar[str] = ""
    http_method_names: ClassVar[list[str]] = ["post"]

    def get_required_permission(self) -> str:
        """Return the run_proxmox_action permission codename."""
        return permission_run_proxmox_action()

    def post(self, request: HttpRequest, pk: int | str) -> HttpResponseRedirect:
        """Forward a verb invocation to proxbox-api."""
        vm = get_object_or_404(
            VirtualMachine.objects.restrict(request.user, "view"),
            pk=pk,
        )
        return _forward_verb(request, vm, self.verb, extra_body=None)


@register_model_view(
    VirtualMachine, "proxbox_operational_start", path="proxbox-operational-start"
)
class OperationalStartView(_OperationalVerbView):
    """POST: dispatch the ``start`` verb."""

    verb = "start"


@register_model_view(
    VirtualMachine, "proxbox_operational_stop", path="proxbox-operational-stop"
)
class OperationalStopView(_OperationalVerbView):
    """POST: dispatch the ``stop`` verb."""

    verb = "stop"


@register_model_view(
    VirtualMachine, "proxbox_operational_snapshot", path="proxbox-operational-snapshot"
)
class OperationalSnapshotView(_OperationalVerbView):
    """POST: dispatch the ``snapshot`` verb. Snapshot name is server-chosen."""

    verb = "snapshot"


@register_model_view(
    VirtualMachine, "proxbox_operational_migrate", path="proxbox-operational-migrate"
)
class OperationalMigrateView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """GET: render target-node picker. POST: dispatch the ``migrate`` verb.

    The picker is reachable regardless of ``allow_writes`` so an operator
    can see the target list. Only POST hits proxbox-api, where the
    backend's ``allow_writes`` check completes the trust boundary.
    """

    http_method_names: ClassVar[list[str]] = ["get", "post"]

    def get_required_permission(self) -> str:
        """Return the run_proxmox_action permission codename."""
        return permission_run_proxmox_action()

    def get(self, request: HttpRequest, pk: int | str) -> HttpResponse:
        """Render the target-node picker for the migrate verb."""
        vm = get_object_or_404(
            VirtualMachine.objects.restrict(request.user, "view"),
            pk=pk,
        )
        ctx = resolve_vm_endpoint_context(vm)
        targets: list[ProxmoxNode] = []
        current_node = ""
        if ctx is not None:
            endpoint_id, _vmid, _vm_type = ctx
            qs = ProxmoxNode.objects.filter(endpoint_id=endpoint_id)
            current_node = _current_node_name(vm)
            if current_node:
                qs = qs.exclude(name=current_node)
            targets = list(qs.order_by("name"))
        return render(
            request,
            "netbox_proxbox/vm_migrate_picker.html",
            {
                "vm": vm,
                "targets": targets,
                "current_node": current_node,
                "resolvable": ctx is not None,
                "action_url": f"{vm.get_absolute_url()}proxbox-operational-migrate/",
            },
        )

    def post(self, request: HttpRequest, pk: int | str) -> HttpResponseRedirect:
        """Forward migrate dispatch with the chosen target node."""
        vm = get_object_or_404(
            VirtualMachine.objects.restrict(request.user, "view"),
            pk=pk,
        )
        target = (request.POST.get("target") or "").strip()
        if not target:
            messages.error(
                request, _("Select a target node before submitting migrate.")
            )
            return HttpResponseRedirect(
                f"{vm.get_absolute_url()}proxbox-operational-migrate/"
            )
        online = request.POST.get("online", "").lower() in ("on", "true", "1", "yes")
        return _forward_verb(
            request,
            vm,
            "migrate",
            extra_body={"target": target, "online": online},
        )


def _current_node_name(vm: VirtualMachine) -> str:
    """Best-effort current Proxmox node name for the VM (used to exclude self-target)."""
    device = getattr(vm, "device", None)
    if device is not None and getattr(device, "name", None):
        return str(device.name)
    cf = getattr(vm, "custom_field_data", None) or {}
    return str(cf.get("proxmox_node") or cf.get("cf_proxmox_node") or "")


def _forward_verb(
    request: HttpRequest,
    vm: VirtualMachine,
    verb: str,
    *,
    extra_body: dict[str, object] | None,
) -> HttpResponseRedirect:
    """POST to proxbox-api ``/proxmox/{vm_type}/{vmid}/{verb}`` and surface result."""
    redirect_to = vm.get_absolute_url()
    resolved = resolve_vm_endpoint_context(vm)
    if resolved is None:
        messages.error(
            request,
            _(
                "This VM is not linked to a Proxmox endpoint, or is missing a "
                "proxmox_vm_id custom field. Operational verbs are unavailable."
            ),
        )
        return HttpResponseRedirect(redirect_to)
    endpoint_id, vmid, vm_type = resolved

    ctx = get_fastapi_request_context()
    if ctx is None or not ctx.http_url:
        messages.error(request, _("No FastAPI backend endpoint is configured."))
        return HttpResponseRedirect(redirect_to)

    url = f"{ctx.http_url}/proxmox/{vm_type}/{vmid}/{verb}"
    headers = dict(ctx.headers or {})
    headers["Idempotency-Key"] = str(uuid.uuid4())
    headers.setdefault("Content-Type", "application/json")

    try:
        response = requests.post(
            url,
            params={"endpoint_id": endpoint_id},
            json=extra_body or {},
            headers=headers,
            timeout=_BACKEND_TIMEOUT_S,
            verify=ctx.verify_ssl,
        )
    except requests.exceptions.RequestException as exc:
        messages.error(
            request,
            _("Backend request failed: {error}").format(
                error=translate_request_exception(exc)
            ),
        )
        return HttpResponseRedirect(redirect_to)

    _surface_backend_response(request, response, verb)
    return HttpResponseRedirect(redirect_to)


def _surface_backend_response(
    request: HttpRequest, response: requests.Response, verb: str
) -> None:
    """Translate a proxbox-api response into a Django flash message."""
    payload: dict[str, object] | None
    try:
        body = response.json()
        payload = body if isinstance(body, dict) else None
    except ValueError:
        payload = None

    if response.status_code in (200, 202):
        messages.success(
            request,
            _("Proxmox {verb} dispatched.").format(verb=verb),
        )
        return

    reason = (payload or {}).get("reason") if payload else None
    detail = (payload or {}).get("detail") if payload else None
    pieces = [
        _("Proxmox {verb} request failed ({status}).").format(
            verb=verb, status=response.status_code
        )
    ]
    if reason:
        pieces.append(_("Reason: {reason}.").format(reason=reason))
    if detail and detail != reason:
        pieces.append(str(detail))
    messages.error(request, " ".join(str(p) for p in pieces))
