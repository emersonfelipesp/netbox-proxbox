"""The post-merge enqueue gate must see intent-only branches.

An intent-only branch is the new state the ProxmoxVMIntent cutover creates: the
operator changes placement or cloud-init and touches nothing on the virtual
machine itself, so the branch carries a proxmoxvmintent ChangeDiff and no
virtualmachine one.

Gating the apply job on the core virtual-machine stream alone makes that branch
a silent no-op -- the validator permits the merge, the merge reports success,
the job is never queued, and Proxmox is never touched. Nothing raises and
nothing looks wrong, which is what makes it dangerous. These tests execute the
gate rather than reading its source, so a regression fails here.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RECEIVER_PATH = REPO_ROOT / "netbox_proxbox" / "signal_receivers.py"
UNION_PATH = REPO_ROOT / "netbox_proxbox" / "intent" / "diff_union.py"


class _Row:
    """A netbox-branching ChangeDiff, in the shape the gate reads."""

    def __init__(self, model, action, *, obj=None, object_id=None, original=None):
        self.object_type = types.SimpleNamespace(model=model)
        self.action = action
        self.object = obj
        self.object_id = object_id
        self.original = original
        self.modified = None
        self.current = None


class _ChangeDiffSet:
    def __init__(self, rows):
        self._rows = list(rows)

    def filter(self, **kwargs):
        model = kwargs["object_type__model"]
        return [r for r in self._rows if r.object_type.model == model]


class _Branch:
    def __init__(self, rows):
        self.pk = 7
        self.changediff_set = _ChangeDiffSet(rows)


class _VM:
    def __init__(self, pk, name="vm"):
        self.pk = pk
        self.name = name


class _Intent:
    def __init__(self, vm):
        self.virtual_machine = vm
        self.virtual_machine_id = vm.pk


def _stub_module(name: str) -> types.ModuleType:
    """A stub module that later real imports can still introspect.

    A bare ModuleType has ``__spec__ = None``, and anything that inspects the
    module -- pytest's assertion rewriter among them -- raises
    ``ValueError: <name>.__spec__ is None``. That surfaced as unrelated tests
    erroring once these stubs were in ``sys.modules``, so give every stub a real
    spec.
    """
    module = types.ModuleType(name)
    module.__spec__ = importlib.machinery.ModuleSpec(name, loader=None)
    return module


def _install_django_stubs() -> None:
    """Enough of Django for the receiver module's import line to succeed.

    `apps.is_installed("netbox_branching")` returns False here, which is the
    branch that leaves `post_merge` as None -- the helper under test stays
    importable while the decorated handler is never registered.
    """
    if "django" not in sys.modules:
        sys.modules["django"] = _stub_module("django")
    if "django.apps" not in sys.modules:
        module = _stub_module("django.apps")
        module.apps = types.SimpleNamespace(is_installed=lambda label: False)
        sys.modules["django.apps"] = module
    if "django.dispatch" not in sys.modules:
        module = _stub_module("django.dispatch")
        module.receiver = lambda *a, **k: lambda fn: fn
        sys.modules["django.dispatch"] = module


VM_TABLE: dict[int, "_VM"] = {}


def _install_virtualization_stub() -> None:
    """A VirtualMachine manager backed by VM_TABLE.

    The deleted-intent path resolves its virtual machine by primary key through
    the ORM, so without this the one case the design note singles out cannot be
    executed at all.
    """
    if "virtualization" not in sys.modules:
        sys.modules["virtualization"] = _stub_module("virtualization")
    if "virtualization.models" in sys.modules:
        return
    module = _stub_module("virtualization.models")

    class DoesNotExist(Exception):
        pass

    class _Manager:
        def get(self, pk):
            if pk not in VM_TABLE:
                raise DoesNotExist(pk)
            return VM_TABLE[pk]

    module.VirtualMachine = type(
        "VirtualMachine", (), {"objects": _Manager(), "DoesNotExist": DoesNotExist}
    )
    sys.modules["virtualization.models"] = module


def _load(name: str, path: Path):
    _install_django_stubs()
    _install_virtualization_stub()
    if "netbox_proxbox" not in sys.modules:
        package = _stub_module("netbox_proxbox")
        package.__path__ = [str(REPO_ROOT / "netbox_proxbox")]
        sys.modules["netbox_proxbox"] = package
    if "netbox_proxbox.intent" not in sys.modules:
        intent = _stub_module("netbox_proxbox.intent")
        intent.__path__ = [str(REPO_ROOT / "netbox_proxbox" / "intent")]
        sys.modules["netbox_proxbox.intent"] = intent
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    """The receiver module's gate, loaded with netbox_branching absent.

    The module degrades to `post_merge = None` without netbox_branching, which
    leaves the helper importable while the decorated handler is not registered.
    """
    _load("netbox_proxbox.intent.diff_union", UNION_PATH)
    module = _load("netbox_proxbox.signal_receivers", RECEIVER_PATH)
    return module._mergeable_virtual_machines


def test_an_intent_only_branch_is_not_a_silent_no_op(gate):
    vm = _VM(11)
    branch = _Branch([_Row("proxmoxvmintent", "update", obj=_Intent(vm))])

    resolved = gate(branch)

    assert resolved, (
        "an intent-only branch must queue the apply job; gating on the "
        "virtual-machine stream alone merges successfully and applies nothing"
    )
    assert [(v.pk, op) for v, op, _row in resolved] == [(11, "update")]


@pytest.mark.parametrize("action", ["create", "update", "delete"])
def test_every_intent_only_action_reaches_the_gate(gate, action):
    vm = _VM(12)
    VM_TABLE[12] = vm
    row = (
        _Row("proxmoxvmintent", action, object_id=3, original={"virtual_machine": 12})
        if action == "delete"
        else _Row("proxmoxvmintent", action, obj=_Intent(vm))
    )
    branch = _Branch([row])

    resolved = gate(branch)

    assert [(v.pk, op) for v, op, _row in resolved] == [(12, "update")], (
        "clearing intent inside a branch is an update to the guest, and for a "
        "deleted row the virtual machine is only reachable through `original`"
    )


def test_a_vm_only_branch_still_reaches_the_gate(gate):
    vm = _VM(13)
    branch = _Branch([_Row("virtualmachine", "create", obj=vm)])

    assert [(v.pk, op) for v, op, _row in gate(branch)] == [(13, "create")]


def test_a_branch_touching_both_streams_yields_one_entry(gate):
    vm = _VM(14)
    branch = _Branch(
        [
            _Row("virtualmachine", "create", obj=vm),
            _Row("proxmoxvmintent", "update", obj=_Intent(vm)),
        ]
    )

    resolved = gate(branch)

    assert [(v.pk, op) for v, op, _row in resolved] == [(14, "create")], (
        "one dispatch per virtual machine, and the core diff's op wins"
    )


def test_a_branch_with_neither_stream_is_still_skipped(gate):
    assert gate(_Branch([])) == []


def test_a_branch_without_changediff_support_is_skipped(gate):
    assert gate(types.SimpleNamespace(pk=1, changediff_set=None)) == []


def test_a_deleted_intent_whose_vm_is_also_gone_is_skipped(gate):
    """Deleting the guest and its intent together must not resurrect a target."""
    VM_TABLE.pop(999, None)
    branch = _Branch(
        [
            _Row(
                "proxmoxvmintent",
                "delete",
                object_id=42,
                original={"virtual_machine": 999},
            )
        ]
    )

    assert gate(branch) == []


def test_a_deleted_core_vm_whose_object_is_gone_still_reaches_the_gate(gate):
    VM_TABLE.pop(999, None)
    row = _Row(
        "virtualmachine",
        "delete",
        object_id=999,
        original={
            "name": "deleted-vm",
            "proxbox_sync_state": {
                "proxmox_vm_id": 199,
                "proxmox_node_name": "pve-deleted",
            },
        },
    )

    assert gate(_Branch([row])) == [(None, "delete", row)]
