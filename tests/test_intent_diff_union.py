"""Behavioral oracle for the combined VM and VM-intent ChangeDiff stream."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import pytest

from tests._intent_golden_capture import load_intent_module


class _Rows:
    def __init__(self, rows):
        self.rows = list(rows)

    def filter(self, *, object_type__model):
        return [row for row in self.rows if row.object_type.model == object_type__model]


def _row(model, action, obj, object_id, **json_fields):
    return SimpleNamespace(
        object_type=SimpleNamespace(model=model),
        action=action,
        object=obj,
        object_id=object_id,
        **json_fields,
    )


def _vm(pk, name=None, user_data=""):
    return SimpleNamespace(
        pk=pk,
        name=name or f"vm-{pk}",
        proxbox_intent=SimpleNamespace(cloud_init_user_data=user_data),
    )


def _branch(*rows):
    return SimpleNamespace(changediff_set=_Rows(rows))


def _operation_pairs(operations):
    return [(vm, op) for vm, op, _row in operations]


@pytest.mark.parametrize("vm_op", ["create", "update", "delete"])
@pytest.mark.parametrize("intent_op", ["create", "update", "delete"])
def test_vm_operation_wins_every_two_stream_operation_pair(vm_op, intent_op):
    union = load_intent_module("diff_union")
    vm = _vm(11)
    branch = _branch(
        _row("virtualmachine", vm_op, vm, vm.pk),
        _row(
            "proxmoxvmintent",
            intent_op,
            SimpleNamespace(virtual_machine_id=vm.pk, virtual_machine=vm),
            31,
        ),
    )

    operations = union.virtual_machine_diff_union(branch)

    assert _operation_pairs(operations) == [(vm, vm_op)]
    assert operations[0][2] is branch.changediff_set.rows[0]


@pytest.mark.parametrize("intent_op", ["create", "update", "delete"])
def test_every_intent_only_operation_becomes_vm_update(monkeypatch, intent_op):
    union = load_intent_module("diff_union")
    vm = _vm(12)
    _install_virtual_machine_module(monkeypatch, {vm.pk: vm})
    branch = _branch(
        _row(
            "proxmoxvmintent",
            intent_op,
            None,
            32,
            original={"virtual_machine": vm.pk},
        )
    )

    operations = union.virtual_machine_diff_union(branch)

    assert _operation_pairs(operations) == [(vm, "update")]
    assert operations[0][2] is branch.changediff_set.rows[0]


def test_intent_delete_resolves_original_when_generic_object_is_gone(monkeypatch):
    union = load_intent_module("diff_union")
    vm = _vm(13)
    _install_virtual_machine_module(monkeypatch, {vm.pk: vm})
    row = _row(
        "proxmoxvmintent",
        "delete",
        None,
        33,
        original={"virtual_machine": vm.pk},
        modified={"virtual_machine": 999},
        current={"virtual_machine": 998},
    )

    assert union.intent_diff_virtual_machine_id(row) == vm.pk
    operations = union.virtual_machine_diff_union(_branch(row))

    assert _operation_pairs(operations) == [(vm, "update")]
    assert operations[0][2] is row


def test_deleted_core_vm_is_retained_with_its_changediff_snapshot(monkeypatch):
    union = load_intent_module("diff_union")
    _install_virtual_machine_module(monkeypatch, {})
    row = _row(
        "virtualmachine",
        "delete",
        None,
        77,
        original={
            "name": "deleted-vm",
            "vmid": 170,
            "node": "pve-deleted",
        },
        current={"name": "deleted-vm"},
    )

    operations = union.virtual_machine_diff_union(_branch(row))

    assert operations == [(None, "delete", row)]


def test_deleted_core_vm_kind_comes_from_the_changediff_snapshot(monkeypatch):
    union = load_intent_module("diff_union")
    _install_virtual_machine_module(monkeypatch, {})
    row = _row(
        "virtualmachine",
        "delete",
        None,
        78,
        original={"virtual_machine_type": {"slug": "lxc-container"}},
    )

    classify = load_intent_module("diff_classify")
    vm, op, changediff = union.virtual_machine_diff_union(_branch(row))[0]

    assert classify.classify_diff(vm, op, changediff) == ("delete", "lxc")


def test_deleted_core_vm_reaches_merge_classification_without_an_object(monkeypatch):
    _install_merge_dependency_stubs(monkeypatch)
    _install_virtual_machine_module(monkeypatch, {})
    merge = load_intent_module("merge_validator")
    row = _row(
        "virtualmachine",
        "delete",
        None,
        79,
        object_repr="deleted-repr",
        original={
            "name": "deleted-name",
            "proxbox_sync_state": {"proxmox_vm_type": "qemu"},
        },
    )

    branch = _branch(row)

    assert merge._classify_vm_diffs(branch) == [
        {
            "op": "delete",
            "kind": "virtualmachine",
            "netbox_id": 79,
            "name": "deleted-name",
        }
    ]
    assert merge._plaintext_password_warnings(branch) == []


def test_intent_parent_resolver_uses_the_documented_fallback_order(monkeypatch):
    union = load_intent_module("diff_union")
    fallback = SimpleNamespace(virtual_machine_id=50)

    class Intent:
        class DoesNotExist(Exception):
            pass

        objects = SimpleNamespace(get=lambda **kwargs: fallback)

    models = types.ModuleType("netbox_proxbox.models")
    models.ProxmoxVMIntent = Intent
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models)

    assert (
        union.intent_diff_virtual_machine_id(
            SimpleNamespace(
                object=SimpleNamespace(virtual_machine_id=10),
                original={"virtual_machine": 20},
                modified={"virtual_machine": 30},
                current={"virtual_machine": 40},
                object_id=1,
            )
        )
        == 10
    )
    assert (
        union.intent_diff_virtual_machine_id(
            SimpleNamespace(
                object=None,
                original={"virtual_machine": 20},
                modified={"virtual_machine": 30},
                current={"virtual_machine": 40},
                object_id=1,
            )
        )
        == 20
    )
    assert (
        union.intent_diff_virtual_machine_id(
            SimpleNamespace(
                object=None,
                original={},
                modified={"virtual_machine": 30},
                current={"virtual_machine": 40},
                object_id=1,
            )
        )
        == 30
    )
    assert (
        union.intent_diff_virtual_machine_id(
            SimpleNamespace(
                object=None,
                original={},
                modified={},
                current={"virtual_machine": 40},
                object_id=1,
            )
        )
        == 40
    )
    assert (
        union.intent_diff_virtual_machine_id(
            SimpleNamespace(
                object=None, original={}, modified={}, current={}, object_id=1
            )
        )
        == 50
    )


def test_merge_classifier_and_warning_oracle(monkeypatch):
    _install_merge_dependency_stubs(monkeypatch)
    merge = load_intent_module("merge_validator")
    vm_create = _vm(21, "new-vm", "#cloud-config\npackages: []")
    vm_intent_only = _vm(22, "intent-vm", "#cloud-config\npassword: secret")
    branch = _branch(
        _row("virtualmachine", "create", vm_create, vm_create.pk),
        _row(
            "proxmoxvmintent",
            "delete",
            SimpleNamespace(
                virtual_machine_id=vm_intent_only.pk,
                virtual_machine=vm_intent_only,
            ),
            41,
        ),
    )

    assert merge._classify_vm_diffs(branch) == [
        {
            "op": "create",
            "kind": "virtualmachine",
            "netbox_id": 21,
            "name": "new-vm",
        },
        {
            "op": "update",
            "kind": "virtualmachine",
            "netbox_id": 22,
            "name": "intent-vm",
        },
    ]
    monkeypatch.setattr(merge, "_warn_plaintext_password_enabled", lambda: True)
    assert merge._plaintext_password_warnings(branch) == [
        {
            "vm": "intent-vm",
            "level": "warn",
            "code": "plaintext_password_warning",
            "message": "cloud_init_user_data contains a plaintext password line",
        }
    ]


def _install_virtual_machine_module(monkeypatch, by_pk):
    class VirtualMachine:
        class DoesNotExist(Exception):
            pass

        @staticmethod
        def _get(*, pk):
            try:
                return by_pk[pk]
            except KeyError as exc:
                raise VirtualMachine.DoesNotExist(pk) from exc

        objects = SimpleNamespace(get=_get)

    virtualization = types.ModuleType("virtualization")
    models = types.ModuleType("virtualization.models")
    models.VirtualMachine = VirtualMachine
    virtualization.models = models
    monkeypatch.setitem(sys.modules, "virtualization", virtualization)
    monkeypatch.setitem(sys.modules, "virtualization.models", models)


def _install_merge_dependency_stubs(monkeypatch):
    firewall = types.ModuleType("netbox_proxbox.intent.firewall_payload")
    firewall.build_firewall_plan_diffs = lambda branch: []
    firewall.default_proxmox_endpoint_id = lambda: None
    firewall.first_endpoint_id_from_diffs = lambda diffs: None
    plan = types.ModuleType("netbox_proxbox.intent.plan_client")
    plan.PlanClientError = RuntimeError
    plan.PlanClientResult = object
    plan.call_plan_endpoint = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "netbox_proxbox.intent.firewall_payload", firewall)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.intent.plan_client", plan)
