"""Tests for netbox_proxbox.templatetags.proxbox_tags."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import pytest


def _load_proxbox_tags(monkeypatch):
    """Load proxbox_tags with Django stubs."""
    django_template = types.ModuleType("django.template")

    class _Library:
        def __init__(self):
            self._filters = {}
            self._tags = {}

        def filter(self, func=None, name=None):
            def decorator(f):
                self._filters[name or f.__name__] = f
                return f

            if func is not None:
                return decorator(func)
            return decorator

        def simple_tag(self, func=None, name=None, takes_context=False):
            def decorator(f):
                self._tags[name or f.__name__] = f
                return f

            if func is not None:
                return decorator(func)
            return decorator

    django_template.Library = _Library

    django_utils_html = types.ModuleType("django.utils.html")

    def _format_html(fmt, *args, **kwargs):
        result = fmt
        for arg in args:
            result = result.replace("{}", str(arg), 1)
        return result

    django_utils_html.format_html = _format_html

    django_utils_safestring = types.ModuleType("django.utils.safestring")
    django_utils_safestring.mark_safe = lambda value: value

    django_mod = types.ModuleType("django")
    django_utils = types.ModuleType("django.utils")
    django_utils.html = django_utils_html
    django_utils.safestring = django_utils_safestring

    netbox_proxbox_config = SimpleNamespace(version="0.0.11")
    netbox_proxbox_mod = types.ModuleType("netbox_proxbox")
    netbox_proxbox_mod.config = netbox_proxbox_config

    stub_modules = {
        "django": django_mod,
        "django.template": django_template,
        "django.utils": django_utils,
        "django.utils.html": django_utils_html,
        "django.utils.safestring": django_utils_safestring,
        "netbox_proxbox": netbox_proxbox_mod,
    }
    for name, mod in stub_modules.items():
        monkeypatch.setitem(sys.modules, name, mod)

    import importlib
    import importlib.util
    from pathlib import Path

    module_name = "netbox_proxbox.templatetags.proxbox_tags"
    sys.modules.pop(module_name, None)
    path = (
        Path(__file__).resolve().parents[1]
        / "netbox_proxbox"
        / "templatetags"
        / "proxbox_tags.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# ── proxbox_version ───────────────────────────────────────────────────────────


def test_proxbox_version_returns_version(monkeypatch):
    tags = _load_proxbox_tags(monkeypatch)
    assert tags.proxbox_version() == "0.0.11"


# ── hyperlinked_object ────────────────────────────────────────────────────────


def test_hyperlinked_object_none(monkeypatch):
    tags = _load_proxbox_tags(monkeypatch)
    assert tags.hyperlinked_object(None) == "—"


def test_hyperlinked_object_with_url(monkeypatch):
    tags = _load_proxbox_tags(monkeypatch)

    class FakeCluster:
        def get_absolute_url(self):
            return "/plugins/proxbox/cluster/1/"

        def __str__(self):
            return "mycluster"

    result = tags.hyperlinked_object(FakeCluster())
    assert "/plugins/proxbox/cluster/1/" in result
    assert "mycluster" in result


def test_hyperlinked_object_no_url_attribute(monkeypatch):
    tags = _load_proxbox_tags(monkeypatch)

    class NoUrl:
        def __str__(self):
            return "plain"

    result = tags.hyperlinked_object(NoUrl())
    assert result == "plain"


# ── div ───────────────────────────────────────────────────────────────────────


def test_div_integer_division(monkeypatch):
    tags = _load_proxbox_tags(monkeypatch)
    assert tags.div(10, 3) == 3


def test_div_exact(monkeypatch):
    tags = _load_proxbox_tags(monkeypatch)
    assert tags.div(12, 4) == 3


def test_div_zero_denominator(monkeypatch):
    tags = _load_proxbox_tags(monkeypatch)
    assert tags.div(10, 0) == 0


def test_div_type_error(monkeypatch):
    tags = _load_proxbox_tags(monkeypatch)
    assert tags.div("abc", "xyz") == 0


def test_div_none(monkeypatch):
    tags = _load_proxbox_tags(monkeypatch)
    assert tags.div(None, 5) == 0


# ── sync_type_label ───────────────────────────────────────────────────────────

EXPECTED_LABELS = {
    "all": "All",
    "devices": "Devices",
    "storage": "Storage",
    "virtual-machines": "VMs",
    "vm-disks": "VM Disks",
    "vm-interfaces": "VM Interfaces",
    "vm-backups": "VM Backups",
    "vm-snapshots": "VM Snapshots",
    "network-interfaces": "Net Ifaces",
    "ip-addresses": "IP Addresses",
    "backup-routines": "Backup Routines",
    "replications": "Replications",
}


@pytest.mark.parametrize("slug,expected", list(EXPECTED_LABELS.items()))
def test_sync_type_label_known_slugs(monkeypatch, slug, expected):
    tags = _load_proxbox_tags(monkeypatch)
    assert tags.sync_type_label(slug) == expected


def test_sync_type_label_unknown_slug_passthrough(monkeypatch):
    tags = _load_proxbox_tags(monkeypatch)
    assert tags.sync_type_label("unknown-type") == "unknown-type"


# ── form_field ────────────────────────────────────────────────────────────────


class _FakeBoundField:
    def __init__(self, name: str):
        self.name = name


class _FakeFormWithMapping:
    """Form-like object that supports ``form[name]`` for bound-field lookup."""

    def __init__(self, fields: dict[str, _FakeBoundField]):
        self._fields = fields

    def __getitem__(self, name: str) -> _FakeBoundField:
        return self._fields[name]


def test_form_field_returns_bound_field_for_known_name(monkeypatch):
    tags = _load_proxbox_tags(monkeypatch)
    bound = _FakeBoundField("overwrite_vm_tags")
    form = _FakeFormWithMapping({"overwrite_vm_tags": bound})

    result = tags.form_field(form, "overwrite_vm_tags")

    assert result is bound


def test_form_field_returns_empty_string_for_missing_field(monkeypatch):
    tags = _load_proxbox_tags(monkeypatch)
    form = _FakeFormWithMapping({"overwrite_vm_tags": _FakeBoundField("x")})

    assert tags.form_field(form, "nope") == ""


def test_form_field_returns_empty_string_when_form_is_none(monkeypatch):
    """Subscripting None raises TypeError; the filter swallows it and returns ''."""
    tags = _load_proxbox_tags(monkeypatch)

    assert tags.form_field(None, "anything") == ""


def test_form_field_returns_empty_string_when_object_not_subscriptable(monkeypatch):
    tags = _load_proxbox_tags(monkeypatch)

    class NotSubscriptable:
        pass

    assert tags.form_field(NotSubscriptable(), "anything") == ""


def test_form_field_is_registered_under_explicit_name(monkeypatch):
    """The decorator uses ``name="form_field"`` — verify the registry sees it."""
    tags = _load_proxbox_tags(monkeypatch)
    assert tags.register._filters.get("form_field") is tags.form_field


# ── proxbox_paginate_url ──────────────────────────────────────────────────────


class _FakeQueryDict(dict):
    """Minimal stand-in for Django's QueryDict used in paginator URL tests."""

    def copy(self) -> "_FakeQueryDict":
        return _FakeQueryDict(self)

    def urlencode(self) -> str:
        from urllib.parse import urlencode

        return urlencode(self)


class _FakeRequest:
    def __init__(self, path: str, params: dict):
        self.path = path
        self.GET = _FakeQueryDict(params)


def test_proxbox_paginate_url_sets_page_and_preserves_other_params(monkeypatch):
    tags = _load_proxbox_tags(monkeypatch)
    request = _FakeRequest("/plugins/proxbox/virtual_machines/", {"per_page": "50"})
    context = {"request": request}

    result = tags.proxbox_paginate_url(context, "page", 3)

    assert result.startswith("/plugins/proxbox/virtual_machines/?")
    assert "page=3" in result
    assert "per_page=50" in result


def test_proxbox_paginate_url_overrides_existing_page(monkeypatch):
    tags = _load_proxbox_tags(monkeypatch)
    request = _FakeRequest("/plugins/proxbox/nodes/", {"page": "2"})
    context = {"request": request}

    result = tags.proxbox_paginate_url(context, "page", 5)

    assert "page=5" in result
    assert "page=2" not in result


def test_proxbox_paginate_url_independent_page_params(monkeypatch):
    """Aggregate pages drive two tables with vm_page / node_page independently."""
    tags = _load_proxbox_tags(monkeypatch)
    request = _FakeRequest("/plugins/proxbox/interfaces/", {"vm_page": "1", "node_page": "1"})
    context = {"request": request}

    result = tags.proxbox_paginate_url(context, "node_page", 4)

    assert "node_page=4" in result
    assert "vm_page=1" in result


def test_proxbox_paginate_url_per_page_resets_page_numbers(monkeypatch):
    tags = _load_proxbox_tags(monkeypatch)
    request = _FakeRequest(
        "/plugins/proxbox/interfaces/",
        {"page": "3", "vm_page": "2", "node_page": "5"},
    )
    context = {"request": request}

    result = tags.proxbox_paginate_url(context, "per_page", 100)

    # Only the per_page parameter should survive; every page cursor is dropped.
    assert result.split("?", 1)[1] == "per_page=100"
    assert "vm_page=" not in result
    assert "node_page=" not in result


def test_proxbox_paginate_url_without_request_is_safe(monkeypatch):
    tags = _load_proxbox_tags(monkeypatch)

    assert tags.proxbox_paginate_url({}, "page", 2) == "?page=2"
