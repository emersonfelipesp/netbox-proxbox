"""Behavioral tests for the Terminal-tab SSH credential helpers.

These execute `validate_terminal_credential` and `one_shot_payload` from
`netbox_proxbox/views/endpoints/ssh_terminal_credential.py`. The module only
needs the two auth-method constants from `netbox_proxbox.models.ssh_credential`,
so we stub that module (Django-heavy) in `sys.modules` and import the helpers
directly — no NetBox bootstrap required.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

HELPER_PATH = (
    Path(__file__).resolve().parents[1]
    / "netbox_proxbox"
    / "views"
    / "endpoints"
    / "ssh_terminal_credential.py"
)


@pytest.fixture()
def helpers(monkeypatch):
    """Load the credential helpers against a stubbed ssh_credential module.

    Loading by file path (not package import) avoids bootstrapping the heavy
    ``netbox_proxbox`` package ``__init__`` chain; the only dependency —
    ``netbox_proxbox.models.ssh_credential`` — is stubbed in ``sys.modules``.
    """
    stub = types.ModuleType("netbox_proxbox.models.ssh_credential")
    stub.AUTH_METHOD_KEY = "key"
    stub.AUTH_METHOD_PASSWORD = "password"
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models.ssh_credential", stub)
    spec = importlib.util.spec_from_file_location(
        "_ssh_terminal_credential_under_test", HELPER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_FP = "SHA256:abcdefghijklmnopqrstuvwxyz12345678901234567"


# --------------------------------------------------------------------------
# validate_terminal_credential
# --------------------------------------------------------------------------


def test_valid_password_credential(helpers):
    data, error = helpers.validate_terminal_credential(
        {"username": "root", "password": "s3cret", "known_host_fingerprint": _FP}
    )
    assert error is None
    assert data == {
        "username": "root",
        "port": 22,
        "auth_method": "password",
        "password": "s3cret",
        "private_key": "",
        "known_host_fingerprint": _FP,
    }


def test_valid_key_credential_infers_auth_method(helpers):
    data, error = helpers.validate_terminal_credential(
        {"username": "root", "private_key": "PEM", "known_host_fingerprint": _FP}
    )
    assert error is None
    assert data["auth_method"] == "key"
    assert data["private_key"] == "PEM"


def test_explicit_auth_method_key_requires_private_key(helpers):
    data, error = helpers.validate_terminal_credential(
        {
            "username": "root",
            "auth_method": "key",
            "password": "ignored",
            "known_host_fingerprint": _FP,
        }
    )
    assert data is None
    assert "Private key is required" in error


def test_password_auth_requires_password(helpers):
    data, error = helpers.validate_terminal_credential(
        {"username": "root", "auth_method": "password", "known_host_fingerprint": _FP}
    )
    assert data is None
    assert "Password is required" in error


def test_missing_username_rejected(helpers):
    data, error = helpers.validate_terminal_credential(
        {"password": "x", "known_host_fingerprint": _FP}
    )
    assert data is None
    assert "username is required" in error


def test_missing_fingerprint_rejected(helpers):
    data, error = helpers.validate_terminal_credential(
        {"username": "root", "password": "x"}
    )
    assert data is None
    assert "fingerprint is required" in error


def test_non_dict_rejected(helpers):
    data, error = helpers.validate_terminal_credential("not-a-dict")
    assert data is None
    assert "must be an object" in error


@pytest.mark.parametrize("bad_port", [70000, -1])
def test_port_out_of_range_rejected(helpers, bad_port):
    data, error = helpers.validate_terminal_credential(
        {
            "username": "root",
            "password": "x",
            "known_host_fingerprint": _FP,
            "port": bad_port,
        }
    )
    assert data is None
    assert "between 1 and 65535" in error


def test_falsy_port_defaults_to_22(helpers):
    # ``port or 22`` treats 0/empty as "unset" and falls back to the default.
    for falsy in (0, "", None):
        data, error = helpers.validate_terminal_credential(
            {
                "username": "root",
                "password": "x",
                "known_host_fingerprint": _FP,
                "port": falsy,
            }
        )
        assert error is None
        assert data["port"] == 22


def test_non_numeric_port_rejected(helpers):
    data, error = helpers.validate_terminal_credential(
        {
            "username": "root",
            "password": "x",
            "known_host_fingerprint": _FP,
            "port": "abc",
        }
    )
    assert data is None
    assert "must be a number" in error


def test_custom_port_accepted(helpers):
    data, error = helpers.validate_terminal_credential(
        {
            "username": "root",
            "password": "x",
            "known_host_fingerprint": _FP,
            "port": 2222,
        }
    )
    assert error is None
    assert data["port"] == 2222


# --------------------------------------------------------------------------
# one_shot_payload
# --------------------------------------------------------------------------


def test_one_shot_payload_password(helpers):
    data = {
        "username": "root",
        "port": 22,
        "auth_method": "password",
        "password": "s3cret",
        "private_key": "",
        "known_host_fingerprint": _FP,
    }
    payload = helpers.one_shot_payload(data)
    assert payload == {
        "username": "root",
        "port": 22,
        "known_host_fingerprint": _FP,
        "password": "s3cret",
    }
    assert "private_key" not in payload


def test_one_shot_payload_key(helpers):
    data = {
        "username": "root",
        "port": 2222,
        "auth_method": "key",
        "password": "",
        "private_key": "PEM",
        "known_host_fingerprint": _FP,
    }
    payload = helpers.one_shot_payload(data)
    assert payload == {
        "username": "root",
        "port": 2222,
        "known_host_fingerprint": _FP,
        "private_key": "PEM",
    }
    assert "password" not in payload
