from __future__ import annotations

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
