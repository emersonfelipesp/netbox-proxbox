"""Tests for test_proxmox_export_view."""

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
        "token_name": "api-id",
        "password": "p@ss",
        "token_value": "s3cret",
        "tags": _TagManager(["lab", "prod"]),
        "site": None,
        "tenant": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_safe_export_never_contains_password_or_token_value(monkeypatch):
    endpoint = _endpoint()

    class _QS:
        def __iter__(self):
            return iter([endpoint])

    view = proxmox_views.ProxmoxEndpointExportView()
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

    view = proxmox_views.ProxmoxEndpointExportView()
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


def test_export_fieldnames_do_not_include_comments():
    """Regression guard: ProxmoxEndpoint has no comments field — must not appear in export."""
    from netbox_proxbox.views.endpoints.proxmox_export import _proxmox_export_fieldnames

    safe_fields = _proxmox_export_fieldnames(include_sensitive=False)
    sensitive_fields = _proxmox_export_fieldnames(include_sensitive=True)
    assert "comments" not in safe_fields
    assert "comments" not in sensitive_fields


def test_export_serialization_does_not_access_comments(monkeypatch):
    """Regression guard: serializing an endpoint without a comments attr must not raise."""
    endpoint = _endpoint()
    # Explicitly remove comments if somehow set (SimpleNamespace allows it).
    if hasattr(endpoint, "comments"):
        delattr(endpoint, "comments")

    from netbox_proxbox.views.endpoints.proxmox_export import _serialize_proxmox_endpoint

    row = _serialize_proxmox_endpoint(endpoint, include_sensitive=False)
    assert "comments" not in row
    assert row["name"] == "pve01"


def test_bulk_import_view_strips_id_column(monkeypatch):
    """Regression guard: an 'id' column exported from another NetBox instance must be ignored.

    NetBox's create_and_update_objects() prefetches by id and then
    _process_import_records() looks up each id — both fail if the id doesn't
    exist locally.  Our override strips 'id' from cleaned_data['data'] before
    delegating to super(), so rows are always created fresh.
    """
    from netbox_proxbox.views.endpoints.proxmox import ProxmoxEndpointBulkImportView

    view = ProxmoxEndpointBulkImportView()

    seen_records = []

    def fake_super(form, request):
        seen_records.extend([dict(r) for r in form.cleaned_data.get("data", [])])
        return []

    # Patch the parent so we can inspect what records reach it.
    monkeypatch.setattr(
        "netbox.views.generic.BulkImportView.create_and_update_objects",
        fake_super,
    )

    records = [
        {"id": "1", "name": "pve01", "port": "8006"},
        {"id": "2", "name": "pve02", "port": "8006"},
        {"name": "pve03", "port": "8006"},  # no id — unchanged
    ]

    class _FakeForm:
        cleaned_data = {"data": records}

    view.create_and_update_objects(_FakeForm(), request=None)

    for row in seen_records:
        assert "id" not in row, f"'id' was not stripped from {row}"

    assert seen_records[0]["name"] == "pve01"
    assert seen_records[2]["name"] == "pve03"


# ── _validate_sensitive_export_token: v1 / v2 / fallback modes ───────────────


def _make_view():
    view = proxmox_views.ProxmoxEndpointExportView()
    view.filterset = None
    return view


class _FakeToken:
    DoesNotExist = KeyError

    def __init__(self, pk, plaintext, version=1):
        self.pk = pk
        self.plaintext = plaintext
        self.version = version


class _FakeTokenManager:
    def __init__(self, token):
        self._token = token

    def get(self, **kwargs):
        pk = kwargs.get("pk")
        version = kwargs.get("version", 1)
        if self._token and self._token.pk == pk and self._token.version == version:
            return self._token
        raise KeyError("not found")


class _FakeUser:
    is_authenticated = True

    def has_perm(self, perm):
        return True


def test_validate_token_v1_mode_uses_plaintext(monkeypatch):
    """v1 mode: constructs 'Token <plaintext>' header from the looked-up token."""
    view = _make_view()
    fake_token = _FakeToken(pk=42, plaintext="abc123" * 7)  # 42-char plaintext
    manager = _FakeTokenManager(fake_token)

    captured_headers = {}

    def fake_authenticate(req):
        captured_headers.update({"auth": req.META.get("HTTP_AUTHORIZATION", "")})
        return (_FakeUser(), fake_token)

    monkeypatch.setattr(
        proxmox_views.TokenAuthentication, "authenticate", fake_authenticate
    )

    import sys
    fake_users_module = type(sys)("users.models")
    fake_users_module.Token = type("Token", (), {
        "objects": manager,
        "DoesNotExist": KeyError,
    })
    monkeypatch.setitem(sys.modules, "users.models", fake_users_module)

    class _Msgs:
        def __init__(self):
            self.errors = []

        def error(self, req, msg):
            self.errors.append(msg)

    msgs = _Msgs()
    monkeypatch.setattr(proxmox_views.messages, "error", msgs.error)

    request = SimpleNamespace(
        POST={"token_version": "v1", "token_id": "42"},
        META={},
        user=_FakeUser(),
    )
    result = view._validate_sensitive_export_token(request)

    assert result is True
    assert captured_headers["auth"] == f"Token {fake_token.plaintext}"
    assert msgs.errors == []


def test_validate_token_v1_mode_missing_token_id(monkeypatch):
    """v1 mode with no token_id returns False and adds an error message."""
    view = _make_view()

    errors = []
    monkeypatch.setattr(proxmox_views.messages, "error", lambda req, msg: errors.append(msg))

    import sys
    fake_users_module = type(sys)("users.models")
    fake_users_module.Token = type("Token", (), {"DoesNotExist": KeyError})
    monkeypatch.setitem(sys.modules, "users.models", fake_users_module)

    request = SimpleNamespace(POST={"token_version": "v1", "token_id": ""}, META={}, user=None)
    result = view._validate_sensitive_export_token(request)
    assert result is False
    assert errors


def test_validate_token_v2_mode_constructs_bearer_header(monkeypatch):
    """v2 mode: constructs 'Bearer key.secret' header from POST fields."""
    view = _make_view()

    captured = {}

    def fake_authenticate(req):
        captured["auth"] = req.META.get("HTTP_AUTHORIZATION", "")
        return (_FakeUser(), None)

    monkeypatch.setattr(proxmox_views.TokenAuthentication, "authenticate", fake_authenticate)

    import sys
    fake_users_module = type(sys)("users.models")
    fake_users_module.Token = type("Token", (), {"DoesNotExist": KeyError})
    monkeypatch.setitem(sys.modules, "users.models", fake_users_module)

    errors = []
    monkeypatch.setattr(proxmox_views.messages, "error", lambda req, msg: errors.append(msg))

    request = SimpleNamespace(
        POST={"token_version": "v2", "token_key": "nbt_abc123", "token_secret": "mysecret"},
        META={},
        user=_FakeUser(),
    )
    result = view._validate_sensitive_export_token(request)

    assert result is True
    assert captured["auth"] == "Bearer nbt_abc123.mysecret"
    assert errors == []


def test_validate_token_v2_mode_missing_secret_returns_false(monkeypatch):
    """v2 mode without token_secret returns False."""
    view = _make_view()
    errors = []
    monkeypatch.setattr(proxmox_views.messages, "error", lambda req, msg: errors.append(msg))

    import sys
    fake_users_module = type(sys)("users.models")
    fake_users_module.Token = type("Token", (), {"DoesNotExist": KeyError})
    monkeypatch.setitem(sys.modules, "users.models", fake_users_module)

    request = SimpleNamespace(
        POST={"token_version": "v2", "token_key": "nbt_abc", "token_secret": ""},
        META={},
        user=None,
    )
    result = view._validate_sensitive_export_token(request)
    assert result is False
    assert errors


def test_validate_token_v1_manual_overrides_dropdown(monkeypatch):
    """v1 mode: v1_manual_token field takes priority over token_id selection."""
    view = _make_view()
    captured = {}

    def fake_authenticate(req):
        captured["auth"] = req.META.get("HTTP_AUTHORIZATION", "")
        return (_FakeUser(), None)

    monkeypatch.setattr(proxmox_views.TokenAuthentication, "authenticate", fake_authenticate)

    import sys
    fake_users_module = type(sys)("users.models")
    fake_users_module.Token = type("Token", (), {"DoesNotExist": KeyError})
    monkeypatch.setitem(sys.modules, "users.models", fake_users_module)

    errors = []
    monkeypatch.setattr(proxmox_views.messages, "error", lambda req, msg: errors.append(msg))

    request = SimpleNamespace(
        POST={
            "token_version": "v1",
            "token_id": "42",           # dropdown selection (should be ignored)
            "v1_manual_token": "manualplaintext1234",  # manual wins
        },
        META={},
        user=_FakeUser(),
    )
    result = view._validate_sensitive_export_token(request)

    assert result is True
    assert captured["auth"] == "Token manualplaintext1234"
    assert errors == []


def test_validate_token_fallback_uses_legacy_netbox_token_field(monkeypatch):
    """Fallback (no token_version) uses the legacy netbox_token POST field."""
    view = _make_view()

    captured = {}

    def fake_authenticate(req):
        captured["auth"] = req.META.get("HTTP_AUTHORIZATION", "")
        return (_FakeUser(), None)

    monkeypatch.setattr(proxmox_views.TokenAuthentication, "authenticate", fake_authenticate)

    import sys
    fake_users_module = type(sys)("users.models")
    fake_users_module.Token = type("Token", (), {"DoesNotExist": KeyError})
    monkeypatch.setitem(sys.modules, "users.models", fake_users_module)

    errors = []
    monkeypatch.setattr(proxmox_views.messages, "error", lambda req, msg: errors.append(msg))

    request = SimpleNamespace(
        POST={"netbox_token": "abcdef1234567890" * 3},
        META={},
        user=_FakeUser(),
    )
    result = view._validate_sensitive_export_token(request)
    assert result is True
    assert captured["auth"].startswith("Token ")
    assert errors == []


def test_quick_add_token_view_exists():
    """ProxmoxExportQuickAddTokenView is importable and is registered in __all__."""
    assert hasattr(proxmox_views, "ProxmoxExportQuickAddTokenView")
    assert "ProxmoxExportQuickAddTokenView" in proxmox_views.__all__


def test_quick_add_token_view_requires_authentication(monkeypatch):
    """Unauthenticated request to quick_add_token returns 401."""
    import importlib

    view_cls = proxmox_views.ProxmoxExportQuickAddTokenView
    view = view_cls()

    class _AnonUser:
        is_authenticated = False

    request = SimpleNamespace(user=_AnonUser(), POST={}, META={}, method="POST")
    response = view.post(request)
    assert response.status_code == 401


def test_quick_add_token_view_requires_add_permission(monkeypatch):
    """Authenticated user without users.add_token perm gets 403."""
    view = proxmox_views.ProxmoxExportQuickAddTokenView()

    class _UserNoPerms:
        is_authenticated = True

        def has_perm(self, perm):
            return False

    request = SimpleNamespace(user=_UserNoPerms(), POST={}, META={}, method="POST")
    response = view.post(request)
    assert response.status_code == 403
