"""Build proxbox-api firewall intent payloads from Branching ChangeDiff rows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from netbox_proxbox.choices import FirewallScopeChoices, FirewallZoneChoices

FIREWALL_MODEL_NAMES = (
    "proxmoxfirewallsecuritygroup",
    "proxmoxfirewallrule",
    "proxmoxfirewallipset",
    "proxmoxfirewallipsetentry",
    "proxmoxfirewallalias",
    "proxmoxfirewalloptions",
)

_SUPPORTED_OPS = {"create", "update", "delete"}


@dataclass(frozen=True)
class FirewallApplyDiff:
    """One firewall apply diff plus the Proxmox endpoint gate target."""

    diff: dict[str, Any]
    endpoint_id: int | None
    obj: object | None = None


def firewall_changediffs(branch: Any) -> list[Any]:
    """Return ChangeDiff rows for persisted firewall models on a branch."""
    changediff_qs = getattr(branch, "changediff_set", None)
    if changediff_qs is None:
        return []

    try:
        return list(changediff_qs.filter(object_type__model__in=FIREWALL_MODEL_NAMES))
    except Exception:  # noqa: BLE001 - test stubs may not support __in lookups
        rows: list[Any] = []
        for model_name in FIREWALL_MODEL_NAMES:
            try:
                rows.extend(list(changediff_qs.filter(object_type__model=model_name)))
            except Exception:  # noqa: BLE001
                continue
        return rows


def build_firewall_plan_diffs(branch: Any) -> list[dict[str, Any]]:
    """Build read-only /intent/plan diffs for firewall ChangeDiff rows."""
    diffs: list[dict[str, Any]] = []
    for row in firewall_changediffs(branch):
        apply_diff = build_firewall_apply_diff(row)
        if apply_diff is None:
            continue
        plan_diff = {
            "op": apply_diff.diff["op"],
            "kind": "firewall",
            "netbox_id": apply_diff.diff.get("netbox_id"),
            "name": _row_name(row),
            "type": apply_diff.diff["payload"].get("action"),
        }
        if apply_diff.endpoint_id is not None:
            plan_diff["endpoint_id"] = apply_diff.endpoint_id
        diffs.append(_drop_none(plan_diff))
    return diffs


def build_firewall_apply_diff(row: Any) -> FirewallApplyDiff | None:
    """Build one proxbox-api ApplyDiff for a firewall ChangeDiff row."""
    op = _row_op(row)
    if op not in _SUPPORTED_OPS:
        return None

    model_name = _row_model_name(row)
    obj = _row_object(row)
    data = _row_data(row, op)
    action = _action_for(model_name, op)
    if action is None:
        return None

    payload = _firewall_payload(model_name, op, action, obj, data)
    if payload is None:
        return None

    diff = {
        "op": op,
        "kind": "firewall",
        "netbox_id": _row_object_id(row, obj),
        "payload": payload,
    }
    return FirewallApplyDiff(
        diff=_drop_none(diff),
        endpoint_id=_endpoint_id_for(obj, data),
        obj=obj,
    )


def firewall_result_key(row: Any, fallback: int) -> str:
    """Stable result key for a firewall ChangeDiff row."""
    model_name = _row_model_name(row) or "firewall"
    identifier = _row_object_id(row, _row_object(row)) or _row_name(row) or fallback
    return f"firewall:{model_name}:{identifier}"


def unsupported_firewall_diff_message(row: Any) -> str:
    """Return a user-facing message for unsupported firewall intent rows."""
    return (
        f"Firewall intent for {_row_model_name(row) or 'object'} "
        f"{_row_op(row)!r} is not supported by proxbox-api apply."
    )


def first_endpoint_id_from_diffs(diffs: list[dict[str, Any]]) -> int | None:
    """Return the first endpoint_id embedded in classified diffs."""
    for diff in diffs:
        endpoint_id = _int_or_none(diff.get("endpoint_id"))
        if endpoint_id is not None:
            return endpoint_id
    return None


def default_proxmox_endpoint_id() -> int | None:
    """Best-effort default ProxmoxEndpoint ID for legacy intent paths."""
    try:
        from netbox_proxbox.models import ProxmoxEndpoint  # noqa: PLC0415
    except Exception:  # pragma: no cover - defensive import guard
        return None

    try:
        endpoint = ProxmoxEndpoint.objects.filter(allow_writes=True).first()
        if endpoint is None:
            endpoint = ProxmoxEndpoint.objects.first()
    except Exception:  # pragma: no cover - test stubs may be partial
        return None
    return _object_id(endpoint)


def _firewall_payload(
    model_name: str,
    op: str,
    action: str,
    obj: object | None,
    data: dict[str, Any],
) -> dict[str, Any] | None:
    body = {} if op == "delete" else _body_for(model_name, op, obj, data)
    payload: dict[str, Any] = {
        "action": action,
        "zone": _zone_for(model_name, obj, data),
        "node": _node_for(model_name, obj, data),
        "vmid": _vmid_for(model_name, obj, data),
        "vm_type": _vm_type_for(model_name, obj, data),
        "vnet": _vnet_for(model_name, obj, data),
        "group": _group_for(model_name, obj, data),
        "pos": _int_or_none(_field(obj, data, "pos")),
        "name": _name_for(model_name, obj, data),
        "cidr": _field(obj, data, "cidr"),
        "body": body,
    }
    return _drop_none(payload)


def _action_for(model_name: str, op: str) -> str | None:
    if model_name == "proxmoxfirewallrule":
        return f"firewall.rule.{op}"
    if model_name == "proxmoxfirewallsecuritygroup":
        if op in {"create", "delete"}:
            return f"firewall.group.{op}"
        return None
    if model_name == "proxmoxfirewallipset":
        if op in {"create", "delete"}:
            return f"firewall.ipset.{op}"
        return None
    if model_name == "proxmoxfirewallipsetentry":
        return f"firewall.ipset.entry.{op}"
    if model_name == "proxmoxfirewallalias":
        return f"firewall.alias.{op}"
    if model_name == "proxmoxfirewalloptions" and op in {"create", "update"}:
        return "firewall.options.update"
    return None


def _body_for(
    model_name: str,
    op: str,
    obj: object | None,
    data: dict[str, Any],
) -> dict[str, Any]:
    if obj is not None:
        if model_name == "proxmoxfirewallsecuritygroup":
            return _drop_empty(
                {
                    "group": getattr(obj, "name", None),
                    "comment": getattr(obj, "comment", None),
                }
            )
        if model_name == "proxmoxfirewallalias" and op == "update":
            body = _firewall_object_state(obj)
            body.pop("name", None)
            return body
        return _firewall_object_state(obj)

    if model_name == "proxmoxfirewallrule":
        return _drop_empty(
            {
                "pos": data.get("pos"),
                "type": data.get("rule_type") or data.get("type"),
                "action": data.get("action"),
                "enable": data.get("enable"),
                "macro": data.get("macro"),
                "iface": data.get("iface"),
                "source": data.get("source"),
                "dest": data.get("dest"),
                "proto": data.get("proto"),
                "dport": data.get("dport"),
                "sport": data.get("sport"),
                "log": data.get("log"),
                "icmp-type": data.get("icmp_type") or data.get("icmp-type"),
                "comment": data.get("comment"),
                "digest": data.get("digest"),
            }
        )
    if model_name == "proxmoxfirewallsecuritygroup":
        return _drop_empty({"group": data.get("name"), "comment": data.get("comment")})
    if model_name == "proxmoxfirewallipset":
        return _drop_empty({"name": data.get("name"), "comment": data.get("comment")})
    if model_name == "proxmoxfirewallipsetentry":
        return _drop_empty(
            {
                "cidr": data.get("cidr"),
                "comment": data.get("comment"),
                "nomatch": data.get("nomatch"),
            }
        )
    if model_name == "proxmoxfirewallalias":
        body = {
            "name": data.get("name"),
            "cidr": data.get("cidr"),
            "comment": data.get("comment"),
        }
        if op == "update":
            body.pop("name", None)
        return _drop_empty(body)
    if model_name == "proxmoxfirewalloptions":
        return _drop_empty(
            {
                "enable": data.get("enable"),
                "policy_in": data.get("policy_in"),
                "policy_out": data.get("policy_out"),
                "options": data.get("options") or {},
            }
        )
    return {}


def _zone_for(model_name: str, obj: object | None, data: dict[str, Any]) -> str | None:
    if model_name == "proxmoxfirewallsecuritygroup":
        return FirewallZoneChoices.DATACENTER
    if model_name in {"proxmoxfirewallrule", "proxmoxfirewalloptions"}:
        return _field(obj, data, "zone")
    if model_name in {"proxmoxfirewallipset", "proxmoxfirewallalias"}:
        return _zone_from_scope(_field(obj, data, "scope"))
    if model_name == "proxmoxfirewallipsetentry":
        ipset = _related(obj, data, "ipset")
        return _zone_from_scope(_field(ipset, data, "scope"))
    return None


def _zone_from_scope(scope: object) -> str | None:
    if scope == FirewallScopeChoices.DATACENTER:
        return FirewallZoneChoices.DATACENTER
    if scope == FirewallScopeChoices.VM_QEMU:
        return FirewallZoneChoices.VM_QEMU
    if scope == FirewallScopeChoices.VM_LXC:
        return FirewallZoneChoices.VM_LXC
    return str(scope) if scope not in (None, "") else None


def _node_for(model_name: str, obj: object | None, data: dict[str, Any]) -> str | None:
    zone = _zone_for(model_name, obj, data)
    if zone == FirewallZoneChoices.NODE:
        return _object_name(_related(obj, data, "proxmox_node")) or _str_or_none(
            data.get("node")
        )
    if zone in {FirewallZoneChoices.VM_QEMU, FirewallZoneChoices.VM_LXC}:
        return _vm_node(_vm_for(model_name, obj, data), data)
    return None


def _vmid_for(model_name: str, obj: object | None, data: dict[str, Any]) -> int | None:
    zone = _zone_for(model_name, obj, data)
    if zone in {FirewallZoneChoices.VM_QEMU, FirewallZoneChoices.VM_LXC}:
        return _vmid(_vm_for(model_name, obj, data), data)
    return None


def _vm_type_for(
    model_name: str, obj: object | None, data: dict[str, Any]
) -> str | None:
    zone = _zone_for(model_name, obj, data)
    if zone == FirewallZoneChoices.VM_QEMU:
        return "qemu"
    if zone == FirewallZoneChoices.VM_LXC:
        return "lxc"
    return None


def _vnet_for(model_name: str, obj: object | None, data: dict[str, Any]) -> str | None:
    if _zone_for(model_name, obj, data) == FirewallZoneChoices.VNET:
        return _str_or_none(_field(obj, data, "iface"))
    return None


def _group_for(model_name: str, obj: object | None, data: dict[str, Any]) -> str | None:
    if model_name == "proxmoxfirewallsecuritygroup":
        return _str_or_none(_field(obj, data, "name"))
    if _zone_for(model_name, obj, data) == FirewallZoneChoices.SECURITY_GROUP:
        return _object_name(_related(obj, data, "security_group")) or _str_or_none(
            data.get("group")
        )
    return None


def _name_for(model_name: str, obj: object | None, data: dict[str, Any]) -> str | None:
    if model_name == "proxmoxfirewallipsetentry":
        ipset = _related(obj, data, "ipset")
        return _object_name(ipset) or _str_or_none(data.get("ipset_name"))
    return _str_or_none(_field(obj, data, "name"))


def _vm_for(model_name: str, obj: object | None, data: dict[str, Any]) -> object | None:
    if model_name == "proxmoxfirewallipsetentry":
        ipset = _related(obj, data, "ipset")
        vm = _related(ipset, data, "virtual_machine")
        return vm if vm is not None else _related(obj, data, "virtual_machine")
    return _related(obj, data, "virtual_machine")


def _firewall_object_state(obj: object) -> dict[str, Any]:
    from netbox_proxbox.intent.firewall_common import (  # noqa: PLC0415
        firewall_object_state,
    )

    return firewall_object_state(obj)


def _resolve_firewall_endpoint(obj: object) -> object | None:
    from netbox_proxbox.intent.firewall_common import (  # noqa: PLC0415
        resolve_firewall_endpoint,
    )

    return resolve_firewall_endpoint(obj)


def _endpoint_id_for(obj: object | None, data: dict[str, Any]) -> int | None:
    if obj is not None:
        try:
            endpoint = _resolve_firewall_endpoint(obj)
        except Exception:  # noqa: BLE001
            endpoint = None
        endpoint_id = _object_id(endpoint)
        if endpoint_id is not None:
            return endpoint_id

    for key in ("endpoint_id", "endpoint"):
        endpoint_id = _object_id(data.get(key))
        if endpoint_id is not None:
            return endpoint_id
    return None


def _row_op(row: Any) -> str:
    action = str(getattr(row, "action", "") or "").lower()
    if action in _SUPPORTED_OPS:
        return action
    prechange_data = getattr(row, "prechange_data", None)
    postchange_data = getattr(row, "postchange_data", None)
    if prechange_data is None and isinstance(postchange_data, dict):
        return "create"
    if isinstance(prechange_data, dict) and postchange_data is None:
        return "delete"
    return "update"


def _row_data(row: Any, op: str) -> dict[str, Any]:
    preferred = "prechange_data" if op == "delete" else "postchange_data"
    fallback = "postchange_data" if preferred == "prechange_data" else "prechange_data"
    data = getattr(row, preferred, None)
    if isinstance(data, dict):
        return data
    data = getattr(row, fallback, None)
    return data if isinstance(data, dict) else {}


def _row_model_name(row: Any) -> str:
    object_type = getattr(row, "object_type", None)
    model = getattr(object_type, "model", None)
    if model:
        return str(model).lower()
    obj = _row_object(row)
    meta = getattr(obj, "_meta", None)
    model_name = getattr(meta, "model_name", None)
    if model_name:
        return str(model_name).lower()
    return str(getattr(row, "model", "") or "").lower()


def _row_object(row: Any) -> object | None:
    return getattr(row, "object", None)


def _row_object_id(row: Any, obj: object | None) -> int | None:
    return _int_or_none(getattr(row, "object_id", None)) or _object_id(obj)


def _row_name(row: Any) -> str | None:
    return _str_or_none(getattr(row, "object_repr", None))


def _field(obj: object | None, data: dict[str, Any], *names: str) -> Any:
    for name in names:
        if isinstance(obj, dict) and obj.get(name) not in (None, ""):
            return obj[name]
        if obj is not None and hasattr(obj, name):
            value = getattr(obj, name)
            if value not in (None, ""):
                return value
        if name in data and data[name] not in (None, ""):
            return data[name]
    return None


def _related(obj: object | None, data: dict[str, Any], name: str) -> object | None:
    value = _field(obj, data, name)
    if value is not None:
        return value
    return data.get(f"{name}_id")


def _object_name(value: object | None) -> str | None:
    if isinstance(value, dict):
        return _str_or_none(value.get("name") or value.get("display"))
    return _str_or_none(getattr(value, "name", None) or value)


def _object_id(value: object | None) -> int | None:
    if isinstance(value, dict):
        return _int_or_none(value.get("id") or value.get("pk"))
    return _int_or_none(
        getattr(value, "pk", None) or getattr(value, "id", None) or value
    )


def _vmid(vm: object | None, data: dict[str, Any]) -> int | None:
    cf = _custom_fields(vm)
    return _int_or_none(
        cf.get("proxmox_vm_id")
        or cf.get("cf_proxmox_vm_id")
        or data.get("vmid")
        or data.get("proxmox_vm_id")
    )


def _vm_node(vm: object | None, data: dict[str, Any]) -> str | None:
    device = getattr(vm, "device", None)
    if device is not None and getattr(device, "name", None):
        return str(device.name)
    cf = _custom_fields(vm)
    return _str_or_none(
        cf.get("proxmox_node")
        or cf.get("cf_proxmox_node")
        or data.get("node")
        or data.get("proxmox_node")
    )


def _custom_fields(value: object | None) -> dict[str, Any]:
    if isinstance(value, dict):
        cf = value.get("custom_field_data") or value.get("custom_fields")
    else:
        cf = getattr(value, "custom_field_data", None)
    return cf if isinstance(cf, dict) else {}


def _str_or_none(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _int_or_none(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _drop_none(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _drop_empty(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value not in (None, "")}
