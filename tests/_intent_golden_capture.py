"""Load the intent modules without Django, for golden capture and replay.

`netbox_proxbox/__init__.py` imports `netbox.plugins`, so an ordinary import of
`netbox_proxbox.intent.payload` cannot run in the mocked suite. These helpers
exec-load the modules under stub parents instead, which is the same trick
`tests/test_templatetags.py` uses.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
INTENT_DIR = REPO_ROOT / "netbox_proxbox" / "intent"


def _install_package_stubs() -> None:
    if "netbox_proxbox" not in sys.modules:
        package = types.ModuleType("netbox_proxbox")
        package.__path__ = [str(REPO_ROOT / "netbox_proxbox")]
        sys.modules["netbox_proxbox"] = package
    if "netbox_proxbox.intent" not in sys.modules:
        intent = types.ModuleType("netbox_proxbox.intent")
        intent.__path__ = [str(INTENT_DIR)]
        sys.modules["netbox_proxbox.intent"] = intent

    # vm_identity is sidecar-only since the VM reflection cutover; the golden
    # fixtures drive it through explicit attributes, so a faithful stand-in is
    # enough and keeps Django out of the import path.
    name = "netbox_proxbox.vm_identity"
    if name not in sys.modules:
        module = types.ModuleType(name)

        def resolve_vm_vmid(vm: Any) -> Any:
            for attr in ("vmid", "proxmox_vm_id"):
                value = getattr(vm, attr, None)
                if value not in (None, ""):
                    return value
            state = getattr(vm, "proxbox_sync_state", None)
            return getattr(state, "proxmox_vm_id", None)

        def resolve_known_vm_type(vm: Any) -> str:
            state = getattr(vm, "proxbox_sync_state", None)
            value = str(getattr(state, "proxmox_vm_type", "") or "").lower()
            return value if value in {"qemu", "lxc"} else ""

        def resolve_vm_node(vm: Any) -> Any:
            device = getattr(vm, "device", None)
            name = getattr(device, "name", None)
            if name not in (None, ""):
                return name
            state = getattr(vm, "proxbox_sync_state", None)
            node = getattr(state, "proxmox_node", None)
            node_name = getattr(node, "name", None)
            if node_name not in (None, ""):
                return node_name
            return getattr(state, "proxmox_node_name", None)

        module.resolve_vm_vmid = resolve_vm_vmid
        module.resolve_known_vm_type = resolve_known_vm_type
        module.resolve_vm_node = resolve_vm_node
        sys.modules[name] = module


def load_intent_module(basename: str):
    """Exec-load ``netbox_proxbox/intent/<basename>.py`` under the stub parents."""
    _install_package_stubs()
    name = f"netbox_proxbox.intent.{basename}"
    if name in sys.modules:
        return sys.modules[name]
    path = INTENT_DIR / f"{basename}.py"
    if basename == "payload" and (
        override := os.environ.get("PROXBOX_INTENT_PAYLOAD_PATH")
    ):
        path = Path(override)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class FakeRelated:
    """Stands in for a related manager whose ``all()`` returns fixed rows."""

    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


class FakeTag:
    def __init__(self, name: str):
        self.name = name


class FakeDisk:
    def __init__(self, size):
        self.size = size


class FakeInterface:
    def __init__(self, name, mac_address=None, enabled=True, mtu=None, description=""):
        self.name = name
        self.mac_address = mac_address
        self.enabled = enabled
        self.mtu = mtu
        self.description = description


class FakeSyncState:
    def __init__(self, vm_id=None, vm_type=None, node_name=None):
        self.proxmox_vm_id = vm_id
        self.proxmox_vm_type = vm_type
        self.proxmox_node = None
        self.proxmox_node_name = node_name


class FakeIntent:
    """A model-shaped ``ProxmoxVMIntent`` row for pipeline tests."""

    def __init__(self, **values):
        fields = (
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
            "intent_state",
            "last_apply_run_id",
        )
        for field in fields:
            default = None if field in {"template_vmid", "swap"} else ""
            setattr(self, field, values.get(field, default))


class FakeVM:
    """A NetBox virtual machine as the intent builders see one."""

    def __init__(
        self,
        *,
        name="",
        vmid=None,
        vcpus=None,
        memory=None,
        description=None,
        custom_field_data=None,
        disks=(),
        tags=(),
        interfaces=(),
        sync_state=None,
        primary_ip4=None,
        primary_ip6=None,
        device=None,
        intent=None,
        pk=1,
    ):
        self.pk = pk
        self.name = name
        self.vmid = vmid
        self.vcpus = vcpus
        self.memory = memory
        self.description = description
        self.custom_field_data = (
            dict(custom_field_data) if custom_field_data is not None else {}
        )
        self.virtual_disks = FakeRelated(disks)
        self.tags = FakeRelated(tags)
        self.interfaces = FakeRelated(interfaces)
        self.proxbox_sync_state = sync_state
        self.primary_ip4 = primary_ip4
        self.primary_ip6 = primary_ip6
        self.device = device
        if intent is not None:
            self.proxbox_intent = intent


__all__ = (
    "FakeDisk",
    "FakeInterface",
    "FakeIntent",
    "FakeRelated",
    "FakeSyncState",
    "FakeTag",
    "FakeVM",
    "load_intent_module",
)
