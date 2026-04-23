"""Contract tests: netbox-proxbox schema mirrors must stay in sync with proxbox-api.

These tests import proxbox-api directly (as a dev test dependency via path reference)
and assert that every enum value and every payload field present in the authoritative
proxbox-api definitions also exists in the manually-maintained mirrors inside this plugin.

Run with: pytest tests/test_sse_schema_mirror.py -v
Requires: proxbox-api installed (e.g. via `uv sync --extra test`)

Note: uses the same netbox_proxbox stub technique as test_schemas.py to bypass
the plugin's Django/NetBox __init__.py without a running NetBox environment.
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Stub netbox_proxbox to bypass __init__.py's Django/NetBox dependency.
# This is the same pattern used in test_schemas.py: inject a stub module
# with __path__ pointing to the real directory so submodule imports work,
# but without executing __init__.py which requires `from netbox.plugins import PluginConfig`.
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[1]
if "netbox_proxbox" not in sys.modules:
    _stub = types.ModuleType("netbox_proxbox")
    _stub.__path__ = [str(_REPO_ROOT / "netbox_proxbox")]
    sys.modules["netbox_proxbox"] = _stub

# ---------------------------------------------------------------------------
# Skip the whole module when proxbox-api is not installed.
# ---------------------------------------------------------------------------
proxbox_api = pytest.importorskip(
    "proxbox_api",
    reason="proxbox-api not installed; run: uv sync --extra test",
)


def _values(enum_cls: type) -> set[str]:
    return {m.value for m in enum_cls}


def _fields(model_cls: type) -> set[str]:
    return set(model_cls.model_fields.keys())


# ---------------------------------------------------------------------------
# Proxmox enum mirrors
# ---------------------------------------------------------------------------


class TestProxmoxEnumMirrors:
    """Each enum in _enums.py must match its counterpart in proxbox-api enum/proxmox.py."""

    def test_backup_mode(self):
        from proxbox_api.enum.proxmox import BackupMode as Src
        from netbox_proxbox.schemas._enums import BackupMode as Mirror

        assert _values(Src) == _values(Mirror)

    def test_compression_algorithm(self):
        from proxbox_api.enum.proxmox import CompressionAlgorithm as Src
        from netbox_proxbox.schemas._enums import CompressionAlgorithm as Mirror

        assert _values(Src) == _values(Mirror)

    def test_notification_mode(self):
        from proxbox_api.enum.proxmox import NotificationMode as Src
        from netbox_proxbox.schemas._enums import NotificationMode as Mirror

        assert _values(Src) == _values(Mirror)

    def test_pbs_change_detection_mode(self):
        from proxbox_api.enum.proxmox import PBSChangeDetectionMode as Src
        from netbox_proxbox.schemas._enums import PBSChangeDetectionMode as Mirror

        assert _values(Src) == _values(Mirror)

    def test_proxmox_vm_status(self):
        from proxbox_api.enum.proxmox import ProxmoxVMStatus as Src
        from netbox_proxbox.schemas._enums import ProxmoxVMStatus as Mirror

        assert _values(Src) == _values(Mirror)

    def test_disk_format_superset(self):
        """netbox-proxbox DiskFormat extends proxbox-api with PBS/archive formats.

        The mirror is intentionally a superset. This test asserts that no proxbox-api
        value has been dropped from the mirror — not that the sets are equal.
        """
        from proxbox_api.enum.proxmox import DiskFormat as Src
        from netbox_proxbox.schemas._enums import DiskFormat as Mirror

        missing = _values(Src) - _values(Mirror)
        assert not missing, (
            f"DiskFormat values in proxbox-api are missing from the netbox-proxbox mirror: {missing}"
        )


# ---------------------------------------------------------------------------
# StreamMessageType → SseEventType coverage
# ---------------------------------------------------------------------------


def test_stream_message_types_covered_by_sse_event_type():
    """Every StreamMessageType value must appear in SseEventType.

    SseEventType is a superset (adds terminal transport events: complete, error, step).
    """
    from proxbox_api.schemas.stream_messages import StreamMessageType
    from netbox_proxbox.schemas.backend_proxy import SseEventType

    missing = _values(StreamMessageType) - _values(SseEventType)
    assert not missing, (
        f"proxbox-api StreamMessageType values not covered by SseEventType: {missing}"
    )


# ---------------------------------------------------------------------------
# SSE payload field coverage
# ---------------------------------------------------------------------------

_PAYLOAD_PAIRS = [
    (
        "proxbox_api.schemas.stream_messages",
        "DiscoveryMessage",
        "netbox_proxbox.schemas.backend_proxy",
        "SseDiscoveryPayload",
    ),
    (
        "proxbox_api.schemas.stream_messages",
        "SubstepMessage",
        "netbox_proxbox.schemas.backend_proxy",
        "SseSubstepPayload",
    ),
    (
        "proxbox_api.schemas.stream_messages",
        "ItemProgressMessage",
        "netbox_proxbox.schemas.backend_proxy",
        "SseItemProgressPayload",
    ),
    (
        "proxbox_api.schemas.stream_messages",
        "PhaseSummaryMessage",
        "netbox_proxbox.schemas.backend_proxy",
        "SsePhaseSummaryPayload",
    ),
    (
        "proxbox_api.schemas.stream_messages",
        "ErrorDetailMessage",
        "netbox_proxbox.schemas.backend_proxy",
        "SseErrorDetailPayload",
    ),
]


@pytest.mark.parametrize("src_mod,src_cls,mirror_mod,mirror_cls", _PAYLOAD_PAIRS)
def test_payload_field_coverage(
    src_mod: str, src_cls: str, mirror_mod: str, mirror_cls: str
):
    """Every field present in the proxbox-api payload model must exist in the mirror.

    The mirror may have extra fields (e.g. renamed aliases, defaults). This test asserts
    no proxbox-api field has been dropped — not that the sets are equal.
    """
    src = getattr(importlib.import_module(src_mod), src_cls)
    mirror = getattr(importlib.import_module(mirror_mod), mirror_cls)
    missing = _fields(src) - _fields(mirror)
    assert not missing, (
        f"{mirror_cls} is missing fields that exist in {src_cls}: {missing}"
    )
