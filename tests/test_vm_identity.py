"""Behavior tests for the canonical typed VM identity resolver."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "netbox_proxbox" / "vm_identity.py"


@pytest.fixture
def vm_identity():
    spec = importlib.util.spec_from_file_location(
        "_vm_identity_under_test", MODULE_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _vm(**state_values):
    return SimpleNamespace(
        device=None,
        cluster=None,
        virtual_machine_type=None,
        proxbox_sync_state=SimpleNamespace(**state_values),
        custom_field_data={},
    )


def test_resolvers_read_every_identity_value_from_typed_state(vm_identity):
    node = SimpleNamespace(name="pve-sidecar")
    cluster = SimpleNamespace(name="cluster-sidecar")
    vm = _vm(
        proxmox_vm_id=501,
        proxmox_vm_type="lxc",
        proxmox_node=node,
        proxmox_node_name="node-fallback",
        proxmox_cluster=cluster,
        proxmox_cluster_name="cluster-fallback",
    )

    assert vm_identity.resolve_vm_vmid(vm) == "501"
    assert vm_identity.resolve_known_vm_type(vm) == "lxc"
    assert vm_identity.resolve_vm_type(vm) == "lxc"
    assert vm_identity.resolve_vm_node(vm) == "pve-sidecar"
    assert vm_identity.resolve_vm_cluster_name(vm) == "cluster-sidecar"


def test_node_prefers_device_then_sidecar_fk_then_sidecar_name(vm_identity):
    vm = _vm(
        proxmox_node=SimpleNamespace(name="pve-fk"),
        proxmox_node_name="pve-name",
    )
    vm.device = SimpleNamespace(name="pve-device")
    assert vm_identity.resolve_vm_node(vm) == "pve-device"

    vm.device = None
    assert vm_identity.resolve_vm_node(vm) == "pve-fk"

    vm.proxbox_sync_state.proxmox_node = None
    assert vm_identity.resolve_vm_node(vm) == "pve-name"


def test_cluster_and_type_use_typed_fallbacks_without_custom_fields(vm_identity):
    vm = _vm(
        proxmox_cluster=None,
        proxmox_cluster_name="cluster-name",
        proxmox_vm_type="",
    )
    vm.virtual_machine_type = SimpleNamespace(slug="lxc-container")

    assert vm_identity.resolve_vm_cluster_name(vm) == "cluster-name"
    assert vm_identity.resolve_known_vm_type(vm) == "lxc"


def test_removed_custom_fields_are_never_identity_fallbacks(vm_identity):
    vm = _vm(
        proxmox_vm_id=None,
        proxmox_vm_type="",
        proxmox_node=None,
        proxmox_node_name="",
    )
    vm.custom_field_data = {
        "proxmox_vm_id": 999,
        "cf_proxmox_vm_id": 998,
        "proxmox_vm_type": "lxc",
        "cf_proxmox_vm_type": "lxc",
        "proxmox_node": "legacy-node",
        "cf_proxmox_node": "legacy-node-2",
    }

    assert vm_identity.resolve_vm_vmid(vm) == ""
    assert vm_identity.resolve_known_vm_type(vm) == ""
    assert vm_identity.resolve_vm_type(vm) == "qemu"
    assert vm_identity.resolve_vm_node(vm) == ""
