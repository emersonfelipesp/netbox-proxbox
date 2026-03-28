from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
NETBOX_ROOT = REPO_ROOT.parent / "netbox" / "netbox"

for candidate in (REPO_ROOT, NETBOX_ROOT):
    candidate_str = str(candidate)
    if candidate.exists() and candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)


try:
    import django
except ModuleNotFoundError:
    pytest.skip(
        "Django/NetBox test dependencies are not installed in this environment.",
        allow_module_level=True,
    )


os.environ.setdefault("NETBOX_CONFIGURATION", "tests.netbox_test_configuration")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netbox.settings")

try:
    django.setup()
except Exception as exc:
    pytest.skip(
        f"NetBox test environment is not available: {exc}", allow_module_level=True
    )


from django.contrib.auth.models import AnonymousUser


proxmox_views = importlib.import_module("netbox_proxbox.views.endpoints.proxmox")


class _Tag:
    def __init__(self, slug: str):
        self.slug = slug


class _TagManager:
    def __init__(self, slugs: list[str]):
        self._slugs = slugs

    def all(self):
        return [_Tag(slug) for slug in self._slugs]


def _endpoint(**overrides):
    data = {
        "pk": 7,
        "name": "pve01",
        "domain": "pve01.example.test",
        "ip_address": SimpleNamespace(address="192.0.2.10/24"),
        "port": 8006,
        "mode": "cluster",
        "version": "8.3.0",
        "repoid": "bookworm",
        "username": "root@pam",
        "verify_ssl": False,
        "comments": "lab",
        "token_name": "api-id",
        "password": "p@ss",
        "token_value": "s3cret",
        "tags": _TagManager(["lab", "prod"]),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_safe_export_never_contains_password_or_token_value(monkeypatch):
    endpoint = _endpoint()

    class _QS:
        def __iter__(self):
            return iter([endpoint])

    view = proxmox_views.ProxmoxEndpointExportCSVView()
    view.filterset = None
    monkeypatch.setattr(view, "get_queryset", lambda request: _QS())

    request = SimpleNamespace(GET={}, POST={}, META={}, user=AnonymousUser())
    response = view._export_response(
        request, include_sensitive=False, data_format="csv"
    )
    csv_text = response.content.decode()

    assert "password" not in csv_text.splitlines()[0]
    assert "token_value" not in csv_text.splitlines()[0]
    assert "api-id" in csv_text
    assert "p@ss" not in csv_text
    assert "s3cret" not in csv_text


def test_sensitive_export_includes_password_and_token_value(monkeypatch):
    endpoint = _endpoint()

    class _QS:
        def __iter__(self):
            return iter([endpoint])

    view = proxmox_views.ProxmoxEndpointExportCSVView()
    view.filterset = None
    monkeypatch.setattr(view, "get_queryset", lambda request: _QS())

    request = SimpleNamespace(GET={}, POST={}, META={}, user=AnonymousUser())
    response = view._export_response(request, include_sensitive=True, data_format="csv")
    csv_text = response.content.decode()

    header = csv_text.splitlines()[0]
    assert "password" in header
    assert "token_value" in header
    assert "p@ss" in csv_text
    assert "s3cret" in csv_text


def test_safe_export_json_and_yaml_formats(monkeypatch):
    endpoint = _endpoint()

    class _QS:
        def __iter__(self):
            return iter([endpoint])

    view = proxmox_views.ProxmoxEndpointExportView()
    view.filterset = None
    monkeypatch.setattr(view, "get_queryset", lambda request: _QS())

    request = SimpleNamespace(GET={}, POST={}, META={}, user=AnonymousUser())

    json_response = view._export_response(
        request, include_sensitive=False, data_format="json"
    )
    json_text = json_response.content.decode()
    assert '"name": "pve01"' in json_text
    assert '"password"' not in json_text
    assert json_response["Content-Disposition"].endswith('safe.json"')

    yaml_response = view._export_response(
        request, include_sensitive=False, data_format="yaml"
    )
    yaml_text = yaml_response.content.decode()
    assert "name: pve01" in yaml_text
    assert "password:" not in yaml_text
    assert yaml_response["Content-Disposition"].endswith('safe.yaml"')
