"""VM detail tab to show live Proxmox HA status via proxbox-api."""

from __future__ import annotations

import requests
from django.http import HttpRequest
from netbox.views import generic
from utilities.views import ViewTab, register_model_view
from virtualization.models import VirtualMachine

from netbox_proxbox.services._endpoint_errors import translate_request_exception
from netbox_proxbox.services.backend_context import get_fastapi_request_context


def _extract_vmid(vm: VirtualMachine) -> int | None:
    cf = getattr(vm, "custom_field_data", {}) or {}
    raw = cf.get("proxmox_vm_id") or cf.get("cf_proxmox_vm_id")
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


@register_model_view(VirtualMachine, "proxmox_ha", path="proxmox-ha")
class ProxmoxVMHATabView(generic.ObjectView):
    """Live Proxmox High-Availability tab for VM details."""

    queryset = VirtualMachine.objects.all()
    template_name = "netbox_proxbox/vm_proxmox_ha.html"
    tab = ViewTab(
        label="HA",
        permission="virtualization.view_virtualmachine",
        weight=1400,
    )

    def get_queryset(self, request: HttpRequest) -> object:
        return VirtualMachine.objects.restrict(request.user, "view")

    def get_extra_context(
        self, request: HttpRequest, instance: VirtualMachine
    ) -> dict[str, object]:
        vmid = _extract_vmid(instance)
        context: dict[str, object] = {
            "vmid": vmid,
            "ha": None,
            "detail": None,
        }

        if vmid is None:
            context["detail"] = (
                "Missing custom field proxmox_vm_id on this virtual machine."
            )
            return context

        ctx = get_fastapi_request_context()
        if ctx is None or not ctx.http_url:
            context["detail"] = "No FastAPI backend endpoint is configured."
            return context

        url = f"{ctx.http_url}/proxmox/cluster/ha/resources/by-vm/{vmid}"
        try:
            response = requests.get(
                url,
                headers=ctx.headers or {},
                timeout=10,
                verify=ctx.verify_ssl,
            )
            if response.status_code == 404:
                context["detail"] = (
                    "Backend does not support HA endpoints — "
                    "upgrade proxbox-api to v0.0.11 or later."
                )
                return context
            response.raise_for_status()
            payload = response.json()
            context["ha"] = payload if isinstance(payload, dict) else None
        except requests.exceptions.RequestException as exc:
            context["detail"] = translate_request_exception(exc)
        except ValueError as exc:
            context["detail"] = f"Invalid HA payload from backend: {exc}"

        return context
