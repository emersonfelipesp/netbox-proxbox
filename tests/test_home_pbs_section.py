"""Tests for the PBS endpoint section on the Proxbox home page."""

from __future__ import annotations

from types import SimpleNamespace

from tests.conftest import load_plugin_module


class _JobQuerySet(list):
    def restrict(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *fields):
        return _JobQuerySet(self)

    def iterator(self, chunk_size=64):
        return iter(self)


def _request():
    return SimpleNamespace(
        user=SimpleNamespace(has_perm=lambda *args, **kwargs: True),
    )


def test_pbs_section_hidden_when_plugin_not_installed(monkeypatch):
    module = load_plugin_module(
        "netbox_proxbox.views.home_context", monkeypatch=monkeypatch
    )

    monkeypatch.setattr(
        module.Job, "objects", _JobQuerySet([]), raising=False
    )
    monkeypatch.setattr(
        module.importlib_util, "find_spec", lambda name: None
    )

    context = module.build_home_dashboard_context(_request())

    assert context["pbs_installed"] is False
    assert context["pbs_endpoint_list"] is None
    assert context["pbs_endpoint_add_url"] is None
    assert context["pbs_endpoint_bulk_import_url"] is None


def test_pbs_section_hidden_when_rest_surface_missing(monkeypatch):
    module = load_plugin_module(
        "netbox_proxbox.views.home_context", monkeypatch=monkeypatch
    )

    monkeypatch.setattr(
        module.Job, "objects", _JobQuerySet([]), raising=False
    )

    monkeypatch.setattr(
        module.importlib_util,
        "find_spec",
        lambda name: SimpleNamespace() if name == "netbox_pbs" else None,
    )

    def _reverse(name, *args, **kwargs):
        if name.startswith("plugins:netbox_pbs"):
            raise module.NoReverseMatch(name)
        return "/dummy/"

    monkeypatch.setattr(module, "reverse", _reverse)

    context = module.build_home_dashboard_context(_request())

    assert context["pbs_installed"] is False
    assert context["pbs_endpoint_list"] is None
    assert context["pbs_endpoint_add_url"] is None
    assert context["pbs_endpoint_bulk_import_url"] is None
