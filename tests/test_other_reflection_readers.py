"""Reader contracts for the remaining typed-sidecar cutover."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "netbox_proxbox"
READER_PATH = PACKAGE_ROOT / "sync_state_readers.py"
STORAGE_VIEW_PATH = PACKAGE_ROOT / "views" / "storage.py"

REMOVED_NAMES = {
    "hardware_chassis_manufacturer",
    "hardware_chassis_product",
    "hardware_chassis_serial",
    "nic_duplex",
    "nic_link",
    "nic_speed_gbps",
    "proxmox_cluster_id",
    "proxmox_cluster_name",
    "proxmox_cluster_status",
    "proxmox_interface",
    "proxmox_ip_addresses",
    "proxmox_mac",
    "proxmox_vlan_id",
    "proxbox_bridge",
    "proxbox_storage_id",
    "proxmox_cluster",
    "proxmox_cpu_type",
    "proxmox_device_names",
    "proxmox_disk",
    "proxmox_interfaces",
    "proxmox_link",
    "proxmox_notes",
    "proxmox_os",
    "proxmox_storage_ids",
    "proxmox_storage_names",
    "proxmox_tags",
    "proxmox_tcp_states",
    "proxmox_vmid",
    "proxbox_last_run_id",
    "proxmox_last_updated",
}


def _load_reader():
    spec = importlib.util.spec_from_file_location("_sync_state_readers", READER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _QuerySpy:
    def __init__(self) -> None:
        self.filters = []

    def filter(self, **kwargs):
        self.filters.append(kwargs)
        return self


def test_virtual_disk_storage_reader_uses_the_typed_relation_without_custom_fields():
    module = _load_reader()
    queryset = _QuerySpy()
    storage = object()

    assert module.virtual_disks_for_storage(queryset, storage) is queryset
    assert queryset.filters == [
        {"proxbox_sync_state__proxbox_storage": storage},
    ]


def test_every_storage_surface_uses_the_canonical_typed_reader():
    tree = ast.parse(STORAGE_VIEW_PATH.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "virtual_disks_for_storage"
    ]
    assert len(calls) == 3


def test_package_has_no_live_removed_reflection_custom_field_lookup():
    for path in PACKAGE_ROOT.rglob("*.py"):
        if "migrations" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg:
                for name in REMOVED_NAMES:
                    assert node.arg not in {
                        f"custom_field_data__{name}",
                        f"custom_field_data__cf_{name}",
                    }, f"{path}: {node.arg}"
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "_cf_value"
                ):
                    for argument in node.args[1:]:
                        if isinstance(argument, ast.Constant) and isinstance(
                            argument.value, str
                        ):
                            assert argument.value.removeprefix("cf_") not in (
                                REMOVED_NAMES
                            ), f"{path}: live reflection lookup for {argument.value}"
                continue
            receiver = node.func.value
            is_custom_field_mapping = (
                isinstance(receiver, ast.Name)
                and receiver.id in {"cf", "custom_fields", "custom_field_data"}
            ) or (
                isinstance(receiver, ast.Attribute)
                and receiver.attr == "custom_field_data"
            )
            if is_custom_field_mapping:
                looked_up = node.args[0].value.removeprefix("cf_")
                assert looked_up not in REMOVED_NAMES, (
                    f"{path}: live reflection lookup for {node.args[0].value}"
                )
