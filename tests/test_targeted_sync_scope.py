"""Source contract: a targeted per-VM sync must not do estate-wide work.

Reported in netbox-proxbox issue #616. Syncing a single VM produced this log on
an 8-endpoint install *before* the VM itself was touched::

    Info | NetBox virtual machines: ['59']
    Info | Syncing cluster/nodes for endpoint 1
    ...                          (repeated for endpoints 2..8)
    Info | Syncing firewall objects from proxbox-api
    Info | Syncing datacenter CPU models from proxbox-api
    Info | Syncing VM templates for endpoint 1
    ...                          (repeated for endpoints 2..8)

The reporter's summary was "the logs show that all clusters are being updated,
although only one VM is synchronizing".

Two separate causes:

1. ``views/vm_sync_now.py`` passed **every enabled** ``ProxmoxEndpoint`` id, so
   even the preflight blocks that *do* honour ``proxmox_endpoint_ids`` ran
   against the whole estate. Covered behaviourally in
   ``tests/test_vm_sync_now_view.py``.
2. ``ProxboxSyncJob.run()`` ran the datacenter-wide passes unconditionally.
   Firewall and datacenter-CPU-model sync take **no** scoping argument at all,
   and VM template sync looped every endpoint. None of them consulted
   ``netbox_vm_ids``. That is what this module pins.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
JOBS_PY = REPO_ROOT / "netbox_proxbox" / "jobs.py"

# Calls that are datacenter-wide and irrelevant to reconciling one VM.
ESTATE_WIDE_CALLS = ("sync_firewall", "sync_datacenter", "sync_vm_templates")


def _run_method() -> ast.FunctionDef:
    """Return the ``ProxboxSyncJob.run`` definition."""
    tree = ast.parse(JOBS_PY.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "ProxboxSyncJob":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "run":
                    return item
    raise AssertionError("ProxboxSyncJob.run not found in jobs.py")


def test_run_defines_a_targeted_vm_run_flag():
    """``run()`` must derive a targeted-run flag from the selected VM ids."""
    source = ast.unparse(_run_method())
    assert "targeted_vm_run" in source, (
        "ProxboxSyncJob.run must compute a targeted-run flag so a single-VM "
        "sync can skip datacenter-wide preflight work"
    )
    assert "targeted_vm_run = bool(netbox_vm_ids)" in source, (
        "the targeted-run flag must be derived from netbox_vm_ids"
    )


@pytest.mark.parametrize("call_name", ESTATE_WIDE_CALLS)
def test_estate_wide_preflight_is_gated_by_the_targeted_flag(call_name):
    """Each datacenter-wide pass must sit under a ``targeted_vm_run`` guard."""
    run_node = _run_method()

    guarded_calls: set[str] = set()
    for node in ast.walk(run_node):
        if not isinstance(node, ast.If):
            continue
        if "targeted_vm_run" not in ast.unparse(node.test):
            continue
        # Collect calls in whichever branch is the non-targeted path.
        for branch in (node.body, node.orelse):
            branch_source = "\n".join(ast.unparse(stmt) for stmt in branch)
            for name in ESTATE_WIDE_CALLS:
                if f"{name}(" in branch_source:
                    guarded_calls.add(name)

    assert call_name in guarded_calls, (
        f"{call_name}() runs unconditionally in ProxboxSyncJob.run; a targeted "
        "single-VM sync would still do estate-wide work. Gate it on "
        "targeted_vm_run."
    )


def test_targeted_skips_are_logged():
    """Skipping must be visible in the job log, not silent."""
    source = ast.unparse(_run_method())
    for label in ("Skipping firewall sync", "Skipping datacenter CPU model sync"):
        assert label in source, (
            f"expected a job-log line containing {label!r} so operators can see "
            "why the pass did not run"
        )
