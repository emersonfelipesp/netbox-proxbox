"""Static and isolated contracts for the independent Proxmox metrics path."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from urllib.parse import urlsplit

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _load_model(monkeypatch: pytest.MonkeyPatch):
    """Load the model without requiring the full NetBox installation."""
    exceptions = types.ModuleType("django.core.exceptions")
    exceptions.ValidationError = type("ValidationError", (Exception,), {})
    validators = types.ModuleType("django.core.validators")

    class URLValidator:
        def __init__(self, *, schemes):
            self.schemes = schemes

        def __call__(self, value):
            parsed = urlsplit(value)
            if parsed.scheme not in self.schemes or not parsed.netloc:
                raise exceptions.ValidationError()

    validators.URLValidator = URLValidator
    models = types.ModuleType("django.db.models")

    class Field:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

    class Q:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def __or__(self, other):
            return (self, "OR", other)

    for name in (
        "BooleanField",
        "CharField",
        "ForeignKey",
        "TextField",
        "URLField",
        "UniqueConstraint",
        "CheckConstraint",
    ):
        setattr(models, name, Field)
    models.Q = Q
    models.CASCADE = object()
    db = types.ModuleType("django.db")
    db.models = models
    urls = types.ModuleType("django.urls")
    urls.NoReverseMatch = type("NoReverseMatch", (Exception,), {})
    urls.reverse = lambda *args, **kwargs: "/metrics/1/"
    translation = types.ModuleType("django.utils.translation")
    translation.gettext_lazy = lambda value: value
    netbox_models = types.ModuleType("netbox.models")

    class NetBoxModel:
        def clean(self):
            return None

        def serialize_object(self, exclude=None):
            excluded = set(exclude or ())
            return {
                name: getattr(self, name, None)
                for name in ("influx_url", "query_token_enc")
                if name not in excluded
            }

    netbox_models.NetBoxModel = NetBoxModel
    for name, module in {
        "django.core.exceptions": exceptions,
        "django.core.validators": validators,
        "django.db": db,
        "django.db.models": models,
        "django.urls": urls,
        "django.utils.translation": translation,
        "netbox.models": netbox_models,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    module_name = "_test_proxmox_metrics_model"
    spec = importlib.util.spec_from_file_location(
        module_name, ROOT / "netbox_proxbox/models/proxmox_metrics.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://influx.example.test:8086", "https://influx.example.test:8086"),
        (
            "http://influx.example.test:8086/metrics",
            "********",
        ),
        ("https://user:secret@influx.example.test:8086", "********"),
        ("https://influx.example.test:8086?org=secret", "********"),
        ("", "********"),
    ],
)
def test_influx_url_display_is_credential_free(monkeypatch, value, expected):
    module = _load_model(monkeypatch)
    assert module.masked_influx_url(value) == expected


def test_model_uses_plugin_owned_ciphertext_and_has_no_external_secret_contract():
    source = _read("netbox_proxbox/models/proxmox_metrics.py")
    assert "query_token_enc" in source
    assert "writer_token_enc" not in source
    assert "set_query_token" in source
    assert "get_query_token" in source
    assert "query_token_secret_ref" not in source
    assert "writer_token_secret_ref" not in source


def test_api_create_removes_write_only_token_before_model_construction():
    source = _read("netbox_proxbox/api/serializers/proxmox_metrics.py")
    assert source.index('token_data = {"query_token"') < source.index(
        "instance = ProxmoxMetricsInfluxDB(**validated_data)"
    )


def test_serialization_masks_ciphertext(monkeypatch):
    module = _load_model(monkeypatch)
    instance = object.__new__(module.ProxmoxMetricsInfluxDB)
    instance.influx_url = "https://influx.example.test:8086"
    instance.query_token_enc = "encrypted-query"
    assert instance.serialize_object() == {
        "influx_url": "https://influx.example.test:8086",
        "query_token_enc": "********",
    }


def test_api_and_ui_surfaces_are_registered():
    api_urls = _read("netbox_proxbox/api/urls.py")
    api_views = _read("netbox_proxbox/api/views.py")
    ui_views = _read("netbox_proxbox/views/proxmox_metrics.py")
    assert '"metrics-influxdb"' in api_urls
    assert 'url_path="data"' in api_views
    assert "query_metrics(instance" in api_views
    assert "ProxmoxMetricsInfluxDBDataView" in ui_views
    assert "proxmoxmetricsinfluxdb_data.html" in ui_views


def test_plugin_proxy_matches_backend_contract_without_direct_influx_access():
    proxy = _read("netbox_proxbox/services/metrics_influx.py")
    template = _read(
        "netbox_proxbox/templates/netbox_proxbox/proxmoxmetricsinfluxdb_data.html"
    )
    for contract_field in (
        '"url"',
        '"org"',
        '"bucket"',
        '"token"',
        '"verify_ssl"',
        '"measurement"',
        '"max_rows"',
    ):
        assert contract_field in proxy
    assert "/proxmox/metrics/influx/query" in proxy
    assert "/api/v2/query" not in proxy
    assert "endpoint.enabled" in proxy
    assert "captured_at" in proxy
    assert "MAX_PROXY_RESPONSE_BYTES" in proxy
    assert "requests.Session()" in proxy
    assert "session.trust_env = False" in proxy
    assert "query_token" not in template


def test_docs_define_the_independent_architecture_and_bounded_data_route():
    architecture = _read("docs/developer/proxmox-metrics-architecture.md")
    api = _read("docs/api/infrastructure.md")
    assert "netbox-monitoring" in architecture
    assert "proxbox-api" in architecture
    assert "arbitrary caller-supplied flux is not accepted" in architecture.lower()
    assert "/api/plugins/proxbox/metrics-influxdb/{id}/data/" in api
    assert "query_token_secret_ref" not in api


def test_migration_quarantines_legacy_values_and_adds_new_constraint():
    migration = _read(
        "netbox_proxbox/migrations/0092_proxmox_metrics_plugin_credentials.py"
    )
    assert "_quarantine_legacy_credentials" in migration
    assert "query_token_secret_ref" in migration
    assert "writer_token_secret_ref" in migration
    assert "query_token_enc" in migration
    assert "query_token_configured" in migration
    assert "_MASKED" in migration
