"""Fast contracts for the shared OpenBao setup surface."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import types

import pytest

ROOT = Path(__file__).parents[1]


def _readiness_module():
    name = "proxbox_test_openbao_readiness"
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "netbox_proxbox/services/openbao_readiness.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_readiness_enumerates_every_missing_prerequisite(monkeypatch) -> None:
    readiness_module = _readiness_module()
    monkeypatch.setattr(readiness_module, "_enabled_plugins", lambda: set())
    monkeypatch.setattr(readiness_module, "_settings_values", lambda: ("proxbox", ""))
    result = readiness_module.openbao_readiness()
    assert result.ready is False
    assert [item.key for item in result.items if not item.ready] == [
        "netbox_openbao",
        "netbox_rpc",
        "default_engine",
        "credential_policy",
        "service_user",
    ]
    assert len(result.errors) == 5


def test_readiness_reports_provider_import_failure_without_traceback(
    monkeypatch,
) -> None:
    readiness_module = _readiness_module()
    monkeypatch.setattr(
        readiness_module,
        "_enabled_plugins",
        lambda: {"netbox_openbao", "netbox_rpc"},
    )
    monkeypatch.setattr(
        readiness_module, "_settings_values", lambda: ("proxbox", "svc")
    )
    monkeypatch.setattr(
        readiness_module,
        "_provider_state",
        lambda *_args: (None, False, "ImportError"),
    )
    monkeypatch.setattr(
        readiness_module, "_service_user_state", lambda *_args: (True, "active")
    )
    result = readiness_module.openbao_readiness()
    assert "ImportError" in result.items[2].detail
    assert result.items[0].ready and result.items[1].ready


def test_storage_readiness_excludes_rpc_and_automation_user(monkeypatch) -> None:
    readiness_module = _readiness_module()
    engine = type("Engine", (), {"slug": "primary"})()
    monkeypatch.setattr(
        readiness_module, "_enabled_plugins", lambda: {"netbox_openbao"}
    )
    monkeypatch.setattr(readiness_module, "_settings_values", lambda: ("proxbox", ""))
    monkeypatch.setattr(
        readiness_module,
        "_provider_state",
        lambda *_args: (engine, True, None),
    )
    storage = readiness_module.openbao_storage_readiness()
    composed = readiness_module.openbao_readiness()
    assert storage.ready is True
    assert [item.key for item in storage.items] == [
        "netbox_openbao",
        "default_engine",
        "credential_policy",
    ]
    assert composed.ready is False
    assert [item.key for item in composed.items if not item.ready] == [
        "netbox_rpc",
        "service_user",
    ]


def test_validator_keeps_one_actionable_error(monkeypatch) -> None:
    from tests.test_openbao_credential_integration import _load_openbao_module

    openbao = _load_openbao_module(monkeypatch)

    monkeypatch.setattr(
        openbao, "openbao_prerequisites_errors", lambda: ["first", "second"]
    )
    with pytest.raises(openbao.ValidationError) as excinfo:
        openbao.validate_openbao_storage_available(storage_backend="openbao")
    assert excinfo.value.messages == ["first"]


def test_validator_consumes_storage_readiness_only(monkeypatch) -> None:
    from tests.test_openbao_credential_integration import _load_openbao_module

    openbao = _load_openbao_module(monkeypatch)
    readiness = types.ModuleType("netbox_proxbox.services.openbao_readiness")
    readiness.openbao_storage_readiness = lambda: SimpleNamespace(errors=())
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services.openbao_readiness", readiness
    )
    assert openbao.openbao_prerequisites_errors() == []


def test_settings_panel_and_command_share_readiness_service() -> None:
    root = ROOT
    view = (root / "netbox_proxbox/views/settings.py").read_text()
    command = (
        root / "netbox_proxbox/management/commands/proxbox_openbao_setup.py"
    ).read_text()
    template = (
        root / "netbox_proxbox/templates/netbox_proxbox/settings.html"
    ).read_text()
    assert '"openbao_readiness": openbao_readiness()' in view
    assert "openbao_readiness()" in command
    assert "data-openbao-readiness" in template
    assert "{% if item.ready %}" in template
    assert "text-bg-success" in template
    assert "text-bg-warning" in template
    assert "item.remedy" in template
