"""Sync parameter resolution and serialization helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from netbox_proxbox.choices import SyncTypeChoices
from netbox_proxbox.constants import OVERWRITE_FIELDS
from netbox_proxbox.sync_types import (
    _TARGETED_VM_JOB_NAME_RE,
    _TARGETED_VM_SYNC_TYPES,
    normalize_sync_types,
)

if TYPE_CHECKING:
    from netbox.jobs import Job
    from virtualization.models import VirtualMachine

    from netbox_proxbox.models import (
        ProxmoxStorage,
        VMBackup,
        VMSnapshot,
        VMTaskHistory,
    )


def _use_guest_agent_interface_name_setting() -> bool:
    """Return current plugin setting for guest-agent VM interface naming."""
    try:
        from netbox_proxbox.models import ProxboxPluginSettings

        return bool(ProxboxPluginSettings.get_solo().use_guest_agent_interface_name)
    except (ImportError, RuntimeError):
        return True


def _proxbox_fetch_max_concurrency_setting() -> int:
    """Return fetch concurrency setting for proxbox-api data collection."""
    try:
        from netbox_proxbox.models import ProxboxPluginSettings

        value = int(ProxboxPluginSettings.get_solo().proxbox_fetch_max_concurrency)
        return max(1, value)
    except (ImportError, RuntimeError, ValueError):
        return 8


def _ignore_ipv6_link_local_addresses_setting() -> bool:
    """Return current plugin setting for ignoring IPv6 link-local addresses."""
    try:
        from netbox_proxbox.models import ProxboxPluginSettings

        return bool(ProxboxPluginSettings.get_solo().ignore_ipv6_link_local_addresses)
    except (ImportError, RuntimeError):
        return True


def _primary_ip_preference_setting() -> str:
    """Return plugin setting for preferred primary IP family."""
    try:
        from netbox_proxbox.models import ProxboxPluginSettings

        value = (
            str(ProxboxPluginSettings.get_solo().primary_ip_preference or "ipv4")
            .strip()
            .lower()
        )
        return "ipv6" if value == "ipv6" else "ipv4"
    except (ImportError, RuntimeError):
        return "ipv4"


def _parse_description_metadata_setting() -> bool:
    """Return plugin setting for description-metadata JSON parsing (opt-in)."""
    try:
        from netbox_proxbox.models import ProxboxPluginSettings

        return bool(ProxboxPluginSettings.get_solo().parse_description_metadata)
    except (ImportError, RuntimeError, AttributeError):
        return False


def _overwrite_device_role_setting() -> bool:
    """Return plugin setting for whether sync should overwrite the device role."""
    try:
        from netbox_proxbox.models import ProxboxPluginSettings

        return bool(ProxboxPluginSettings.get_solo().overwrite_device_role)
    except (ImportError, RuntimeError, AttributeError):
        return True


def _overwrite_device_type_setting() -> bool:
    """Return plugin setting for whether sync should overwrite the device type."""
    try:
        from netbox_proxbox.models import ProxboxPluginSettings

        return bool(ProxboxPluginSettings.get_solo().overwrite_device_type)
    except (ImportError, RuntimeError, AttributeError):
        return True


def _overwrite_device_tags_setting() -> bool:
    """Return plugin setting for whether sync should overwrite device tags."""
    try:
        from netbox_proxbox.models import ProxboxPluginSettings

        return bool(ProxboxPluginSettings.get_solo().overwrite_device_tags)
    except (ImportError, RuntimeError, AttributeError):
        return True


def _overwrite_vm_role_setting() -> bool:
    """Return plugin setting for whether sync should overwrite the VM role."""
    try:
        from netbox_proxbox.models import ProxboxPluginSettings

        return bool(ProxboxPluginSettings.get_solo().overwrite_vm_role)
    except (ImportError, RuntimeError, AttributeError):
        return True


def _overwrite_vm_tags_setting() -> bool:
    """Return plugin setting for whether sync should overwrite VM tags."""
    try:
        from netbox_proxbox.models import ProxboxPluginSettings

        return bool(ProxboxPluginSettings.get_solo().overwrite_vm_tags)
    except (ImportError, RuntimeError, AttributeError):
        return True


def _global_overwrites() -> dict[str, bool]:
    """Return overwrite flags from the global plugin settings singleton."""
    try:
        from netbox_proxbox.models import ProxboxPluginSettings

        settings = ProxboxPluginSettings.get_solo()
        return {name: bool(getattr(settings, name)) for name in OVERWRITE_FIELDS}
    except (ImportError, RuntimeError, AttributeError):
        return {name: True for name in OVERWRITE_FIELDS}


def effective_overwrites_for_endpoint(
    proxmox_endpoint_id: int | str | None,
) -> dict[str, bool]:
    """Resolve overwrite flags for a single endpoint, falling back to global when unset.

    When ``proxmox_endpoint_id`` is ``None`` or the endpoint cannot be loaded the
    result mirrors the global ProxboxPluginSettings singleton, so non-endpoint
    contexts behave exactly like before this helper existed.
    """
    if proxmox_endpoint_id in (None, "", 0, "0"):
        return _global_overwrites()
    try:
        from netbox_proxbox.models import ProxmoxEndpoint

        endpoint = ProxmoxEndpoint.objects.filter(pk=int(proxmox_endpoint_id)).first()
    except (ImportError, RuntimeError, ValueError, TypeError):
        return _global_overwrites()
    if endpoint is None:
        return _global_overwrites()
    return {
        name: bool(value) for name, value in endpoint.effective_overwrites().items()
    }


def effective_tenant_regex_for_endpoint(
    proxmox_endpoint_id: int | str | None,
) -> tuple[bool, list[dict]]:
    """Resolve (enabled, rules) for tenant-regex assignment on a given endpoint.

    The endpoint can override both the toggle and the rule list. When an
    endpoint's rule list is non-null it **replaces** the global list. Any
    failure to load returns the global values, mirroring
    ``effective_overwrites_for_endpoint``.
    """
    try:
        from netbox_proxbox.models import ProxboxPluginSettings
    except (ImportError, RuntimeError):
        return False, []
    try:
        settings_obj = ProxboxPluginSettings.get_solo()
    except Exception:
        return False, []
    enabled = bool(getattr(settings_obj, "enable_tenant_name_regex", False))
    rules_value = getattr(settings_obj, "tenant_name_regex_rules", None) or []
    rules: list[dict] = list(rules_value) if isinstance(rules_value, list) else []

    if proxmox_endpoint_id in (None, "", 0, "0"):
        return enabled, rules
    try:
        from netbox_proxbox.models import ProxmoxEndpoint

        endpoint = ProxmoxEndpoint.objects.filter(pk=int(proxmox_endpoint_id)).first()
    except (ImportError, RuntimeError, ValueError, TypeError):
        return enabled, rules
    if endpoint is None:
        return enabled, rules
    ep_enabled = getattr(endpoint, "enable_tenant_name_regex", None)
    if ep_enabled is not None:
        enabled = bool(ep_enabled)
    ep_rules = getattr(endpoint, "tenant_name_regex_rules", None)
    if ep_rules is not None:
        rules = list(ep_rules) if isinstance(ep_rules, list) else []
    return enabled, rules


def _serialize_sync_params(
    *,
    sync_types: list[str],
    proxmox_endpoint_ids: list[str],
    netbox_endpoint_ids: list[str],
    netbox_vm_ids: list[str],
    batch_object_type: str | None = None,
    batch_object_ids: list[str] | None = None,
    fastapi_endpoint_id: int | None = None,
    run_id: str | None = None,
) -> dict[str, object]:
    """Return a backward-compatible params block for Job.data."""
    if len(sync_types) == 1:
        sync_type = sync_types[0]
    elif netbox_vm_ids:
        sync_type = SyncTypeChoices.VIRTUAL_MACHINES
    else:
        sync_type = SyncTypeChoices.ALL

    result = {
        "sync_types": list(sync_types),
        "sync_type": sync_type,
        "proxmox_endpoint_ids": list(proxmox_endpoint_ids),
        "netbox_endpoint_ids": list(netbox_endpoint_ids),
        "netbox_vm_ids": list(netbox_vm_ids),
        "batch_object_type": batch_object_type,
        "batch_object_ids": list(batch_object_ids or []),
    }
    if fastapi_endpoint_id is not None:
        result["fastapi_endpoint_id"] = fastapi_endpoint_id
    if run_id:
        result["run_id"] = run_id
    return result


def _infer_targeted_vm_job_params(job: Job) -> dict[str, object] | None:
    """Infer targeted VM params from a legacy job row name when explicit params are absent."""
    name = str(getattr(job, "name", "") or "").strip()
    match = _TARGETED_VM_JOB_NAME_RE.match(name)
    if not match:
        return None
    vm_id = match.group(1)
    return {
        "sync_types": list(_TARGETED_VM_SYNC_TYPES),
        "proxmox_endpoint_ids": [],
        "netbox_endpoint_ids": [],
        "netbox_vm_ids": [vm_id],
    }


def _normalize_batch_object_ids(object_ids: list[str] | None) -> list[str]:
    """Return a cleaned list of selected object IDs."""
    return [str(object_id) for object_id in list(object_ids or []) if str(object_id)]


def _resolve_vm_cluster_name(vm: VirtualMachine) -> str:
    """Derive a Proxmox cluster name from a NetBox VM record."""
    from netbox_proxbox.models import ProxmoxCluster

    cluster = getattr(vm, "cluster", None)
    if cluster is None:
        return ""
    proxmox_cluster = ProxmoxCluster.objects.filter(netbox_cluster=cluster).first()
    if proxmox_cluster is not None:
        return str(proxmox_cluster.name)
    return str(getattr(cluster, "name", "") or "")


def _resolve_vm_node(vm: VirtualMachine) -> str:
    """Derive the best-effort Proxmox node name for a NetBox VM."""
    device = getattr(vm, "device", None)
    if device is not None and getattr(device, "name", None):
        return str(device.name)

    custom_field_data = getattr(vm, "custom_field_data", None) or {}
    node = custom_field_data.get("proxmox_node") or custom_field_data.get(
        "cf_proxmox_node", ""
    )
    return str(node or "")


def _resolve_vm_type(vm: VirtualMachine) -> str:
    vm_type_obj = getattr(vm, "virtual_machine_type", None)
    if vm_type_obj and hasattr(vm_type_obj, "slug"):
        slug = str(vm_type_obj.slug)
        if "lxc" in slug:
            return "lxc"
        if "qemu" in slug:
            return "qemu"
    custom_field_data = getattr(vm, "custom_field_data", None) or {}
    return str(
        custom_field_data.get("proxmox_vm_type")
        or custom_field_data.get("cf_proxmox_vm_type")
        or "qemu"
    )


def _resolve_vm_vmid(vm: VirtualMachine) -> str:
    custom_field_data = getattr(vm, "custom_field_data", None) or {}
    vmid = custom_field_data.get("proxmox_vm_id") or custom_field_data.get(
        "cf_proxmox_vm_id"
    )
    return str(vmid or "")


def _resolve_storage_nodes(storage: ProxmoxStorage) -> str:
    """Return a best-effort Proxmox node name for a storage-backed row."""
    nodes = getattr(storage, "nodes", None)
    if not nodes:
        return ""
    first = str(nodes).split(",", 1)[0].strip()
    return first


def _resolve_vm_batch_params(vm: VirtualMachine) -> dict[str, object]:
    """Build individual VM sync parameters."""
    cluster_name = _resolve_vm_cluster_name(vm)
    node = _resolve_vm_node(vm)
    vm_type = _resolve_vm_type(vm)
    vmid = _resolve_vm_vmid(vm)
    if not cluster_name or not node or not vmid:
        return {"error": "Missing VM sync context.", "status": 422}
    return {
        "path": "sync/individual/vm",
        "query_params": {
            "cluster_name": cluster_name,
            "node": node,
            "type": vm_type,
            "vmid": vmid,
        },
    }


def _resolve_vm_backup_batch_params(backup: VMBackup) -> dict[str, object]:
    """Build individual backup sync parameters."""
    storage_obj = getattr(backup, "proxmox_storage", None)
    vm_obj = getattr(backup, "virtual_machine", None)
    if storage_obj is None or vm_obj is None:
        return {"error": "Missing backup sync context.", "status": 422}

    cluster_name = str(getattr(getattr(storage_obj, "cluster", None), "name", "") or "")
    node = _resolve_storage_nodes(storage_obj) or _resolve_vm_node(vm_obj)
    vmid = str(
        getattr(backup, "vmid", None)
        or getattr(getattr(vm_obj, "custom_field_data", None), "get", lambda *_: None)(
            "proxmox_vm_id"
        )
        or _resolve_vm_vmid(vm_obj)
        or ""
    )
    volume_id = str(getattr(backup, "volume_id", None) or "")
    storage_name = str(
        getattr(backup, "storage", None) or getattr(storage_obj, "name", "") or ""
    )

    if not cluster_name or not node or not vmid or not storage_name or not volume_id:
        return {"error": "Missing backup sync context.", "status": 422}

    return {
        "path": "sync/individual/backup",
        "query_params": {
            "cluster_name": cluster_name,
            "node": node,
            "storage": storage_name,
            "vmid": vmid,
            "volid": volume_id,
        },
    }


def _resolve_vm_snapshot_batch_params(snapshot: VMSnapshot) -> dict[str, object]:
    """Build individual snapshot sync parameters."""
    vm_obj = getattr(snapshot, "virtual_machine", None)
    if vm_obj is None:
        return {"error": "Missing snapshot sync context.", "status": 422}

    cluster_name = _resolve_vm_cluster_name(vm_obj)
    node = str(getattr(snapshot, "node", None) or _resolve_vm_node(vm_obj) or "")
    vm_type = _resolve_vm_type(vm_obj)
    vmid = str(getattr(snapshot, "vmid", None) or _resolve_vm_vmid(vm_obj) or "")
    snapshot_name = str(getattr(snapshot, "name", None) or "")

    if not cluster_name or not node or not vmid or not snapshot_name:
        return {"error": "Missing snapshot sync context.", "status": 422}

    query_params: dict[str, object] = {
        "cluster_name": cluster_name,
        "node": node,
        "type": vm_type,
        "vmid": vmid,
        "snapshot_name": snapshot_name,
    }
    storage_obj = getattr(snapshot, "proxmox_storage", None)
    if storage_obj is not None and getattr(storage_obj, "name", None):
        query_params["storage_name"] = str(storage_obj.name)

    return {"path": "sync/individual/snapshot", "query_params": query_params}


def _resolve_storage_batch_params(storage: ProxmoxStorage) -> dict[str, object]:
    """Build individual storage sync parameters."""
    cluster = getattr(storage, "cluster", None)
    cluster_name = str(getattr(cluster, "name", "") or "")
    storage_name = str(getattr(storage, "name", None) or "")
    if not cluster_name or not storage_name:
        return {"error": "Missing storage sync context.", "status": 422}

    return {
        "path": "sync/individual/storage",
        "query_params": {
            "cluster_name": cluster_name,
            "storage_name": storage_name,
        },
    }


def _resolve_task_history_batch_params(
    task_history: VMTaskHistory,
) -> dict[str, object]:
    """Build individual task history sync parameters."""
    vm_obj = getattr(task_history, "virtual_machine", None)
    if vm_obj is None:
        return {"error": "Missing task-history sync context.", "status": 422}

    node = str(getattr(task_history, "node", None) or _resolve_vm_node(vm_obj) or "")
    vm_type = str(
        getattr(task_history, "vm_type", None) or _resolve_vm_type(vm_obj) or "qemu"
    )
    vmid = str(getattr(task_history, "vmid", None) or _resolve_vm_vmid(vm_obj) or "")
    upid = str(getattr(task_history, "upid", None) or "")
    cluster_name = _resolve_vm_cluster_name(vm_obj)

    if not node or not vmid:
        return {"error": "Missing task-history sync context.", "status": 422}

    query_params: dict[str, object] = {
        "node": node,
        "vm_type": vm_type,
        "vmid": vmid,
    }
    if upid:
        query_params["upid"] = upid
    if cluster_name:
        query_params["cluster_name"] = cluster_name

    return {"path": "sync/individual/task-history", "query_params": query_params}
