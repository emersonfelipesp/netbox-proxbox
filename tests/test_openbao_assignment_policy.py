"""Policy selection and optional assignment-registration contracts."""

from __future__ import annotations

import sys
import types
from unittest.mock import Mock

import pytest

from tests.test_openbao_credential_integration import _load_openbao_module


def _policy_modules(monkeypatch, *, policy: object | None, engine: object) -> Mock:
    models = types.ModuleType("netbox_openbao.models")
    models.CredentialPolicy = types.SimpleNamespace(objects=Mock())
    models.CredentialPolicy.objects.filter.return_value.first.return_value = policy
    utils = types.ModuleType("netbox_openbao.utils")
    utils.get_default_engine = lambda: engine
    monkeypatch.setitem(sys.modules, "netbox_openbao.models", models)
    monkeypatch.setitem(sys.modules, "netbox_openbao.utils", utils)
    return models.CredentialPolicy.objects


@pytest.mark.parametrize("slug", ["proxbox", "operator-policy"])
def test_policy_uses_exact_slug_and_default_engine(monkeypatch, slug: str) -> None:
    module = _load_openbao_module(monkeypatch)
    engine, policy = object(), object()
    manager = _policy_modules(monkeypatch, policy=policy, engine=engine)
    monkeypatch.setattr(
        module,
        "_plugin_settings",
        lambda: types.SimpleNamespace(openbao_policy_slug=slug),
    )

    assert module._default_policy() is policy
    manager.filter.assert_called_once_with(engine=engine, slug=slug)
    manager.filter.return_value.order_by.assert_not_called()


def test_missing_policy_names_setting_slug_and_setup_command(monkeypatch) -> None:
    module = _load_openbao_module(monkeypatch)
    _policy_modules(monkeypatch, policy=None, engine=object())
    monkeypatch.setattr(
        module,
        "_plugin_settings",
        lambda: types.SimpleNamespace(openbao_policy_slug="restricted"),
    )

    with pytest.raises(module.ValidationError) as caught:
        module._default_policy()

    message = str(caught.value)
    assert "openbao_policy_slug" in message
    assert "restricted" in message
    assert "proxbox_openbao_setup" in message


def test_absent_settings_uses_declared_policy_default(monkeypatch) -> None:
    module = _load_openbao_module(monkeypatch)
    manager = _policy_modules(monkeypatch, policy=object(), engine="default-engine")

    module._default_policy()

    manager.filter.assert_called_once_with(engine="default-engine", slug="proxbox")


def test_missing_engine_never_queries_policy(monkeypatch) -> None:
    module = _load_openbao_module(monkeypatch)
    manager = _policy_modules(monkeypatch, policy=object(), engine=None)

    with pytest.raises(module.ValidationError, match="SecretEngine"):
        module._default_policy()

    manager.filter.assert_not_called()


@pytest.mark.parametrize("installed", [False, True])
def test_registry_runs_only_for_enabled_plugin(monkeypatch, installed: bool) -> None:
    module = _load_openbao_module(monkeypatch)
    registry = types.ModuleType("netbox_openbao.registry")
    registry.register_assignable_models = Mock()
    monkeypatch.setitem(sys.modules, "netbox_openbao.registry", registry)
    monkeypatch.setattr(module, "is_netbox_openbao_installed", lambda: installed)

    module.register_openbao_assignable_models()

    if installed:
        registry.register_assignable_models.assert_called_once_with(
            "netbox_proxbox.proxmoxendpoint",
            "netbox_proxbox.fastapiendpoint",
            "netbox_proxbox.pbsendpoint",
            "netbox_proxbox.pdmendpoint",
            "netbox_proxbox.firecrackerhost",
        )
    else:
        registry.register_assignable_models.assert_not_called()


def test_old_registry_warns_with_required_version(monkeypatch, caplog) -> None:
    module = _load_openbao_module(monkeypatch)
    monkeypatch.setattr(module, "is_netbox_openbao_installed", lambda: True)
    monkeypatch.setitem(
        sys.modules,
        "netbox_openbao.registry",
        types.ModuleType("netbox_openbao.registry"),
    )

    module.register_openbao_assignable_models()

    assert "netbox-openbao 0.1.0 or newer" in caplog.text
    assert "assignable_models" in caplog.text
