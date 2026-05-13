"""Tests for ``netbox_proxbox.api.ssh_credentials``.

The endpoint module is half permission policy and half decrypt-and-return
plumbing. Both halves are exercised here without booting Django/DRF:

* ``_ProxboxBackendBearer.has_permission`` — accepts the configured
  FastAPI endpoint token, rejects everything else.
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
# Behavior: _ProxboxBackendBearer.has_permission
# ---------------------------------------------------------------------------


def _stub_for_ssh_credentials(monkeypatch, *, token: str | None = "expected-token"):
    """Minimal stubs so ``ssh_credentials.py`` imports cleanly."""

    django = types.ModuleType("django")
    django_conf = types.ModuleType("django.conf")
    django_conf.settings = SimpleNamespace(DEBUG=False)

    django_shortcuts = types.ModuleType("django.shortcuts")
    django_shortcuts.get_object_or_404 = lambda *a, **kw: SimpleNamespace()

    rest_framework = types.ModuleType("rest_framework")
    rf_status = types.ModuleType("rest_framework.status")
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

    class _FastAPIEndpoint:
        @classmethod
        def configure(cls, token_value):
            class _QS:
                @staticmethod
                def first():
                    if token_value is None:
                        return None
                    return SimpleNamespace(token=token_value)

            cls.objects = _QS

    _FastAPIEndpoint.configure(token)

    class _ProxboxPluginSettings:
        @staticmethod
        def get_solo():
            return SimpleNamespace(encryption_key="")

    class _NodeSSHCredential:
        pass

    np_models = types.ModuleType("netbox_proxbox.models")
    np_models.FastAPIEndpoint = _FastAPIEndpoint
    np_models.NodeSSHCredential = _NodeSSHCredential
    np_models.ProxboxPluginSettings = _ProxboxPluginSettings

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
        FastAPIEndpoint=_FastAPIEndpoint,
        NodeSSHCredential=_NodeSSHCredential,
        ProxboxPluginSettings=_ProxboxPluginSettings,
    )


def _load_ssh_credentials_view(monkeypatch, *, token: str | None = "expected-token"):
    stubs = _stub_for_ssh_credentials(monkeypatch, token=token)
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


def test_bearer_rejects_missing_header(monkeypatch):
    module, _ = _load_ssh_credentials_view(monkeypatch)
    perm = module._ProxboxBackendBearer()
    assert perm.has_permission(_request(), object()) is False


def test_bearer_rejects_non_bearer_scheme(monkeypatch):
    module, _ = _load_ssh_credentials_view(monkeypatch)
    perm = module._ProxboxBackendBearer()
    assert perm.has_permission(_request(header="Basic abc"), object()) is False


def test_bearer_rejects_empty_token(monkeypatch):
    module, _ = _load_ssh_credentials_view(monkeypatch)
    perm = module._ProxboxBackendBearer()
    assert perm.has_permission(_request(header="Bearer "), object()) is False


def test_bearer_rejects_wrong_token(monkeypatch):
    module, _ = _load_ssh_credentials_view(monkeypatch)
    perm = module._ProxboxBackendBearer()
    assert perm.has_permission(_request(header="Bearer wrong"), object()) is False


def test_bearer_accepts_matching_token(monkeypatch):
    module, _ = _load_ssh_credentials_view(monkeypatch)
    perm = module._ProxboxBackendBearer()
    assert (
        perm.has_permission(_request(header="Bearer expected-token"), object()) is True
    )


def test_bearer_rejects_when_no_endpoint_row(monkeypatch):
    module, _ = _load_ssh_credentials_view(monkeypatch, token=None)
    perm = module._ProxboxBackendBearer()
    assert perm.has_permission(_request(header="Bearer anything"), object()) is False


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


def test_secrets_view_uses_backend_bearer(api_ast):
    cls = _class_def(api_ast, "NodeSSHCredentialSecretsAPIView")
    targets = []
    for node in cls.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "permission_classes":
                    targets.append(node)
    assert targets, "permission_classes assignment missing on SecretsAPIView"
    src = ast.get_source_segment(API_PATH.read_text(), targets[0])
    assert src is not None and "_ProxboxBackendBearer" in src


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


def test_urls_register_crud_router():
    src = URLS_PATH.read_text()
    assert "router.register" in src
    assert "ssh-credentials" in src
    assert "NodeSSHCredentialViewSet" in src
    assert "nodesshcredential" in src
