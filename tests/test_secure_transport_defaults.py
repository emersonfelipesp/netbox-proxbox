"""Mocked-suite contracts for secure transport defaults and key quality.

Covers the three parts of the insecure-defaults fix without a NetBox
runtime: the model defaults and their migration, the E2E harness opting out
of HTTPS explicitly, removal of the process-wide CA-bundle mutation, and the
canonical Fernet key validator. Database behaviour lives in
``test_secure_transport_defaults_django.py``.
"""

from __future__ import annotations

import ast
import base64
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MODELS = REPO_ROOT / "netbox_proxbox" / "models"
MIGRATION = REPO_ROOT / "netbox_proxbox" / "migrations" / "0104_security_hardening.py"


def _field_default(path: Path, class_name: str, field_name: str) -> object:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if (
                    isinstance(item, ast.Assign)
                    and isinstance(item.targets[0], ast.Name)
                    and item.targets[0].id == field_name
                ):
                    call = item.value
                    assert isinstance(call, ast.Call)
                    for keyword in call.keywords:
                        if keyword.arg == "default":
                            return ast.literal_eval(keyword.value)
    raise AssertionError(f"{class_name}.{field_name} default not found")


def test_backend_endpoint_defaults_to_https() -> None:
    assert (
        _field_default(MODELS / "fastapi_endpoint.py", "FastAPIEndpoint", "use_https")
        is True
    )


def test_proxmox_endpoint_defaults_to_tls_verification() -> None:
    assert (
        _field_default(MODELS / "proxmox_endpoint.py", "ProxmoxEndpoint", "verify_ssl")
        is True
    )


def test_migration_only_alters_the_two_defaults() -> None:
    tree = ast.parse(MIGRATION.read_text(encoding="utf-8"))
    altered = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "AlterField"
        ):
            keywords = {kw.arg: kw.value for kw in node.keywords}
            field = keywords["field"]
            default = next(kw.value for kw in field.keywords if kw.arg == "default")
            altered.add(
                (
                    ast.literal_eval(keywords["model_name"]),
                    ast.literal_eval(keywords["name"]),
                )
            )
            assert ast.literal_eval(default) is True
    assert altered == {
        ("fastapiendpoint", "use_https"),
        ("proxmoxendpoint", "verify_ssl"),
    }
    source = MIGRATION.read_text(encoding="utf-8")
    assert "RunSQL" not in source
    # The only data step is the settings-read grant; it must never rewrite
    # stored transport settings on existing rows.
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            segment = ast.get_source_segment(source, node) or ""
            assert "use_https" not in segment
            assert "verify_ssl" not in segment


def test_e2e_harness_opts_out_of_https_explicitly() -> None:
    source = (REPO_ROOT / "tests" / "e2e" / "stack_setup.py").read_text(
        encoding="utf-8"
    )
    assert '"use_https": False' in source


def test_backend_url_builder_never_mutates_the_process_environment() -> None:
    source = (REPO_ROOT / "netbox_proxbox" / "utils" / "__init__.py").read_text(
        encoding="utf-8"
    )
    assert "REQUESTS_CA_BUNDLE" not in source
    assert "mkcert" not in source
    assert "os.environ" not in source


@pytest.fixture
def encryption():
    spec = importlib.util.spec_from_file_location(
        "_encryption_under_test",
        REPO_ROOT / "netbox_proxbox" / "utils" / "encryption.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generated_fernet_keys_are_canonical(encryption) -> None:
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode("ascii")

    assert encryption.is_canonical_fernet_key(key)
    assert encryption.is_canonical_fernet_key(f"  {key}\n")
    encryption.require_canonical_fernet_key(key)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "a" * 32,
        "correct-horse-battery-staple-123",
        "x" * 44,
        base64.urlsafe_b64encode(b"y" * 31).decode("ascii"),
        base64.urlsafe_b64encode(b"z" * 33).decode("ascii"),
        # Non-zero padding bits: decodes to the same bytes as "A" * 43 + "=".
        "A" * 42 + "B=",
        # Standard-base64 alphabet: the same key under a different spelling.
        base64.b64encode(b"\xfb" * 32).decode("ascii"),
    ],
)
def test_non_canonical_keys_are_rejected_for_new_writes(encryption, raw: str) -> None:
    assert not encryption.is_canonical_fernet_key(raw)
    with pytest.raises(encryption.EncryptionKeyInvalid):
        encryption.require_canonical_fernet_key(raw)


def test_legacy_raw_keys_still_decrypt(encryption) -> None:
    """Read compatibility: stored 32-byte raw keys keep working."""
    legacy = "L" * 32
    ciphertext = encryption.encrypt("secret", key=legacy)

    assert encryption.decrypt(ciphertext, key=legacy) == "secret"
    assert not encryption.is_canonical_fernet_key(legacy)


def test_strict_spelling_is_required_for_aliases(encryption) -> None:
    canonical = base64.urlsafe_b64encode(b"\xfb" * 32).decode("ascii")

    assert "-" in canonical or "_" in canonical
    assert encryption.is_canonical_fernet_key(canonical)
    assert encryption.is_canonical_fernet_key("A" * 43 + "=")


def test_key_aliases_match_on_decoded_key_material(encryption) -> None:
    """A rotation between spellings of one key must be seen as the same key."""
    canonical = base64.urlsafe_b64encode(b"\xfb" * 32).decode("ascii")
    standard_alphabet = base64.b64encode(b"\xfb" * 32).decode("ascii")

    assert encryption.keys_match("A" * 43 + "=", "A" * 42 + "B=")
    assert encryption.keys_match(canonical, standard_alphabet)
    assert not encryption.keys_match(canonical, "A" * 43 + "=")
