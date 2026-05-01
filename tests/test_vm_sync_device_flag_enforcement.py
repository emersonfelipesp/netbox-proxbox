"""Lock the VM-sync device flag enforcement contract (PR #342).

Ensures the six ``overwrite_device_*`` flags are part of the canonical
``OVERWRITE_FIELDS`` tuple and that they are forwarded to the proxbox-api
``full-update/stream`` endpoint as flat query params when a sync runs.

The behavior tested:

1. The six device flags listed in ``OVERWRITE_FIELD_GROUPS["Device"]`` are
   exposed in ``OVERWRITE_FIELDS`` so every sync stage that flattens the tuple
   automatically includes them.
2. ``sync_stages._build_base_query_params`` encodes per-endpoint device-flag
   values as ``"true"`` / ``"false"`` strings on a single-endpoint scope so the
   FastAPI backend honors the user's choice.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

DEVICE_OVERWRITE_FIELDS = (
    "overwrite_device_role",
    "overwrite_device_type",
    "overwrite_device_tags",
    "overwrite_device_status",
    "overwrite_device_description",
    "overwrite_device_custom_fields",
)


def _load_constants():
    spec = importlib.util.spec_from_file_location(
        "_netbox_proxbox_constants_for_device_flags",
        REPO_ROOT / "netbox_proxbox" / "constants.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_all_six_device_flags_are_in_overwrite_fields():
    constants = _load_constants()
    for field in DEVICE_OVERWRITE_FIELDS:
        assert field in constants.OVERWRITE_FIELDS, (
            f"{field} dropped from OVERWRITE_FIELDS — VM sync would silently "
            "fall back to backend default (always overwrite)"
        )


def test_device_group_label_uses_device_prefix():
    constants = _load_constants()
    device_group = next(
        (
            fields
            for name, fields in constants.OVERWRITE_FIELD_GROUPS
            if name == "Device"
        ),
        None,
    )
    assert device_group is not None, "Device group missing from OVERWRITE_FIELD_GROUPS"
    assert device_group == DEVICE_OVERWRITE_FIELDS


@pytest.fixture
def sync_stages_module(monkeypatch):
    """Load sync_stages.py with a single-endpoint scope and stub state."""
    constants = _load_constants()
    fields = tuple(constants.OVERWRITE_FIELDS)

    state = {
        "global": {name: True for name in fields},
        "per_endpoint": {name: True for name in fields},
    }

    pkg = types.ModuleType("netbox_proxbox")
    pkg.__path__ = [str(REPO_ROOT / "netbox_proxbox")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", pkg)

    constants_mod = types.ModuleType("netbox_proxbox.constants")
    constants_mod.OVERWRITE_FIELDS = fields
    monkeypatch.setitem(sys.modules, "netbox_proxbox.constants", constants_mod)

    choices_mod = types.ModuleType("netbox_proxbox.choices")
    choices_mod.SyncTypeChoices = SimpleNamespace(
        ALL="all",
        VIRTUAL_MACHINES="virtual-machines",
        VIRTUAL_MACHINES_BACKUPS="vm-backups",
        VIRTUAL_MACHINES_SNAPSHOTS="vm-snapshots",
        VIRTUAL_MACHINES_DISKS="vm-disks",
        DEVICES="devices",
        STORAGE="storage",
        TASK_HISTORY="task-history",
        NETWORK_INTERFACES="network-interfaces",
        VM_INTERFACES="vm-interfaces",
        IP_ADDRESSES="ip-addresses",
        REPLICATIONS="replications",
        BACKUP_ROUTINES="backup-routines",
    )
    monkeypatch.setitem(sys.modules, "netbox_proxbox.choices", choices_mod)

    class _ProxboxPluginSettings:
        @classmethod
        def get_solo(cls):
            return SimpleNamespace(
                use_guest_agent_interface_name=True,
                proxbox_fetch_max_concurrency=8,
                ignore_ipv6_link_local_addresses=True,
                primary_ip_preference="ipv4",
                **state["global"],
            )

    def _effective_overwrites():
        return {
            name: state["per_endpoint"][name]
            if state["per_endpoint"][name] is not None
            else state["global"][name]
            for name in fields
        }

    endpoint = SimpleNamespace(
        pk=1,
        effective_overwrites=_effective_overwrites,
        **state["per_endpoint"],
    )

    class _Manager:
        def filter(self, **kwargs):
            return self

        def first(self):
            return endpoint

        def __iter__(self):
            return iter([endpoint])

    class _ProxmoxEndpoint:
        objects = _Manager()

    models_mod = types.ModuleType("netbox_proxbox.models")
    models_mod.ProxboxPluginSettings = _ProxboxPluginSettings
    models_mod.ProxmoxEndpoint = _ProxmoxEndpoint
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models_mod)

    netbox_jobs_mod = types.ModuleType("netbox.jobs")
    netbox_jobs_mod.Job = type("Job", (), {})
    monkeypatch.setitem(sys.modules, "netbox.jobs", netbox_jobs_mod)

    for name in (
        "netbox_proxbox.sync_types",
        "netbox_proxbox.sync_params",
        "netbox_proxbox.sync_ownership",
        "netbox_proxbox.sync_stages",
    ):
        sys.modules.pop(name, None)
        spec = importlib.util.spec_from_file_location(
            name,
            REPO_ROOT / "netbox_proxbox" / f"{name.split('.')[-1]}.py",
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)

    module = sys.modules["netbox_proxbox.sync_stages"]
    module._state = state  # type: ignore[attr-defined]
    return module


def test_device_flags_serialized_for_single_endpoint(sync_stages_module):
    fields = _load_constants().OVERWRITE_FIELDS
    sync_stages_module._state["per_endpoint"] = {
        **{name: True for name in fields},
        **{name: False for name in DEVICE_OVERWRITE_FIELDS},
    }
    sync_stages_module._state["global"] = {
        **{name: True for name in fields},
        **{name: False for name in DEVICE_OVERWRITE_FIELDS},
    }

    base_query = sync_stages_module._build_base_query_params(
        proxmox_endpoint_ids=["1"],
        netbox_endpoint_ids=None,
    )

    for field in DEVICE_OVERWRITE_FIELDS:
        assert base_query.get(field) == "false", (
            f"{field}=False not propagated to backend query string; "
            "VM sync would let the backend default override the user's choice"
        )
