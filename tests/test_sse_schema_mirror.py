"""Validate netbox-proxbox REST/SSE mirrors against the proxbox-api wire contract.

netbox-proxbox and proxbox-api communicate over REST, SSE, and WebSocket. The
plugin must not import or install proxbox-api as a Python package; instead, this
test compares the plugin's local Pydantic mirrors with a committed manifest
captured from the proxbox-api release API contract.
"""

from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path

# Stub netbox_proxbox to bypass __init__.py's Django/NetBox dependency. This is
# the same pattern used in test_schemas.py: submodule imports work without
# executing __init__.py, which requires a live NetBox environment.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if "netbox_proxbox" not in sys.modules:
    _stub = types.ModuleType("netbox_proxbox")
    _stub.__path__ = [str(_REPO_ROOT / "netbox_proxbox")]
    sys.modules["netbox_proxbox"] = _stub

_CONTRACT_PATH = _REPO_ROOT / "contracts" / "proxbox_api_sse_schema.json"


def _contract() -> dict[str, object]:
    return json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))


def _contract_enum_values(name: str) -> set[str]:
    values = _contract()["enum_values"]
    assert isinstance(values, dict)
    enum_values = values[name]
    assert isinstance(enum_values, list)
    return set(enum_values)


def _contract_payload_fields(name: str) -> set[str]:
    payloads = _contract()["payload_fields"]
    assert isinstance(payloads, dict)
    fields = payloads[name]
    assert isinstance(fields, list)
    return set(fields)


def _values(enum_cls: type) -> set[str]:
    return {m.value for m in enum_cls}


def _fields(model_cls: type) -> set[str]:
    return set(model_cls.model_fields.keys())


class TestProxmoxEnumMirrors:
    """Local enum mirrors must cover the proxbox-api wire enum values."""

    def test_backup_mode(self):
        from netbox_proxbox.schemas._enums import BackupMode as Mirror

        assert _contract_enum_values("BackupMode") == _values(Mirror)

    def test_compression_algorithm(self):
        from netbox_proxbox.schemas._enums import CompressionAlgorithm as Mirror

        assert _contract_enum_values("CompressionAlgorithm") == _values(Mirror)

    def test_notification_mode(self):
        from netbox_proxbox.schemas._enums import NotificationMode as Mirror

        assert _contract_enum_values("NotificationMode") == _values(Mirror)

    def test_pbs_change_detection_mode(self):
        from netbox_proxbox.schemas._enums import PBSChangeDetectionMode as Mirror

        assert _contract_enum_values("PBSChangeDetectionMode") == _values(Mirror)

    def test_proxmox_vm_status(self):
        from netbox_proxbox.schemas._enums import ProxmoxVMStatus as Mirror

        assert _contract_enum_values("ProxmoxVMStatus") == _values(Mirror)

    def test_disk_format_superset(self):
        """netbox-proxbox DiskFormat intentionally adds PBS/archive formats."""
        from netbox_proxbox.schemas._enums import DiskFormat as Mirror

        missing = _contract_enum_values("DiskFormat") - _values(Mirror)
        assert not missing, (
            "DiskFormat values from the proxbox-api wire contract are missing "
            f"from the netbox-proxbox mirror: {missing}"
        )


def test_stream_message_types_covered_by_sse_event_type():
    """Every backend stream event value must appear in SseEventType."""
    from netbox_proxbox.schemas.backend_proxy import SseEventType

    missing = _contract_enum_values("StreamMessageType") - _values(SseEventType)
    assert not missing, (
        f"proxbox-api stream event values not covered by SseEventType: {missing}"
    )


_PAYLOAD_PAIRS = [
    ("DiscoveryMessage", "netbox_proxbox.schemas.backend_proxy", "SseDiscoveryPayload"),
    ("SubstepMessage", "netbox_proxbox.schemas.backend_proxy", "SseSubstepPayload"),
    (
        "ItemProgressMessage",
        "netbox_proxbox.schemas.backend_proxy",
        "SseItemProgressPayload",
    ),
    (
        "PhaseSummaryMessage",
        "netbox_proxbox.schemas.backend_proxy",
        "SsePhaseSummaryPayload",
    ),
    (
        "ErrorDetailMessage",
        "netbox_proxbox.schemas.backend_proxy",
        "SseErrorDetailPayload",
    ),
    (
        "DuplicateNameResolvedMessage",
        "netbox_proxbox.schemas.backend_proxy",
        "SseDuplicateNameResolvedPayload",
    ),
]


def test_contract_identifies_proxbox_api_release():
    source = _contract()["source"]
    assert isinstance(source, dict)
    assert source["project"] == "proxbox-api"
    assert source["release"] == "0.0.11"


def test_contract_test_does_not_import_proxbox_api():
    assert "proxbox_api" not in sys.modules


def test_contract_field_groups_are_not_empty():
    contract = _contract()
    assert contract["enum_values"]
    assert contract["payload_fields"]


def test_payload_field_coverage_contract_shape():
    for src_cls, mirror_mod, mirror_cls in _PAYLOAD_PAIRS:
        mirror = getattr(importlib.import_module(mirror_mod), mirror_cls)
        missing = _contract_payload_fields(src_cls) - _fields(mirror)
        assert not missing, (
            f"{mirror_cls} is missing fields from the proxbox-api wire "
            f"contract for {src_cls}: {missing}"
        )
