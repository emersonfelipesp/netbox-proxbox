"""Isolated tests for ProxmoxEndpoint service-monitoring eligibility."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = REPO_ROOT / "netbox_proxbox" / "models" / "proxmox_endpoint.py"


def _stub_proxmox_endpoint_dependencies(monkeypatch):
    django = types.ModuleType("django")
    core = types.ModuleType("django.core")
    core_exceptions = types.ModuleType("django.core.exceptions")

    class _ValidationError(Exception):
        def __init__(self, message):
            super().__init__(message)
            self.message = message
            self.message_dict = (
                message if isinstance(message, dict) else {"__all__": [message]}
            )

    core_exceptions.ValidationError = _ValidationError

    core_validators = types.ModuleType("django.core.validators")
    core_validators.MaxValueValidator = lambda value: ("max", value)
    core_validators.MinValueValidator = lambda value: ("min", value)

    db = types.ModuleType("django.db")
    db_models = types.ModuleType("django.db.models")

    class _Field:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    for name in (
        "BooleanField",
        "CharField",
        "DateTimeField",
        "DecimalField",
        "ForeignKey",
        "JSONField",
        "ManyToManyField",
        "PositiveIntegerField",
        "PositiveSmallIntegerField",
        "TextField",
    ):
        setattr(db_models, name, _Field)
    db_models.PROTECT = object()
    db_models.SET_NULL = object()
    db_models.UniqueConstraint = _Field
    db.models = db_models

    urls = types.ModuleType("django.urls")
    urls.reverse = lambda *args, **kwargs: "/dummy/"

    utils = types.ModuleType("django.utils")
    utils_translation = types.ModuleType("django.utils.translation")
    utils_translation.gettext_lazy = lambda value: value
    utils.translation = utils_translation

    np_pkg = types.ModuleType("netbox_proxbox")
    np_pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox")]

    choices = types.ModuleType("netbox_proxbox.choices")
    choices.ProxmoxAccessMethodChoices = types.SimpleNamespace(
        API="api",
        API_SSH="api_ssh",
    )
    choices.ProxmoxEndpointEnvironmentChoices = []
    choices.ProxmoxModeChoices = types.SimpleNamespace(
        PROXMOX_MODE_UNDEFINED="undefined"
    )
    choices.SyncModeChoices = types.SimpleNamespace(
        ALWAYS="always",
        DISABLED="disabled",
    )

    constants = types.ModuleType("netbox_proxbox.constants")
    constants.OVERWRITE_FIELDS = ()
    constants.SYNC_MODE_RESOURCE_TYPES = {"vm"}

    fields = types.ModuleType("netbox_proxbox.fields")
    fields.DomainField = _Field

    base = types.ModuleType("netbox_proxbox.models.base")
    base.PORT_VALIDATORS = []

    class _EndpointBase:
        class Meta:
            pass

        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

        @property
        def ip(self):
            return ""

        def clean(self):
            return None

    base.EndpointBase = _EndpointBase

    ssh_credential = types.ModuleType("netbox_proxbox.models.ssh_credential")
    ssh_credential.AUTH_METHOD_CHOICES = (("key", "Key"), ("password", "Password"))
    ssh_credential.AUTH_METHOD_KEY = "key"
    ssh_credential.AUTH_METHOD_PASSWORD = "password"
    ssh_credential.SSH_CRED_SOURCE_CHOICES = (
        ("dedicated", "Dedicated"),
        ("reuse_endpoint", "Reuse"),
    )
    ssh_credential.SSH_CRED_SOURCE_DEDICATED = "dedicated"
    ssh_credential.SSH_CRED_SOURCE_REUSE = "reuse_endpoint"
    ssh_credential.normalize_fingerprint = lambda value: value.strip()

    primary_secrets = types.ModuleType("netbox_proxbox.models.primary_secrets")
    primary_secrets.decrypt_primary_secret = lambda value: value or ""
    primary_secrets.encrypt_primary_secret = lambda value: value or ""

    enc_mod = types.ModuleType("netbox_proxbox.utils.encryption")
    enc_mod.encrypt = lambda value, key: f"enc:{value}"
    enc_mod.decrypt = lambda value, key: value.removeprefix("enc:")
    utils_pkg = types.ModuleType("netbox_proxbox.utils")
    utils_pkg.encryption = enc_mod

    for name, mod in [
        ("django", django),
        ("django.core", core),
        ("django.core.exceptions", core_exceptions),
        ("django.core.validators", core_validators),
        ("django.db", db),
        ("django.db.models", db_models),
        ("django.urls", urls),
        ("django.utils", utils),
        ("django.utils.translation", utils_translation),
        ("netbox_proxbox", np_pkg),
        ("netbox_proxbox.choices", choices),
        ("netbox_proxbox.constants", constants),
        ("netbox_proxbox.fields", fields),
        ("netbox_proxbox.models.base", base),
        ("netbox_proxbox.models.ssh_credential", ssh_credential),
        ("netbox_proxbox.models.primary_secrets", primary_secrets),
        ("netbox_proxbox.utils", utils_pkg),
        ("netbox_proxbox.utils.encryption", enc_mod),
    ]:
        monkeypatch.setitem(sys.modules, name, mod)


def _load_proxmox_endpoint(monkeypatch):
    _stub_proxmox_endpoint_dependencies(monkeypatch)
    spec = importlib.util.spec_from_file_location(
        "_prox_endpoint_under_test", MODEL_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _eligible_endpoint(module):
    return module.ProxmoxEndpoint(
        allow_writes=True,
        access_methods="api_ssh",
        ssh_credential_source="dedicated",
        domain="pve.example.test",
        ssh_username="root",
        ssh_known_host_fingerprint="SHA256:" + "A" * 43,
        ssh_auth_method="key",
        ssh_private_key_enc="ciphertext",
        ssh_password_enc="",
        service_monitoring_enabled=True,
    )


def test_service_monitoring_eligible_requires_writes_ssh_and_credentials(monkeypatch):
    module = _load_proxmox_endpoint(monkeypatch)
    endpoint = _eligible_endpoint(module)

    assert endpoint.service_monitoring_eligible is True

    endpoint.allow_writes = False
    assert endpoint.service_monitoring_eligible is False
    endpoint.allow_writes = True

    endpoint.access_methods = "api"
    assert endpoint.service_monitoring_eligible is False
    endpoint.access_methods = "api_ssh"

    endpoint.ssh_private_key_enc = ""
    assert endpoint.service_monitoring_eligible is False


def test_clean_rejects_enabled_service_monitoring_when_ineligible(monkeypatch):
    module = _load_proxmox_endpoint(monkeypatch)
    endpoint = _eligible_endpoint(module)
    endpoint.allow_writes = False

    ValidationError = sys.modules["django.core.exceptions"].ValidationError
    with pytest.raises(ValidationError) as exc:
        endpoint.clean()

    assert "service_monitoring_enabled" in exc.value.message_dict
    assert "allow_writes" in exc.value.message_dict["service_monitoring_enabled"]


def test_clean_accepts_enabled_service_monitoring_when_eligible(monkeypatch):
    module = _load_proxmox_endpoint(monkeypatch)
    endpoint = _eligible_endpoint(module)

    endpoint.clean()
    assert endpoint.ssh_known_host_fingerprint.startswith("SHA256:")
