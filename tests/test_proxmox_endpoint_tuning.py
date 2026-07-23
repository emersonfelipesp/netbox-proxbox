"""Behavior tests for effective Proxmox endpoint connection tuning."""

from __future__ import annotations

import ast
import sys
import types
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from tests.test_service_monitoring_model import _load_proxmox_endpoint


def _plugin_setting_default(field_name: str):
    """Read one declared model-field default without bootstrapping NetBox."""
    source_path = (
        Path(__file__).resolve().parents[1]
        / "netbox_proxbox"
        / "models"
        / "plugin_settings.py"
    )
    tree = ast.parse(source_path.read_text())
    settings_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ProxboxPluginSettings"
    )
    assignment = next(
        node
        for node in settings_class.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == field_name
            for target in node.targets
        )
    )
    assert isinstance(assignment.value, ast.Call)
    default_node = next(
        keyword.value
        for keyword in assignment.value.keywords
        if keyword.arg == "default"
    )
    if isinstance(default_node, ast.Call):
        assert isinstance(default_node.func, ast.Name)
        assert default_node.func.id == "Decimal"
        return Decimal(ast.literal_eval(default_node.args[0]))
    return ast.literal_eval(default_node)


def _stub_plugin_settings(
    monkeypatch,
    *,
    timeout: int = 5,
    max_retries: int = 0,
    retry_backoff: Decimal = Decimal("0.50"),
) -> None:
    module = types.ModuleType("netbox_proxbox.models.plugin_settings")

    class _ProxboxPluginSettings:
        @classmethod
        def get_solo(cls):
            return SimpleNamespace(
                proxmox_timeout=timeout,
                proxmox_max_retries=max_retries,
                proxmox_retry_backoff=retry_backoff,
            )

    module.ProxboxPluginSettings = _ProxboxPluginSettings
    monkeypatch.setitem(
        sys.modules,
        "netbox_proxbox.models.plugin_settings",
        module,
    )


def test_plugin_settings_declares_current_proxmox_connection_defaults() -> None:
    assert _plugin_setting_default("proxmox_timeout") == 5
    assert _plugin_setting_default("proxmox_max_retries") == 0
    assert _plugin_setting_default("proxmox_retry_backoff") == Decimal("0.50")


def test_effective_connection_tuning_inherits_global_values(monkeypatch) -> None:
    endpoint_module = _load_proxmox_endpoint(monkeypatch)
    _stub_plugin_settings(
        monkeypatch,
        timeout=45,
        max_retries=2,
        retry_backoff=Decimal("1.75"),
    )
    endpoint = endpoint_module.ProxmoxEndpoint(
        timeout=None,
        max_retries=None,
        retry_backoff=None,
    )

    assert endpoint.effective_connection_tuning() == {
        "timeout": 45,
        "max_retries": 2,
        "retry_backoff": Decimal("1.75"),
    }


def test_effective_connection_tuning_preserves_explicit_zero(monkeypatch) -> None:
    endpoint_module = _load_proxmox_endpoint(monkeypatch)
    _stub_plugin_settings(
        monkeypatch,
        timeout=45,
        max_retries=2,
        retry_backoff=Decimal("1.75"),
    )
    endpoint = endpoint_module.ProxmoxEndpoint(
        timeout=12,
        max_retries=0,
        retry_backoff=Decimal("0.00"),
    )

    assert endpoint.effective_connection_tuning() == {
        "timeout": 12,
        "max_retries": 0,
        "retry_backoff": Decimal("0.00"),
    }


def test_effective_connection_tuning_supports_mixed_override_and_inheritance(
    monkeypatch,
) -> None:
    endpoint_module = _load_proxmox_endpoint(monkeypatch)
    _stub_plugin_settings(
        monkeypatch,
        timeout=45,
        max_retries=2,
        retry_backoff=Decimal("1.75"),
    )
    endpoint = endpoint_module.ProxmoxEndpoint(
        timeout=90,
        max_retries=None,
        retry_backoff=None,
    )

    assert endpoint.effective_connection_tuning() == {
        "timeout": 90,
        "max_retries": 2,
        "retry_backoff": Decimal("1.75"),
    }
