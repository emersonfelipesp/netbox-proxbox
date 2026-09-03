"""Source guards for the VM reflection typed-sidecar cutover."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
from types import SimpleNamespace


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "netbox_proxbox"
INTENT_DEFINITIONS_PATH = PACKAGE_ROOT / "migrations" / "_v0_0_16_release_data.py"

RESOLVER_READERS = (
    "views/operational.py",
    "views/vm_ha.py",
    "views/vm_config.py",
    "views/sync_now/vm.py",
    "intent/firewall_common.py",
    "intent/firewall_payload.py",
    "intent/payload.py",
    "intent/snapshot.py",
    "sync_params.py",
)

# `template_content.py` is deliberately absent. It no longer resolves VM
# reflection identity at all: its only remaining read is the console gate, which
# uses a stricter authoritative-sidecar check than the generic resolver -- an
# unknown VM type must disqualify the console, whereas the generic resolver
# defaults to "qemu". Routing it through the resolver would loosen a security
# gate to satisfy a source assertion. The package-wide lookup guard below still
# covers this file, which is what actually matters here.

REMOVED_LOOKUPS = (
    'custom_field_data.get("proxmox_vm_id")',
    'custom_field_data.get("cf_proxmox_vm_id")',
    'custom_field_data.get("proxmox_vm_type")',
    'custom_field_data.get("cf_proxmox_vm_type")',
    "custom_field_data__proxmox_vm_id",
    "custom_field_data__proxmox_vm_type",
    "custom_field_data__cf_proxmox_vm_type",
)


def test_every_vm_reflection_reader_uses_the_canonical_resolver() -> None:
    for relative_path in RESOLVER_READERS:
        source = (PACKAGE_ROOT / relative_path).read_text()
        assert "netbox_proxbox.vm_identity" in source, relative_path


def test_package_has_no_live_vm_reflection_custom_field_lookup() -> None:
    for path in PACKAGE_ROOT.rglob("*.py"):
        if "migrations" in path.parts:
            continue
        source = path.read_text()
        for removed_lookup in REMOVED_LOOKUPS:
            assert removed_lookup not in source, f"{path}: {removed_lookup}"


def test_intent_payloads_use_the_plugin_owned_model_fields() -> None:
    payload = (PACKAGE_ROOT / "intent" / "payload.py").read_text()
    snapshot = (PACKAGE_ROOT / "intent" / "snapshot.py").read_text()

    for required in (
        "target_node",
        "target_storage",
        "iso",
        "template_vmid",
        "swap",
        "rootfs",
        "ostemplate",
        "cloud_init_user",
        "cloud_init_ssh_keys",
        "cloud_init_user_data",
        "cloud_init_network",
    ):
        assert required in payload
    assert '"custom_field_data": custom_fields' in snapshot
    assert '"intent": _intent_snapshot(vm)' in snapshot
    assert "custom_field_data" not in payload
    assert "proxmox_vm_id" not in payload
    assert "proxmox_vm_id" not in snapshot


def _load_intent_module(monkeypatch, name: str):
    root = types.ModuleType("netbox_proxbox")
    root.__path__ = [str(PACKAGE_ROOT)]
    intent = types.ModuleType("netbox_proxbox.intent")
    intent.__path__ = [str(PACKAGE_ROOT / "intent")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", root)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.intent", intent)
    monkeypatch.setitem(
        sys.modules,
        "netbox_proxbox.vm_identity",
        SimpleNamespace(
            resolve_vm_vmid=lambda vm: str(
                getattr(vm.proxbox_sync_state, "proxmox_vm_id", "") or ""
            ),
            resolve_vm_node=lambda vm: str(
                getattr(vm.proxbox_sync_state, "proxmox_node_name", "") or ""
            ),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "netbox_proxbox.intent.description_metadata",
        SimpleNamespace(build_description_with_metadata=lambda vm, value: value),
    )
    module_name = f"_typed_{name}_under_test"
    spec = importlib.util.spec_from_file_location(
        module_name,
        PACKAGE_ROOT / "intent" / f"{name}.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_intent_definitions():
    spec = importlib.util.spec_from_file_location(
        "_intent_definitions_under_test",
        INTENT_DEFINITIONS_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_intent_payload_reads_vmid_from_sidecar_and_keeps_intent_fields(
    monkeypatch,
) -> None:
    module = _load_intent_module(monkeypatch, "payload")
    vm = SimpleNamespace(
        proxbox_sync_state=SimpleNamespace(proxmox_vm_id=701),
        proxbox_intent=SimpleNamespace(
            iso="local:iso/debian.iso",
            cloud_init_user="debian",
        ),
        custom_field_data={},
        name="vm-701",
        vcpus=2,
        memory=2048,
        description="typed payload",
    )

    payload = module.build_vm_payload(vm)

    assert payload["vmid"] == 701
    assert payload["iso"] == "local:iso/debian.iso"
    assert payload["cloud_init"] == {"user": "debian"}


def test_intent_snapshot_reads_vmid_from_sidecar_with_empty_custom_fields(
    monkeypatch,
) -> None:
    module = _load_intent_module(monkeypatch, "snapshot")
    vm = SimpleNamespace(
        vmid=None,
        proxbox_sync_state=SimpleNamespace(
            proxmox_vm_id=702, proxmox_node_name="pve-a"
        ),
        custom_field_data={},
        name="vm-702",
        tags=None,
        interfaces=None,
        vminterface_set=None,
        virtual_disks=None,
        primary_ip4=None,
        primary_ip6=None,
    )

    snapshot = module.build_metadata_snapshot(vm)

    assert snapshot["vmid"] == 702
    assert snapshot["node"] == "pve-a"
    assert snapshot["custom_field_data"] == {}
    assert snapshot["intent"] == {}


def test_target_node_and_storage_are_read_from_the_intent_model(
    monkeypatch,
) -> None:
    payload_module = _load_intent_module(monkeypatch, "payload")
    vm = SimpleNamespace(
        proxbox_sync_state=SimpleNamespace(
            proxmox_vm_id=703, proxmox_node_name="pve-reflected"
        ),
        proxbox_intent=SimpleNamespace(
            target_node="pve-intent",
            target_storage="ceph-intent",
        ),
        custom_field_data={},
        name="vm-703",
        vcpus=4,
        memory=4096,
        description="dual-role intent",
        tags=None,
        virtual_disks=None,
    )

    assert payload_module.build_vm_payload(vm)["node"] == "pve-intent"
    assert payload_module.build_vm_payload(vm)["storage"] == "ceph-intent"
    assert payload_module.build_lxc_payload(vm)["node"] == "pve-intent"
    assert payload_module.build_lxc_payload(vm)["storage"] == "ceph-intent"

    snapshot_module = _load_intent_module(monkeypatch, "snapshot")
    vm.cores = 4
    vm.interfaces = None
    vm.vminterface_set = None
    vm.primary_ip4 = None
    vm.primary_ip6 = None
    snapshot = snapshot_module.build_metadata_snapshot(vm)
    assert snapshot["node"] == "pve-reflected"
