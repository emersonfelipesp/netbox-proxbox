"""Fail-closed behavior for the shared per-branch intent resolver."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest


RESOLVER_PATH = (
    Path(__file__).resolve().parents[1]
    / "netbox_proxbox"
    / "services"
    / "branch_intent.py"
)


class _Query:
    def __init__(self, row=None, *, raises: bool = False) -> None:
        self.row = row
        self.raises = raises
        self.filters: list[dict] = []

    def filter(self, **kwargs):
        self.filters.append(kwargs)
        if self.raises:
            raise RuntimeError("database unavailable")
        return self

    def first(self):
        return self.row


def _load_resolver(
    monkeypatch: pytest.MonkeyPatch,
    *,
    available: bool = True,
    branch_row=...,
    intent_row=None,
    branch_query_raises: bool = False,
    intent_query_raises: bool = False,
):
    package = types.ModuleType("netbox_proxbox")
    package.__path__ = []  # type: ignore[attr-defined]
    services = types.ModuleType("netbox_proxbox.services")
    services.__path__ = []  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", package)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services)

    lifecycle = types.ModuleType("netbox_proxbox.services.branch_lifecycle")
    lifecycle.is_branching_available = lambda: available
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.services.branch_lifecycle", lifecycle
    )

    if branch_row is ...:
        branch_row = SimpleNamespace(pk=7, schema_id="schema-7")
    branch_query = _Query(branch_row, raises=branch_query_raises)
    branching_models = types.ModuleType("netbox_branching.models")
    branching_models.Branch = SimpleNamespace(objects=branch_query)
    monkeypatch.setitem(sys.modules, "netbox_branching.models", branching_models)

    intent_query = _Query(intent_row, raises=intent_query_raises)
    models = types.ModuleType("netbox_proxbox.models")
    models.ProxboxBranchIntent = SimpleNamespace(objects=intent_query)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models)

    name = "netbox_proxbox.services.branch_intent"
    spec = importlib.util.spec_from_file_location(name, RESOLVER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module, branch_query, intent_query


@pytest.mark.parametrize(
    (
        "available",
        "branch",
        "branch_row",
        "intent_row",
        "branch_raises",
        "intent_raises",
    ),
    [
        (True, SimpleNamespace(pk=7, schema_id="schema-7"), ..., None, False, False),
        (
            False,
            SimpleNamespace(pk=7, schema_id="schema-7"),
            ...,
            SimpleNamespace(apply_to_proxmox=True, apply_destroy_confirmed=True),
            False,
            False,
        ),
        (
            True,
            SimpleNamespace(pk=7, schema_id="schema-7"),
            None,
            SimpleNamespace(apply_to_proxmox=True, apply_destroy_confirmed=True),
            False,
            False,
        ),
        (
            True,
            None,
            ...,
            SimpleNamespace(apply_to_proxmox=True, apply_destroy_confirmed=True),
            False,
            False,
        ),
        (
            True,
            SimpleNamespace(pk=7, schema_id="schema-7"),
            ...,
            SimpleNamespace(apply_to_proxmox=True, apply_destroy_confirmed=True),
            True,
            False,
        ),
        (
            True,
            SimpleNamespace(pk=7, schema_id="schema-7"),
            ...,
            SimpleNamespace(apply_to_proxmox=True, apply_destroy_confirmed=True),
            False,
            True,
        ),
    ],
    ids=(
        "no-intent-row",
        "branching-absent",
        "branch-deleted",
        "branch-none",
        "branch-lookup-raises",
        "intent-lookup-raises",
    ),
)
def test_resolver_fails_closed_for_both_flags(
    monkeypatch,
    available,
    branch,
    branch_row,
    intent_row,
    branch_raises,
    intent_raises,
):
    module, _branch_query, _intent_query = _load_resolver(
        monkeypatch,
        available=available,
        branch_row=branch_row,
        intent_row=intent_row,
        branch_query_raises=branch_raises,
        intent_query_raises=intent_raises,
    )

    flags = module.resolve_branch_intent_flags(branch)

    assert flags.apply_to_proxmox is False
    assert flags.apply_destroy_confirmed is False


def test_resolver_returns_both_true_flags_and_ignores_custom_fields(monkeypatch):
    intent = SimpleNamespace(
        apply_to_proxmox=True,
        apply_destroy_confirmed=True,
    )
    module, branch_query, intent_query = _load_resolver(
        monkeypatch,
        intent_row=intent,
    )
    branch = SimpleNamespace(
        pk=7,
        schema_id="schema-7",
        custom_field_data={},
    )

    flags = module.resolve_branch_intent_flags(branch)

    assert flags.apply_to_proxmox is True
    assert flags.apply_destroy_confirmed is True
    assert branch_query.filters == [{"pk": 7, "schema_id": "schema-7"}]
    assert intent_query.filters == [{"branch_id": 7, "branch_schema_id": "schema-7"}]


def test_resolver_requires_literal_boolean_true(monkeypatch):
    module, _branch_query, _intent_query = _load_resolver(
        monkeypatch,
        intent_row=SimpleNamespace(
            apply_to_proxmox=1,
            apply_destroy_confirmed="yes",
        ),
    )

    flags = module.resolve_branch_intent_flags(
        SimpleNamespace(pk=7, schema_id="schema-7")
    )

    assert flags.apply_to_proxmox is False
    assert flags.apply_destroy_confirmed is False
