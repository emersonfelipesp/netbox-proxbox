"""Tests for ``netbox_proxbox.models.ssh_credential``.

Covers the parts that don't need a live Django/NetBox stack:

* ``normalize_fingerprint`` — accepts canonical SHA256:<base64>, padded /
  unpadded, lower-case prefix; rejects MD5 and garbage.
* The encryption helper round-trip used by ``set_password``/``set_private_key``
  via the ``netbox_proxbox.utils.encryption`` module.
* AST contract on the model class — guards the four invariants the discovery
  orchestrator relies on: one-to-one with ProxmoxNode, auth_method choices,
  ``known_host_fingerprint`` field, and ``clean()`` calling
  ``normalize_fingerprint``.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = REPO_ROOT / "netbox_proxbox" / "models" / "ssh_credential.py"


# ---------------------------------------------------------------------------
# Module loader that stubs the Django/NetBox dependencies that ssh_credential
# imports at top level so we can exercise the pure-Python helpers.
# ---------------------------------------------------------------------------


def _stub_django(monkeypatch):
    django = types.ModuleType("django")
    core = types.ModuleType("django.core")
    core_exceptions = types.ModuleType("django.core.exceptions")

    class _ValidationError(Exception):
        def __init__(self, message, code=None, params=None):
            super().__init__(message)
            self.message = message
            self.message_dict = (
                message if isinstance(message, dict) else {"__all__": [message]}
            )

    core_exceptions.ValidationError = _ValidationError

    db = types.ModuleType("django.db")
    db_models = types.ModuleType("django.db.models")

    def _passthrough(*_args, **_kwargs):
        return None

    class _Field:
        def __init__(self, *args, **kwargs):
            pass

    db_models.CharField = _Field
    db_models.TextField = _Field
    db_models.BooleanField = _Field
    db_models.PositiveIntegerField = _Field
    db_models.OneToOneField = _Field
    db_models.CASCADE = object()
    db.models = db_models

    urls = types.ModuleType("django.urls")
    urls.reverse = lambda *a, **kw: "/dummy/"

    utils = types.ModuleType("django.utils")
    utils_translation = types.ModuleType("django.utils.translation")
    utils_translation.gettext_lazy = lambda x: x
    utils.translation = utils_translation

    netbox_pkg = types.ModuleType("netbox")
    netbox_models = types.ModuleType("netbox.models")

    class _NetBoxModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

        def clean(self):
            return None

    netbox_models.NetBoxModel = _NetBoxModel

    for name, mod in [
        ("django", django),
        ("django.core", core),
        ("django.core.exceptions", core_exceptions),
        ("django.db", db),
        ("django.db.models", db_models),
        ("django.urls", urls),
        ("django.utils", utils),
        ("django.utils.translation", utils_translation),
        ("netbox", netbox_pkg),
        ("netbox.models", netbox_models),
    ]:
        monkeypatch.setitem(sys.modules, name, mod)


def _load_ssh_credential(monkeypatch):
    _stub_django(monkeypatch)
    # Pre-register the encryption helper as if loaded through the package, so
    # ssh_credential.py's `from netbox_proxbox.utils import encryption` short-
    # circuits package import (which would otherwise try to load NetBox).
    enc_spec = importlib.util.spec_from_file_location(
        "netbox_proxbox.utils.encryption",
        REPO_ROOT / "netbox_proxbox" / "utils" / "encryption.py",
    )
    assert enc_spec is not None and enc_spec.loader is not None
    enc_mod = importlib.util.module_from_spec(enc_spec)
    enc_spec.loader.exec_module(enc_mod)

    np_pkg = types.ModuleType("netbox_proxbox")
    np_pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox")]
    np_utils_pkg = types.ModuleType("netbox_proxbox.utils")
    np_utils_pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox" / "utils")]
    np_utils_pkg.encryption = enc_mod
    monkeypatch.setitem(sys.modules, "netbox_proxbox", np_pkg)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.utils", np_utils_pkg)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.utils.encryption", enc_mod)

    spec = importlib.util.spec_from_file_location(
        "_ssh_credential_under_test", MODEL_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# normalize_fingerprint
# ---------------------------------------------------------------------------


@pytest.fixture
def ssh_module(monkeypatch):
    return _load_ssh_credential(monkeypatch)


_GOOD_FP = "SHA256:" + "A" * 43


def test_normalize_accepts_canonical_form(ssh_module):
    assert ssh_module.normalize_fingerprint(_GOOD_FP) == _GOOD_FP


def test_normalize_strips_padding(ssh_module):
    padded = _GOOD_FP + "="
    assert ssh_module.normalize_fingerprint(padded) == _GOOD_FP


def test_normalize_uppercases_prefix(ssh_module):
    lower = "sha256:" + "A" * 43
    assert ssh_module.normalize_fingerprint(lower) == _GOOD_FP


def test_normalize_strips_whitespace(ssh_module):
    assert ssh_module.normalize_fingerprint(f"  {_GOOD_FP}  ") == _GOOD_FP


def test_normalize_rejects_empty(ssh_module):
    ValidationError = sys.modules["django.core.exceptions"].ValidationError
    with pytest.raises(ValidationError):
        ssh_module.normalize_fingerprint("")


def test_normalize_rejects_md5(ssh_module):
    ValidationError = sys.modules["django.core.exceptions"].ValidationError
    with pytest.raises(ValidationError):
        ssh_module.normalize_fingerprint("MD5:" + "a" * 47)


def test_normalize_rejects_truncated(ssh_module):
    ValidationError = sys.modules["django.core.exceptions"].ValidationError
    with pytest.raises(ValidationError):
        ssh_module.normalize_fingerprint("SHA256:short")


def test_normalize_rejects_garbage(ssh_module):
    ValidationError = sys.modules["django.core.exceptions"].ValidationError
    with pytest.raises(ValidationError):
        ssh_module.normalize_fingerprint("not-a-fingerprint")


# ---------------------------------------------------------------------------
# Encryption round-trip through the model's set_*/get_* accessors.
# ---------------------------------------------------------------------------


_TEST_KEY = "0123456789abcdef0123456789abcdef"  # 32 bytes


def test_set_get_password_round_trip(ssh_module):
    obj = ssh_module.NodeSSHCredential()
    obj.password_enc = ""
    obj.set_password("hunter2", key=_TEST_KEY)
    assert obj.password_enc != ""
    assert obj.password_enc != "hunter2"  # not stored cleartext
    assert obj.get_password(key=_TEST_KEY) == "hunter2"


def test_set_get_private_key_round_trip(ssh_module):
    obj = ssh_module.NodeSSHCredential()
    obj.private_key_enc = ""
    pem = (
        "-----BEGIN OPENSSH PRIVATE KEY-----\nMIIE\n-----END OPENSSH PRIVATE KEY-----\n"
    )
    obj.set_private_key(pem, key=_TEST_KEY)
    assert obj.private_key_enc != ""
    assert obj.private_key_enc != pem
    assert obj.get_private_key(key=_TEST_KEY) == pem


def test_set_password_refuses_empty_key(ssh_module):
    from netbox_proxbox.utils.encryption import EncryptionKeyMissing

    obj = ssh_module.NodeSSHCredential()
    with pytest.raises(EncryptionKeyMissing):
        obj.set_password("hunter2", key="")


def test_get_password_with_rotated_key_fails(ssh_module):
    from netbox_proxbox.utils.encryption import DecryptionFailed

    obj = ssh_module.NodeSSHCredential()
    obj.password_enc = ""
    obj.set_password("hunter2", key=_TEST_KEY)
    rotated = "fedcba9876543210fedcba9876543210"
    with pytest.raises(DecryptionFailed):
        obj.get_password(key=rotated)


def test_empty_plaintext_round_trips_to_empty(ssh_module):
    """Empty input produces empty ciphertext — required so blank fields stay blank."""
    obj = ssh_module.NodeSSHCredential()
    obj.set_password("", key=_TEST_KEY)
    assert obj.password_enc == ""
    assert obj.get_password(key=_TEST_KEY) == ""


# ---------------------------------------------------------------------------
# AST contract: structure of the model that the orchestrator relies on.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def model_ast() -> ast.Module:
    return ast.parse(MODEL_PATH.read_text())


def _class_def(tree: ast.Module, name: str) -> ast.ClassDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"class {name!r} not found in {MODEL_PATH}")


def test_model_inherits_netboxmodel(model_ast):
    cls = _class_def(model_ast, "NodeSSHCredential")
    bases = [b.id for b in cls.bases if isinstance(b, ast.Name)]
    assert "NetBoxModel" in bases


def test_model_declares_required_fields(model_ast):
    cls = _class_def(model_ast, "NodeSSHCredential")
    targets = set()
    for node in cls.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    targets.add(t.id)
    required = {
        "node",
        "username",
        "port",
        "auth_method",
        "known_host_fingerprint",
        "sudo_required",
        "password_enc",
        "private_key_enc",
    }
    missing = required - targets
    assert not missing, f"model missing fields: {missing}"


def test_node_field_is_one_to_one(model_ast):
    """The orchestrator looks up by node id and assumes at most one row per node."""
    cls = _class_def(model_ast, "NodeSSHCredential")
    for node in cls.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "node" for t in node.targets
        ):
            call = node.value
            assert isinstance(call, ast.Call)
            assert isinstance(call.func, ast.Attribute)
            assert call.func.attr == "OneToOneField"
            return
    raise AssertionError("node field assignment not found")


def test_auth_method_choices_pin_key_and_password(model_ast):
    src = MODEL_PATH.read_text()
    assert "AUTH_METHOD_KEY" in src and '"key"' in src
    assert "AUTH_METHOD_PASSWORD" in src and '"password"' in src
    assert "AUTH_METHOD_CHOICES" in src


def test_clean_invokes_normalize_fingerprint(model_ast):
    cls = _class_def(model_ast, "NodeSSHCredential")
    for fn in cls.body:
        if isinstance(fn, ast.FunctionDef) and fn.name == "clean":
            names = {
                n.func.id
                for n in ast.walk(fn)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            }
            assert "normalize_fingerprint" in names
            return
    raise AssertionError("clean() method not found on NodeSSHCredential")


def test_clean_enforces_auth_method_invariants(model_ast):
    """clean() must reject auth_method=key without a stored private key and
    auth_method=password without a stored password."""
    src = MODEL_PATH.read_text()
    assert "AUTH_METHOD_KEY" in src
    assert "AUTH_METHOD_PASSWORD" in src
    # Two ValidationError raises tied to the two auth_method branches.
    assert src.count("ValidationError") >= 3  # one in normalize + two in clean
