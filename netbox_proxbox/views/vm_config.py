"""VM detail tab to show live Proxmox config (QEMU/LXC) via proxbox-api."""

from __future__ import annotations

import json
import re

import requests
from django.http import HttpRequest
from netbox.views import generic
from pydantic import ValidationError
from utilities.views import ViewTab, register_model_view
from virtualization.models import VirtualMachine

from netbox_proxbox.models import FastAPIEndpoint, ProxmoxEndpoint, VMSnapshot
from netbox_proxbox.schemas.proxmox_vm import ProxmoxVMConfig
from netbox_proxbox.utils import get_backend_auth_headers, get_fastapi_url
from netbox_proxbox.views.backend_sync import sync_proxmox_endpoint_to_backend
from netbox_proxbox.views.error_utils import (
    extract_proxmox_backend_error_detail,
    parse_requests_response_json,
)


def _extract_vmid(vm: VirtualMachine) -> int | None:
    cf = getattr(vm, "custom_field_data", {}) or {}
    raw = cf.get("proxmox_vm_id") or cf.get("cf_proxmox_vm_id")
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _extract_vm_type(vm: VirtualMachine) -> str:
    cf = getattr(vm, "custom_field_data", {}) or {}
    vm_type = str(cf.get("proxmox_vm_type") or "qemu").strip().lower()
    return vm_type if vm_type in {"qemu", "lxc"} else "qemu"


def _extract_node(vm: VirtualMachine, vmid: int | None) -> str | None:
    cf = getattr(vm, "custom_field_data", {}) or {}
    node = (cf.get("proxmox_node") or cf.get("node") or "").strip()
    if node:
        return node

    desc = getattr(vm, "description", "") or ""
    match = re.search(r"Synced from Proxmox node\s+([a-zA-Z0-9._-]+)", desc)
    if match:
        return match.group(1)

    if vmid is not None:
        snap_node = (
            VMSnapshot.objects.filter(virtual_machine=vm, vmid=vmid)
            .order_by("-last_updated")
            .values_list("node", flat=True)
            .first()
        )
        if snap_node:
            return str(snap_node)
    return None


def _pick_proxmox_endpoint(
    request: HttpRequest, vm: VirtualMachine
) -> ProxmoxEndpoint | None:
    proxmox_qs = ProxmoxEndpoint.objects.restrict(request.user, "view")
    cluster_name = getattr(getattr(vm, "cluster", None), "name", None)
    if cluster_name:
        matched = proxmox_qs.filter(name=cluster_name).first()
        if matched:
            return matched
    return proxmox_qs.first()


@register_model_view(VirtualMachine, "proxmox_config", path="proxmox-config")
class ProxmoxVMConfigTabView(generic.ObjectView):
    """Live Proxmox config tab for VM details (supports QEMU and LXC)."""

    queryset = VirtualMachine.objects.all()
    template_name = "netbox_proxbox/vm_proxmox_config.html"
    tab = ViewTab(
        label="Proxmox Config",
        permission="virtualization.view_virtualmachine",
        weight=1200,
    )

    def get_queryset(self, request: HttpRequest) -> object:
        """Return queryset."""
        return VirtualMachine.objects.restrict(request.user, "view")

    def get_extra_context(
        self, request: HttpRequest, instance: VirtualMachine
    ) -> dict[str, object]:
        """Return extra context."""
        vmid = _extract_vmid(instance)
        vm_type = _extract_vm_type(instance)
        node = _extract_node(instance, vmid)

        context: dict[str, object] = {
            "vmid": vmid,
            "vm_type": vm_type,
            "node": node,
            "config_payload": None,
            "firewall_payload": None,
            "config_sections": {"disks": [], "networks": [], "advanced": []},
            "normalized": {},
            "detail": None,
        }

        if vmid is None:
            context["detail"] = (
                "Missing custom field proxmox_vm_id on this virtual machine."
            )
            return context
        if not node:
            context["detail"] = (
                "Unable to determine Proxmox node for this VM. "
                "Sync snapshots once or add custom field proxmox_node."
            )
            return context

        fastapi_obj = FastAPIEndpoint.objects.restrict(request.user, "view").first()
        proxmox_obj = _pick_proxmox_endpoint(request, instance)
        if fastapi_obj is None:
            context["detail"] = "No FastAPI endpoint is visible."
            return context
        if proxmox_obj is None:
            context["detail"] = "No Proxmox endpoint is visible."
            return context

        fastapi_info = get_fastapi_url(fastapi_obj) or {}
        fastapi_url = fastapi_info.get("http_url")
        if not fastapi_url:
            context["detail"] = "No FastAPI backend URL is configured."
            return context

        verify_ssl = bool(fastapi_info.get("verify_ssl", True))
        headers = get_backend_auth_headers(fastapi_obj)
        sync_ok, sync_detail, _ = sync_proxmox_endpoint_to_backend(
            proxmox_obj,
            base_url=fastapi_url,
            auth_headers=headers,
            backend_verify_ssl=verify_ssl,
            timeout=8,
        )
        if not sync_ok:
            context["detail"] = sync_detail
            return context

        query_params: dict[str, str] = {"source": "database"}
        if proxmox_obj.name:
            query_params["name"] = proxmox_obj.name

        config_url = f"{fastapi_url}/proxmox/{node}/{vm_type}/{vmid}/config"
        try:
            config_response = requests.get(
                config_url,
                params=query_params,
                headers=headers,
                verify=verify_ssl,
                timeout=8,
            )
            config_response.raise_for_status()
            parsed, parse_error = parse_requests_response_json(
                config_response, log_label="proxmox/vm-config"
            )
            if parse_error:
                context["detail"] = parse_error
                return context

            if not isinstance(parsed, dict):
                context["detail"] = "Unexpected VM config payload type."
                return context

            try:
                validated = ProxmoxVMConfig.model_validate(parsed)
                normalized = validated.to_normalized_context(
                    vm_name=instance.name or ""
                )
            except ValidationError as exc:
                context["detail"] = f"Config validation failed: {exc}"
                return context

            disks, networks, advanced = validated.flatten_sections(parsed)
            context["config_payload"] = parsed
            context["config_sections"] = {
                "disks": disks,
                "networks": networks,
                "advanced": advanced,
            }
            context["normalized"] = normalized

            if vm_type == "qemu":
                firewall_url = (
                    f"{fastapi_url}/proxmox/nodes/{node}/qemu/{vmid}/firewall"
                )
                try:
                    fw_response = requests.get(
                        firewall_url,
                        params=query_params,
                        headers=headers,
                        verify=verify_ssl,
                        timeout=8,
                    )
                    if fw_response.status_code < 400:
                        fw_parsed, fw_err = parse_requests_response_json(
                            fw_response, log_label="proxmox/qemu-firewall"
                        )
                        if not fw_err:
                            context["firewall_payload"] = fw_parsed
                except requests.exceptions.RequestException:
                    pass
        except requests.exceptions.RequestException as exc:
            detail, _ = extract_proxmox_backend_error_detail(
                exc,
                proxmox_host=proxmox_obj.domain
                or str(proxmox_obj.ip_address).split("/")[0],
                proxmox_port=proxmox_obj.port,
                backend_url=config_url,
            )
            context["detail"] = detail

        context["config_payload_json"] = (
            json.dumps(context["config_payload"], indent=2, sort_keys=True)
            if context["config_payload"]
            else "{}"
        )
        context["firewall_payload_json"] = (
            json.dumps(context["firewall_payload"], indent=2, sort_keys=True)
            if context["firewall_payload"] is not None
            else ""
        )
        return context
