"""Request-local readiness tests for ``ProxmoxEndpointSerializer``."""

from __future__ import annotations

import sys
import types

import pytest

from tests.test_service_monitoring_model import _load_endpoint_serializer


class _Endpoint:
    """Secret-presence endpoint whose plaintext accessor must remain unused."""

    def __init__(
        self,
        *,
        pk: int,
        storage: str = "",
        source: str = "dedicated",
        auth_method: str = "password",
        rpc_enabled: bool | None = None,
    ) -> None:
        self.pk = pk
        self.credential_storage_backend = storage
        self.ssh_credential_source = source
        self.ssh_auth_method = auth_method
        self.rpc_enabled = rpc_enabled
        self.allow_writes = True
        self.access_methods = "api_ssh"
        self.name = f"endpoint-{pk}"
        self.domain = "pve.example.test"
        self.ip = ""
        self.ssh_host = self.domain
        self.ssh_username = "root"
        self.username = "root@pam"
        self.effective_ssh_username = "root"
        self.ssh_known_host_fingerprint = "SHA256:test"
        self.password_enc = "encrypted-api-password"
        self.ssh_password_enc = "encrypted-ssh-password"
        self.ssh_private_key_enc = "encrypted-private-key"
        self.openbao_password_credential_uuid = "api-password-uuid"
        self.openbao_ssh_password_credential_uuid = "ssh-password-uuid"
        self.openbao_ssh_keypair_credential_uuid = "ssh-keypair-uuid"

    @property
    def password(self) -> str:
        raise AssertionError("readiness must not resolve credential material")

    @property
    def service_monitoring_eligible(self) -> bool:
        raise AssertionError(
            "serialization must not invoke model readiness or provider authorization"
        )


def _install_storage_resolver(monkeypatch, resolver) -> None:
    module = types.ModuleType("netbox_proxbox.integrations.openbao")
    module.effective_credential_storage_backend = resolver
    module.is_netbox_openbao_installed = lambda: False
    monkeypatch.setitem(sys.modules, module.__name__, module)


def _install_rpc_gate(monkeypatch, installed: bool) -> None:
    module = types.ModuleType("netbox_proxbox.integrations.rpc")
    module.is_netbox_rpc_installed = lambda: installed
    monkeypatch.setitem(sys.modules, module.__name__, module)


def test_global_storage_is_fresh_per_serializer_and_reused_within_one(
    monkeypatch,
) -> None:
    module = _load_endpoint_serializer(monkeypatch)
    resolutions = iter(("legacy_encrypted", "openbao"))
    calls = []

    def resolve() -> str:
        calls.append("resolve")
        return next(resolutions)

    _install_storage_resolver(monkeypatch, resolve)
    first = module.ProxmoxEndpointSerializer()
    second = module.ProxmoxEndpointSerializer()

    assert first.get_has_ssh_password(_Endpoint(pk=1)) is True
    assert first.get_has_ssh_private_key(_Endpoint(pk=2)) is True
    assert second.get_has_ssh_password(_Endpoint(pk=3)) is False
    assert calls == ["resolve", "resolve"]


def test_explicit_storage_overrides_do_not_resolve_the_global_default(
    monkeypatch,
) -> None:
    module = _load_endpoint_serializer(monkeypatch)

    def unexpected_resolution() -> str:
        raise AssertionError("explicit endpoint storage must win")

    _install_storage_resolver(monkeypatch, unexpected_resolution)
    serializer = module.ProxmoxEndpointSerializer()

    assert serializer.get_has_ssh_password(_Endpoint(pk=1, storage="legacy_encrypted"))
    assert not serializer.get_has_ssh_private_key(_Endpoint(pk=2, storage="openbao"))


def test_openbao_readiness_uses_one_authorized_metadata_map(monkeypatch) -> None:
    module = _load_endpoint_serializer(monkeypatch)
    rows = [
        ("api-password-uuid", "password", None),
        ("ssh-password-uuid", "ssh-password", 7),
        ("ssh-keypair-uuid", "wrong-type", None),
    ]
    calls = []

    class _CredentialQuery:
        def restrict(self, user, action):
            calls.append(("restrict", user, action))
            return self

        def filter(self, **kwargs):
            calls.append(("filter", kwargs))
            return self

        def values_list(self, *fields):
            calls.append(("values_list", fields))
            return rows

    class _Groups:
        def filter(self, **kwargs):
            calls.append(("groups", kwargs))
            return self

        def values_list(self, *fields, **kwargs):
            calls.append(("group_values", fields, kwargs))
            return [7]

    credential_model = types.SimpleNamespace(objects=_CredentialQuery())
    django_apps = types.ModuleType("django.apps")
    django_apps.apps = types.SimpleNamespace(
        get_model=lambda app, model: credential_model
    )
    monkeypatch.setitem(sys.modules, django_apps.__name__, django_apps)
    _install_storage_resolver(monkeypatch, lambda: "openbao")
    sys.modules["netbox_proxbox.integrations.openbao"].is_netbox_openbao_installed = (
        lambda: True
    )
    user = types.SimpleNamespace(
        is_authenticated=True,
        is_superuser=False,
        groups=_Groups(),
    )
    request = types.SimpleNamespace(user=user)
    endpoints = [_Endpoint(pk=1), _Endpoint(pk=2, source="reuse_endpoint")]
    serializer = module.ProxmoxEndpointSerializer(
        endpoints, many=True, context={"request": request}
    )

    representations = serializer.data

    assert [item["has_ssh_password"] for item in representations] == [True, True]
    assert [item["has_ssh_private_key"] for item in representations] == [False, False]
    assert [item["has_ssh_terminal_credentials"] for item in representations] == [
        True,
        True,
    ]
    assert [call[0] for call in calls].count("restrict") == 1
    assert [call[0] for call in calls].count("values_list") == 1


def test_openbao_direct_readiness_without_actor_fails_closed(monkeypatch) -> None:
    module = _load_endpoint_serializer(monkeypatch)
    _install_storage_resolver(monkeypatch, lambda: "openbao")
    endpoint = _Endpoint(pk=1, storage="openbao")

    serializer = module.ProxmoxEndpointSerializer()

    assert serializer.get_has_ssh_password(endpoint) is False
    assert serializer.get_has_ssh_private_key(endpoint) is False


def test_absent_rpc_is_checked_once_and_disables_endpoint_overrides(
    monkeypatch,
) -> None:
    module = _load_endpoint_serializer(monkeypatch)
    calls = []
    rpc = types.ModuleType("netbox_proxbox.integrations.rpc")

    def is_installed() -> bool:
        calls.append("gate")
        return False

    rpc.is_netbox_rpc_installed = is_installed
    monkeypatch.setitem(sys.modules, rpc.__name__, rpc)
    monkeypatch.delitem(sys.modules, "netbox_rpc.models", raising=False)
    serializer = module.ProxmoxEndpointSerializer()

    assert (
        serializer.get_effective_rpc_enabled(_Endpoint(pk=1, rpc_enabled=True)) is False
    )
    assert serializer.get_effective_rpc_enabled(_Endpoint(pk=2)) is False
    assert calls == ["gate"]


def test_enabled_rpc_settings_are_request_local_and_endpoint_overrides_win(
    monkeypatch,
) -> None:
    module = _load_endpoint_serializer(monkeypatch)
    _install_rpc_gate(monkeypatch, True)
    calls = []
    rpc_models = types.ModuleType("netbox_rpc.models")

    class RpcPluginSettings:
        @classmethod
        def get_solo(cls):
            calls.append("settings")
            return types.SimpleNamespace(enabled=True)

    rpc_models.RpcPluginSettings = RpcPluginSettings
    monkeypatch.setitem(sys.modules, rpc_models.__name__, rpc_models)
    import_calls = []
    real_import = __import__

    def counted_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "netbox_rpc.models":
            import_calls.append("import")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", counted_import)
    serializer = module.ProxmoxEndpointSerializer()

    assert (
        serializer.get_effective_rpc_enabled(_Endpoint(pk=1, rpc_enabled=False))
        is False
    )
    assert (
        serializer.get_effective_rpc_enabled(_Endpoint(pk=2, rpc_enabled=True)) is True
    )
    assert serializer.get_effective_rpc_enabled(_Endpoint(pk=3)) is True
    assert serializer.get_effective_rpc_enabled(_Endpoint(pk=4)) is True
    assert import_calls == ["import"]
    assert calls == ["settings"]


def test_rpc_override_fails_closed_when_enabled_companion_model_is_missing(
    monkeypatch,
) -> None:
    module = _load_endpoint_serializer(monkeypatch)
    _install_rpc_gate(monkeypatch, True)
    rpc_models = types.ModuleType("netbox_rpc.models")
    monkeypatch.setitem(sys.modules, rpc_models.__name__, rpc_models)

    serializer = module.ProxmoxEndpointSerializer()

    assert (
        serializer.get_effective_rpc_enabled(_Endpoint(pk=1, rpc_enabled=True)) is False
    )


def test_rpc_override_propagates_non_import_failure(monkeypatch) -> None:
    module = _load_endpoint_serializer(monkeypatch)
    _install_rpc_gate(monkeypatch, True)
    real_import = __import__

    def broken_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "netbox_rpc.models":
            raise RuntimeError("broken enabled companion")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", broken_import)

    with pytest.raises(RuntimeError, match="broken enabled companion"):
        module.ProxmoxEndpointSerializer().get_effective_rpc_enabled(
            _Endpoint(pk=1, rpc_enabled=True)
        )


def test_full_dedicated_and_reuse_representations_are_secret_free(monkeypatch) -> None:
    module = _load_endpoint_serializer(monkeypatch)
    storage_calls = []
    settings_calls = []

    def resolve_storage() -> str:
        storage_calls.append("storage")
        return "legacy_encrypted"

    class RpcPluginSettings:
        @classmethod
        def get_solo(cls):
            settings_calls.append("settings")
            return types.SimpleNamespace(enabled=True)

    _install_storage_resolver(monkeypatch, resolve_storage)
    _install_rpc_gate(monkeypatch, True)
    rpc_models = types.ModuleType("netbox_rpc.models")
    rpc_models.RpcPluginSettings = RpcPluginSettings
    monkeypatch.setitem(sys.modules, rpc_models.__name__, rpc_models)
    serializer = module.ProxmoxEndpointSerializer(
        [
            _Endpoint(pk=1),
            _Endpoint(
                pk=2,
                source="reuse_endpoint",
            ),
        ],
        many=True,
    )

    representations = serializer.data

    assert [item["service_monitoring_eligible"] for item in representations] == [
        True,
        True,
    ]
    assert [item["has_ssh_terminal_credentials"] for item in representations] == [
        True,
        True,
    ]
    assert storage_calls == ["storage"]
    assert settings_calls == ["settings"]


def test_dedicated_and_reused_ssh_readiness_never_resolve_material(monkeypatch) -> None:
    module = _load_endpoint_serializer(monkeypatch)
    _install_storage_resolver(monkeypatch, lambda: "legacy_encrypted")
    serializer = module.ProxmoxEndpointSerializer()
    dedicated = _Endpoint(pk=1, source="dedicated", auth_method="key")
    reused = _Endpoint(pk=2, source="reuse_endpoint")

    assert serializer.get_has_ssh_password(dedicated) is True
    assert serializer.get_has_ssh_private_key(dedicated) is True
    assert serializer.get_has_ssh_terminal_credentials(dedicated) is True
    assert serializer.get_has_ssh_terminal_credentials(reused) is True
