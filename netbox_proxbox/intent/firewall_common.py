"""Shared helpers for pushing NetBox firewall objects to proxbox-api."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import quote

from netbox_proxbox.choices import (
    FirewallScopeChoices,
    FirewallSyncStatusChoices,
    FirewallZoneChoices,
)
from netbox_proxbox.models import (
    ProxmoxEndpoint,
    ProxmoxFirewallAlias,
    ProxmoxFirewallIPSet,
    ProxmoxFirewallIPSetEntry,
    ProxmoxFirewallOptions,
    ProxmoxFirewallRule,
    ProxmoxFirewallSecurityGroup,
    ProxmoxNode,
)
from netbox_proxbox.services._endpoint_errors import translate_request_exception
from netbox_proxbox.services.backend_context import get_fastapi_request_context
from netbox_proxbox.services.http_client import (
    HttpClient,
    HttpError,
    get_default_http_client,
)

FIREWALL_PUSH_TIMEOUT_SECONDS = 30


@dataclass
class FirewallPushResult:
    """Parsed result from one proxbox-api firewall write call."""

    status: str
    endpoint_id: int | None
    path: str
    method: str
    payload: dict[str, Any] | None
    response: dict[str, Any] | None
    reason: str | None = None
    detail: str | None = None
    http_status: int = 200

    def to_response(self) -> dict[str, Any]:
        """Return a JSON-serializable API response payload."""
        return asdict(self)


@dataclass
class FirewallPreviewResult:
    """NetBox-vs-Proxmox preview for one firewall object."""

    status: str
    netbox_state: dict[str, Any]
    proxmox_state: dict[str, Any] | None = None
    differing_fields: list[str] = field(default_factory=list)
    reason: str | None = None
    detail: str | None = None

    def to_response(self) -> dict[str, Any]:
        """Return a JSON-serializable API response payload."""
        return asdict(self)


class FirewallPushError(Exception):
    """Raised when a firewall object cannot be pushed."""

    def __init__(
        self,
        reason: str,
        detail: str,
        *,
        status_code: int = 400,
        response: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail
        self.status_code = status_code
        self.response = response or {}


def validation_errors_for_rule(
    data: dict[str, Any],
    *,
    instance: object | None = None,
) -> dict[str, str]:
    """Return model/form/API validation errors for firewall rules."""
    zone = _value(data, instance, "zone")
    errors: dict[str, str] = {}

    if zone == FirewallZoneChoices.NODE and not _value(data, instance, "proxmox_node"):
        errors["proxmox_node"] = "Node-level firewall rules require a Proxmox node."

    if zone == FirewallZoneChoices.SECURITY_GROUP and not _value(
        data, instance, "security_group"
    ):
        errors["security_group"] = (
            "Security-group firewall rules require a security group."
        )

    if zone in {FirewallZoneChoices.VM_QEMU, FirewallZoneChoices.VM_LXC}:
        vm = _value(data, instance, "virtual_machine")
        if vm is None:
            errors["virtual_machine"] = "VM firewall rules require a virtual machine."
        elif _extract_vm_id(vm) is None:
            errors["virtual_machine"] = (
                "The virtual machine must have a proxmox_vm_id custom field."
            )

    if zone == FirewallZoneChoices.VNET and not _value(data, instance, "iface"):
        errors["iface"] = (
            "VNet firewall rules use the interface field as the VNet name."
        )

    return errors


def validation_errors_for_scoped_object(
    data: dict[str, Any],
    *,
    instance: object | None = None,
) -> dict[str, str]:
    """Return validation errors for IP sets and aliases."""
    scope = _value(data, instance, "scope")
    errors: dict[str, str] = {}

    if scope in {FirewallScopeChoices.VM_QEMU, FirewallScopeChoices.VM_LXC}:
        vm = _value(data, instance, "virtual_machine")
        if vm is None:
            errors["virtual_machine"] = "VM-scoped firewall objects require a VM."
        elif _extract_vm_id(vm) is None:
            errors["virtual_machine"] = (
                "The virtual machine must have a proxmox_vm_id custom field."
            )

    return errors


def validation_errors_for_options(
    data: dict[str, Any],
    *,
    instance: object | None = None,
) -> dict[str, str]:
    """Return validation errors for firewall options rows."""
    zone = _value(data, instance, "zone")
    errors: dict[str, str] = {}

    if zone == FirewallZoneChoices.NODE and not _value(data, instance, "proxmox_node"):
        errors["proxmox_node"] = "Node-level firewall options require a Proxmox node."

    if zone in {FirewallZoneChoices.VM_QEMU, FirewallZoneChoices.VM_LXC}:
        vm = _value(data, instance, "virtual_machine")
        if vm is None:
            errors["virtual_machine"] = "VM firewall options require a virtual machine."
        elif _extract_vm_id(vm) is None:
            errors["virtual_machine"] = (
                "The virtual machine must have a proxmox_vm_id custom field."
            )

    if zone in {FirewallZoneChoices.SECURITY_GROUP, FirewallZoneChoices.VNET}:
        errors["zone"] = (
            "Firewall options are only supported for datacenter, node, and VM zones."
        )

    return errors


def mark_firewall_object_stale(obj: object) -> None:
    """Mark a manually edited firewall object, or its parent, as stale."""
    target = _status_target(obj)
    if target is None:
        return
    setattr(target, "status", FirewallSyncStatusChoices.STALE)


def save_status_for_firewall_object(obj: object, status: str) -> None:
    """Persist a status update for an object that has a firewall status field."""
    target = _status_target(obj)
    if target is None:
        return
    setattr(target, "status", status)
    save = getattr(target, "save", None)
    if callable(save):
        save(update_fields=["status"])


def resolve_firewall_endpoint(obj: object) -> ProxmoxEndpoint | None:
    """Resolve the ProxmoxEndpoint associated with a firewall object."""
    endpoint = getattr(obj, "endpoint", None)
    if endpoint is not None:
        return endpoint

    if isinstance(obj, ProxmoxFirewallIPSetEntry):
        return resolve_firewall_endpoint(obj.ipset)

    node = getattr(obj, "proxmox_node", None)
    if node is not None and getattr(node, "endpoint", None) is not None:
        return node.endpoint

    security_group = getattr(obj, "security_group", None)
    if (
        security_group is not None
        and getattr(security_group, "endpoint", None) is not None
    ):
        return security_group.endpoint

    vm = getattr(obj, "virtual_machine", None)
    if vm is not None:
        return _endpoint_from_vm(vm)

    return None


def push_firewall_object(
    obj: object,
    *,
    actor: str,
    client: HttpClient | None = None,
) -> FirewallPushResult:
    """Push one firewall object through proxbox-api."""
    if isinstance(obj, ProxmoxFirewallSecurityGroup):
        return push_security_group(obj, actor=actor, client=client)
    if isinstance(obj, ProxmoxFirewallRule):
        return push_rule(obj, actor=actor, client=client)
    if isinstance(obj, ProxmoxFirewallIPSet):
        return push_ipset(obj, actor=actor, client=client)
    if isinstance(obj, ProxmoxFirewallIPSetEntry):
        return push_ipset_entry(obj, actor=actor, client=client)
    if isinstance(obj, ProxmoxFirewallAlias):
        return push_alias(obj, actor=actor, client=client)
    if isinstance(obj, ProxmoxFirewallOptions):
        return push_options(obj, actor=actor, client=client)

    raise FirewallPushError(
        "unsupported_firewall_object",
        f"{type(obj).__name__} cannot be pushed to Proxmox firewall endpoints.",
        status_code=400,
    )


def preview_firewall_object(
    obj: object,
    *,
    client: HttpClient | None = None,
) -> FirewallPreviewResult:
    """Fetch live Proxmox state and compare it with the NetBox object."""
    netbox_state = firewall_object_state(obj)
    endpoint = resolve_firewall_endpoint(obj)
    if endpoint is None:
        return FirewallPreviewResult(
            status="error",
            netbox_state=netbox_state,
            reason="endpoint_required",
            detail="This firewall object is not linked to a Proxmox endpoint.",
        )

    path, params = _preview_read_target(obj)
    if not path:
        return FirewallPreviewResult(
            status="skipped",
            netbox_state=netbox_state,
            reason="firewall_preview_not_available",
            detail="Live preview is not available for this firewall object.",
        )

    context = get_fastapi_request_context()
    if context is None or not context.http_url:
        return FirewallPreviewResult(
            status="error",
            netbox_state=netbox_state,
            reason="fastapi_endpoint_required",
            detail="No FastAPI backend endpoint is configured.",
        )

    http_client = client or get_default_http_client()
    try:
        response = http_client.get(
            f"{context.http_url.rstrip('/')}{path}",
            params=params,
            headers=dict(context.headers or {}),
            verify=bool(context.verify_ssl),
            timeout=FIREWALL_PUSH_TIMEOUT_SECONDS,
        )
    except HttpError as exc:
        return FirewallPreviewResult(
            status="error",
            netbox_state=netbox_state,
            reason="backend_request_failed",
            detail=translate_request_exception(exc),
        )

    payload = _response_json(response)
    if response.status_code >= 400:
        return FirewallPreviewResult(
            status="error",
            netbox_state=netbox_state,
            reason=str(_payload_value(payload, "reason") or "firewall_preview_failed"),
            detail=str(_payload_value(payload, "detail") or response.text),
        )

    proxmox_state = _select_proxmox_state(obj, payload, endpoint)
    differing_fields = _differing_fields(netbox_state, proxmox_state or {})
    return FirewallPreviewResult(
        status="ready" if proxmox_state is not None else "missing",
        netbox_state=netbox_state,
        proxmox_state=proxmox_state,
        differing_fields=differing_fields,
        reason=None if proxmox_state is not None else "proxmox_object_not_found",
        detail=None
        if proxmox_state is not None
        else "No matching live Proxmox object was found.",
    )


def firewall_object_state(obj: object) -> dict[str, Any]:
    """Return comparable NetBox state for a firewall object."""
    if isinstance(obj, ProxmoxFirewallSecurityGroup):
        return _drop_empty({"name": obj.name, "comment": obj.comment})
    if isinstance(obj, ProxmoxFirewallRule):
        return _rule_payload(obj)
    if isinstance(obj, ProxmoxFirewallIPSet):
        return _drop_empty({"name": obj.name, "comment": obj.comment})
    if isinstance(obj, ProxmoxFirewallIPSetEntry):
        return _drop_empty(
            {"cidr": obj.cidr, "comment": obj.comment, "nomatch": obj.nomatch}
        )
    if isinstance(obj, ProxmoxFirewallAlias):
        return _drop_empty({"name": obj.name, "cidr": obj.cidr, "comment": obj.comment})
    if isinstance(obj, ProxmoxFirewallOptions):
        return _drop_empty(
            {
                "enable": obj.enable,
                "policy_in": obj.policy_in,
                "policy_out": obj.policy_out,
                **dict(obj.options or {}),
            }
        )
    return {}


def push_security_group(
    group: ProxmoxFirewallSecurityGroup,
    *,
    actor: str,
    client: HttpClient | None = None,
) -> FirewallPushResult:
    payload = _drop_empty({"group": group.name, "comment": group.comment})
    return _call_firewall_backend(
        group,
        method="post",
        path="/proxmox/firewall/datacenter/groups",
        payload=payload,
        actor=actor,
        client=client,
    )


def push_rule(
    rule: ProxmoxFirewallRule,
    *,
    actor: str,
    client: HttpClient | None = None,
) -> FirewallPushResult:
    method, path = _rule_push_target(rule)
    return _call_firewall_backend(
        rule,
        method=method,
        path=path,
        payload=_rule_payload(rule),
        actor=actor,
        client=client,
    )


def push_ipset(
    ipset: ProxmoxFirewallIPSet,
    *,
    actor: str,
    client: HttpClient | None = None,
) -> FirewallPushResult:
    path, _params = _scoped_collection_path(ipset, "ipsets")
    payload = _drop_empty({"name": ipset.name, "comment": ipset.comment})
    return _call_firewall_backend(
        ipset,
        method="post",
        path=path,
        payload=payload,
        actor=actor,
        client=client,
    )


def push_ipset_entry(
    entry: ProxmoxFirewallIPSetEntry,
    *,
    actor: str,
    client: HttpClient | None = None,
) -> FirewallPushResult:
    path, _params = _ipset_entry_path(entry)
    payload = _drop_empty(
        {"cidr": entry.cidr, "comment": entry.comment, "nomatch": entry.nomatch}
    )
    method = "put" if _has_remote_marker(entry) else "post"
    return _call_firewall_backend(
        entry,
        method=method,
        path=path if method == "post" else f"{path}/{quote(str(entry.cidr), safe='')}",
        payload=payload,
        actor=actor,
        client=client,
    )


def push_alias(
    alias: ProxmoxFirewallAlias,
    *,
    actor: str,
    client: HttpClient | None = None,
) -> FirewallPushResult:
    collection, _params = _scoped_collection_path(alias, "aliases")
    method = "put" if _has_remote_marker(alias) else "post"
    path = (
        collection
        if method == "post"
        else _path_add_segments(collection, quote(str(alias.name), safe=""))
    )
    payload = _drop_empty(
        {
            "name": alias.name,
            "cidr": alias.cidr,
            "comment": alias.comment,
        }
    )
    return _call_firewall_backend(
        alias,
        method=method,
        path=path,
        payload=payload,
        actor=actor,
        client=client,
    )


def push_options(
    options: ProxmoxFirewallOptions,
    *,
    actor: str,
    client: HttpClient | None = None,
) -> FirewallPushResult:
    path = _options_path(options)
    payload = _drop_empty(
        {
            "enable": options.enable,
            "policy_in": options.policy_in,
            "policy_out": options.policy_out,
            "options": dict(options.options or {}),
        }
    )
    return _call_firewall_backend(
        options,
        method="put",
        path=path,
        payload=payload,
        actor=actor,
        client=client,
    )


def _call_firewall_backend(
    obj: object,
    *,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
    actor: str,
    client: HttpClient | None = None,
) -> FirewallPushResult:
    actor_value = (actor or "").strip()
    if not actor_value:
        raise FirewallPushError(
            "actor_required",
            "Firewall pushes require an authenticated actor.",
            status_code=422,
        )

    endpoint = resolve_firewall_endpoint(obj)
    if endpoint is None:
        save_status_for_firewall_object(obj, FirewallSyncStatusChoices.ERROR)
        raise FirewallPushError(
            "endpoint_required",
            "This firewall object is not linked to a Proxmox endpoint.",
            status_code=400,
        )
    if not getattr(endpoint, "allow_writes", False):
        save_status_for_firewall_object(obj, FirewallSyncStatusChoices.ERROR)
        raise FirewallPushError(
            "writes_disabled_for_endpoint",
            "Firewall writes are disabled on the linked Proxmox endpoint.",
            status_code=403,
            response={"endpoint_id": getattr(endpoint, "pk", None)},
        )

    context = get_fastapi_request_context()
    if context is None or not context.http_url:
        save_status_for_firewall_object(obj, FirewallSyncStatusChoices.ERROR)
        raise FirewallPushError(
            "fastapi_endpoint_required",
            "No FastAPI backend endpoint is configured.",
            status_code=400,
        )

    headers = dict(context.headers or {})
    headers["X-Proxbox-Actor"] = actor_value
    headers.setdefault("Content-Type", "application/json")
    endpoint_id = int(getattr(endpoint, "pk", getattr(endpoint, "id", 0)))
    separator = "&" if "?" in path else "?"
    url = f"{context.http_url.rstrip('/')}{path}{separator}endpoint_id={endpoint_id}"
    http_client = client or get_default_http_client()

    try:
        response = getattr(http_client, method)(
            url,
            json=payload or {},
            headers=headers,
            verify=bool(context.verify_ssl),
            timeout=FIREWALL_PUSH_TIMEOUT_SECONDS,
        )
    except HttpError as exc:
        save_status_for_firewall_object(obj, FirewallSyncStatusChoices.ERROR)
        raise FirewallPushError(
            "backend_request_failed",
            translate_request_exception(exc),
            status_code=502,
        ) from exc

    body = _response_json(response)
    if response.status_code >= 400:
        save_status_for_firewall_object(obj, FirewallSyncStatusChoices.ERROR)
        reason = _payload_value(body, "reason") or "proxmox_firewall_push_failed"
        detail = _payload_value(body, "detail") or response.text
        raise FirewallPushError(
            str(reason),
            str(detail),
            status_code=response.status_code,
            response=body if isinstance(body, dict) else {},
        )

    result = FirewallPushResult(
        status=str(_payload_value(body, "status") or "pushed"),
        endpoint_id=endpoint_id,
        path=path,
        method=method,
        payload=payload,
        response=body if isinstance(body, dict) else None,
        reason=_payload_value(body, "reason"),
        detail=_payload_value(body, "detail"),
        http_status=response.status_code,
    )
    if result.status == "skipped":
        save_status_for_firewall_object(obj, FirewallSyncStatusChoices.STALE)
    else:
        save_status_for_firewall_object(obj, FirewallSyncStatusChoices.ACTIVE)
    return result


def _preview_read_target(obj: object) -> tuple[str, dict[str, str] | None]:
    if isinstance(obj, ProxmoxFirewallSecurityGroup):
        return "/proxmox/firewall/datacenter/groups", None
    if isinstance(obj, ProxmoxFirewallRule):
        return _rule_preview_target(obj)
    if isinstance(obj, ProxmoxFirewallIPSet):
        return _scoped_preview_target(obj, "ipsets")
    if isinstance(obj, ProxmoxFirewallIPSetEntry):
        return _scoped_preview_target(obj.ipset, "ipsets")
    if isinstance(obj, ProxmoxFirewallAlias):
        return _scoped_preview_target(obj, "aliases")
    if isinstance(obj, ProxmoxFirewallOptions):
        return _options_preview_target(obj)
    return "", None


def _rule_preview_target(
    rule: ProxmoxFirewallRule,
) -> tuple[str, dict[str, str] | None]:
    if rule.zone == FirewallZoneChoices.DATACENTER:
        return "/proxmox/firewall/datacenter/rules", None
    if rule.zone == FirewallZoneChoices.SECURITY_GROUP:
        return "/proxmox/firewall/datacenter/groups", None
    if rule.zone == FirewallZoneChoices.NODE:
        return (
            f"/proxmox/firewall/nodes/{quote(_node_name(rule.proxmox_node), safe='')}/rules",
            None,
        )
    if rule.zone in {FirewallZoneChoices.VM_QEMU, FirewallZoneChoices.VM_LXC}:
        vmid, node, vm_type = _vm_context(rule.virtual_machine, zone=rule.zone)
        return (
            f"/proxmox/firewall/vms/{vmid}/rules",
            {"node": node, "vm_type": vm_type},
        )
    if rule.zone == FirewallZoneChoices.VNET:
        return "", None
    return "", None


def _scoped_preview_target(
    obj: ProxmoxFirewallIPSet | ProxmoxFirewallAlias,
    noun: str,
) -> tuple[str, dict[str, str] | None]:
    if obj.scope == FirewallScopeChoices.DATACENTER:
        return f"/proxmox/firewall/datacenter/{noun}", None
    if obj.scope in {FirewallScopeChoices.VM_QEMU, FirewallScopeChoices.VM_LXC}:
        vmid, node, vm_type = _vm_context(obj.virtual_machine, scope=obj.scope)
        return (
            f"/proxmox/firewall/vms/{vmid}/{noun}",
            {"node": node, "vm_type": vm_type},
        )
    return "", None


def _options_preview_target(
    options: ProxmoxFirewallOptions,
) -> tuple[str, dict[str, str] | None]:
    if options.zone == FirewallZoneChoices.DATACENTER:
        return "/proxmox/firewall/datacenter/options", None
    if options.zone == FirewallZoneChoices.NODE:
        return (
            f"/proxmox/firewall/nodes/{quote(_node_name(options.proxmox_node), safe='')}/options",
            None,
        )
    if options.zone in {FirewallZoneChoices.VM_QEMU, FirewallZoneChoices.VM_LXC}:
        vmid, node, vm_type = _vm_context(options.virtual_machine, zone=options.zone)
        return (
            f"/proxmox/firewall/vms/{vmid}/options",
            {"node": node, "vm_type": vm_type},
        )
    return "", None


def _select_proxmox_state(
    obj: object,
    payload: object,
    endpoint: ProxmoxEndpoint,
) -> dict[str, Any] | None:
    cluster_name = getattr(endpoint, "name", None)
    if isinstance(obj, ProxmoxFirewallOptions):
        return payload if isinstance(payload, dict) else None
    if isinstance(obj, ProxmoxFirewallSecurityGroup):
        return _find_item(payload, name=obj.name, cluster_name=cluster_name)
    if isinstance(obj, ProxmoxFirewallRule):
        if obj.zone == FirewallZoneChoices.SECURITY_GROUP:
            group = getattr(obj.security_group, "name", None)
            sg_state = _find_item(payload, name=group, cluster_name=cluster_name)
            return _find_item((sg_state or {}).get("rules"), pos=obj.pos)
        return _find_item(payload, pos=obj.pos, cluster_name=cluster_name)
    if isinstance(obj, ProxmoxFirewallIPSet):
        return _find_item(payload, name=obj.name, cluster_name=cluster_name)
    if isinstance(obj, ProxmoxFirewallIPSetEntry):
        ipset_state = _find_item(
            payload, name=obj.ipset.name, cluster_name=cluster_name
        )
        return _find_item((ipset_state or {}).get("entries"), cidr=obj.cidr)
    if isinstance(obj, ProxmoxFirewallAlias):
        return _find_item(payload, name=obj.name, cluster_name=cluster_name)
    return None


def _find_item(
    payload: object,
    *,
    cluster_name: str | None = None,
    name: str | None = None,
    pos: int | None = None,
    cidr: str | None = None,
) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        items = [payload]
    elif isinstance(payload, list):
        items = [item for item in payload if isinstance(item, dict)]
    else:
        return None

    for item in items:
        if cluster_name and item.get("cluster_name") not in {None, cluster_name}:
            continue
        if name is not None and (item.get("name") or item.get("group")) != name:
            continue
        if pos is not None and _coerce_int(item.get("pos")) != int(pos):
            continue
        if cidr is not None and item.get("cidr") != cidr:
            continue
        return item
    return None


def _differing_fields(
    netbox_state: dict[str, Any],
    proxmox_state: dict[str, Any],
) -> list[str]:
    fields = sorted(set(netbox_state) | set(proxmox_state))
    differing: list[str] = []
    for field_name in fields:
        netbox_value = _normalize_compare_value(netbox_state.get(field_name))
        proxmox_value = _normalize_compare_value(
            proxmox_state.get(field_name)
            if field_name != "icmp-type"
            else proxmox_state.get("icmp-type") or proxmox_state.get("icmp_type")
        )
        if netbox_value != proxmox_value:
            differing.append(field_name)
    return differing


def _normalize_compare_value(value: Any) -> Any:
    if isinstance(value, bool):
        return int(value)
    if value is None:
        return ""
    return value


def _coerce_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _rule_push_target(rule: ProxmoxFirewallRule) -> tuple[str, str]:
    create = not _has_remote_marker(rule)
    suffix = "" if create else f"/{int(rule.pos)}"
    method = "post" if create else "put"

    if rule.zone == FirewallZoneChoices.DATACENTER:
        return method, f"/proxmox/firewall/datacenter/rules{suffix}"

    if rule.zone == FirewallZoneChoices.NODE:
        node_name = _node_name(rule.proxmox_node)
        return (
            method,
            f"/proxmox/firewall/nodes/{quote(node_name, safe='')}/rules{suffix}",
        )

    if rule.zone == FirewallZoneChoices.SECURITY_GROUP:
        group_name = getattr(rule.security_group, "name", None)
        if not group_name:
            raise FirewallPushError(
                "security_group_required",
                "Security-group firewall rules require a security group.",
                status_code=400,
            )
        return (
            method,
            "/proxmox/firewall/datacenter/groups/"
            f"{quote(str(group_name), safe='')}/rules{suffix}",
        )

    if rule.zone in {FirewallZoneChoices.VM_QEMU, FirewallZoneChoices.VM_LXC}:
        vmid, node, vm_type = _vm_context(rule.virtual_machine, zone=rule.zone)
        return (
            method,
            f"/proxmox/firewall/vms/{vmid}/rules{suffix}"
            f"?node={quote(node, safe='')}&vm_type={vm_type}",
        )

    if rule.zone == FirewallZoneChoices.VNET:
        vnet = (rule.iface or "").strip()
        if not vnet:
            raise FirewallPushError(
                "vnet_required",
                "VNet firewall rules require the interface field to hold the VNet name.",
                status_code=400,
            )
        return method, f"/proxmox/firewall/vnets/{quote(vnet, safe='')}/rules{suffix}"

    raise FirewallPushError(
        "unsupported_firewall_zone",
        f"Unsupported firewall rule zone: {rule.zone}",
        status_code=400,
    )


def _scoped_collection_path(
    obj: ProxmoxFirewallIPSet | ProxmoxFirewallAlias,
    noun: str,
) -> tuple[str, dict[str, str]]:
    if obj.scope == FirewallScopeChoices.DATACENTER:
        return f"/proxmox/firewall/datacenter/{noun}", {}
    if obj.scope in {FirewallScopeChoices.VM_QEMU, FirewallScopeChoices.VM_LXC}:
        vmid, node, vm_type = _vm_context(obj.virtual_machine, scope=obj.scope)
        return (
            f"/proxmox/firewall/vms/{vmid}/{noun}"
            f"?node={quote(node, safe='')}&vm_type={vm_type}",
            {"node": node, "vm_type": vm_type},
        )
    raise FirewallPushError(
        "unsupported_firewall_scope",
        f"Unsupported firewall scope: {obj.scope}",
        status_code=400,
    )


def _ipset_entry_path(entry: ProxmoxFirewallIPSetEntry) -> tuple[str, dict[str, str]]:
    ipset = entry.ipset
    collection, params = _scoped_collection_path(ipset, "ipsets")
    return _path_add_segments(
        collection, quote(str(ipset.name), safe=""), "entries"
    ), params


def _options_path(options: ProxmoxFirewallOptions) -> str:
    if options.zone == FirewallZoneChoices.DATACENTER:
        return "/proxmox/firewall/datacenter/options"
    if options.zone == FirewallZoneChoices.NODE:
        node_name = _node_name(options.proxmox_node)
        return f"/proxmox/firewall/nodes/{quote(node_name, safe='')}/options"
    if options.zone in {FirewallZoneChoices.VM_QEMU, FirewallZoneChoices.VM_LXC}:
        vmid, node, vm_type = _vm_context(options.virtual_machine, zone=options.zone)
        return (
            f"/proxmox/firewall/vms/{vmid}/options?node={quote(node, safe='')}"
            f"&vm_type={vm_type}"
        )
    raise FirewallPushError(
        "unsupported_firewall_options_zone",
        "Firewall options pushes are only supported for datacenter, node, and VM zones.",
        status_code=400,
    )


def _path_add_segments(path: str, *segments: str) -> str:
    """Append path segments before any query string."""
    base, separator, query = path.partition("?")
    updated = "/".join(
        [base.rstrip("/"), *[segment.strip("/") for segment in segments]]
    )
    return f"{updated}{separator}{query}" if separator else updated


def _rule_payload(rule: ProxmoxFirewallRule) -> dict[str, Any]:
    return _drop_empty(
        {
            "pos": rule.pos,
            "type": rule.rule_type,
            "action": rule.action,
            "enable": rule.enable,
            "macro": rule.macro,
            "iface": rule.iface,
            "source": rule.source,
            "dest": rule.dest,
            "proto": rule.proto,
            "dport": rule.dport,
            "sport": rule.sport,
            "log": rule.log,
            "icmp-type": rule.icmp_type,
            "comment": rule.comment,
            "digest": rule.digest,
        }
    )


def _drop_empty(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value not in (None, "")}


def _has_remote_marker(obj: object) -> bool:
    if getattr(obj, "digest", ""):
        return True
    raw = getattr(obj, "raw_config", None) or {}
    return bool(isinstance(raw, dict) and raw)


def _value(data: dict[str, Any], instance: object | None, field: str) -> Any:
    if field in data:
        return data[field]
    if instance is not None:
        return getattr(instance, field, None)
    return None


def _extract_vm_id(vm: object | None) -> int | None:
    if vm is None:
        return None
    cf = getattr(vm, "custom_field_data", None)
    if cf is None and isinstance(vm, dict):
        cf = vm.get("custom_field_data") or vm.get("custom_fields")
    cf = cf or {}
    raw = cf.get("proxmox_vm_id") or cf.get("cf_proxmox_vm_id")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _vm_node_name(vm: object | None) -> str:
    if vm is None:
        return ""
    device = getattr(vm, "device", None)
    if device is not None and getattr(device, "name", None):
        return str(device.name)
    cf = getattr(vm, "custom_field_data", None) or {}
    return str(cf.get("proxmox_node") or cf.get("cf_proxmox_node") or "").strip()


def _vm_context(
    vm: object | None,
    *,
    zone: str | None = None,
    scope: str | None = None,
) -> tuple[int, str, str]:
    vmid = _extract_vm_id(vm)
    node = _vm_node_name(vm)
    vm_type = "lxc" if (zone or scope) in {"vm_lxc"} else "qemu"
    if vmid is None:
        raise FirewallPushError(
            "vmid_required",
            "VM-scoped firewall pushes require proxmox_vm_id on the virtual machine.",
            status_code=400,
        )
    if not node:
        raise FirewallPushError(
            "vm_node_required",
            "VM-scoped firewall pushes require a Proxmox node name on the VM.",
            status_code=400,
        )
    return vmid, node, vm_type


def _node_name(node: ProxmoxNode | None) -> str:
    name = (getattr(node, "name", "") or "").strip()
    if not name:
        raise FirewallPushError(
            "node_required",
            "Node-level firewall pushes require a Proxmox node.",
            status_code=400,
        )
    return name


def _endpoint_from_vm(vm: object) -> ProxmoxEndpoint | None:
    cluster = getattr(vm, "cluster", None)
    if cluster is None:
        return None
    tracking = getattr(cluster, "proxmox_cluster_tracking", None)
    if tracking is None:
        return None
    first = getattr(tracking, "first", None)
    proxmox_cluster = first() if callable(first) else None
    return getattr(proxmox_cluster, "endpoint", None)


def _status_target(obj: object) -> object | None:
    if hasattr(obj, "status"):
        return obj
    ipset = getattr(obj, "ipset", None)
    if ipset is not None and hasattr(ipset, "status"):
        return ipset
    return None


def _response_json(response: object) -> object:
    try:
        return response.json()
    except ValueError:
        return None


def _payload_value(payload: object, key: str) -> Any:
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if key in payload:
            return payload[key]
        if isinstance(detail, dict):
            return detail.get(key)
    return None
