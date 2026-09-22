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
    django_views = types.ModuleType("django.views")
    django_views_decorators = types.ModuleType("django.views.decorators")
    django_views_debug = types.ModuleType("django.views.decorators.debug")
    django_views_debug.sensitive_variables = lambda *_args: lambda func: func
    monkeypatch.setitem(sys.modules, "django", django_root)
    monkeypatch.setitem(sys.modules, "django.utils", django_utils)
    monkeypatch.setitem(
        sys.modules, "django.utils.translation", django_utils_translation
    )
    monkeypatch.setitem(sys.modules, "django.views", django_views)
    monkeypatch.setitem(sys.modules, "django.views.decorators", django_views_decorators)
    monkeypatch.setitem(
        sys.modules, "django.views.decorators.debug", django_views_debug
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


@pytest.mark.parametrize(
    "plugins, expected", [([], LEGACY), (["netbox_openbao"], OPENBAO)]
)
@pytest.mark.parametrize("saved", [None, ""])
def test_effective_storage_backend_defaults_follow_enabled_plugins(
    monkeypatch, plugins, expected, saved
) -> None:
    openbao = _load_openbao_module(monkeypatch)
    settings_module = types.ModuleType("django.conf")
    settings_module.settings = types.SimpleNamespace(PLUGINS=plugins)
    monkeypatch.setitem(sys.modules, "django.conf", settings_module)
    row = (
        None
        if saved is None
        else types.SimpleNamespace(credential_storage_backend=saved)
    )
    monkeypatch.setattr(openbao, "_plugin_settings", lambda: row)
    assert openbao.effective_credential_storage_backend(None) == expected


@pytest.mark.parametrize("installed", [False, True])
@pytest.mark.parametrize("saved", [LEGACY, OPENBAO])
@pytest.mark.parametrize("endpoint_backend", ["", LEGACY, OPENBAO])
def test_explicit_storage_selections_remain_authoritative(
    monkeypatch, installed, saved, endpoint_backend
) -> None:
    openbao = _load_openbao_module(monkeypatch)
    monkeypatch.setattr(openbao, "is_netbox_openbao_installed", lambda: installed)
    monkeypatch.setattr(
        openbao,
        "_plugin_settings",
        lambda: types.SimpleNamespace(credential_storage_backend=saved),
    )
    endpoint = types.SimpleNamespace(credential_storage_backend=endpoint_backend)
    assert openbao.effective_credential_storage_backend(endpoint) == (
        endpoint_backend or saved
    )
    assert (
        openbao.effective_credential_storage_backend(endpoint, override=LEGACY)
        == LEGACY
    )
    assert (
        openbao.effective_credential_storage_backend(endpoint, override=OPENBAO)
        == OPENBAO
    )


SECRET_CASES = [
    ("resolve_endpoint_password", "openbao_password_credential_uuid", "password"),
    ("resolve_endpoint_token_value", "openbao_token_credential_uuid", "token"),
    (
        "resolve_endpoint_ssh_password",
        "openbao_ssh_password_credential_uuid",
        "password",
    ),
    (
        "resolve_endpoint_ssh_private_key",
        "openbao_ssh_keypair_credential_uuid",
        "private_key",
    ),
]


@pytest.mark.parametrize("resolver,reference,field", SECRET_CASES)
@pytest.mark.parametrize(
    "failure",
    [
        "unset",
        "missing",
        "disabled",
        "denied",
        "provider_error",
        "empty",
        "wrong_type",
        "missing_field",
        "bad_payload",
    ],
)
def test_openbao_resolvers_fail_loud_without_disclosing_provider_material(
    monkeypatch, resolver, reference, field, failure
) -> None:
    openbao = _load_openbao_module(monkeypatch)
    endpoint = types.SimpleNamespace(
        name="PVE example", pk=17, credential_storage_backend=OPENBAO
    )
    setattr(
        endpoint,
        reference,
        None if failure == "unset" else "11111111-1111-4111-8111-111111111111",
    )
    credential = object()
    if failure != "disabled":
        monkeypatch.setattr(
            openbao,
            "_credential_for_uuid",
            lambda uuid: None if failure in {"unset", "missing"} else credential,
        )
    else:
        monkeypatch.setattr(openbao, "is_netbox_openbao_installed", lambda: False)
    forbidden = "provider-secret-must-not-escape"

    def reveal(*args, **kwargs):
        if failure in {"denied", "provider_error"}:
            raise RuntimeError(forbidden)
        if failure == "bad_payload":
            return [forbidden]
        if failure == "missing_field":
            return {"other": forbidden}
        return {field: {"secret": forbidden} if failure == "wrong_type" else ""}

    monkeypatch.setattr(openbao, "reveal_credential_material", reveal)
    with pytest.raises(openbao.ValidationError) as caught:
        getattr(openbao, resolver)(endpoint)
    assert "PVE example" in str(caught.value)
    assert reference in str(caught.value)
    assert forbidden not in str(caught.value)
    assert caught.value.__suppress_context__ or failure not in {
        "denied",
        "provider_error",
    }


@pytest.mark.parametrize("resolver,reference,field", SECRET_CASES)
def test_openbao_resolvers_preserve_exact_material_and_actor(
    monkeypatch, resolver, reference, field
) -> None:
    openbao = _load_openbao_module(monkeypatch)
    endpoint = types.SimpleNamespace(credential_storage_backend=OPENBAO)
    setattr(endpoint, reference, "reference")
    actor = object()
    credential = object()
    monkeypatch.setattr(openbao, "_credential_for_uuid", lambda value: credential)
    with patch.object(
        openbao, "reveal_credential_material", return_value={field: " secret\n"}
    ) as reveal:
        assert getattr(openbao, resolver)(endpoint, user=actor) == " secret\n"
    reveal.assert_called_once_with(credential, user=actor)


@pytest.mark.parametrize("token_selected", [False, True])
def test_api_credentials_do_not_reveal_an_unselected_absent_auth_method(
    monkeypatch, token_selected
) -> None:
    openbao = _load_openbao_module(monkeypatch)
    endpoint = types.SimpleNamespace(
        credential_storage_backend=OPENBAO,
        token_name="api-token" if token_selected else "",
        openbao_password_credential_uuid=None if token_selected else "password-ref",
        openbao_token_credential_uuid="token-ref" if token_selected else None,
    )
    with (
        patch.object(
            openbao, "resolve_endpoint_password", return_value="password-secret"
        ) as password,
        patch.object(
            openbao, "resolve_endpoint_token_value", return_value="token-secret"
        ) as token,
    ):
        result = openbao.resolve_endpoint_api_credentials(endpoint)
    assert result == (
        {"password": "", "token_value": "token-secret"}
        if token_selected
        else {"password": "password-secret", "token_value": ""}
    )
    assert password.call_count == (0 if token_selected else 1)
    assert token.call_count == (1 if token_selected else 0)


@pytest.mark.parametrize("token_selected", [False, True])
def test_selected_api_auth_missing_material_does_not_downgrade(
    monkeypatch, token_selected
) -> None:
    openbao = _load_openbao_module(monkeypatch)
    endpoint = types.SimpleNamespace(
        name="PVE",
        pk=9,
        credential_storage_backend=OPENBAO,
        token_name="api-token" if token_selected else "",
        openbao_password_credential_uuid=None,
        openbao_token_credential_uuid=None,
        password="legacy-secret",
        token_value="legacy-token",
    )
    monkeypatch.setattr(openbao, "_credential_for_uuid", lambda uuid: None)
    with pytest.raises(openbao.ValidationError):
        openbao.resolve_endpoint_api_credentials(endpoint)


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


def test_legacy_resolvers_decrypt_all_four_material_types_with_real_fernet(
    monkeypatch,
) -> None:
    from cryptography.fernet import Fernet

    openbao = _load_openbao_module(monkeypatch)
    key = Fernet.generate_key()
    config = types.SimpleNamespace(
        encryption_key=key.decode(), credential_storage_backend=""
    )
    model_settings = types.SimpleNamespace(
        get_solo=lambda: config, objects=types.SimpleNamespace(first=lambda: config)
    )
    sys.modules["netbox_proxbox.models"].ProxboxPluginSettings = model_settings
    settings_module = types.ModuleType("netbox_proxbox.models.plugin_settings")
    settings_module.ProxboxPluginSettings = model_settings
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.models.plugin_settings", settings_module
    )
    utilities = types.ModuleType("netbox_proxbox.utils")
    utilities.__path__ = [str(REPO_ROOT / "netbox_proxbox" / "utils")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox.utils", utilities)
    for name, path in (
        ("netbox_proxbox.utils.encryption", "utils/encryption.py"),
        ("netbox_proxbox.models.primary_secrets", "models/primary_secrets.py"),
    ):
        spec = importlib.util.spec_from_file_location(
            name, REPO_ROOT / "netbox_proxbox" / path
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
    monkeypatch.setattr(openbao, "is_netbox_openbao_installed", lambda: False)
    endpoint = types.SimpleNamespace(credential_storage_backend="")
    for resolver, field in (
        ("resolve_endpoint_password", "password_enc"),
        ("resolve_endpoint_token_value", "token_value_enc"),
        ("resolve_endpoint_ssh_password", "ssh_password_enc"),
        ("resolve_endpoint_ssh_private_key", "ssh_private_key_enc"),
    ):
        setattr(endpoint, field, Fernet(key).encrypt(b"exact-secret").decode())
        assert getattr(openbao, resolver)(endpoint) == "exact-secret"
    endpoint.password = "api-password"
    endpoint.token_value = "api-token"
    assert openbao.resolve_endpoint_api_credentials(endpoint) == {
        "password": "api-password",
        "token_value": "api-token",
    }


def test_api_selector_rejects_unknown_material_field(monkeypatch) -> None:
    openbao = _load_openbao_module(monkeypatch)
    with pytest.raises(ValueError, match="Unsupported endpoint API credential field"):
        openbao.resolve_endpoint_api_secret(types.SimpleNamespace(), "ssh_private_key")


@pytest.mark.parametrize("selected", [False, True])
def test_api_selector_uses_submitted_auth_without_changing_storage(
    monkeypatch, selected
):
    openbao = _load_openbao_module(monkeypatch)
    endpoint = types.SimpleNamespace(
        name="repair",
        credential_storage_backend=OPENBAO,
        token_name="old-token" if not selected else "",
        openbao_password_credential_uuid=None,
        openbao_token_credential_uuid=None,
    )
    optional_field = "password" if selected else "token_value"
    assert (
        openbao.resolve_endpoint_api_secret(
            endpoint, optional_field, token_selected=selected
        )
        == ""
    )
    required_field = "token_value" if selected else "password"
    with pytest.raises(openbao.ValidationError):
        openbao.resolve_endpoint_api_secret(
            endpoint, required_field, token_selected=selected
        )
    assert endpoint.credential_storage_backend == OPENBAO


@pytest.mark.parametrize("token_selected", [False, True])
def test_api_selector_does_not_hide_a_stale_optional_reference(
    monkeypatch, token_selected
) -> None:
    openbao = _load_openbao_module(monkeypatch)
    endpoint = types.SimpleNamespace(
        name="stale-secondary",
        credential_storage_backend=OPENBAO,
        token_name="token" if token_selected else "",
        openbao_password_credential_uuid="password-ref",
        openbao_token_credential_uuid="token-ref",
    )
    monkeypatch.setattr(openbao, "_credential_for_uuid", lambda value: None)
    field = "password" if token_selected else "token_value"
    with pytest.raises(openbao.ValidationError):
        openbao.resolve_endpoint_api_secret(endpoint, field)
