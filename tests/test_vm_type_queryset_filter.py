"""Behavior tests for typed VM-type queryset filtering."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
UTILS_PATHS = (
    REPO_ROOT / "netbox_proxbox" / "utils.py",
    REPO_ROOT / "netbox_proxbox" / "utils" / "__init__.py",
)


class _Q:
    def __init__(self, **lookup):
        self.lookup = lookup
        self.children: tuple[_Q, ...] = ()

    def __or__(self, other: "_Q") -> "_Q":
        combined = _Q()
        combined.children = (self, other)
        return combined

    def matches(self, row: object) -> bool:
        if self.children:
            return any(child.matches(row) for child in self.children)
        for path, expected in self.lookup.items():
            value = row
            try:
                for segment in path.split("__"):
                    value = getattr(value, segment)
            except AttributeError:
                return False
            if value != expected:
                return False
        return True


class _QuerySet:
    def __init__(self, rows):
        self.rows = list(rows)

    def filter(self, query):
        return _QuerySet(row for row in self.rows if query.matches(row))


@pytest.fixture(params=UTILS_PATHS, ids=("module", "package"))
def utils_module(request, monkeypatch):
    root = types.ModuleType("netbox_proxbox")
    root.__path__ = [str(REPO_ROOT / "netbox_proxbox")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", root)
    monkeypatch.setitem(
        sys.modules,
        "netbox_proxbox.type_defs",
        types.SimpleNamespace(FastAPIAuthSource=object, FastAPIUrlSource=object),
    )
    monkeypatch.setitem(
        sys.modules,
        "netbox_proxbox.vm_identity",
        types.SimpleNamespace(resolve_vm_type=lambda vm: "qemu"),
    )
    monkeypatch.setitem(sys.modules, "django", types.ModuleType("django"))
    django_db = types.ModuleType("django.db")
    django_models = types.ModuleType("django.db.models")
    django_models.Q = _Q
    monkeypatch.setitem(sys.modules, "django.db", django_db)
    monkeypatch.setitem(sys.modules, "django.db.models", django_models)

    module_name = f"_vm_filter_{request.param.parent.name}"
    spec = importlib.util.spec_from_file_location(module_name, request.param)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_filter_uses_typed_sidecar_and_preserves_native_type_branch(utils_module):
    class _Meta:
        @staticmethod
        def get_field(name):
            if name != "virtual_machine_type":
                raise LookupError(name)
            return object()

    model = type("VirtualMachine", (), {"_meta": _Meta()})
    typed = SimpleNamespace(
        pk=1,
        proxbox_sync_state=SimpleNamespace(proxmox_vm_type="lxc"),
        virtual_machine_type=SimpleNamespace(slug="qemu-virtual-machine"),
        custom_field_data={},
    )
    native = SimpleNamespace(
        pk=2,
        proxbox_sync_state=SimpleNamespace(proxmox_vm_type="qemu"),
        virtual_machine_type=SimpleNamespace(slug="lxc-container"),
        custom_field_data={},
    )
    removed_custom_field_only = SimpleNamespace(
        pk=3,
        virtual_machine_type=SimpleNamespace(slug="qemu-virtual-machine"),
        custom_field_data={"proxmox_vm_type": "lxc"},
    )

    result = utils_module.filter_queryset_by_proxmox_vm_type(
        _QuerySet((typed, native, removed_custom_field_only)),
        model,
        vm_type="lxc",
        vm_type_slug="lxc-container",
    )

    assert [row.pk for row in result.rows] == [1, 2]
