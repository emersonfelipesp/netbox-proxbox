"""Tests for the ensure_cloud_customer_network management command."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace


class _ObjectManager:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.rows: list[SimpleNamespace] = []

    def get_or_create(self, defaults: dict | None = None, **lookup):
        for row in self.rows:
            if all(getattr(row, key) == value for key, value in lookup.items()):
                return row, False
        values = {**lookup, **(defaults or {})}
        row = SimpleNamespace(pk=len(self.rows) + 1, **values)
        self.rows.append(row)
        return row, True


class _Settings:
    def __init__(self):
        self.cloud_network_lock_enabled = False
        self.cloud_customer_prefix_id = None
        self.cloud_customer_bridge = "vmbr1"
        self.cloud_customer_vlan_tag = None
        self.cloud_customer_gateway = ""
        self.saved_update_fields: list[list[str]] = []

    def save(self, *, update_fields: list[str]) -> None:
        self.saved_update_fields.append(update_fields)


def _load_command(monkeypatch):
    role_manager = _ObjectManager("Role")
    vlan_manager = _ObjectManager("VLAN")
    prefix_manager = _ObjectManager("Prefix")
    ip_address_manager = _ObjectManager("IPAddress")

    class _Role:
        objects = role_manager

    class _VLAN:
        objects = vlan_manager

    class _Prefix:
        objects = prefix_manager

    class _IPAddress:
        objects = ip_address_manager

    ipam_mod = types.ModuleType("ipam")
    ipam_models_mod = types.ModuleType("ipam.models")
    ipam_models_mod.Role = _Role
    ipam_models_mod.VLAN = _VLAN
    ipam_models_mod.Prefix = _Prefix
    ipam_models_mod.IPAddress = _IPAddress
    ipam_mod.models = ipam_models_mod
    monkeypatch.setitem(sys.modules, "ipam", ipam_mod)
    monkeypatch.setitem(sys.modules, "ipam.models", ipam_models_mod)

    settings = _Settings()

    class _ProxboxPluginSettings:
        @classmethod
        def get_solo(cls):
            return settings

    models_mod = types.ModuleType("netbox_proxbox.models")
    models_mod.ProxboxPluginSettings = _ProxboxPluginSettings
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models_mod)

    root = Path(__file__).resolve().parents[2]
    path = (
        root
        / "netbox_proxbox"
        / "management"
        / "commands"
        / "ensure_cloud_customer_network.py"
    )
    sys.modules.pop(
        "netbox_proxbox.management.commands.ensure_cloud_customer_network",
        None,
    )
    spec = importlib.util.spec_from_file_location(
        "netbox_proxbox.management.commands.ensure_cloud_customer_network",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["netbox_proxbox.management.commands.ensure_cloud_customer_network"] = (
        module
    )
    spec.loader.exec_module(module)

    return SimpleNamespace(
        module=module,
        settings=settings,
        role_manager=role_manager,
        vlan_manager=vlan_manager,
        prefix_manager=prefix_manager,
        ip_address_manager=ip_address_manager,
    )


def _run(command_module, *, enable_lock: bool = True) -> list[str]:
    output: list[str] = []
    command = command_module.Command()
    command.stdout = SimpleNamespace(write=output.append)
    command.style = SimpleNamespace(SUCCESS=lambda value: value)
    command.handle(
        prefix="168.0.98.0/25",
        vlan=2050,
        vlan_name="cloud-vmbr1",
        bridge="vmbr1",
        gateway="168.0.98.1",
        role_name="Cloud Customer",
        role_slug="cloud-customer",
        enable_lock=enable_lock,
    )
    return output


def test_ensure_cloud_customer_network_is_idempotent_and_populates_settings(
    monkeypatch,
):
    command = _load_command(monkeypatch)

    first_output = _run(command.module)
    second_output = _run(command.module)

    assert len(command.role_manager.rows) == 1
    assert len(command.vlan_manager.rows) == 1
    assert len(command.prefix_manager.rows) == 1
    assert len(command.ip_address_manager.rows) == 1

    prefix = command.prefix_manager.rows[0]
    gateway = command.ip_address_manager.rows[0]
    assert prefix.prefix == "168.0.98.0/25"
    assert prefix.role.slug == "cloud-customer"
    assert prefix.vlan.vid == 2050
    assert gateway.address == "168.0.98.1/25"
    assert gateway.status == "reserved"
    assert gateway.description == "cloud-customer gateway"

    assert command.settings.cloud_network_lock_enabled is True
    assert command.settings.cloud_customer_prefix_id == prefix.pk
    assert command.settings.cloud_customer_bridge == "vmbr1"
    assert command.settings.cloud_customer_vlan_tag == 2050
    assert command.settings.cloud_customer_gateway == "168.0.98.1"
    assert command.settings.saved_update_fields[-1] == [
        "cloud_customer_prefix_id",
        "cloud_customer_bridge",
        "cloud_customer_vlan_tag",
        "cloud_customer_gateway",
        "cloud_network_lock_enabled",
    ]

    assert "role=created" in first_output[0]
    assert "vlan=created" in first_output[0]
    assert "prefix=created" in first_output[0]
    assert "gateway=created" in first_output[0]
    assert "role=existing" in second_output[0]
    assert "vlan=existing" in second_output[0]
    assert "prefix=existing" in second_output[0]
    assert "gateway=existing" in second_output[0]
