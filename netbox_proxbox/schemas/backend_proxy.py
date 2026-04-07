"""Pydantic V2 schemas for ProxBox FastAPI backend proxy payloads."""

from __future__ import annotations

from collections.abc import Iterator
from pydantic import Field

from netbox_proxbox.schemas._base import ProxboxBaseModel, ProxboxLenientModel


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


class SseErrorPayload(ProxboxBaseModel):
    """Payload of an ``error`` SSE event."""

    step: str = "stream"
    status: str = "failed"
    error: str = ""
