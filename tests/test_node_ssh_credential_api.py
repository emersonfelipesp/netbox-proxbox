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

    django_shortcuts = types.ModuleType("django.shortcuts")
    django_shortcuts.get_object_or_404 = lambda queryset, **kw: queryset.get(**kw)

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

    class _ProxmoxEndpoint:
        pass

    np_models = types.ModuleType("netbox_proxbox.models")
    np_models.NodeSSHCredential = _NodeSSHCredential
    np_models.ProxboxPluginSettings = _ProxboxPluginSettings
    np_models.ProxmoxEndpoint = _ProxmoxEndpoint

    enc_mod = types.ModuleType("netbox_proxbox.utils.encryption")

    class EncryptionError(Exception):
        pass

    enc_mod.EncryptionError = EncryptionError
    enc_mod.encrypt = lambda plaintext, *, key: plaintext
    enc_mod.decrypt = lambda ciphertext, *, key: ciphertext

    np_utils = types.ModuleType("netbox_proxbox.utils")
    np_utils.encryption = enc_mod

    for name, mod in [
        ("django", django),
        ("django.conf", django_conf),
        ("django.shortcuts", django_shortcuts),
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
        ("netbox_proxbox.utils", np_utils),
        ("netbox_proxbox.utils.encryption", enc_mod),
    ]:
        monkeypatch.setitem(sys.modules, name, mod)

    return SimpleNamespace(
        NodeSSHCredential=_NodeSSHCredential,
        ProxboxPluginSettings=_ProxboxPluginSettings,
        ProxmoxEndpoint=_ProxmoxEndpoint,
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


def _request(*, header: str = ""):
    return SimpleNamespace(
        headers={"Authorization": header} if header else {},
        is_secure=lambda: False,
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
            raise AssertionError(f"unexpected lookup: {kwargs}")

    queryset = _QuerySet()
    stubs.NodeSSHCredential.objects = queryset

    assert module._credential_for_node_identifier(42) is credential
    assert queryset.calls == [{"node_id": 42}]
    assert queryset.select_related_fields == ("node", "node__netbox_device")


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
