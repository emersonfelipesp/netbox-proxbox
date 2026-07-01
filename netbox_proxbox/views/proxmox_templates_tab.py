"""Templates tab for the Proxmox endpoint detail page.

Lists the templates that live on a single Proxmox endpoint, grouped into three
categories the UI can filter by:

* **Cloud-Init** — QEMU/KVM templates with a cloud-init drive or ``cicustom``.
* **Plain QEMU/KVM** — QEMU templates with neither (no cloud-init).
* **LXC** — CT (``vztmpl``) template images on the endpoint's storages.

Data is fetched live from ``proxbox-api`` (the same integration boundary used by
the rest of the plugin: :func:`get_fastapi_request_context` for the URL/auth and
:func:`resolve_backend_endpoint_id` to translate the NetBox endpoint pk to the
backend's own endpoint id). The view degrades gracefully — a missing/disabled
FastAPI backend, an unresolved endpoint, or a request failure renders an
informative message and empty lists instead of raising.

When the optional **netbox-packer** plugin is installed the tab offers a
"Create Cloud-Init template image" shortcut linking to its build page; when it is
absent the button is disabled with an explanatory tooltip.
"""

from __future__ import annotations

import logging
import posixpath
from typing import Any

import requests
from django.http import HttpRequest
from django.urls import reverse
from netbox.views import generic
from utilities.views import ViewTab, register_model_view

from netbox_proxbox.integrations.packer import (
    is_netbox_packer_installed,
    packer_template_add_url,
)
from netbox_proxbox.models import ProxmoxEndpoint
from netbox_proxbox.services.backend_context import get_fastapi_request_context
from netbox_proxbox.views.backend_sync import resolve_backend_endpoint_id

logger = logging.getLogger("netbox_proxbox.views.proxmox_templates_tab")

__all__ = ("ProxmoxEndpointTemplatesTabView",)

# Templates are usually a small handful, but each QEMU template costs one config
# read on the backend — keep a bounded timeout so a slow cluster cannot hang the
# page render indefinitely.
_TEMPLATES_FETCH_TIMEOUT = 30


def _coerce_int(value: object) -> int | None:
    """Best-effort int coercion; returns ``None`` for missing/invalid values."""
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _bytes_to_gib(value: object) -> float | None:
    """Convert a byte count to GiB rounded to one decimal, or ``None``."""
    num = _coerce_int(value)
    if num is None or num <= 0:
        return None
    return round(num / (1024**3), 1)


def _row_has_cloud_init(row: dict[str, Any]) -> bool:
    """Return ``True`` when a QEMU template row carries cloud-init.

    Derived from the real config (``cloud_init_drives`` non-empty **or**
    ``cicustom`` set) rather than the response's ``cloud_init`` flag, which the
    backend currently hard-codes to ``True`` on every row.
    """
    drives = row.get("cloud_init_drives")
    if isinstance(drives, (list, tuple)) and len(drives) > 0:
        return True
    cicustom = row.get("cicustom")
    return bool(cicustom and str(cicustom).strip())


def _normalize_qemu_template(row: dict[str, Any]) -> dict[str, Any]:
    """Shape a proxbox-api QEMU template row for the tab template."""
    vmid = _coerce_int(row.get("source_vmid")) or _coerce_int(row.get("vmid"))
    return {
        "vmid": vmid,
        "name": str(row.get("name") or (f"Template {vmid}" if vmid else "Template")),
        "node": str(row.get("target_node") or row.get("node") or ""),
        "status": row.get("status") or None,
        "memory_mb": _coerce_int(row.get("memory_mb")),
        "disk_gib": _bytes_to_gib(row.get("maxdisk_bytes")),
        "tags": row.get("tags") or None,
        "description": row.get("description") or None,
        "cloud_init": _row_has_cloud_init(row),
        "cloud_init_drives": ", ".join(row.get("cloud_init_drives") or []) or None,
        "cicustom": row.get("cicustom") or None,
    }


def _normalize_lxc_template(row: dict[str, Any]) -> dict[str, Any]:
    """Shape a proxbox-api LXC (vztmpl) template row for the tab template."""
    volid = str(row.get("volid") or "")
    # local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst -> debian-12-...tar.zst
    name = posixpath.basename(volid.split(":", 1)[-1]) if volid else volid
    return {
        "volid": volid,
        "name": name or volid,
        "storage": str(row.get("storage") or ""),
        "size_gib": _bytes_to_gib(row.get("size")),
    }


def _fetch_endpoint_templates(instance: ProxmoxEndpoint) -> dict[str, Any]:
    """Fetch and classify the endpoint's templates from proxbox-api.

    Returns a context fragment: ``cloudinit_templates`` / ``plain_templates`` /
    ``lxc_templates`` lists, their counts, a ``backend_available`` flag, and an
    optional ``backend_error`` message. Never raises.
    """
    result: dict[str, Any] = {
        "cloudinit_templates": [],
        "plain_templates": [],
        "lxc_templates": [],
        "backend_available": False,
        "backend_error": None,
    }

    ctx = get_fastapi_request_context()
    if ctx is None or not ctx.http_url:
        result["backend_error"] = (
            "No enabled ProxBox (FastAPI) backend is configured. Configure a "
            "FastAPI endpoint to list live templates for this Proxmox endpoint."
        )
        return result

    base_url = ctx.http_url.rstrip("/")
    headers = ctx.headers or {}
    verify_ssl = bool(ctx.verify_ssl)

    backend_endpoint_id, resolve_error = resolve_backend_endpoint_id(
        instance,
        base_url=base_url,
        auth_headers=headers,
        backend_verify_ssl=verify_ssl,
    )
    if backend_endpoint_id is None:
        result["backend_error"] = resolve_error or (
            "Could not resolve this endpoint on the ProxBox backend. Run an "
            "endpoint sync and try again."
        )
        return result

    try:
        qemu_response = requests.get(
            f"{base_url}/cloud/vm/templates",
            params={"endpoint_id": backend_endpoint_id, "cloud_init_only": "false"},
            headers=headers,
            verify=verify_ssl,
            timeout=_TEMPLATES_FETCH_TIMEOUT,
        )
        qemu_response.raise_for_status()
        qemu_payload = qemu_response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning(
            "Failed to fetch QEMU templates for endpoint %s: %s", instance.pk, exc
        )
        result["backend_error"] = f"Could not fetch QEMU templates: {exc}"
        return result

    qemu_rows = qemu_payload.get("results") if isinstance(qemu_payload, dict) else None
    for row in qemu_rows or []:
        if not isinstance(row, dict):
            continue
        normalized = _normalize_qemu_template(row)
        if normalized["cloud_init"]:
            result["cloudinit_templates"].append(normalized)
        else:
            result["plain_templates"].append(normalized)

    try:
        lxc_response = requests.get(
            f"{base_url}/cloud/lxc/templates",
            params={"endpoint_id": backend_endpoint_id},
            headers=headers,
            verify=verify_ssl,
            timeout=_TEMPLATES_FETCH_TIMEOUT,
        )
        lxc_response.raise_for_status()
        lxc_payload = lxc_response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning(
            "Failed to fetch LXC templates for endpoint %s: %s", instance.pk, exc
        )
        # QEMU data already fetched — surface a partial error but keep what we have.
        result["backend_available"] = True
        result["backend_error"] = f"Could not fetch LXC templates: {exc}"
        return result

    if isinstance(lxc_payload, list):
        for row in lxc_payload:
            if isinstance(row, dict) and row.get("volid"):
                result["lxc_templates"].append(_normalize_lxc_template(row))

    result["backend_available"] = True
    return result


@register_model_view(ProxmoxEndpoint, "templates", path="templates")
class ProxmoxEndpointTemplatesTabView(generic.ObjectView):
    """Tab listing Cloud-Init, plain QEMU/KVM, and LXC templates for an endpoint."""

    queryset = ProxmoxEndpoint.objects.all()
    template_name = "netbox_proxbox/proxmoxendpoint_templates.html"
    tab = ViewTab(
        label="Templates",
        permission="netbox_proxbox.view_proxmoxendpoint",
        weight=960,
    )

    def get_extra_context(
        self, request: HttpRequest, instance: ProxmoxEndpoint
    ) -> dict[str, object]:
        """Fetch live templates and resolve the netbox-packer create action."""
        context = _fetch_endpoint_templates(instance)
        context["total_count"] = (
            len(context["cloudinit_templates"])
            + len(context["plain_templates"])
            + len(context["lxc_templates"])
        )
        packer_installed = is_netbox_packer_installed()
        context["packer_installed"] = packer_installed
        context["packer_add_url"] = (
            packer_template_add_url() if packer_installed else None
        )
        context["allow_writes"] = bool(getattr(instance, "allow_writes", False))
        context["create_instance_url"] = reverse(
            "plugins:netbox_proxbox:proxmoxendpoint_create_instance",
            args=[instance.pk],
        )
        return context
