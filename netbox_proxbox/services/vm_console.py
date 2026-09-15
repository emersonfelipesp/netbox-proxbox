"""Resolve and validate the standalone browser-console trust boundary."""

from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urlsplit, urlunsplit

from django.http import HttpRequest

from netbox_proxbox.models import FastAPIEndpoint, ProxmoxEndpoint
from netbox_proxbox.schemas.backend_proxy import BackendRequestContext
from netbox_proxbox.services.backend_context import get_fastapi_request_context
from netbox_proxbox.views.backend_sync import resolve_backend_endpoint_id

_BROWSER_STREAM_PATH = "/proxmox/console/browser-stream"
_STREAM_TOKEN = re.compile(r"[A-Za-z0-9_-]{32,256}\Z")


class ConsoleResolutionError(Exception):
    """A safe, user-facing refusal at the console identity boundary."""

    def __init__(
        self,
        detail: str,
        *,
        status: int = 409,
        code: str | None = None,
        remediation: str | None = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status = status
        self.code = code
        self.remediation = remediation


@dataclass(frozen=True, slots=True)
class ConsoleIdentity:
    """Complete synchronized identity required to address one Proxmox guest."""

    virtual_machine_id: int
    endpoint: ProxmoxEndpoint
    vmid: int
    node: str
    vm_type: str
    backend_raw_id: int | None


@dataclass(frozen=True, slots=True)
class ConsoleBackend:
    """One trusted proxbox-api instance and its resolved endpoint identifier."""

    context: BackendRequestContext
    backend_endpoint_id: int
    websocket_base: str


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def resolve_console_identity(vm: object) -> ConsoleIdentity:
    """Return the exact typed sync identity or fail closed on partial/drifted data."""
    try:
        state = getattr(vm, "proxbox_sync_state")
    except AttributeError as exc:
        raise ConsoleResolutionError(
            "This virtual machine has no Proxbox synchronization state.",
            code="SYNC_STATE_MISSING",
            remediation=(
                "Run Repair / Rebuild to synchronize this guest from Proxmox, "
                "then return here and connect again."
            ),
        ) from exc

    vm_pk = _positive_int(getattr(vm, "pk", None))
    state_vm_pk = _positive_int(getattr(state, "virtual_machine_id", None))
    endpoint = getattr(state, "endpoint", None)
    node = getattr(state, "proxmox_node", None)
    vmid = _positive_int(getattr(state, "proxmox_vm_id", None))
    backend_raw_id = _positive_int(getattr(state, "proxmox_endpoint_raw_id", None))
    vm_type = str(getattr(state, "proxmox_vm_type", "") or "").strip().lower()
    node_name = str(getattr(node, "name", "") or "").strip()
    stored_node_name = str(getattr(state, "proxmox_node_name", "") or "").strip()

    if vm_pk is None or state_vm_pk != vm_pk:
        raise ConsoleResolutionError(
            "The Proxbox synchronization identity does not belong to this VM.",
            code="SYNC_IDENTITY_INCONSISTENT",
            remediation=(
                "Run Repair / Rebuild to replace the stale identity from live "
                "Proxmox inventory, then retry."
            ),
        )
    if not isinstance(endpoint, ProxmoxEndpoint):
        detail = (
            "This VM has backend endpoint data, but its required NetBox Proxmox "
            "endpoint link is missing. The endpoint API can still be connected; "
            "the console cannot authorize an unlinked backend endpoint."
            if backend_raw_id is not None
            else "This VM is missing both its NetBox Proxmox endpoint link and "
            "its synchronized backend mapping, so the console cannot determine "
            "which endpoint it may authorize."
        )
        raise ConsoleResolutionError(
            detail,
            code="SYNC_ENDPOINT_LINK_MISSING",
            remediation=(
                "Run Repair / Rebuild to refresh the VM's typed endpoint and node "
                "links from Proxmox. An administrator must run it if you do not "
                "have permission to enqueue Proxbox sync jobs."
            ),
        )
    if not endpoint.enabled:
        raise ConsoleResolutionError(
            "The NetBox Proxmox endpoint linked to this VM is disabled. An API "
            "health check can still succeed independently, but disabled endpoints "
            "cannot authorize console sessions.",
            code="SYNC_ENDPOINT_DISABLED",
            remediation=(
                "Ask a Proxbox administrator to enable the linked endpoint, run a "
                "full sync, and retry the console."
            ),
        )
    if (
        node is None
        or getattr(node, "endpoint_id", None) != endpoint.pk
        or not node_name
    ):
        raise ConsoleResolutionError(
            "The synchronized Proxmox node link is missing or belongs to another endpoint.",
            code="SYNC_NODE_LINK_INVALID",
            remediation=(
                "Run Repair / Rebuild to refresh the endpoint and node relations, "
                "then retry."
            ),
        )
    if stored_node_name and stored_node_name != node_name:
        raise ConsoleResolutionError(
            "The synchronized Proxmox node name no longer matches its linked node.",
            code="SYNC_NODE_IDENTITY_DRIFTED",
            remediation=(
                "Run Repair / Rebuild to refresh the node identity from live "
                "Proxmox inventory, then retry."
            ),
        )
    cluster = getattr(state, "proxmox_cluster", None)
    if cluster is not None and getattr(cluster, "endpoint_id", None) != endpoint.pk:
        raise ConsoleResolutionError(
            "The synchronized Proxmox cluster belongs to another endpoint.",
            code="SYNC_CLUSTER_IDENTITY_DRIFTED",
            remediation=(
                "Run Repair / Rebuild to refresh the cluster relationship from "
                "live Proxmox inventory, then retry."
            ),
        )
    if vmid is None or vm_type not in {"qemu", "lxc"}:
        raise ConsoleResolutionError(
            "The synchronized guest is missing a valid VMID or workload type.",
            code="SYNC_GUEST_IDENTITY_INCOMPLETE",
            remediation=(
                "Run Repair / Rebuild to refresh the guest identity from live "
                "Proxmox inventory, then retry."
            ),
        )

    return ConsoleIdentity(
        virtual_machine_id=vm_pk,
        endpoint=endpoint,
        vmid=vmid,
        node=node_name,
        vm_type=vm_type,
        backend_raw_id=backend_raw_id,
    )


def resolve_console_backend(identity: ConsoleIdentity) -> ConsoleBackend:
    """Resolve exactly one browser-capable proxbox-api and verify endpoint affinity."""
    matches: list[ConsoleBackend] = []
    for fastapi_endpoint in FastAPIEndpoint.objects.filter(enabled=True).order_by("pk"):
        context = get_fastapi_request_context(endpoint_id=fastapi_endpoint.pk)
        if context is None or not context.http_url:
            continue
        websocket_base = str(context.detail.get("websocket_url") or "").strip()
        if not websocket_base:
            continue
        backend_id, _error = resolve_backend_endpoint_id(
            identity.endpoint,
            base_url=context.http_url,
            auth_headers=context.headers,
            backend_verify_ssl=context.verify_ssl,
            timeout=10,
        )
        if backend_id is None:
            continue
        if (
            identity.backend_raw_id is not None
            and identity.backend_raw_id != backend_id
        ):
            continue
        matches.append(
            ConsoleBackend(
                context=context,
                backend_endpoint_id=backend_id,
                websocket_base=websocket_base,
            )
        )

    if not matches:
        raise ConsoleResolutionError(
            "No trusted proxbox-api endpoint matches this synchronized guest.",
            status=503,
        )
    if len(matches) != 1:
        raise ConsoleResolutionError(
            "Multiple proxbox-api endpoints match this synchronized guest; refusing to guess.",
            status=409,
        )
    return matches[0]


def console_origin(request: HttpRequest) -> str:
    """Return the exact HTTPS browser origin used to bind a relay ticket."""
    parsed = urlsplit(request.build_absolute_uri("/"))
    try:
        port = parsed.port
    except ValueError as exc:
        raise ConsoleResolutionError(
            "Browser console sessions require a valid NetBox HTTPS origin.",
            status=503,
        ) from exc
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise ConsoleResolutionError(
            "Browser console sessions require NetBox to be served over HTTPS.",
            status=503,
        )
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def browser_websocket_url(
    websocket_base: str,
    websocket_path: object,
    *,
    stream_token: object,
) -> str:
    """Join a validated relay path to the configured public proxbox-api authority."""
    base = urlsplit(websocket_base)
    path = urlsplit(str(websocket_path or ""))
    token = stream_token if isinstance(stream_token, str) else ""
    try:
        base_port = base.port
    except ValueError as exc:
        raise ConsoleResolutionError(
            "proxbox-api returned an invalid browser-console relay path.",
            status=502,
        ) from exc
    if (
        base.scheme != "wss"
        or not base.netloc
        or not base.hostname
        or base.username is not None
        or base.password is not None
        or (base_port is not None and not 1 <= base_port <= 65535)
        or path.scheme
        or path.netloc
        or path.fragment
        or path.path != _BROWSER_STREAM_PATH
        or path.query
        or _STREAM_TOKEN.fullmatch(token) is None
    ):
        raise ConsoleResolutionError(
            "proxbox-api returned an invalid browser-console relay path.",
            status=502,
        )
    return urlunsplit(("wss", base.netloc, path.path, "", ""))


__all__ = (
    "ConsoleBackend",
    "ConsoleIdentity",
    "ConsoleResolutionError",
    "browser_websocket_url",
    "console_origin",
    "resolve_console_backend",
    "resolve_console_identity",
)
