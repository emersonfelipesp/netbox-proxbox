"""Tests for netbox-openbao credential storage integration."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.django_stubs import install_django_stubs

REPO_ROOT = Path(__file__).resolve().parents[1]
OPENBAO = "openbao"
LEGACY = "legacy_encrypted"


def _load_openbao_module(monkeypatch):
    install_django_stubs(monkeypatch)

    django_root = types.ModuleType("django")
    django_utils = types.ModuleType("django.utils")
    django_utils_translation = types.ModuleType("django.utils.translation")
    django_utils_translation.gettext_lazy = lambda value: value
    django_utils.translation = django_utils_translation
    django_root.utils = django_utils
    monkeypatch.setitem(sys.modules, "django", django_root)
    monkeypatch.setitem(sys.modules, "django.utils", django_utils)
    monkeypatch.setitem(
        sys.modules, "django.utils.translation", django_utils_translation
    )

    django_core_exceptions = types.ModuleType("django.core.exceptions")

    class ValidationError(Exception):
        def __init__(self, message=None):
            if isinstance(message, dict):
                self.error_dict = message
                self.messages = [str(next(iter(message.values())))]
            else:
                self.messages = [str(message)]
            super().__init__(self.messages[0] if self.messages else "")

    django_core_exceptions.ValidationError = ValidationError
    monkeypatch.setitem(sys.modules, "django.core.exceptions", django_core_exceptions)

    utilities_choices = types.ModuleType("utilities.choices")

    class ChoiceSet:
        CHOICES = ()

    utilities_choices.ChoiceSet = ChoiceSet
    monkeypatch.setitem(sys.modules, "utilities.choices", utilities_choices)

    pkg = types.ModuleType("netbox_proxbox")
    pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", pkg)

    choices_spec = importlib.util.spec_from_file_location(
        "netbox_proxbox.choices",
        REPO_ROOT / "netbox_proxbox" / "choices.py",
    )
    assert choices_spec is not None and choices_spec.loader is not None
    choices_mod = importlib.util.module_from_spec(choices_spec)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.choices", choices_mod)
    choices_spec.loader.exec_module(choices_mod)

    integrations_pkg = types.ModuleType("netbox_proxbox.integrations")
    integrations_pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox" / "integrations")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox.integrations", integrations_pkg)

    models_mod = types.ModuleType("netbox_proxbox.models")

    models_mod.ProxboxPluginSettings = types.SimpleNamespace(
        objects=types.SimpleNamespace(first=lambda: None),
    )
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models_mod)

    spec = importlib.util.spec_from_file_location(
        "netbox_proxbox.integrations.openbao",
        REPO_ROOT / "netbox_proxbox" / "integrations" / "openbao.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.integrations.openbao", module)
    spec.loader.exec_module(module)
    return module


def test_effective_storage_backend_defaults_to_openbao(monkeypatch) -> None:
    openbao = _load_openbao_module(monkeypatch)
    assert openbao.effective_credential_storage_backend(None) == OPENBAO


def test_openbao_prerequisites_errors_when_plugin_missing(monkeypatch) -> None:
    openbao = _load_openbao_module(monkeypatch)
    with patch.object(openbao, "is_netbox_openbao_installed", return_value=False):
        errors = openbao.openbao_prerequisites_errors()
    assert errors
    assert "netbox-openbao" in str(errors[0]).lower()


def test_validate_write_mode_skips_legacy_backend(monkeypatch) -> None:
    openbao = _load_openbao_module(monkeypatch)
    openbao.validate_write_mode_openbao_requirements(
        None,
        allow_writes=True,
        storage_backend=LEGACY,
    )


def test_validate_write_mode_requires_openbao_when_enabled(monkeypatch) -> None:
    openbao = _load_openbao_module(monkeypatch)
    with patch.object(
        openbao, "openbao_prerequisites_errors", return_value=["missing"]
    ):
        with pytest.raises(Exception) as excinfo:
            openbao.validate_write_mode_openbao_requirements(
                None,
                allow_writes=True,
                storage_backend=OPENBAO,
            )
    assert "missing" in str(excinfo.value)


def test_read_only_endpoint_does_not_require_openbao_on_write_flag_false(
    monkeypatch,
) -> None:
    openbao = _load_openbao_module(monkeypatch)
    openbao.validate_write_mode_openbao_requirements(
        None,
        allow_writes=False,
        storage_backend=OPENBAO,
    )


def test_resolve_token_value_uses_openbao_credential(monkeypatch) -> None:
    openbao = _load_openbao_module(monkeypatch)
    credential_uuid = "11111111-1111-4111-8111-111111111111"
    endpoint = types.SimpleNamespace(
        credential_storage_backend=OPENBAO,
        token_value_enc="",
        openbao_token_credential_uuid=credential_uuid,
    )
    with (
        patch.object(
            openbao,
            "effective_credential_storage_backend",
            return_value=OPENBAO,
        ),
        patch.object(
            openbao,
            "_credential_for_uuid",
            return_value=object(),
        ) as mock_lookup,
        patch.object(
            openbao,
            "reveal_credential_material",
            return_value={"token": "secret-token"},
        ) as mock_reveal,
    ):
        assert openbao.resolve_endpoint_token_value(endpoint) == "secret-token"
    mock_lookup.assert_called_once_with(credential_uuid)
    mock_reveal.assert_called_once()


def test_openbao_actor_requires_configured_service_user(monkeypatch) -> None:
    openbao = _load_openbao_module(monkeypatch)
    settings = types.SimpleNamespace(openbao_service_username="")
    with patch.object(openbao, "_plugin_settings", return_value=settings):
        with pytest.raises(Exception) as excinfo:
            openbao._openbao_actor(None)
    assert "service username" in str(excinfo.value).lower()


def test_validate_openbao_storage_requires_plugin(monkeypatch) -> None:
    openbao = _load_openbao_module(monkeypatch)
    with patch.object(openbao, "is_netbox_openbao_installed", return_value=False):
        with pytest.raises(Exception) as excinfo:
            openbao.validate_openbao_storage_available(None, storage_backend=OPENBAO)
    assert "netbox-openbao" in str(excinfo.value).lower()


def test_ssh_getters_import_endpoint_uses_openbao_storage() -> None:
    """Regression for round-2 NameError in SSH getter methods."""
    source = (
        REPO_ROOT / "netbox_proxbox" / "models" / "proxmox_endpoint.py"
    ).read_text()
    for method in ("get_ssh_password", "get_ssh_private_key"):
        start = source.index(f"def {method}")
        block = source[start : source.index("\n    def ", start + 1)]
        assert "endpoint_uses_openbao_storage" in block
        assert "from netbox_proxbox.integrations.openbao import" in block
