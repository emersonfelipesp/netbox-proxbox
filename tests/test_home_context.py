"""Tests for test_home_context."""

from __future__ import annotations

import sys
import types
from datetime import datetime, timezone
from types import SimpleNamespace

from tests.conftest import load_plugin_module


class _JobQuerySet(list):
    def restrict(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *fields):
        return _JobQuerySet(sorted(self, key=lambda item: item.created, reverse=True))

    def iterator(self, chunk_size=64):
        return iter(self)


class _EndpointQuerySet(list):
    def restrict(self, user, action):
        self.restrict_call = (user, action)
        return self

    def order_by(self, *fields):
        self.order_by_call = fields
        return self

    def exists(self):
        return bool(self)


class _FakeField:
    def __init__(self, name):
        self.name = name


class _FakeMeta:
    app_label = "netbox_pbs"
    model_name = "pbsserver"
    verbose_name = "PBS server"
    verbose_name_plural = "PBS servers"
    ordering = ("name",)

    def get_fields(self):
        return [
            _FakeField("name"),
            _FakeField("host"),
            _FakeField("port"),
            _FakeField("token_id"),
            _FakeField("fingerprint"),
            _FakeField("verify_ssl"),
            _FakeField("status"),
            _FakeField("version"),
            _FakeField("last_seen_at"),
        ]


class PBSServer:
    _meta = _FakeMeta()

    def __init__(self):
        self.pk = 7
        self.name = "PBS01"
        self.host = "10.0.30.134"
        self.port = 8007
        self.token_id = "sensitive-token-id"
        self.fingerprint = "sensitive-fingerprint"
        self.verify_ssl = True
        self.status = "online"
        self.version = "3.2"
        self.last_seen_at = datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return f"/plugins/pbs/servers/{self.pk}/"


def _install_installed_plugin_stubs(monkeypatch, app_configs):
    django_apps_module = types.ModuleType("django.apps")
    configs_by_label = {config.label: config for config in app_configs}
    django_apps_module.apps = SimpleNamespace(
        get_app_config=lambda label: configs_by_label[label]
    )

    registry_module = types.ModuleType("netbox.registry")
    registry_module.registry = {
        "plugins": {"installed": [config.label for config in app_configs]}
    }

    monkeypatch.setitem(sys.modules, "django.apps", django_apps_module)
    monkeypatch.setitem(sys.modules, "netbox.registry", registry_module)
    setattr(sys.modules["django"], "apps", django_apps_module)
    setattr(sys.modules["netbox"], "registry", registry_module)


def test_home_context_exposes_latest_active_proxbox_job(monkeypatch):
    module = load_plugin_module(
        "netbox_proxbox.views.home_context", monkeypatch=monkeypatch
    )

    proxbox_job = SimpleNamespace(
        pk=2,
        created=2,
        status="running",
        name="Proxbox Sync: Full update",
    )
    other_job = SimpleNamespace(
        pk=1,
        created=1,
        status="running",
        name="Non-Proxbox job",
    )

    monkeypatch.setattr(
        module.Job,
        "objects",
        _JobQuerySet([other_job, proxbox_job]),
        raising=False,
    )
    monkeypatch.setattr(
        module,
        "is_proxbox_sync_job",
        lambda job: str(getattr(job, "name", "")).startswith("Proxbox Sync"),
    )

    context = module.build_home_dashboard_context(
        SimpleNamespace(
            user=SimpleNamespace(has_perm=lambda *args, **kwargs: True),
        )
    )

    assert context["active_proxbox_job"] is proxbox_job


def test_companion_endpoint_groups_render_required_plugin_endpoint_models(monkeypatch):
    module = load_plugin_module(
        "netbox_proxbox.views.home_context", monkeypatch=monkeypatch
    )
    endpoint = PBSServer()
    PBSServer.objects = _EndpointQuerySet([endpoint])

    app_config = SimpleNamespace(
        label="netbox_pbs",
        name="netbox_pbs",
        verbose_name="NetBox PBS",
        version="0.0.1",
        base_url="pbs",
        required_plugins=["netbox_proxbox"],
        get_models=lambda: [PBSServer],
    )
    _install_installed_plugin_stubs(monkeypatch, [app_config])

    request = SimpleNamespace(
        user=SimpleNamespace(),
        build_absolute_uri=lambda path: f"https://netbox.example{path}",
    )

    groups = module.build_companion_endpoint_groups(request, absolute_urls=True)

    assert groups == [
        {
            "plugin_name": "NetBox PBS",
            "plugin_package": "netbox_pbs",
            "plugin_version": "0.0.1",
            "plugin_base_url": "pbs",
            "model_name": "PBSServer",
            "model_label": "PBS server",
            "model_label_plural": "PBS servers",
            "endpoints": [
                {
                    "id": 7,
                    "name": "PBS01",
                    "url": "https://netbox.example/plugins/pbs/servers/7/",
                    "connection_status": {
                        "label": "Connection Status",
                        "service": "pbs",
                        "badge_id": "pbs-status-badge-7",
                        "message_id": "pbs-connection-error-7",
                        "url": "/dummy/",
                    },
                    "fields": [
                        {"name": "host", "label": "Host", "value": "10.0.30.134"},
                        {"name": "port", "label": "Port", "value": "8007"},
                        {"name": "status", "label": "Status", "value": "online"},
                        {"name": "version", "label": "Version", "value": "3.2"},
                        {"name": "verify_ssl", "label": "Verify SSL", "value": "Yes"},
                        {
                            "name": "last_seen_at",
                            "label": "Last seen",
                            "value": "2026-05-24T12:00:00+00:00",
                        },
                    ],
                }
            ],
        }
    ]
    assert PBSServer.objects.restrict_call == (request.user, "view")


def test_companion_endpoint_groups_ignore_unrelated_plugins(monkeypatch):
    module = load_plugin_module(
        "netbox_proxbox.views.home_context", monkeypatch=monkeypatch
    )
    PBSServer.objects = _EndpointQuerySet([PBSServer()])

    app_config = SimpleNamespace(
        label="netbox_dns",
        name="netbox_dns",
        verbose_name="NetBox DNS",
        required_plugins=[],
        get_models=lambda: [PBSServer],
    )
    _install_installed_plugin_stubs(monkeypatch, [app_config])

    groups = module.build_companion_endpoint_groups(
        SimpleNamespace(user=SimpleNamespace())
    )

    assert groups == []
