"""Pydantic V2 schemas for ProxBox FastAPI backend proxy payloads."""

from collections.abc import Iterator
from enum import Enum
from pydantic import Field

from netbox_proxbox.schemas._base import ProxboxBaseModel, ProxboxLenientModel


class SseEventType(str, Enum):
    """All SSE event names emitted by proxbox-api sync streams.

    Mirrors ``proxbox_api.schemas.stream_messages.StreamMessageType`` plus the
    terminal transport events. Keep in sync with proxbox-api's stream_messages.py.
    """

    # Terminal events
    COMPLETE = "complete"
    ERROR = "error"
    STEP = "step"
    # Structured progress events
    DISCOVERY = "discovery"
    SUBSTEP = "substep"
    ITEM_PROGRESS = "item_progress"
    PHASE_SUMMARY = "phase_summary"
    ERROR_DETAIL = "error_detail"
    PROGRESS = "progress"
    # Bootstrap status frame emitted as the first frame of each sync run
    BOOTSTRAP_DONE = "bootstrap_done"
    DUPLICATE_NAME_RESOLVED = "duplicate_name_resolved"
    HARDWARE_DISCOVERY = "hardware_discovery"
    # Migrate verb SSE channel (operational-verbs.md §7.1) — emitted on
    # /proxmox/{vm_type}/{vmid}/migrate/{task_upid}/stream by proxbox-api
    # 0.0.12; mirrored here so the test_sse_schema_mirror canary catches
    # any drift in either direction.
    MIGRATE_DISPATCHED = "migrate_dispatched"
    MIGRATE_PROGRESS = "migrate_progress"
    MIGRATE_SUCCEEDED = "migrate_succeeded"
    MIGRATE_FAILED = "migrate_failed"


# ---------------------------------------------------------------------------
# Structured event payload schemas
# Mirror of proxbox_api.schemas.stream_messages — kept in sync manually.
# These are used for type-safe parsing of the rich progress events.
# ---------------------------------------------------------------------------


class SseProgressInfo(ProxboxLenientModel):
    """Progress tracking. Mirrors proxbox_api ProgressInfo."""

    current: int = 0
    total: int = 0
    percent: float = 0.0


class SseTimingInfo(ProxboxLenientModel):
    """Timing information. Mirrors proxbox_api TimingInfo."""

    elapsed_ms: int | None = None
    started_at: str | None = None
    finished_at: str | None = None


class SseItemInfo(ProxboxLenientModel):
    """Item being synced. Mirrors proxbox_api ItemInfo."""

    name: str
    netbox_id: int | None = None
    netbox_url: str | None = None
    item_type: str | None = None
    extra: dict[str, object] | None = None


class SseDiscoveryPayload(ProxboxLenientModel):
    """Payload of a ``discovery`` event. Mirrors proxbox_api DiscoveryMessage."""

    event: str = SseEventType.DISCOVERY
    phase: str = ""
    status: str = "discovered"
    message: str = ""
    count: int = 0
    items: list[SseItemInfo] = Field(default_factory=list)
    progress: SseProgressInfo | None = None
    metadata: dict[str, object] | None = None


class SseSubstepPayload(ProxboxLenientModel):
    """Payload of a ``substep`` event. Mirrors proxbox_api SubstepMessage."""

    event: str = SseEventType.SUBSTEP
    phase: str = ""
    substep: str = ""
    status: str = ""
    message: str = ""
    item: SseItemInfo | None = None
    timing: SseTimingInfo | None = None
    result: dict[str, object] | None = None


class SseItemProgressPayload(ProxboxLenientModel):
    """Payload of an ``item_progress`` event. Mirrors proxbox_api ItemProgressMessage."""

    event: str = SseEventType.ITEM_PROGRESS
    phase: str = ""
    status: str = ""
    message: str = ""
    item: SseItemInfo | None = None
    operation: str = ""
    progress: SseProgressInfo = Field(default_factory=SseProgressInfo)
    timing: SseTimingInfo | None = None
    error: str | None = None
    warning: str | None = None


class SsePhaseSummaryPayload(ProxboxLenientModel):
    """Payload of a ``phase_summary`` event. Mirrors proxbox_api PhaseSummaryMessage."""

    event: str = SseEventType.PHASE_SUMMARY
    phase: str = ""
    status: str = "completed"
    message: str = ""
    result: dict[str, int] = Field(default_factory=dict)
    timing: SseTimingInfo | None = None


class SseErrorDetailPayload(ProxboxLenientModel):
    """Payload of an ``error_detail`` event. Mirrors proxbox_api ErrorDetailMessage."""

    event: str = SseEventType.ERROR_DETAIL
    phase: str | None = None
    item: SseItemInfo | None = None
    category: str = "unknown"
    message: str = ""
    detail: str | None = None
    suggestion: str | None = None
    traceback: str | None = None


class SseDuplicateNameResolvedPayload(ProxboxLenientModel):
    """Payload of a ``duplicate_name_resolved`` event.

    Mirrors proxbox_api DuplicateNameResolvedMessage. Emitted once per VM
    whose name collided with another VM in the same NetBox cluster (suffix
    applied) or whose NetBox record was manually renamed by an operator
    (``operator_renamed=True``, no rename performed).
    """

    event: str = SseEventType.DUPLICATE_NAME_RESOLVED
    cluster: str = ""
    original_name: str = ""
    resolved_name: str = ""
    vmid: int = 0
    suffix_index: int = 1
    operator_renamed: bool = False


class SseHardwareDiscoveryPayload(ProxboxLenientModel):
    """Payload of a ``hardware_discovery`` event from newer proxbox-api builds."""

    event: str = SseEventType.HARDWARE_DISCOVERY
    node: str = ""
    cluster: str | None = None
    chassis_serial: str | None = None
    chassis_manufacturer: str | None = None
    chassis_product: str | None = None
    nic_count: int = 0
    duration_ms: int | None = None


class FastAPIUrlDict(ProxboxBaseModel):
    """Resolved HTTP/WebSocket URLs and TLS flag for a FastAPI endpoint.

    Replaces the ``FastAPIUrlDict`` TypedDict in ``type_defs.py``.
    Note: ``domain`` and ``ip_address`` are stored as strings here; the raw Django
    model values are stringified before construction.
    """

    domain: str | None = None
    ip_address: str | None = None
    ip_address_url: str = ""
    http_url: str = ""
    websocket_url: str = ""
    verify_ssl: bool = False


class BackendRequestContext(ProxboxBaseModel):
    """Resolved connection parameters for ProxBox FastAPI backend HTTP calls.

    Replaces the ``BackendRequestContext`` TypedDict in ``type_defs.py``.
    """

    detail: dict[str, object] = Field(default_factory=dict)
    endpoint_id: int | None = None
    target_fingerprint: str = ""
    http_url: str | None = None
    ip_address_url: str | None = None
    verify_ssl: bool = True
    headers: dict[str, str] = Field(default_factory=dict)


class SseFrame(ProxboxLenientModel):
    """Parsed SSE frame carrying event name and raw JSON data."""

    event: str = "message"
    data: dict[str, object] = Field(default_factory=dict)

    def __iter__(self) -> Iterator[object]:
        yield self.event
        yield self.data

    def __getitem__(self, index: int) -> object:
        if index == 0:
            return self.event
        if index == 1:
            return self.data
        raise IndexError(index)

    def __len__(self) -> int:
        return 2


class SseCompletePayload(ProxboxLenientModel):
    """Payload of a terminal ``complete`` SSE event from a proxbox-api sync stream."""

    ok: bool = True
    message: str | None = None
    result: dict[str, object] | list[object] | None = None
    errors: list[dict[str, object]] = Field(default_factory=list)

    @property
    def first_error_detail(self) -> str | None:
        """Handle first error detail."""
        if self.errors:
            first = self.errors[0]
            detail = first.get("detail")
            return str(detail) if detail else None
        return None


class SseErrorPayload(ProxboxLenientModel):
    """Payload of an ``error`` SSE event."""

    step: str = "stream"
    status: str = "failed"
    error: str = ""
