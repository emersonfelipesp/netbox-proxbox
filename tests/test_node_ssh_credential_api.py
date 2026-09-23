"""Tests for ``netbox_proxbox.api.ssh_credentials``.

The endpoint module is half permission policy and half decrypt-and-return
plumbing. Both halves are exercised here without booting Django/DRF:

* ``_NetBoxTokenCanViewNodeSSHCredential.has_permission`` — accepts NetBox
  API-token requests whose user has ``view_nodesshcredential`` and rejects
  browser/session-style callers.
* AST contract on the two ``APIView`` classes — locks the permission
  classes, the HTTPS-required guard, and the encryption-key-missing
  ``503`` branch.
* AST contract on URL wiring in ``netbox_proxbox/api/urls.py`` — pins
  the two by-node routes and the CRUD router registration.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
API_PATH = REPO_ROOT / "netbox_proxbox" / "api" / "ssh_credentials.py"
URLS_PATH = REPO_ROOT / "netbox_proxbox" / "api" / "urls.py"


# ---------------------------------------------------------------------------
# Behavior: _NetBoxTokenCanViewNodeSSHCredential.has_permission
# ---------------------------------------------------------------------------


def _stub_for_ssh_credentials(
    monkeypatch,
    *,
    authenticated: bool = True,
    has_perm: bool = True,
):
    """Minimal stubs so ``ssh_credentials.py`` imports cleanly."""

    django = types.ModuleType("django")
    django.__path__ = []
    django_conf = types.ModuleType("django.conf")
    django_conf.settings = SimpleNamespace(DEBUG=False)
    django_exceptions = types.ModuleType("django.core.exceptions")
    django_exceptions.ValidationError = type("ValidationError", (Exception,), {})
    django_exceptions.PermissionDenied = type("PermissionDenied", (Exception,), {})
    monkeypatch.setitem(sys.modules, "django.core.exceptions", django_exceptions)

    django_shortcuts = types.ModuleType("django.shortcuts")
    django_shortcuts.get_object_or_404 = lambda queryset, **kw: queryset.get(**kw)
    django_views = types.ModuleType("django.views")
    django_views_decorators = types.ModuleType("django.views.decorators")
    django_views_debug = types.ModuleType("django.views.decorators.debug")
    django_views_debug.sensitive_variables = lambda *_args: lambda func: func

    netbox = types.ModuleType("netbox")
    netbox.__path__ = []
    netbox_api = types.ModuleType("netbox.api")
    netbox_api.__path__ = []
    netbox_api_auth = types.ModuleType("netbox.api.authentication")

    class _TokenAuthentication:
        def authenticate(self, request):
            header = request.headers.get("Authorization", "")
            accepted_headers = {
                "Token expected-token",
                "Bearer nbt_key.expected-secret",
            }
            if header not in accepted_headers:
                return None

            user = SimpleNamespace(is_authenticated=authenticated)

            def _has_perm(permission):
                return has_perm and permission in (
                    "netbox_proxbox.view_nodesshcredential",
                    "netbox_proxbox.view_proxmoxendpoint",
                    "netbox_proxbox.open_ssh_terminal_proxmoxendpoint",
                )

            user.has_perm = _has_perm
            return user, SimpleNamespace(key=header.split(" ", 1)[1])

    netbox_api_auth.TokenAuthentication = _TokenAuthentication
    netbox.api = netbox_api
    netbox_api.authentication = netbox_api_auth

    utilities = types.ModuleType("utilities")
    utilities.__path__ = []
    utilities_permissions = types.ModuleType("utilities.permissions")
    utilities_permissions.get_permission_for_model = lambda _model, action: (
        f"netbox_proxbox.{action}_proxmoxendpoint"
    )

    rest_framework = types.ModuleType("rest_framework")
    rest_framework.__path__ = []
    rf_status = types.ModuleType("rest_framework.status")
    rf_status.HTTP_404_NOT_FOUND = 404
    rf_status.HTTP_403_FORBIDDEN = 403
    rf_status.HTTP_422_UNPROCESSABLE_ENTITY = 422
    rf_status.HTTP_503_SERVICE_UNAVAILABLE = 503

    class _BasePermission:
        pass

    rf_permissions = types.ModuleType("rest_framework.permissions")
    rf_permissions.BasePermission = _BasePermission

    class _Request:
        pass

    rf_request = types.ModuleType("rest_framework.request")
    rf_request.Request = _Request

    class _Response:
        def __init__(self, data=None, status=None):
            self.data = data
            self.status_code = status or 200

    rf_response = types.ModuleType("rest_framework.response")
    rf_response.Response = _Response

    class _APIView:
        pass

    rf_views = types.ModuleType("rest_framework.views")
    rf_views.APIView = _APIView

    class _ProxboxPluginSettings:
        @staticmethod
        def get_solo():
            return SimpleNamespace(encryption_key="")

    class _NodeSSHCredential:
        class DoesNotExist(Exception):
            pass

        class MultipleObjectsReturned(Exception):
            pass

    class _ProxmoxEndpoint:
        pass

    class _ProxmoxNode:
        class DoesNotExist(Exception):
            pass

        class MultipleObjectsReturned(Exception):
            pass

    np_models = types.ModuleType("netbox_proxbox.models")
    np_models.NodeSSHCredential = _NodeSSHCredential
    np_models.ProxboxPluginSettings = _ProxboxPluginSettings
    np_models.ProxmoxEndpoint = _ProxmoxEndpoint
    np_models.ProxmoxNode = _ProxmoxNode

    np_models_ssh = types.ModuleType("netbox_proxbox.models.ssh_credential")
    np_models_ssh.AUTH_METHOD_PASSWORD = "password"
    np_models_ssh.SSH_CRED_SOURCE_REUSE = "reuse_endpoint"

    enc_mod = types.ModuleType("netbox_proxbox.utils.encryption")

    class EncryptionError(Exception):
        pass

    class EncryptionKeyMissing(EncryptionError):
        pass

    enc_mod.EncryptionError = EncryptionError
    enc_mod.EncryptionKeyMissing = EncryptionKeyMissing
    enc_mod.encrypt = lambda plaintext, *, key: plaintext
    enc_mod.decrypt = lambda ciphertext, *, key: ciphertext

    np_utils = types.ModuleType("netbox_proxbox.utils")
    np_utils.encryption = enc_mod

    netbox_plugins = types.ModuleType("netbox.plugins")
    netbox_plugins.PluginConfig = type("PluginConfig", (), {})
    netbox.plugins = netbox_plugins

    np_pkg = types.ModuleType("netbox_proxbox")
    np_pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox")]
    np_integrations = types.ModuleType("netbox_proxbox.integrations")
    np_integrations.__path__ = [str(REPO_ROOT / "netbox_proxbox" / "integrations")]
    np_openbao = types.ModuleType("netbox_proxbox.integrations.openbao")
    np_openbao.endpoint_uses_openbao_storage = lambda endpoint: False
    np_openbao.node_uses_openbao_storage = lambda credential: False
    np_openbao.node_openbao_assignment_lookup = lambda credential: None
    np_openbao.node_openbao_assignment_readiness = lambda credential: (False, "")
    np_openbao.resolve_endpoint_api_secret = lambda endpoint, field: getattr(
        endpoint, field
    )
    np_openbao.resolve_node_ssh_password = lambda credential, *, key, user=None: (
        credential.get_password(key=key)
    )
    np_openbao.resolve_node_ssh_private_key = lambda credential, *, key, user=None: (
        credential.get_private_key(key=key)
    )

    for name, mod in [
        ("django", django),
        ("django.conf", django_conf),
        ("django.shortcuts", django_shortcuts),
        ("django.views", django_views),
        ("django.views.decorators", django_views_decorators),
        ("django.views.decorators.debug", django_views_debug),
        ("netbox", netbox),
        ("netbox.api", netbox_api),
        ("netbox.api.authentication", netbox_api_auth),
        ("utilities", utilities),
        ("utilities.permissions", utilities_permissions),
        ("rest_framework", rest_framework),
        ("rest_framework.status", rf_status),
        ("rest_framework.permissions", rf_permissions),
        ("rest_framework.request", rf_request),
        ("rest_framework.response", rf_response),
        ("rest_framework.views", rf_views),
        ("netbox_proxbox.models", np_models),
        ("netbox_proxbox.models.ssh_credential", np_models_ssh),
        ("netbox_proxbox.utils", np_utils),
        ("netbox_proxbox.utils.encryption", enc_mod),
        ("netbox.plugins", netbox_plugins),
        ("netbox_proxbox", np_pkg),
        ("netbox_proxbox.integrations", np_integrations),
        ("netbox_proxbox.integrations.openbao", np_openbao),
    ]:
        monkeypatch.setitem(sys.modules, name, mod)

    return SimpleNamespace(
        NodeSSHCredential=_NodeSSHCredential,
        ProxboxPluginSettings=_ProxboxPluginSettings,
        ProxmoxEndpoint=_ProxmoxEndpoint,
        ProxmoxNode=_ProxmoxNode,
    )


def _load_ssh_credentials_view(
    monkeypatch,
    *,
    authenticated: bool = True,
    has_perm: bool = True,
):
    stubs = _stub_for_ssh_credentials(
        monkeypatch,
        authenticated=authenticated,
        has_perm=has_perm,
    )
    spec = importlib.util.spec_from_file_location(
        "_ssh_credentials_under_test", API_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, stubs


def _request(*, header: str = "", secure: bool = False):
    return SimpleNamespace(
        headers={"Authorization": header} if header else {},
        is_secure=lambda: secure,
    )


def test_netbox_token_rejects_missing_header(monkeypatch):
    module, _ = _load_ssh_credentials_view(monkeypatch)
    perm = module._NetBoxTokenCanViewNodeSSHCredential()
    assert perm.has_permission(_request(), object()) is False


def test_netbox_token_rejects_non_api_token_scheme(monkeypatch):
    module, _ = _load_ssh_credentials_view(monkeypatch)
    perm = module._NetBoxTokenCanViewNodeSSHCredential()
    assert perm.has_permission(_request(header="Basic abc"), object()) is False


def test_netbox_token_rejects_empty_token(monkeypatch):
    module, _ = _load_ssh_credentials_view(monkeypatch)
    perm = module._NetBoxTokenCanViewNodeSSHCredential()
    assert perm.has_permission(_request(header="Bearer "), object()) is False


def test_netbox_token_rejects_wrong_token(monkeypatch):
    module, _ = _load_ssh_credentials_view(monkeypatch)
    perm = module._NetBoxTokenCanViewNodeSSHCredential()
    assert perm.has_permission(_request(header="Bearer wrong"), object()) is False


def test_netbox_token_accepts_token_scheme(monkeypatch):
    module, _ = _load_ssh_credentials_view(monkeypatch)
    perm = module._NetBoxTokenCanViewNodeSSHCredential()
    assert (
        perm.has_permission(_request(header="Token expected-token"), object()) is True
    )


def test_netbox_token_accepts_bearer_scheme(monkeypatch):
    module, _ = _load_ssh_credentials_view(monkeypatch)
    perm = module._NetBoxTokenCanViewNodeSSHCredential()
    assert (
        perm.has_permission(_request(header="Bearer nbt_key.expected-secret"), object())
        is True
    )


def test_netbox_token_stores_authenticated_user_for_object_permissions(monkeypatch):
    module, _ = _load_ssh_credentials_view(monkeypatch)
    request = _request(header="Bearer nbt_key.expected-secret")
    perm = module._NetBoxTokenCanReadEndpointSSHCredential()

    assert perm.has_permission(request, object()) is True
    assert request.user.is_authenticated is True
    assert request.auth.key == "nbt_key.expected-secret"


def test_netbox_token_rejects_user_without_permission(monkeypatch):
    module, _ = _load_ssh_credentials_view(monkeypatch, has_perm=False)
    perm = module._NetBoxTokenCanViewNodeSSHCredential()
    assert (
        perm.has_permission(_request(header="Token expected-token"), object()) is False
    )


def test_netbox_token_rejects_unauthenticated_user(monkeypatch):
    module, _ = _load_ssh_credentials_view(monkeypatch, authenticated=False)
    perm = module._NetBoxTokenCanViewNodeSSHCredential()
    assert (
        perm.has_permission(_request(header="Token expected-token"), object()) is False
    )


# ---------------------------------------------------------------------------
# Behavior: node lookup accepts ProxmoxNode PK with NetBox device PK fallback
# ---------------------------------------------------------------------------


def test_credential_lookup_prefers_proxmox_node_id(monkeypatch):
    module, stubs = _load_ssh_credentials_view(monkeypatch)
    credential = SimpleNamespace(pk=1)

    class _QuerySet:
        def __init__(self):
            self.calls = []

        def select_related(self, *fields):
            self.select_related_fields = fields
            return self

        def get(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs == {"node_id": 42}:
                return credential
            if kwargs == {"node__netbox_device_id": 42}:
                raise stubs.NodeSSHCredential.DoesNotExist()
            raise AssertionError(f"unexpected lookup: {kwargs}")

    queryset = _QuerySet()
    stubs.NodeSSHCredential.objects = queryset

    assert module._credential_for_node_identifier(42) is credential
    assert queryset.calls == [{"node_id": 42}, {"node__netbox_device_id": 42}]
    assert queryset.select_related_fields == (
        "node",
        "node__netbox_device",
        "node__endpoint",
    )


def test_credential_lookup_falls_back_to_netbox_device_id(monkeypatch):
    module, stubs = _load_ssh_credentials_view(monkeypatch)
    credential = SimpleNamespace(pk=2)

    class _QuerySet:
        def __init__(self):
            self.calls = []

        def select_related(self, *fields):
            return self

        def get(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs == {"node_id": 99}:
                raise stubs.NodeSSHCredential.DoesNotExist()
            if kwargs == {"node__netbox_device_id": 99}:
                return credential
            raise AssertionError(f"unexpected lookup: {kwargs}")

    queryset = _QuerySet()
    stubs.NodeSSHCredential.objects = queryset

    assert module._credential_for_node_identifier(99) is credential
    assert queryset.calls == [
        {"node_id": 99},
        {"node__netbox_device_id": 99},
    ]


def test_credential_lookup_refuses_a_pk_versus_device_id_collision(monkeypatch):
    """42 is simultaneously node 42's own credential row's PK match *and*
    node 100's linked-device PK match, for two genuinely different
    credentials. Both interpretations are valid on their own; picking either
    silently would return the wrong caller's secret material.
    """
    module, stubs = _load_ssh_credentials_view(monkeypatch)
    by_pk_credential = SimpleNamespace(pk=1, node_id=42)
    by_device_credential = SimpleNamespace(pk=2, node_id=100)

    class _QuerySet:
        def select_related(self, *_fields):
            return self

        def get(self, **kwargs):
            if kwargs == {"node_id": 42}:
                return by_pk_credential
            if kwargs == {"node__netbox_device_id": 42}:
                return by_device_credential
            raise AssertionError(f"unexpected lookup: {kwargs}")

    stubs.NodeSSHCredential.objects = _QuerySet()

    with pytest.raises(module._AmbiguousNodeIdentifier):
        module._credential_for_node_identifier(42)


def test_credential_lookup_refuses_pk_plus_multiple_device_matches(
    monkeypatch,
):
    """One PK match plus several device-id matches is ambiguous: a caller
    passing a device id could otherwise receive the PK node's credential."""
    module, stubs = _load_ssh_credentials_view(monkeypatch)
    by_pk_credential = SimpleNamespace(pk=1, node_id=42)

    class _QuerySet:
        def select_related(self, *_fields):
            return self

        def get(self, **kwargs):
            if kwargs == {"node_id": 42}:
                return by_pk_credential
            if kwargs == {"node__netbox_device_id": 42}:
                raise stubs.NodeSSHCredential.MultipleObjectsReturned()
            raise AssertionError(f"unexpected lookup: {kwargs}")

    stubs.NodeSSHCredential.objects = _QuerySet()

    with pytest.raises(module._AmbiguousNodeIdentifier):
        module._credential_for_node_identifier(42)


# ---------------------------------------------------------------------------
# Behavior: _metadata_payload never exposes ciphertext or plaintext secrets
# ---------------------------------------------------------------------------


def test_metadata_payload_omits_secrets(monkeypatch):
    module, _ = _load_ssh_credentials_view(monkeypatch)
    cred = SimpleNamespace(
        pk=7,
        node_id=42,
        username="proxbox-discovery",
        port=22,
        auth_method="key",
        known_host_fingerprint="SHA256:" + "A" * 43,
        sudo_required=True,
        password_enc="ciphertext-password",
        private_key_enc="",
        has_password=True,
        has_private_key=False,
    )
    payload = module._metadata_payload(cred)
    assert payload == {
        "id": 7,
        "node_id": 42,
        "username": "proxbox-discovery",
        "port": 22,
        "auth_method": "key",
        "known_host_fingerprint": "SHA256:" + "A" * 43,
        "sudo_required": True,
        "has_password": True,
        "has_private_key": False,
    }
    # No ciphertext, no decrypted plaintext, no _enc fields leaked.
    assert "password_enc" not in payload
    assert "private_key_enc" not in payload
    assert "password" not in payload
    assert "private_key" not in payload


def _node_credential_queryset(credential, *, node_ssh_credential_stub):
    """Stand-in for ``NodeSSHCredential.objects`` supporting both the PK and
    linked-device-PK lookups ``_credential_for_node_identifier()`` always
    issues. Only the PK lookup matches; the device-PK lookup raises
    ``DoesNotExist``.
    """

    class _QuerySet:
        def select_related(self, *_fields):
            return self

        def get(self, **kwargs):
            if kwargs == {"node_id": credential.node_id}:
                return credential
            if "node__netbox_device_id" in kwargs:
                raise node_ssh_credential_stub.DoesNotExist()
            raise AssertionError(f"unexpected credential lookup: {kwargs}")

    return _QuerySet()


def test_node_secrets_view_resolves_openbao_with_authenticated_actor(monkeypatch):
    module, stubs = _load_ssh_credentials_view(monkeypatch)
    actor = SimpleNamespace(username="proxbox-api")
    credential = SimpleNamespace(
        pk=7,
        node_id=42,
        node=SimpleNamespace(endpoint=SimpleNamespace(ssh_access_enabled=True)),
        username="proxbox-discovery",
        port=22,
        auth_method="password",
        known_host_fingerprint="SHA256:" + "A" * 43,
        sudo_required=True,
        has_password=True,
        has_private_key=False,
    )
    stubs.NodeSSHCredential.objects = _node_credential_queryset(
        credential, node_ssh_credential_stub=stubs.NodeSSHCredential
    )
    openbao = sys.modules["netbox_proxbox.integrations.openbao"]
    openbao.node_uses_openbao_storage = lambda _credential: True
    calls = []

    def _resolve_password(_credential, *, key, user=None):
        calls.append((key, user))
        return "openbao-password"

    openbao.resolve_node_ssh_password = _resolve_password
    request = SimpleNamespace(
        user=actor,
        is_secure=lambda: True,
    )

    response = module.NodeSSHCredentialSecretsAPIView().get(request, 42)

    assert response.status_code == 200
    assert response.data["password"] == "openbao-password"
    assert response.data["private_key"] == ""
    assert calls == [("", actor)]


def test_node_secrets_view_sanitizes_openbao_failure(monkeypatch):
    module, stubs = _load_ssh_credentials_view(monkeypatch)
    credential = SimpleNamespace(
        pk=7,
        node_id=42,
        node=SimpleNamespace(endpoint=SimpleNamespace(ssh_access_enabled=True)),
        username="proxbox-discovery",
        port=22,
        auth_method="password",
        known_host_fingerprint="SHA256:" + "A" * 43,
        sudo_required=True,
        has_password=True,
        has_private_key=False,
    )
    stubs.NodeSSHCredential.objects = _node_credential_queryset(
        credential, node_ssh_credential_stub=stubs.NodeSSHCredential
    )
    openbao = sys.modules["netbox_proxbox.integrations.openbao"]
    openbao.node_uses_openbao_storage = lambda _credential: True

    def _fail(*_args, **_kwargs):
        raise module.ValidationError("provider-internal-secret-path")

    openbao.resolve_node_ssh_password = _fail
    request = SimpleNamespace(user=object(), is_secure=lambda: True)

    response = module.NodeSSHCredentialSecretsAPIView().get(request, 42)

    assert response.status_code == 503
    assert "provider-internal-secret-path" not in str(response.data)
    assert response.data == {
        "detail": (
            "Stored SSH credential cannot be resolved. Credential storage "
            "recovery is required."
        )
    }


def test_endpoint_metadata_payload_omits_secrets(monkeypatch):
    module, _ = _load_ssh_credentials_view(monkeypatch)
    endpoint = SimpleNamespace(
        pk=3,
        ssh_host="pve.example.com",
        ssh_username="proxbox",
        ssh_port=22,
        ssh_auth_method="key",
        ssh_known_host_fingerprint="SHA256:" + "A" * 43,
        ssh_password_enc="ciphertext-password",
        ssh_private_key_enc="ciphertext-key",
    )
    payload = module._endpoint_metadata_payload(endpoint)
    assert payload == {
        "endpoint_id": 3,
        "host": "pve.example.com",
        "username": "proxbox",
        "port": 22,
        "auth_method": "key",
        "known_host_fingerprint": "SHA256:" + "A" * 43,
        "has_password": True,
        "has_private_key": True,
    }
    assert "ssh_password_enc" not in payload
    assert "ssh_private_key_enc" not in payload
    assert "password" not in payload
    assert "private_key" not in payload


def test_endpoint_metadata_payload_uses_reuse_effective_username(monkeypatch):
    module, _ = _load_ssh_credentials_view(monkeypatch)
    endpoint = SimpleNamespace(
        pk=3,
        ssh_host="pve.example.com",
        ssh_access_enabled=True,
        ssh_credential_source="reuse_endpoint",
        effective_ssh_username="root",
        ssh_username="ignored",
        ssh_port=22,
        ssh_auth_method="key",
        ssh_known_host_fingerprint="SHA256:" + "A" * 43,
        password="endpoint-secret",
        password_enc="ciphertext-endpoint-password",
        ssh_password_enc="ciphertext-password",
        ssh_private_key_enc="ciphertext-key",
    )
    payload = module._endpoint_metadata_payload(endpoint)
    assert payload["username"] == "root"
    assert payload["auth_method"] == "password"
    assert payload["has_password"] is True
    assert payload["has_private_key"] is False


class _EndpointQuerySet:
    def __init__(self, endpoint):
        self.endpoint = endpoint
        self.restrict_calls = []

    def restrict(self, user, action):
        self.restrict_calls.append((user, action))
        return self

    def get(self, **kwargs):
        if kwargs == {"pk": self.endpoint.pk}:
            return self.endpoint
        raise AssertionError(f"unexpected endpoint lookup: {kwargs}")


def _endpoint_secret_request():
    return SimpleNamespace(
        headers={"Authorization": "Token expected-token"},
        is_secure=lambda: True,
        user=SimpleNamespace(username="proxbox-api"),
    )


def test_endpoint_secrets_view_reuse_returns_endpoint_password(monkeypatch):
    module, stubs = _load_ssh_credentials_view(monkeypatch)
    endpoint = SimpleNamespace(
        pk=11,
        ssh_host="pve.example.com",
        ssh_access_enabled=True,
        ssh_credential_source="reuse_endpoint",
        effective_ssh_username="root",
        ssh_username="ignored",
        ssh_port=22,
        ssh_auth_method="key",
        ssh_known_host_fingerprint="SHA256:" + "A" * 43,
        password="endpoint-secret",
        password_enc="ciphertext-endpoint-password",
        ssh_password_enc="",
        ssh_private_key_enc="",
        has_ssh_terminal_credentials=True,
    )
    stubs.ProxmoxEndpoint.objects = _EndpointQuerySet(endpoint)

    response = module.ProxmoxEndpointSSHCredentialSecretsAPIView().get(
        _endpoint_secret_request(),
        endpoint.pk,
    )

    assert response.status_code == 200
    assert response.data["username"] == "root"
    assert response.data["auth_method"] == "password"
    assert response.data["password"] == "endpoint-secret"
    assert response.data["private_key"] == ""


def test_endpoint_secrets_view_reuse_token_only_returns_422(monkeypatch):
    module, stubs = _load_ssh_credentials_view(monkeypatch)
    endpoint = SimpleNamespace(
        pk=12,
        ssh_host="pve.example.com",
        ssh_access_enabled=True,
        ssh_credential_source="reuse_endpoint",
        effective_ssh_username="root",
        ssh_username="ignored",
        ssh_port=22,
        ssh_auth_method="key",
        ssh_known_host_fingerprint="SHA256:" + "A" * 43,
        password="",
        ssh_password_enc="",
        ssh_private_key_enc="",
        has_ssh_terminal_credentials=False,
    )
    stubs.ProxmoxEndpoint.objects = _EndpointQuerySet(endpoint)

    response = module.ProxmoxEndpointSSHCredentialSecretsAPIView().get(
        _endpoint_secret_request(),
        endpoint.pk,
    )

    assert response.status_code == 422
    assert (
        "Token-only endpoints cannot reuse SSH credentials" in response.data["detail"]
    )


def test_endpoint_secrets_view_dedicated_decrypts_existing_payload(monkeypatch):
    module, stubs = _load_ssh_credentials_view(monkeypatch)
    stubs.ProxboxPluginSettings.get_solo = staticmethod(
        lambda: SimpleNamespace(encryption_key="fernet-key")
    )
    endpoint = SimpleNamespace(
        pk=13,
        ssh_host="pve.example.com",
        ssh_access_enabled=True,
        ssh_credential_source="dedicated",
        ssh_username="proxbox",
        ssh_port=22,
        ssh_auth_method="password",
        ssh_known_host_fingerprint="SHA256:" + "A" * 43,
        password="endpoint-secret",
        ssh_password_enc="ciphertext-password",
        ssh_private_key_enc="",
        has_ssh_terminal_credentials=True,
        get_ssh_password=lambda *, key: f"decrypted-with-{key}",
    )
    stubs.ProxmoxEndpoint.objects = _EndpointQuerySet(endpoint)

    response = module.ProxmoxEndpointSSHCredentialSecretsAPIView().get(
        _endpoint_secret_request(),
        endpoint.pk,
    )

    assert response.status_code == 200
    assert response.data["username"] == "proxbox"
    assert response.data["auth_method"] == "password"
    assert response.data["password"] == "decrypted-with-fernet-key"
    assert response.data["private_key"] == ""


# ---------------------------------------------------------------------------
# AST contract on the two APIView classes
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def api_ast() -> ast.Module:
    return ast.parse(API_PATH.read_text())


def _class_def(tree: ast.Module, name: str) -> ast.ClassDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"class {name!r} not found")


def test_by_node_view_uses_dashboard_permission(api_ast):
    cls = _class_def(api_ast, "NodeSSHCredentialByNodeAPIView")
    src = ast.get_source_segment(API_PATH.read_text(), cls)
    assert src is not None
    assert "_ProxboxDashboardPermission" in src


def test_secrets_view_uses_netbox_token_permission(api_ast):
    cls = _class_def(api_ast, "NodeSSHCredentialSecretsAPIView")
    targets = []
    for node in cls.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "permission_classes":
                    targets.append(node)
    assert targets, "permission_classes assignment missing on SecretsAPIView"
    src = ast.get_source_segment(API_PATH.read_text(), targets[0])
    assert src is not None and "_NetBoxTokenCanViewNodeSSHCredential" in src


def test_endpoint_secrets_view_uses_terminal_permission(api_ast):
    cls = _class_def(api_ast, "ProxmoxEndpointSSHCredentialSecretsAPIView")
    src = ast.get_source_segment(API_PATH.read_text(), cls)
    assert src is not None
    assert "_NetBoxTokenCanReadEndpointSSHCredential" in src
    assert (
        'get_permission_for_model(ProxmoxEndpoint, "open_ssh_terminal")'
        in API_PATH.read_text()
    )


def test_endpoint_secrets_view_restricts_by_view_and_terminal_permissions(api_ast):
    cls = _class_def(api_ast, "ProxmoxEndpointSSHCredentialSecretsAPIView")
    src = ast.get_source_segment(API_PATH.read_text(), cls)
    assert src is not None
    assert 'restrict(request.user, "view")' in src
    assert 'request.user, "open_ssh_terminal"' in src


def test_secrets_view_blocks_non_https_in_production(api_ast):
    """The secrets view must refuse non-HTTPS requests when DEBUG is False."""
    src = API_PATH.read_text()
    assert "is_secure" in src
    assert "django_settings.DEBUG" in src
    assert "HTTPS required" in src


def test_secrets_view_returns_503_when_key_missing(api_ast):
    src = API_PATH.read_text()
    assert "HTTP_503_SERVICE_UNAVAILABLE" in src
    assert "encryption_key" in src


# ---------------------------------------------------------------------------
# AST contract on URL wiring
# ---------------------------------------------------------------------------


def test_urls_register_by_node_metadata_route():
    src = URLS_PATH.read_text()
    assert "ssh-credentials/by-node/<int:node_id>/" in src
    assert "NodeSSHCredentialByNodeAPIView" in src
    assert "api-ssh-credential-by-node" in src


def test_urls_register_secrets_route():
    src = URLS_PATH.read_text()
    assert "ssh-credentials/by-node/<int:node_id>/credentials/" in src
    assert "NodeSSHCredentialSecretsAPIView" in src
    assert "api-ssh-credential-secrets" in src


def test_urls_register_endpoint_secrets_route():
    src = URLS_PATH.read_text()
    assert "ssh-credentials/by-endpoint/<int:endpoint_id>/credentials/" in src
    assert "ProxmoxEndpointSSHCredentialSecretsAPIView" in src
    assert "api-ssh-credential-endpoint-secrets" in src


def test_urls_register_crud_router():
    src = URLS_PATH.read_text()
    assert "router.register" in src
    assert "ssh-credentials" in src
    assert "NodeSSHCredentialViewSet" in src
    assert "nodesshcredential" in src


# ---------------------------------------------------------------------------
# Contract: node host-key scan view + URL wiring (Terminal-tab credential modal)
# ---------------------------------------------------------------------------


def test_node_host_key_scan_view_is_declared() -> None:
    src = API_PATH.read_text()
    assert "class NodeHostKeyFingerprintAPIView(APIView):" in src
    # Gated by an open_ssh_terminal session permission (mirrors the tab), not a
    # NetBox API token.
    assert "class _ProxmoxEndpointOpenTerminalPermission(BasePermission):" in src
    assert 'user.has_perm("netbox_proxbox.open_ssh_terminal")' in src
    assert "permission_classes = [_ProxmoxEndpointOpenTerminalPermission]" in src
    # Resolves the node IP server-side, honors the modal ?port=, enforces the
    # owning endpoint's SSH access method, and proxies to proxbox-api.
    assert "node.ip_address" in src
    assert 'request.query_params.get("port")' in src
    assert "endpoint.ssh_access_enabled" in src
    assert "/ssh/host-key-fingerprint" in src
    # Degrades gracefully on an old/absent backend (404 -> 503) and never sends a
    # credential (only reads the public host key).
    assert "status.HTTP_503_SERVICE_UNAVAILABLE" in src
    assert "status.HTTP_403_FORBIDDEN" in src


def test_node_host_key_scan_route_is_registered() -> None:
    src = URLS_PATH.read_text()
    assert "ssh-credentials/by-node/<int:node_id>/host-key-fingerprint/" in src
    assert "NodeHostKeyFingerprintAPIView" in src
    assert 'name="api-ssh-credential-node-host-key"' in src


# ---------------------------------------------------------------------------
# Behavior: NodeSSHCredentialSecretsAPIView._resolve_from_device_openbao
# (issue #614)
# ---------------------------------------------------------------------------


class _NodeQuerySet:
    """Stand-in for ``ProxmoxNode.objects`` with real ``.get()`` semantics:
    zero matches raises ``DoesNotExist``, more than one raises
    ``MultipleObjectsReturned`` — the same fail-closed behavior Django's ORM
    gives ``_credential_for_node_identifier()`` on the local-credential path.
    """

    def __init__(self, nodes: list, *, does_not_exist, multiple_returned) -> None:
        self._nodes = nodes
        self._does_not_exist = does_not_exist
        self._multiple_returned = multiple_returned

    def select_related(self, *_fields):
        return self

    def get(self, **kwargs):
        ((field, value),) = kwargs.items()
        matches = [n for n in self._nodes if getattr(n, field) == value]
        if not matches:
            raise self._does_not_exist()
        if len(matches) > 1:
            raise self._multiple_returned()
        return matches[0]


def _load_device_openbao_fallback(monkeypatch, *, resolver, nodes: list | None = None):
    """Load ssh_credentials with a NodeSSHCredential lookup miss and a stub
    ``netbox_proxbox.api.device_openbao_ssh_resolver`` module providing
    *resolver*.

    *nodes* defaults to a single ``ProxmoxNode`` whose own ``pk`` (42) differs
    from its linked NetBox device's id (4242), so a test that requests either
    identifier exercises the real PK-first/device-PK-second resolution
    instead of a stub that returns the same node regardless of lookup.
    """
    module, stubs = _load_ssh_credentials_view(monkeypatch)

    class _MissingQuerySet:
        def select_related(self, *_fields):
            return self

        def get(self, **_kwargs):
            raise stubs.NodeSSHCredential.DoesNotExist()

    stubs.NodeSSHCredential.objects = _MissingQuerySet()

    if nodes is None:
        nodes = [
            SimpleNamespace(
                pk=42, netbox_device_id=4242, netbox_device=SimpleNamespace()
            )
        ]
    module.ProxmoxNode.objects = _NodeQuerySet(
        nodes,
        does_not_exist=stubs.ProxmoxNode.DoesNotExist,
        multiple_returned=stubs.ProxmoxNode.MultipleObjectsReturned,
    )

    resolver_mod = types.ModuleType("netbox_proxbox.api.device_openbao_ssh_resolver")
    resolver_mod.resolve_node_ssh_from_device_openbao = resolver
    monkeypatch.setitem(
        sys.modules,
        "netbox_proxbox.api.device_openbao_ssh_resolver",
        resolver_mod,
    )
    return module, nodes[0]


def _fallback_request(*, port: str | None = None):
    return SimpleNamespace(
        user=SimpleNamespace(),
        is_secure=lambda: True,
        query_params={} if port is None else {"port": port},
    )


def test_resolve_from_device_openbao_returns_payload_on_match(monkeypatch):
    calls = []

    def _resolver(node, *, user=None, port=None):
        calls.append((node, user, port))
        return {"node_id": node.pk, "username": "root"}

    module, node = _load_device_openbao_fallback(monkeypatch, resolver=_resolver)
    request = _fallback_request()

    response = module.NodeSSHCredentialSecretsAPIView().get(request, 42)

    assert response.status_code == 200
    assert response.data == {"node_id": 42, "username": "root"}
    assert calls == [(node, request.user, None)]


def test_resolve_from_device_openbao_forwards_a_valid_port(monkeypatch):
    calls = []

    def _resolver(node, *, user=None, port=None):
        calls.append(port)
        return {"node_id": node.pk}

    module, _node = _load_device_openbao_fallback(monkeypatch, resolver=_resolver)
    request = _fallback_request(port="2222")

    module.NodeSSHCredentialSecretsAPIView().get(request, 42)

    assert calls == [2222]


def test_resolve_from_device_openbao_ignores_an_invalid_port(monkeypatch):
    calls = []

    def _resolver(node, *, user=None, port=None):
        calls.append(port)
        return {"node_id": node.pk}

    module, _node = _load_device_openbao_fallback(monkeypatch, resolver=_resolver)
    request = _fallback_request(port="not-a-port")

    module.NodeSSHCredentialSecretsAPIView().get(request, 42)

    assert calls == [None]


def test_resolve_from_device_openbao_returns_404_when_nothing_matches(monkeypatch):
    module, _node = _load_device_openbao_fallback(
        monkeypatch, resolver=lambda *a, **k: None
    )
    request = _fallback_request()

    response = module.NodeSSHCredentialSecretsAPIView().get(request, 42)

    assert response.status_code == 404
    assert "No local NodeSSHCredential" in response.data["detail"]


def test_resolve_from_device_openbao_translates_permission_denied_to_403(
    monkeypatch,
):
    def _deny(*_args, **_kwargs):
        raise module_permission_denied_exception("ambiguous match")

    module, _node = _load_device_openbao_fallback(monkeypatch, resolver=_deny)
    request = _fallback_request()

    response = module.NodeSSHCredentialSecretsAPIView().get(request, 42)

    assert response.status_code == 403
    assert response.data == {"detail": "ambiguous match"}


def test_resolve_from_device_openbao_falls_back_to_linked_device_id(monkeypatch):
    """proxbox-api may pass the linked ``dcim.Device`` id instead of the
    ``ProxmoxNode`` PK, exactly as ``_credential_for_node_identifier()``
    already tolerates on the local-credential path. The node's own pk (42)
    differs from its device id (4242) so a stub that ignored the lookup field
    would pass this test vacuously.
    """
    calls = []

    def _resolver(node, *, user=None, port=None):
        calls.append(node.pk)
        return {"node_id": node.pk}

    module, node = _load_device_openbao_fallback(monkeypatch, resolver=_resolver)
    request = _fallback_request()

    response = module.NodeSSHCredentialSecretsAPIView().get(
        request, node.netbox_device_id
    )

    assert response.status_code == 200
    assert calls == [node.pk]


def test_resolve_from_device_openbao_returns_404_for_unknown_identifier(monkeypatch):
    module, _node = _load_device_openbao_fallback(
        monkeypatch, resolver=lambda *a, **k: {"should": "not run"}
    )
    request = _fallback_request()

    response = module.NodeSSHCredentialSecretsAPIView().get(request, 999999)

    assert response.status_code == 404


def test_resolve_from_device_openbao_refuses_an_ambiguous_device_id(monkeypatch):
    """Two ProxmoxNode rows linked to the same NetBox device must fail
    closed rather than silently resolving to an arbitrary one of them.
    """

    def _boom(*_args, **_kwargs):
        raise AssertionError("the resolver must not run on an ambiguous lookup")

    shared_device_id = 4242
    nodes = [
        SimpleNamespace(
            pk=42, netbox_device_id=shared_device_id, netbox_device=SimpleNamespace()
        ),
        SimpleNamespace(
            pk=43, netbox_device_id=shared_device_id, netbox_device=SimpleNamespace()
        ),
    ]
    module, _node = _load_device_openbao_fallback(
        monkeypatch, resolver=_boom, nodes=nodes
    )
    request = _fallback_request()

    response = module.NodeSSHCredentialSecretsAPIView().get(request, shared_device_id)

    assert response.status_code == 404
    assert "Multiple Proxmox nodes" in response.data["detail"]


def test_resolve_from_device_openbao_refuses_a_pk_versus_device_id_collision(
    monkeypatch,
):
    """42 is simultaneously node A's own pk *and* node B's linked device id,
    for two genuinely different nodes. Silently preferring either interpretation
    would resolve — and potentially reveal — the wrong node's SSH material.
    """

    def _boom(*_args, **_kwargs):
        raise AssertionError("the resolver must not run on an ambiguous lookup")

    node_a = SimpleNamespace(
        pk=42, netbox_device_id=9001, netbox_device=SimpleNamespace()
    )
    node_b = SimpleNamespace(
        pk=100, netbox_device_id=42, netbox_device=SimpleNamespace()
    )
    module, _node = _load_device_openbao_fallback(
        monkeypatch, resolver=_boom, nodes=[node_a, node_b]
    )
    request = _fallback_request()

    response = module.NodeSSHCredentialSecretsAPIView().get(request, 42)

    assert response.status_code == 404
    assert "matches both a Proxmox node's own id" in response.data["detail"]


def test_resolve_from_device_openbao_refuses_pk_plus_multiple_device_matches(
    monkeypatch,
):
    """One PK match plus several device-id matches must fail closed and never
    reveal any node's secret."""
    calls = []

    def _resolver(node, *, user=None, port=None):
        calls.append(node.pk)
        return {"node_id": node.pk}

    node_a = SimpleNamespace(
        pk=42, netbox_device_id=9001, netbox_device=SimpleNamespace()
    )
    node_b = SimpleNamespace(
        pk=100, netbox_device_id=42, netbox_device=SimpleNamespace()
    )
    node_c = SimpleNamespace(
        pk=101, netbox_device_id=42, netbox_device=SimpleNamespace()
    )
    module, _node = _load_device_openbao_fallback(
        monkeypatch, resolver=_resolver, nodes=[node_a, node_b, node_c]
    )
    request = _fallback_request()

    response = module.NodeSSHCredentialSecretsAPIView().get(request, 42)

    assert response.status_code == 404
    assert calls == []


def module_permission_denied_exception(message):
    """Raise the same ``PermissionDenied`` class the loaded module imported."""
    return sys.modules["django.core.exceptions"].PermissionDenied(message)


# ---------------------------------------------------------------------------
# Behavior: NodeHostKeyFingerprintAPIView.get (node host-key scan)
# ---------------------------------------------------------------------------


def _load_node_scan(
    monkeypatch, *, ssh_enabled=True, ip_address="10.0.0.5", ctx="default"
):
    """Load ssh_credentials with node + backend-context stubs for the scan view."""
    module, _stubs = _load_ssh_credentials_view(monkeypatch)
    # The node scan view uses a 502 status the shared stub does not define.
    module.status.HTTP_502_BAD_GATEWAY = 502

    endpoint = SimpleNamespace(ssh_access_enabled=ssh_enabled)
    node = SimpleNamespace(ip_address=ip_address, endpoint=endpoint)

    class _NodeQS:
        def restrict(self, *a, **k):
            return self

        def select_related(self, *a, **k):
            return self

        def get(self, **kw):
            return node

    module.ProxmoxNode.objects = _NodeQS()

    backend_context = types.ModuleType("netbox_proxbox.services.backend_context")
    ctx_obj = (
        SimpleNamespace(http_url="http://backend", headers={}, verify_ssl=True)
        if ctx == "default"
        else ctx
    )
    backend_context.get_fastapi_request_context = lambda: ctx_obj
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services.backend_context", backend_context
    )
    return module, node


def _scan_request(port="2222"):
    return SimpleNamespace(user=SimpleNamespace(), query_params={"port": port})


def test_node_scan_403_when_ssh_disabled(monkeypatch):
    module, _ = _load_node_scan(monkeypatch, ssh_enabled=False)
    resp = module.NodeHostKeyFingerprintAPIView().get(_scan_request(), 15)
    assert resp.status_code == 403


def test_node_scan_422_when_node_has_no_ip(monkeypatch):
    module, _ = _load_node_scan(monkeypatch, ip_address="")
    resp = module.NodeHostKeyFingerprintAPIView().get(_scan_request(), 15)
    assert resp.status_code == 422


def test_node_scan_503_when_no_backend(monkeypatch):
    module, _ = _load_node_scan(monkeypatch, ctx=None)
    resp = module.NodeHostKeyFingerprintAPIView().get(_scan_request(), 15)
    assert resp.status_code == 503


def test_node_scan_success_forwards_host_and_port(monkeypatch):
    module, _ = _load_node_scan(monkeypatch)
    captured = {}

    def fake_get(
        url, params=None, headers=None, verify=None, timeout=None, allow_redirects=True
    ):
        captured["url"] = url
        captured["params"] = params
        return SimpleNamespace(
            status_code=200,
            ok=True,
            json=lambda: {"fingerprint": "SHA256:xyz", "key_type": "ssh-ed25519"},
        )

    monkeypatch.setattr(module.requests, "get", fake_get)
    resp = module.NodeHostKeyFingerprintAPIView().get(_scan_request(port="2222"), 15)
    assert resp.status_code == 200
    assert resp.data["fingerprint"] == "SHA256:xyz"
    assert resp.data["port"] == 2222
    assert captured["url"].endswith("/ssh/host-key-fingerprint")
    assert captured["params"] == {"host": "10.0.0.5", "port": 2222}


def test_node_scan_invalid_port_defaults_to_22(monkeypatch):
    module, _ = _load_node_scan(monkeypatch)
    captured = {}

    def fake_get(
        url, params=None, headers=None, verify=None, timeout=None, allow_redirects=True
    ):
        captured["params"] = params
        return SimpleNamespace(
            status_code=200, ok=True, json=lambda: {"fingerprint": "SHA256:z"}
        )

    monkeypatch.setattr(module.requests, "get", fake_get)
    resp = module.NodeHostKeyFingerprintAPIView().get(
        _scan_request(port="not-a-number"), 15
    )
    assert resp.status_code == 200
    assert captured["params"]["port"] == 22


def test_node_scan_503_when_backend_lacks_route(monkeypatch):
    module, _ = _load_node_scan(monkeypatch)

    def fake_get(
        url, params=None, headers=None, verify=None, timeout=None, allow_redirects=True
    ):
        return SimpleNamespace(status_code=404, ok=False, json=lambda: {})

    monkeypatch.setattr(module.requests, "get", fake_get)
    resp = module.NodeHostKeyFingerprintAPIView().get(_scan_request(), 15)
    assert resp.status_code == 503
