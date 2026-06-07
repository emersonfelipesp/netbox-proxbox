"""Sync service for dedicated Proxmox VM template inventory."""

from __future__ import annotations

import logging
import math
import re
import time
from dataclasses import dataclass, field
from typing import Any

import requests
from django.db import transaction
from django.utils import timezone

try:
    from netbox_proxbox.choices import SyncModeChoices
except ImportError:  # pragma: no cover - compatibility for focused import stubs

    class SyncModeChoices:  # type: ignore[no-redef]
        ALWAYS = "always"
        BOOTSTRAP_ONLY = "bootstrap_only"
        DISABLED = "disabled"


from netbox_proxbox.models import (
    ProxmoxCluster,
    ProxmoxEndpoint,
    ProxmoxNode,
    ProxmoxVMTemplate,
)
from netbox_proxbox.services.backend_proxy import get_fastapi_request_context
from netbox_proxbox.views.backend_sync import resolve_backend_endpoint_id
from netbox_proxbox.sync_stages import (
    _add_bootstrap_only_tag,
    _bootstrap_only_should_skip_existing,
    _has_bootstrap_only_tag,
)

logger = logging.getLogger(__name__)

SYNC_TIMEOUT = 30
_DISK_KEY_RE = re.compile(r"^(?:scsi|virtio|ide|sata|efidisk|tpmstate|mp)\d+$|^rootfs$")


@dataclass
class VMTemplateSyncResult:
    """Counters and outcome for a Proxmox VM template sync run."""

    success: bool = False
    error: str | None = None
    endpoint_id: int | None = None
    endpoint_name: str = ""
    endpoints_processed: int = 0
    templates_created: int = 0
    templates_updated: int = 0
    templates_skipped: int = 0
    templates_deleted: int = 0
    per_endpoint: list[dict[str, object]] = field(default_factory=list)


def _endpoint_sync_mode(endpoint: ProxmoxEndpoint) -> str:
    try:
        return endpoint.effective_sync_mode("vm_template")
    except (AttributeError, ValueError):
        return SyncModeChoices.ALWAYS


def _coerce_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _bytes_to_mib(value: object) -> int | None:
    raw = _coerce_int(value)
    if raw is None:
        return None
    return int(math.ceil(raw / (1024**2))) if raw > 0 else 0


def _bytes_to_gib(value: object) -> int | None:
    raw = _coerce_int(value)
    if raw is None:
        return None
    return int(math.ceil(raw / (1024**3))) if raw > 0 else 0


def _coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _iter_cluster_resource_rows(
    payload: object,
) -> list[tuple[str | None, dict[str, Any]]]:
    """Return ``(cluster_name, resource)`` rows from proxbox-api cluster resources."""
    rows: list[tuple[str | None, dict[str, Any]]] = []
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                if len(item) == 1 and all(isinstance(v, list) for v in item.values()):
                    for cluster_name, resources in item.items():
                        for resource in resources:
                            if isinstance(resource, dict):
                                rows.append((str(cluster_name), resource))
                else:
                    rows.append((None, item))
    elif isinstance(payload, dict):
        for cluster_name, resources in payload.items():
            if isinstance(resources, list):
                for resource in resources:
                    if isinstance(resource, dict):
                        rows.append((str(cluster_name), resource))
    return rows


def _template_name(resource: dict[str, Any], config: dict[str, Any]) -> str:
    return str(
        resource.get("name")
        or config.get("name")
        or config.get("hostname")
        or f"template-{resource.get('vmid')}"
    )


def _template_type(resource: dict[str, Any]) -> str:
    proxmox_type = str(resource.get("type") or "qemu").strip().lower()
    return proxmox_type if proxmox_type in {"qemu", "lxc"} else "qemu"


def _network_config(config: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in config.items() if str(key).startswith("net")}


def _disk_config(config: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in config.items() if _DISK_KEY_RE.match(str(key))}


def _cloud_init_enabled(config: dict[str, Any]) -> bool:
    cloud_init_keys = {"ciuser", "cipassword", "sshkeys", "ipconfig0", "citype"}
    if any(key in config for key in cloud_init_keys):
        return True
    return any("cloudinit" in str(value).lower() for value in config.values())


def _resolve_cluster(
    endpoint: ProxmoxEndpoint, cluster_name: str | None
) -> ProxmoxCluster | None:
    queryset = ProxmoxCluster.objects.filter(endpoint=endpoint)
    if cluster_name:
        cluster = queryset.filter(name=cluster_name).first()
        if cluster is not None:
            return cluster
    return queryset.first()


def _resolve_node(endpoint: ProxmoxEndpoint, node_name: str) -> ProxmoxNode | None:
    if not node_name:
        return None
    return ProxmoxNode.objects.filter(endpoint=endpoint, name=node_name).first()


def _fetch_template_config(
    *,
    fastapi_url: str,
    auth_headers: dict[str, str],
    verify_ssl: bool,
    backend_endpoint_id: int,
    node_name: str,
    proxmox_type: str,
    vmid: int,
) -> dict[str, Any]:
    if not node_name:
        return {}
    try:
        response = requests.get(
            f"{fastapi_url}/proxmox/{node_name}/{proxmox_type}/{vmid}/config",
            params={
                "source": "database",
                "proxmox_endpoint_ids": str(backend_endpoint_id),
            },
            headers=auth_headers,
            verify=verify_ssl,
            timeout=SYNC_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        logger.debug(
            "Could not fetch Proxmox template config for backend endpoint=%s vmid=%s: %s",
            backend_endpoint_id,
            vmid,
            exc,
        )
        return {}
    return payload if isinstance(payload, dict) else {}


def _template_defaults(
    *,
    endpoint: ProxmoxEndpoint,
    cluster_name: str | None,
    resource: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any] | None:
    vmid = _coerce_int(resource.get("vmid"))
    if vmid is None:
        return None

    node_name = str(resource.get("node") or config.get("node") or "")
    proxmox_type = _template_type(resource)
    raw_config = config or resource
    return {
        "name": _template_name(resource, config),
        "vmid": vmid,
        "cluster": _resolve_cluster(endpoint, cluster_name),
        "node": _resolve_node(endpoint, node_name),
        "node_name": node_name,
        "status": str(resource.get("status") or config.get("status") or ""),
        "vcpus": _coerce_int(
            resource.get("maxcpu") or config.get("cores") or config.get("cpulimit")
        ),
        "memory": _bytes_to_mib(resource.get("maxmem"))
        or _coerce_int(config.get("memory")),
        "disk": _bytes_to_gib(resource.get("maxdisk")),
        "proxmox_type": proxmox_type,
        "os_type": str(config.get("ostype") or config.get("ostemplate") or ""),
        "description": str(
            config.get("description") or resource.get("description") or ""
        ),
        "cloud_init_enabled": _cloud_init_enabled(config),
        "net_config": _network_config(config),
        "disk_config": _disk_config(config),
        "raw_config": raw_config,
        "last_synced": timezone.now(),
    }


def _upsert_template(
    *,
    endpoint: ProxmoxEndpoint,
    defaults: dict[str, Any],
    mode: str,
    result: VMTemplateSyncResult,
) -> ProxmoxVMTemplate | None:
    vmid = int(defaults["vmid"])
    template = ProxmoxVMTemplate.objects.filter(
        proxmox_endpoint=endpoint,
        vmid=vmid,
    ).first()
    if template and _bootstrap_only_should_skip_existing(template, mode):
        result.templates_skipped += 1
        return template

    update_fields = dict(defaults)
    update_fields.pop("vmid", None)
    if template is None:
        template = ProxmoxVMTemplate.objects.create(
            proxmox_endpoint=endpoint,
            vmid=vmid,
            **update_fields,
        )
        if mode == SyncModeChoices.BOOTSTRAP_ONLY:
            _add_bootstrap_only_tag(template)
        result.templates_created += 1
        return template

    for field_name, value in update_fields.items():
        setattr(template, field_name, value)
    template.save(update_fields=list(update_fields))
    result.templates_updated += 1
    return template


def sync_vm_templates(
    endpoint_id: int,
    fastapi_url: str | None = None,
    auth_headers: dict[str, str] | None = None,
) -> VMTemplateSyncResult:
    """Sync Proxmox template VMs for one Proxmox endpoint."""
    result = VMTemplateSyncResult(endpoint_id=endpoint_id)
    try:
        endpoint = ProxmoxEndpoint.objects.get(pk=endpoint_id)
    except ProxmoxEndpoint.DoesNotExist:
        result.error = "Endpoint not found"
        logger.error("ProxmoxEndpoint %s not found", endpoint_id)
        return result

    result.endpoint_name = str(endpoint)
    mode = _endpoint_sync_mode(endpoint)
    if mode == SyncModeChoices.DISABLED:
        result.success = True
        result.endpoints_processed = 1
        result.per_endpoint.append(
            {
                "endpoint_id": endpoint_id,
                "endpoint_name": result.endpoint_name,
                "success": True,
                "runtime_seconds": 0.0,
                "skipped": True,
                "reason": "sync_mode_vm_template=disabled",
            }
        )
        logger.info("Skipping VM template sync for endpoint %s: disabled", endpoint_id)
        return result

    verify_ssl = True
    if not fastapi_url:
        ctx = get_fastapi_request_context()
        if ctx is None or not ctx.http_url:
            result.error = "FastAPI URL not configured"
            logger.error(result.error)
            return result
        fastapi_url = ctx.http_url
        verify_ssl = bool(ctx.verify_ssl)
        if auth_headers is None:
            auth_headers = ctx.headers or {}

    if auth_headers is None:
        auth_headers = {}

    backend_endpoint_id, resolve_error = resolve_backend_endpoint_id(
        endpoint,
        base_url=fastapi_url,
        auth_headers=auth_headers,
        backend_verify_ssl=verify_ssl,
    )
    if backend_endpoint_id is None:
        result.error = resolve_error or "Could not resolve backend Proxmox endpoint id"
        logger.error(
            "Could not resolve backend endpoint id for endpoint %s: %s",
            endpoint_id,
            resolve_error,
        )
        return result

    started = time.monotonic()
    try:
        response = requests.get(
            f"{fastapi_url}/proxmox/cluster/resources",
            params={
                "type": "vm",
                "source": "database",
                "proxmox_endpoint_ids": str(backend_endpoint_id),
            },
            headers=auth_headers,
            verify=verify_ssl,
            timeout=SYNC_TIMEOUT,
        )
        response.raise_for_status()
        resources_payload = response.json()
    except requests.RequestException as exc:
        result.error = f"HTTP error fetching Proxmox VM templates: {exc}"
        logger.error(result.error)
        return result

    template_rows: list[tuple[str | None, dict[str, Any], dict[str, Any]]] = []
    for cluster_name, resource in _iter_cluster_resource_rows(resources_payload):
        if not _coerce_bool(resource.get("template")):
            continue
        proxmox_type = _template_type(resource)
        if proxmox_type not in {"qemu", "lxc"}:
            continue
        vmid = _coerce_int(resource.get("vmid"))
        if vmid is None:
            continue

        node_name = str(resource.get("node") or "")
        config = _fetch_template_config(
            fastapi_url=fastapi_url,
            auth_headers=auth_headers,
            verify_ssl=verify_ssl,
            backend_endpoint_id=backend_endpoint_id,
            node_name=node_name,
            proxmox_type=proxmox_type,
            vmid=vmid,
        )
        template_rows.append((cluster_name, resource, config))

    processed = 0
    with transaction.atomic():
        existing_keys = set(
            ProxmoxVMTemplate.objects.filter(proxmox_endpoint=endpoint).values_list(
                "vmid", "proxmox_type"
            )
        )
        synced_keys: set[tuple[int, str]] = set()

        for cluster_name, resource, config in template_rows:
            defaults = _template_defaults(
                endpoint=endpoint,
                cluster_name=cluster_name,
                resource=resource,
                config=config,
            )
            if defaults is None:
                continue
            template = _upsert_template(
                endpoint=endpoint,
                defaults=defaults,
                mode=mode,
                result=result,
            )
            if template is not None:
                synced_keys.add((int(defaults["vmid"]), str(defaults["proxmox_type"])))
                processed += 1

        stale_keys = existing_keys - synced_keys
        if stale_keys:
            stale_ids = [
                template.pk
                for template in ProxmoxVMTemplate.objects.filter(
                    proxmox_endpoint=endpoint
                )
                if (template.vmid, template.proxmox_type) in stale_keys
                and not _has_bootstrap_only_tag(template)
            ]
            if stale_ids:
                deleted_count, _ = ProxmoxVMTemplate.objects.filter(
                    pk__in=stale_ids
                ).delete()
                result.templates_deleted += deleted_count

    runtime_seconds = round(time.monotonic() - started, 3)
    result.success = True
    result.endpoints_processed = 1
    result.per_endpoint.append(
        {
            "endpoint_id": endpoint_id,
            "endpoint_name": result.endpoint_name,
            "success": True,
            "runtime_seconds": runtime_seconds,
            "templates_deleted": result.templates_deleted,
        }
    )
    logger.info(
        "VM template sync for endpoint %s complete: processed=%s created=%s updated=%s skipped=%s deleted=%s",
        endpoint_id,
        processed,
        result.templates_created,
        result.templates_updated,
        result.templates_skipped,
        result.templates_deleted,
    )
    return result
