"""Create VM/LXC instances from live Proxmox endpoint templates.

The Templates tab posts here directly from NetBox to proxbox-api. The trust
boundary intentionally mirrors operational verbs: NetBox permission check,
NetBox-side ``allow_writes`` pre-check, proxbox-api write gate, then an
individual sync-back so the newly-created instance appears in NetBox.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import re
import uuid
from typing import ClassVar

import requests
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views import View
from utilities.views import (
    ContentTypePermissionRequiredMixin,
    TokenConditionalLoginRequiredMixin,
    register_model_view,
)
from virtualization.models import VirtualMachine

from netbox_proxbox.models import ProxmoxCluster, ProxmoxEndpoint, ProxmoxNode
from netbox_proxbox.services._endpoint_errors import translate_request_exception
from netbox_proxbox.services.backend_context import get_fastapi_request_context
from netbox_proxbox.services.individual_sync import sync_individual
from netbox_proxbox.views.backend_sync import resolve_backend_endpoint_id
from netbox_proxbox.views.proxbox_access import permission_run_proxmox_action

logger = logging.getLogger("netbox_proxbox.views.proxmox_create_instance")

__all__ = (
    "ProxmoxEndpointCreateInstanceView",
    "build_cloud_init_payload",
    "build_lxc_provision_payload",
    "build_provision_headers",
    "build_qemu_provision_payload",
    "endpoint_allows_instance_create",
    "is_vmid_collision_response",
    "validate_create_instance_payload",
)

_PROVISION_TIMEOUT_S = 90
_DATACENTER_OPTIONS_TIMEOUT_S = 10
_MAX_VMID_ATTEMPTS = 20
_MAX_REQUEST_BYTES = 16 * 1024
_DEFAULT_BASE_VMID = 100
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_HOSTNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]*$")
_NODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_STORAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]*$")
_SSH_KEY_PREFIXES = (
    "ssh-ed25519 ",
    "ssh-rsa ",
    "ecdsa-sha2-",
    "sk-ecdsa-sha2-",
    "sk-ssh-ed25519 ",
)
QEMU_PAYLOAD_KEYS = {
    "endpoint_id",
    "template_vmid",
    "new_vmid",
    "new_name",
    "target_node",
    "cloud_init",
    "start_after_provision",
    "storage",
    "memory_mb",
    "cores",
    "full_clone",
}
LXC_PAYLOAD_KEYS = {
    "endpoint_id",
    "hostname",
    "ostemplate",
    "target_node",
    "rootfs_storage",
    "rootfs_size_gb",
    "memory_mb",
    "cores",
    "password",
    "start_after_provision",
}


class CreateInstanceValidationError(ValueError):
    """Structured validation error translated to a JSON 400 response."""

    def __init__(self, reason: str, detail: str, *, status_code: int = 400) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail
        self.status_code = status_code


def endpoint_allows_instance_create(endpoint: object) -> bool:
    """Return whether this endpoint is locally allowed to perform writes."""
    return bool(getattr(endpoint, "allow_writes", False))


def build_provision_headers(
    base_headers: dict[str, str] | None, username: object
) -> dict[str, str]:
    """Build proxbox-api provision headers with actor and idempotency metadata."""
    actor = str(username or "").strip() or "netbox"
    headers = dict(base_headers or {})
    headers["X-Proxbox-Actor"] = actor
    headers["Idempotency-Key"] = str(uuid.uuid4())
    headers["Content-Type"] = "application/json"
    return headers


def build_cloud_init_payload(raw: object) -> dict[str, object]:
    """Validate and build the proxbox-api ``cloud_init`` object.

    All inner fields are optional. Empty input returns ``{}`` so QEMU
    provisioning can still send the required top-level object.
    """
    if raw in (None, ""):
        return {}
    if not isinstance(raw, dict):
        raise CreateInstanceValidationError(
            "invalid_cloud_init", "cloud_init must be an object."
        )

    _reject_unknown_keys(
        raw,
        {"user", "ssh_keys", "network", "search_domain", "dns_servers"},
        label="cloud_init",
    )
    payload: dict[str, object] = {}
    user = _optional_string(
        raw.get("user"),
        field="cloud_init.user",
        max_length=64,
        pattern=_NAME_RE,
    )
    if user:
        payload["user"] = user

    ssh_keys = _validate_ssh_keys(raw.get("ssh_keys"))
    if ssh_keys:
        payload["ssh_keys"] = ssh_keys

    network = _validate_cloud_init_network(raw.get("network"))
    if network:
        payload["network"] = network

    search_domain = _optional_string(
        raw.get("search_domain"),
        field="cloud_init.search_domain",
        max_length=255,
        pattern=_HOSTNAME_RE,
    )
    if search_domain:
        payload["search_domain"] = search_domain

    dns_servers = _validate_dns_servers(raw.get("dns_servers"))
    if dns_servers:
        payload["dns_servers"] = dns_servers
    return payload


def build_qemu_provision_payload(
    *,
    endpoint_id: int,
    template_vmid: int,
    new_vmid: int,
    new_name: str,
    target_node: str,
    cloud_init: dict[str, object] | None = None,
    start_after_provision: bool = True,
    storage: str | None = None,
    memory_mb: int | None = None,
    cores: int | None = None,
    full_clone: bool = False,
) -> dict[str, object]:
    """Build the exact proxbox-api QEMU provision body."""
    payload: dict[str, object] = {
        "endpoint_id": int(endpoint_id),
        "template_vmid": int(template_vmid),
        "new_vmid": int(new_vmid),
        "new_name": new_name,
        "target_node": target_node,
        "cloud_init": cloud_init or {},
        "start_after_provision": bool(start_after_provision),
        "storage": storage,
        "memory_mb": memory_mb,
        "cores": cores,
        "full_clone": bool(full_clone),
    }
    return {key: payload[key] for key in QEMU_PAYLOAD_KEYS}


def build_lxc_provision_payload(
    *,
    endpoint_id: int,
    hostname: str,
    ostemplate: str,
    target_node: str,
    rootfs_storage: str = "local-lvm",
    rootfs_size_gb: int = 8,
    memory_mb: int | None = None,
    cores: int | None = None,
    password: str | None = None,
    start_after_provision: bool = True,
) -> dict[str, object]:
    """Build the exact proxbox-api LXC provision body."""
    payload: dict[str, object] = {
        "endpoint_id": int(endpoint_id),
        "hostname": hostname,
        "ostemplate": ostemplate,
        "target_node": target_node,
        "rootfs_storage": rootfs_storage,
        "rootfs_size_gb": int(rootfs_size_gb),
        "memory_mb": memory_mb,
        "cores": cores,
        "password": password,
        "start_after_provision": bool(start_after_provision),
    }
    return {key: payload[key] for key in LXC_PAYLOAD_KEYS}


def validate_create_instance_payload(data: object) -> tuple[str, dict[str, object]]:
    """Validate the browser JSON and return ``(kind, normalized)``."""
    if not isinstance(data, dict):
        raise CreateInstanceValidationError(
            "invalid_payload", "Request body must be a JSON object."
        )

    kind = _required_string(
        data.get("kind"), field="kind", max_length=16, pattern=None
    ).lower()
    if kind == "qemu":
        return kind, _validate_qemu_payload(data)
    if kind == "lxc":
        return kind, _validate_lxc_payload(data)
    raise CreateInstanceValidationError(
        "invalid_kind", 'kind must be either "qemu" or "lxc".'
    )


def is_vmid_collision_response(response: object) -> bool:
    """Return whether a proxbox-api response looks like a VMID collision."""
    status_code = int(getattr(response, "status_code", 0) or 0)
    if status_code not in {400, 409, 500, 502}:
        return False
    payload = _response_json(response)
    pieces = [
        str(payload.get("reason") or ""),
        str(payload.get("detail") or ""),
        str(payload.get("error") or ""),
        str(getattr(response, "text", "") or ""),
    ]
    body_text = " ".join(pieces).lower()
    return (
        "config file already exists" in body_text
        or ("unable to create vm" in body_text and "already exists" in body_text)
        or ("vmid" in body_text and "already exists" in body_text)
        or ("vmid" in body_text and "already in use" in body_text)
    )


@register_model_view(ProxmoxEndpoint, "create_instance", path="create-instance")
class ProxmoxEndpointCreateInstanceView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """POST: create a QEMU VM or LXC container from a selected endpoint template."""

    http_method_names: ClassVar[list[str]] = ["post"]

    def get_required_permission(self) -> str:
        """Return the Proxmox action permission codename."""
        return permission_run_proxmox_action()

    def post(self, request: HttpRequest, pk: int | str) -> JsonResponse:
        """Validate input, call proxbox-api, and sync the new instance into NetBox."""
        endpoint = get_object_or_404(
            ProxmoxEndpoint.objects.restrict(request.user, "view"),
            pk=pk,
        )
        if not endpoint_allows_instance_create(endpoint):
            return _json_error(
                "writes_disabled_for_endpoint",
                "Enable write access on this endpoint to create instances.",
                status=403,
            )

        try:
            kind, normalized = validate_create_instance_payload(_request_json(request))
        except CreateInstanceValidationError as exc:
            return _json_error(exc.reason, exc.detail, status=exc.status_code)

        ctx = get_fastapi_request_context()
        if ctx is None or not ctx.http_url:
            return _json_error(
                "fastapi_endpoint_required",
                "No enabled ProxBox (FastAPI) backend is configured.",
                status=503,
            )

        base_url = ctx.http_url.rstrip("/")
        base_headers = dict(ctx.headers or {})
        verify_ssl = bool(ctx.verify_ssl)
        backend_endpoint_id, resolve_error = resolve_backend_endpoint_id(
            endpoint,
            base_url=base_url,
            auth_headers=base_headers,
            backend_verify_ssl=verify_ssl,
        )
        if backend_endpoint_id is None:
            return _json_error(
                "backend_endpoint_unresolved",
                resolve_error
                or "Could not resolve this endpoint on the ProxBox backend.",
                status=502,
            )

        headers = build_provision_headers(
            base_headers, getattr(getattr(request, "user", None), "username", "")
        )
        if kind == "qemu":
            return _provision_qemu(
                request,
                endpoint=endpoint,
                normalized=normalized,
                backend_endpoint_id=backend_endpoint_id,
                base_url=base_url,
                headers=headers,
                verify_ssl=verify_ssl,
            )
        return _provision_lxc(
            request,
            endpoint=endpoint,
            normalized=normalized,
            backend_endpoint_id=backend_endpoint_id,
            base_url=base_url,
            headers=headers,
            verify_ssl=verify_ssl,
        )


def _provision_qemu(
    request: HttpRequest,
    *,
    endpoint: ProxmoxEndpoint,
    normalized: dict[str, object],
    backend_endpoint_id: int,
    base_url: str,
    headers: dict[str, str],
    verify_ssl: bool,
) -> JsonResponse:
    cluster_name = _resolve_cluster_name(endpoint, str(normalized["target_node"]))
    base_vmid = _fetch_next_vmid_base(
        base_url=base_url,
        headers=headers,
        verify_ssl=verify_ssl,
        cluster_name=cluster_name,
    )
    payload = build_qemu_provision_payload(
        endpoint_id=backend_endpoint_id,
        template_vmid=int(normalized["template_vmid"]),
        new_vmid=base_vmid,
        new_name=str(normalized["new_name"]),
        target_node=str(normalized["target_node"]),
        cloud_init=normalized.get("cloud_init")
        if isinstance(normalized.get("cloud_init"), dict)
        else {},
        start_after_provision=bool(normalized["start_after_provision"]),
        storage=normalized.get("storage")
        if isinstance(normalized.get("storage"), str)
        else None,
        memory_mb=normalized.get("memory_mb")
        if isinstance(normalized.get("memory_mb"), int)
        else None,
        cores=normalized.get("cores")
        if isinstance(normalized.get("cores"), int)
        else None,
        full_clone=bool(normalized["full_clone"]),
    )

    try:
        response, chosen_vmid = _post_qemu_with_vmid_retry(
            url=f"{base_url}/cloud/vm/provision",
            payload=payload,
            headers=headers,
            verify_ssl=verify_ssl,
            timeout=_PROVISION_TIMEOUT_S,
            base_vmid=base_vmid,
            max_attempts=_MAX_VMID_ATTEMPTS,
        )
    except requests.exceptions.Timeout:
        return _timeout_response(new_vmid=int(payload["new_vmid"]))
    except VmidReservationError as exc:
        return _json_error(exc.reason, exc.detail, status=exc.status_code)
    except requests.exceptions.RequestException as exc:
        return _json_error(
            "backend_request_failed",
            translate_request_exception(exc),
            status=502,
        )

    backend_error = _backend_error_response(response)
    if backend_error is not None:
        return backend_error

    body = _response_json(response)
    new_vmid = _positive_int(body.get("new_vmid")) or chosen_vmid
    return _success_response_after_sync(
        request,
        endpoint=endpoint,
        cluster_name=cluster_name,
        target_node=str(normalized["target_node"]),
        vm_type="qemu",
        new_vmid=new_vmid,
        body=body,
    )


def _provision_lxc(
    request: HttpRequest,
    *,
    endpoint: ProxmoxEndpoint,
    normalized: dict[str, object],
    backend_endpoint_id: int,
    base_url: str,
    headers: dict[str, str],
    verify_ssl: bool,
) -> JsonResponse:
    payload = build_lxc_provision_payload(
        endpoint_id=backend_endpoint_id,
        hostname=str(normalized["hostname"]),
        ostemplate=str(normalized["ostemplate"]),
        target_node=str(normalized["target_node"]),
        rootfs_storage=str(normalized["rootfs_storage"]),
        rootfs_size_gb=int(normalized["rootfs_size_gb"]),
        memory_mb=normalized.get("memory_mb")
        if isinstance(normalized.get("memory_mb"), int)
        else None,
        cores=normalized.get("cores")
        if isinstance(normalized.get("cores"), int)
        else None,
        password=normalized.get("password")
        if isinstance(normalized.get("password"), str)
        else None,
        start_after_provision=bool(normalized["start_after_provision"]),
    )

    try:
        response = requests.post(
            f"{base_url}/cloud/lxc/provision",
            json=payload,
            headers=headers,
            verify=verify_ssl,
            timeout=_PROVISION_TIMEOUT_S,
        )
    except requests.exceptions.Timeout:
        return _timeout_response()
    except requests.exceptions.RequestException as exc:
        return _json_error(
            "backend_request_failed",
            translate_request_exception(exc),
            status=502,
        )

    backend_error = _backend_error_response(response)
    if backend_error is not None:
        return backend_error

    body = _response_json(response)
    new_vmid = _positive_int(body.get("new_vmid"))
    if new_vmid is None:
        return _json_error(
            "invalid_backend_response",
            "ProxBox backend did not return a new_vmid for the created container.",
            status=502,
        )
    cluster_name = _resolve_cluster_name(endpoint, str(normalized["target_node"]))
    return _success_response_after_sync(
        request,
        endpoint=endpoint,
        cluster_name=cluster_name,
        target_node=str(normalized["target_node"]),
        vm_type="lxc",
        new_vmid=new_vmid,
        body=body,
    )


class VmidReservationError(RuntimeError):
    """Raised when all QEMU VMID retry attempts collide."""

    def __init__(self, reason: str, detail: str, *, status_code: int = 409) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail
        self.status_code = status_code


def _post_qemu_with_vmid_retry(
    *,
    url: str,
    payload: dict[str, object],
    headers: dict[str, str],
    verify_ssl: bool,
    timeout: int,
    base_vmid: int,
    max_attempts: int,
) -> tuple[object, int]:
    """POST QEMU provision, incrementing VMID only for collision responses."""
    last_vmid = base_vmid
    for attempt in range(max_attempts):
        candidate_vmid = base_vmid + attempt
        last_vmid = candidate_vmid
        payload["new_vmid"] = candidate_vmid
        attempt_headers = dict(headers)
        attempt_headers["Idempotency-Key"] = str(uuid.uuid4())
        response = requests.post(
            url,
            json=payload,
            headers=attempt_headers,
            verify=verify_ssl,
            timeout=timeout,
        )
        if is_vmid_collision_response(response):
            continue
        return response, candidate_vmid
    raise VmidReservationError(
        "vmid_reservation_exhausted",
        (
            "Could not reserve a free VMID after "
            f"{max_attempts} attempts starting at {base_vmid}; last tried {last_vmid}."
        ),
    )


def _success_response_after_sync(
    request: HttpRequest,
    *,
    endpoint: ProxmoxEndpoint,
    cluster_name: str,
    target_node: str,
    vm_type: str,
    new_vmid: int,
    body: dict[str, object],
) -> JsonResponse:
    detail = body.get("detail")
    detail_text = str(detail) if detail not in (None, "") else ""
    sync_note = _sync_created_instance(
        endpoint=endpoint,
        request=request,
        cluster_name=cluster_name,
        target_node=target_node,
        vm_type=vm_type,
        new_vmid=new_vmid,
    )
    netbox_url = _find_created_vm_url(request, new_vmid)
    if sync_note:
        detail_text = f"{detail_text} {sync_note}".strip()
    elif not netbox_url:
        detail_text = (
            f"{detail_text} Created instance has not appeared in NetBox yet; "
            "it should appear after the next sync."
        ).strip()

    payload: dict[str, object] = {
        "success": True,
        "new_vmid": new_vmid,
        "status": str(body.get("status") or "created"),
    }
    if netbox_url:
        payload["netbox_url"] = netbox_url
    if detail_text:
        payload["detail"] = detail_text
    return JsonResponse(payload, status=200)


def _sync_created_instance(
    *,
    endpoint: ProxmoxEndpoint,
    request: HttpRequest,
    cluster_name: str,
    target_node: str,
    vm_type: str,
    new_vmid: int,
) -> str | None:
    if not cluster_name:
        return (
            "Created instance sync is pending because the endpoint is not linked "
            "to a Proxmox cluster in NetBox."
        )
    try:
        response, status = sync_individual(
            "sync/individual/vm",
            {
                "cluster_name": cluster_name,
                "node": target_node,
                "type": vm_type,
                "vmid": new_vmid,
            },
        )
    except Exception as exc:  # pragma: no cover - defensive around external sync
        logger.exception(
            "Single-object sync failed after provisioning endpoint %s VMID %s",
            getattr(endpoint, "pk", None),
            new_vmid,
        )
        return f"Created instance sync is pending: {exc}"

    if 200 <= int(status) < 300:
        return None
    detail = ""
    if isinstance(response, dict):
        detail = str(response.get("error") or response.get("detail") or "")
    return "Created instance sync is pending" + (
        f": {detail}" if detail else f" (sync returned HTTP {status})."
    )


def _find_created_vm_url(request: HttpRequest, new_vmid: int) -> str | None:
    qs = VirtualMachine.objects.restrict(request.user, "view")
    for lookup in (
        {"custom_field_data__proxmox_vm_id": new_vmid},
        {"custom_field_data__proxmox_vm_id": str(new_vmid)},
        {"custom_field_data__cf_proxmox_vm_id": new_vmid},
        {"custom_field_data__cf_proxmox_vm_id": str(new_vmid)},
    ):
        vm = qs.filter(**lookup).first()
        if vm is not None:
            return str(vm.get_absolute_url())
    return None


def _backend_error_response(response: object) -> JsonResponse | None:
    status_code = int(getattr(response, "status_code", 0) or 0)
    if 200 <= status_code < 300:
        return None
    body = _response_json(response)
    reason = body.get("reason") or "provision_failed"
    detail = (
        body.get("detail") or getattr(response, "text", "") or f"HTTP {status_code}"
    )
    payload: dict[str, object] = {
        "success": False,
        "reason": str(reason),
        "detail": str(detail),
    }
    if "endpoint_id" in body:
        payload["endpoint_id"] = body["endpoint_id"]
    return JsonResponse(payload, status=status_code or 502)


def _timeout_response(new_vmid: int | None = None) -> JsonResponse:
    detail = (
        "Provision request timed out after 90 seconds. The instance is likely "
        "still being created and will appear after the next sync."
    )
    payload: dict[str, object] = {
        "success": True,
        "status": "pending",
        "reason": "request_timeout",
        "detail": detail,
    }
    if new_vmid is not None:
        payload["new_vmid"] = new_vmid
    return JsonResponse(payload, status=202)


def _json_error(reason: str, detail: str, *, status: int) -> JsonResponse:
    return JsonResponse(
        {"success": False, "reason": reason, "detail": detail},
        status=status,
    )


def _request_json(request: HttpRequest) -> object:
    body = getattr(request, "body", b"") or b""
    if len(body) > _MAX_REQUEST_BYTES:
        raise CreateInstanceValidationError(
            "payload_too_large",
            "Create-instance request body is too large.",
            status_code=413,
        )
    if not body:
        return {}
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CreateInstanceValidationError(
            "invalid_json", "Request body must be valid JSON."
        ) from exc


def _validate_qemu_payload(data: dict[str, object]) -> dict[str, object]:
    _reject_unknown_keys(
        data,
        {
            "kind",
            "source",
            "template_vmid",
            "name",
            "new_name",
            "target_node",
            "cloud_init",
            "start_after_provision",
            "storage",
            "memory_mb",
            "cores",
            "full_clone",
        },
        label="payload",
    )
    template_vmid = _coerce_required_int(
        data.get("template_vmid", data.get("source")),
        field="source",
        min_value=100,
    )
    new_name = _required_string(
        data.get("new_name", data.get("name")),
        field="name",
        max_length=128,
        pattern=_NAME_RE,
    )
    target_node = _required_string(
        data.get("target_node"),
        field="target_node",
        max_length=128,
        pattern=_NODE_RE,
    )
    return {
        "template_vmid": template_vmid,
        "new_name": new_name,
        "target_node": target_node,
        "cloud_init": build_cloud_init_payload(data.get("cloud_init")),
        "start_after_provision": _coerce_bool(
            data.get("start_after_provision"), default=True
        ),
        "storage": _optional_string(
            data.get("storage"),
            field="storage",
            max_length=128,
            pattern=_STORAGE_RE,
        ),
        "memory_mb": _coerce_optional_int(
            data.get("memory_mb"), field="memory_mb", min_value=64
        ),
        "cores": _coerce_optional_int(data.get("cores"), field="cores", min_value=1),
        "full_clone": _coerce_bool(data.get("full_clone"), default=False),
    }


def _validate_lxc_payload(data: dict[str, object]) -> dict[str, object]:
    _reject_unknown_keys(
        data,
        {
            "kind",
            "source",
            "ostemplate",
            "hostname",
            "name",
            "target_node",
            "rootfs_storage",
            "rootfs_size_gb",
            "memory_mb",
            "cores",
            "password",
            "start_after_provision",
        },
        label="payload",
    )
    return {
        "hostname": _required_string(
            data.get("hostname", data.get("name")),
            field="hostname",
            max_length=63,
            pattern=_HOSTNAME_RE,
        ),
        "ostemplate": _required_string(
            data.get("ostemplate", data.get("source")),
            field="source",
            max_length=512,
            pattern=_STORAGE_RE,
        ),
        "target_node": _required_string(
            data.get("target_node"),
            field="target_node",
            max_length=128,
            pattern=_NODE_RE,
        ),
        "rootfs_storage": _optional_string(
            data.get("rootfs_storage"),
            field="rootfs_storage",
            max_length=128,
            pattern=_STORAGE_RE,
        )
        or "local-lvm",
        "rootfs_size_gb": _coerce_optional_int(
            data.get("rootfs_size_gb"),
            field="rootfs_size_gb",
            min_value=1,
            max_value=10000,
        )
        or 8,
        "memory_mb": _coerce_optional_int(
            data.get("memory_mb"), field="memory_mb", min_value=64
        ),
        "cores": _coerce_optional_int(data.get("cores"), field="cores", min_value=1),
        "password": _optional_string(
            data.get("password"), field="password", max_length=256, pattern=None
        ),
        "start_after_provision": _coerce_bool(
            data.get("start_after_provision"), default=True
        ),
    }


def _reject_unknown_keys(
    data: dict[str, object], allowed: set[str], *, label: str
) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise CreateInstanceValidationError(
            "unknown_fields",
            f"Unknown {label} field(s): {', '.join(unknown)}.",
        )


def _required_string(
    value: object,
    *,
    field: str,
    max_length: int,
    pattern: re.Pattern[str] | None,
) -> str:
    text = _optional_string(
        value,
        field=field,
        max_length=max_length,
        pattern=pattern,
    )
    if not text:
        raise CreateInstanceValidationError(
            "missing_required_field", f"{field} is required."
        )
    return text


def _optional_string(
    value: object,
    *,
    field: str,
    max_length: int,
    pattern: re.Pattern[str] | None,
) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise CreateInstanceValidationError(
            "invalid_field", f"{field} must be a string."
        )
    text = value.strip()
    if not text:
        return None
    if len(text) > max_length:
        raise CreateInstanceValidationError(
            "invalid_field", f"{field} must be at most {max_length} characters."
        )
    if pattern is not None and pattern.fullmatch(text) is None:
        raise CreateInstanceValidationError(
            "invalid_field", f"{field} contains unsupported characters."
        )
    return text


def _coerce_required_int(value: object, *, field: str, min_value: int) -> int:
    result = _coerce_optional_int(value, field=field, min_value=min_value)
    if result is None:
        raise CreateInstanceValidationError(
            "missing_required_field", f"{field} is required."
        )
    return result


def _coerce_optional_int(
    value: object,
    *,
    field: str,
    min_value: int,
    max_value: int | None = None,
) -> int | None:
    if value in (None, ""):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise CreateInstanceValidationError(
            "invalid_field", f"{field} must be an integer."
        ) from exc
    if number < min_value:
        raise CreateInstanceValidationError(
            "invalid_field", f"{field} must be at least {min_value}."
        )
    if max_value is not None and number > max_value:
        raise CreateInstanceValidationError(
            "invalid_field", f"{field} must be at most {max_value}."
        )
    return number


def _coerce_bool(value: object, *, default: bool) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    raise CreateInstanceValidationError(
        "invalid_field", "Boolean fields must be true or false."
    )


def _validate_ssh_keys(value: object) -> list[str] | None:
    if value in (None, ""):
        return None
    if not isinstance(value, list):
        raise CreateInstanceValidationError(
            "invalid_field", "cloud_init.ssh_keys must be a list."
        )
    if len(value) > 20:
        raise CreateInstanceValidationError(
            "invalid_field", "cloud_init.ssh_keys can contain at most 20 keys."
        )
    keys: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise CreateInstanceValidationError(
                "invalid_field", "cloud_init.ssh_keys entries must be strings."
            )
        key = item.strip()
        if not key:
            continue
        if "\n" in key or "\r" in key or len(key) > 4096:
            raise CreateInstanceValidationError(
                "invalid_field", "cloud_init.ssh_keys contains an invalid key."
            )
        if not key.startswith(_SSH_KEY_PREFIXES):
            raise CreateInstanceValidationError(
                "invalid_field", "cloud_init.ssh_keys entries must be SSH public keys."
            )
        keys.append(key)
    return keys or None


def _validate_cloud_init_network(value: object) -> dict[str, object] | None:
    if value in (None, ""):
        return None
    if not isinstance(value, dict):
        raise CreateInstanceValidationError(
            "invalid_field", "cloud_init.network must be an object."
        )
    _reject_unknown_keys(value, {"ip", "cidr", "gw"}, label="cloud_init.network")
    ip_text = _required_string(
        value.get("ip"), field="cloud_init.network.ip", max_length=64, pattern=None
    )
    gw_text = _required_string(
        value.get("gw"), field="cloud_init.network.gw", max_length=64, pattern=None
    )
    try:
        ip_obj = ipaddress.ip_address(ip_text)
        gw_obj = ipaddress.ip_address(gw_text)
    except ValueError as exc:
        raise CreateInstanceValidationError(
            "invalid_field", "cloud_init.network ip and gw must be valid IP addresses."
        ) from exc
    if ip_obj.version != gw_obj.version:
        raise CreateInstanceValidationError(
            "invalid_field",
            "cloud_init.network ip and gw must use the same IP version.",
        )
    max_prefix = 32 if ip_obj.version == 4 else 128
    cidr = _coerce_required_int(
        value.get("cidr"), field="cloud_init.network.cidr", min_value=0
    )
    if cidr > max_prefix:
        raise CreateInstanceValidationError(
            "invalid_field",
            f"cloud_init.network.cidr must be at most {max_prefix}.",
        )
    return {"ip": str(ip_obj), "cidr": cidr, "gw": str(gw_obj)}


def _validate_dns_servers(value: object) -> list[str] | None:
    if value in (None, ""):
        return None
    if not isinstance(value, list):
        raise CreateInstanceValidationError(
            "invalid_field", "cloud_init.dns_servers must be a list."
        )
    if len(value) > 5:
        raise CreateInstanceValidationError(
            "invalid_field", "cloud_init.dns_servers can contain at most 5 servers."
        )
    servers: list[str] = []
    for item in value:
        if item in (None, ""):
            continue
        if not isinstance(item, str):
            raise CreateInstanceValidationError(
                "invalid_field", "cloud_init.dns_servers entries must be strings."
            )
        try:
            servers.append(str(ipaddress.ip_address(item.strip())))
        except ValueError as exc:
            raise CreateInstanceValidationError(
                "invalid_field",
                "cloud_init.dns_servers entries must be valid IP addresses.",
            ) from exc
    return servers or None


def _fetch_next_vmid_base(
    *,
    base_url: str,
    headers: dict[str, str],
    verify_ssl: bool,
    cluster_name: str,
) -> int:
    try:
        response = requests.get(
            f"{base_url}/proxmox/datacenter/options",
            headers=headers,
            verify=verify_ssl,
            timeout=_DATACENTER_OPTIONS_TIMEOUT_S,
        )
        response.raise_for_status()
        return _extract_next_vmid(response.json(), cluster_name=cluster_name)
    except (requests.exceptions.RequestException, ValueError, TypeError) as exc:
        logger.debug("Falling back to VMID base %s: %s", _DEFAULT_BASE_VMID, exc)
        return _DEFAULT_BASE_VMID


def _extract_next_vmid(payload: object, *, cluster_name: str) -> int:
    rows = payload if isinstance(payload, list) else [payload]
    selected: dict[str, object] | None = None
    fallback: dict[str, object] | None = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        next_id = row.get("next_id")
        if isinstance(next_id, dict):
            fallback = fallback or next_id
            if cluster_name and row.get("cluster_name") == cluster_name:
                selected = next_id
                break
    next_id = selected or fallback or {}
    for key in ("vmid", "next_vmid", "new_vmid", "nextid", "next-id", "id"):
        candidate = _positive_int(next_id.get(key))
        if candidate is not None and candidate >= _DEFAULT_BASE_VMID:
            return candidate
    return _DEFAULT_BASE_VMID


def _resolve_cluster_name(endpoint: ProxmoxEndpoint, target_node: str) -> str:
    try:
        node = (
            ProxmoxNode.objects.filter(endpoint=endpoint, name=target_node)
            .select_related("proxmox_cluster")
            .first()
        )
    except Exception:  # pragma: no cover - defensive for mixed NetBox versions
        node = None
    if node is not None:
        cluster = getattr(node, "proxmox_cluster", None)
        if cluster is not None and getattr(cluster, "name", ""):
            return str(cluster.name)
    cluster = ProxmoxCluster.objects.filter(endpoint=endpoint).first()
    return str(getattr(cluster, "name", "") or "")


def _response_json(response: object) -> dict[str, object]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _positive_int(value: object) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None
