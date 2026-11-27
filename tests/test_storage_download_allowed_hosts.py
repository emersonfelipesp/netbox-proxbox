"""Contracts for the storage download exact-hostname allowlist."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


class ValidationError(Exception):
    """Minimal Django ValidationError stand-in for the dependency-light suite."""

    def __init__(self, message):
        super().__init__(message)
        self.messages = message if isinstance(message, list) else [message]


def _load_normalizer(monkeypatch):
    django = types.ModuleType("django")
    django_core = types.ModuleType("django.core")
    django_exceptions = types.ModuleType("django.core.exceptions")
    django_exceptions.ValidationError = ValidationError
    monkeypatch.setitem(sys.modules, "django", django)
    monkeypatch.setitem(sys.modules, "django.core", django_core)
    monkeypatch.setitem(sys.modules, "django.core.exceptions", django_exceptions)
    path = REPO_ROOT / "netbox_proxbox/storage_download_hosts.py"
    spec = importlib.util.spec_from_file_location("storage_download_hosts_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.normalize_storage_download_allowed_hosts


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ([], []),
        (["downloads.example.com"], ["downloads.example.com"]),
        (
            [" Vendor.EXAMPLE.com. ", "cdn.vendor.example"],
            ["vendor.example.com", "cdn.vendor.example"],
        ),
    ],
)
def test_normalizer_accepts_and_normalizes_exact_hostnames(
    monkeypatch, value, expected
):
    normalize = _load_normalizer(monkeypatch)
    assert normalize(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "downloads.example.com",
        [1],
        [""],
        ["https://downloads.example.com"],
        ["user@downloads.example.com"],
        ["downloads.example.com:443"],
        ["downloads.example.com/path"],
        ["downloads.example.com?file=iso"],
        ["downloads.example.com#file"],
        ["*.example.com"],
        [".".join(("192", "0", "2", "1"))],
        ["2001:db8::1"],
        ["localhost"],
        ["bad_label.example.com"],
        ["downloads.example.com", "DOWNLOADS.EXAMPLE.COM."],
        [f"{'a' * 63}.{'b' * 63}.{'c' * 63}.{'d' * 62}.com"],
        [f"host{index}.example.com" for index in range(65)],
    ],
)
def test_normalizer_rejects_unsafe_or_invalid_values(monkeypatch, value):
    normalize = _load_normalizer(monkeypatch)
    with pytest.raises(ValidationError):
        normalize(value)


def test_form_round_trip_uses_lines_and_shared_normalizer():
    form = (REPO_ROOT / "netbox_proxbox/forms/settings.py").read_text(encoding="utf-8")
    view = (REPO_ROOT / "netbox_proxbox/views/settings.py").read_text(encoding="utf-8")

    assert "def clean_storage_download_allowed_hosts" in form
    assert "value.splitlines()" in form
    assert "normalize_storage_download_allowed_hosts(entries)" in form
    assert '"storage_download_allowed_hosts": "\\n".join(' in view
    assert (
        "settings_obj.storage_download_allowed_hosts = form.cleaned_data.get(" in view
    )


def test_serializer_uses_shared_validator_and_exposes_field():
    serializer = (REPO_ROOT / "netbox_proxbox/api/serializers/settings.py").read_text(
        encoding="utf-8"
    )

    assert "def validate_storage_download_allowed_hosts" in serializer
    assert "normalize_storage_download_allowed_hosts(value)" in serializer
    assert '"storage_download_allowed_hosts",' in serializer


def test_migration_adds_field_after_schema_tip():
    migration = (
        REPO_ROOT / "netbox_proxbox/migrations/0109_guest_uid_identity.py"
    ).read_text(encoding="utf-8")

    assert '("netbox_proxbox", "0108_v0_0_31_schema_validation")' in migration
    assert 'field_name="storage_download_allowed_hosts"' in migration
    assert "add_field_idempotent(" in migration
