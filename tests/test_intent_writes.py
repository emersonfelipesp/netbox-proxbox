"""Apply-owned intent stamps create rows and remain best effort."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace

from tests._intent_golden_capture import load_intent_module


def test_stamp_updates_only_an_existing_intent_row(monkeypatch):
    calls = []

    class _Query:
        def filter(self, **kwargs):
            calls.append(("filter", kwargs))
            return self

        def update(self, **kwargs):
            calls.append(("update", kwargs))
            return 1

    intent_model = SimpleNamespace(objects=_Query())
    models = types.ModuleType("netbox_proxbox.models")
    models.ProxmoxVMIntent = intent_model
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models)
    writes = load_intent_module("intent_writes")
    vm = SimpleNamespace(pk=73)

    writes.stamp_intent_state(vm, "applied", run_uuid="run-uuid")

    assert calls == [
        ("filter", {"virtual_machine": vm}),
        (
            "update",
            {
                "intent_state": "applied",
                "last_apply_run_id": "run-uuid",
            },
        ),
    ]


def test_stamp_does_not_create_a_missing_intent_row(monkeypatch):
    class _Query:
        def filter(self, **kwargs):
            return self

        def update(self, **kwargs):
            return 0

    models = types.ModuleType("netbox_proxbox.models")
    models.ProxmoxVMIntent = SimpleNamespace(objects=_Query())
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models)
    writes = load_intent_module("intent_writes")

    writes.stamp_intent_state(SimpleNamespace(pk=75), "applied")


def test_stamp_never_raises_when_persistence_fails(monkeypatch):
    def fail(**kwargs):
        raise RuntimeError("database unavailable")

    models = types.ModuleType("netbox_proxbox.models")
    models.ProxmoxVMIntent = SimpleNamespace(
        objects=SimpleNamespace(filter=lambda **kwargs: SimpleNamespace(update=fail))
    )
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models)
    writes = load_intent_module("intent_writes")

    writes.stamp_intent_state(SimpleNamespace(pk=74), "failed")
