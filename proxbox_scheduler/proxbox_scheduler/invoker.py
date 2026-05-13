"""Sync invocation strategies for proxbox-scheduler.

Two concrete invokers are shipped:

* :class:`HttpInvoker` — calls ``GET /full-update/stream`` on proxbox-api and
  consumes the SSE stream until a terminal event, returning success/failure.
  This is the only mode that works for managed-NetBox deployments where the
  scheduler container cannot exec into the NetBox container.

* :class:`ExecInvoker` — runs a subprocess (defaults to
  ``python manage.py proxbox_sync --wait --enqueue-once``). Works when the
  scheduler sidecar shares the NetBox runtime, and benefits from
  ``enqueue_once()`` dedup against any NetBox-side recurring schedule.

Both invokers return an :class:`InvokeResult` so the runner can apply a
uniform error-backoff policy.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Protocol

import requests

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InvokeResult:
    """Outcome of a single sync trigger."""

    success: bool
    detail: str = ""
    exit_code: int | None = None

    @classmethod
    def ok(cls, detail: str = "") -> "InvokeResult":
        return cls(success=True, detail=detail, exit_code=0)

    @classmethod
    def failed(cls, detail: str, exit_code: int | None = None) -> "InvokeResult":
        return cls(success=False, detail=detail, exit_code=exit_code)


class Invoker(Protocol):
    """An invoker is anything callable that triggers one sync run."""

    def trigger(self) -> InvokeResult: ...


_TERMINAL_EVENT_NAMES = {
    "complete",
    "completed",
    "done",
    "finished",
    "error",
    "failed",
    "cancelled",
    "canceled",
}
_FAILURE_EVENT_NAMES = {"error", "failed", "cancelled", "canceled"}


def _parse_sse_event_name(line: str) -> str | None:
    if not line.startswith("event:"):
        return None
    return line.split(":", 1)[1].strip().lower()


class HttpInvoker:
    """Trigger a sync over HTTP/SSE against proxbox-api.

    The scheduler issues a single ``GET /full-update/stream`` request and
    blocks until proxbox-api emits a terminal event. Connection / response
    failures are returned as :class:`InvokeResult.failed`.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        timeout_seconds: float,
        verify_ssl: bool,
        session: requests.Session | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._verify_ssl = verify_ssl
        self._session = session or requests.Session()

    @property
    def stream_url(self) -> str:
        return f"{self._base_url}/full-update/stream"

    def trigger(self) -> InvokeResult:
        headers = {"Accept": "text/event-stream"}
        if self._api_key:
            headers["X-Proxbox-API-Key"] = self._api_key

        try:
            response = self._session.get(
                self.stream_url,
                headers=headers,
                stream=True,
                timeout=self._timeout,
                verify=self._verify_ssl,
            )
        except requests.RequestException as exc:
            return InvokeResult.failed(f"connection error: {exc}")

        if response.status_code != 200:
            try:
                body = response.text[:200]
            except Exception:  # noqa: BLE001
                body = ""
            return InvokeResult.failed(
                f"HTTP {response.status_code} from {self.stream_url}: {body}",
                exit_code=response.status_code,
            )

        last_event: str | None = None
        try:
            for raw_line in response.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                name = _parse_sse_event_name(raw_line)
                if name is None:
                    continue
                last_event = name
                if name in _TERMINAL_EVENT_NAMES:
                    break
        except requests.RequestException as exc:
            return InvokeResult.failed(f"stream interrupted: {exc}")
        finally:
            response.close()

        if last_event is None:
            return InvokeResult.failed("stream closed before any SSE event")
        if last_event in _FAILURE_EVENT_NAMES:
            return InvokeResult.failed(f"sync reported terminal '{last_event}' event")
        return InvokeResult.ok(detail=f"terminal event: {last_event}")


class ExecInvoker:
    """Trigger a sync by running a local subprocess.

    Defaults to ``python manage.py proxbox_sync --wait --enqueue-once``,
    which means the scheduler co-exists safely with any NetBox-side
    recurring ``ScheduleSyncForm`` configuration: a pending job is
    short-circuited and the scheduler's invocation no-ops.
    """

    def __init__(
        self,
        *,
        command: list[str],
        timeout_seconds: float,
        runner: Callable[..., Any] | None = None,
    ) -> None:
        if not command:
            raise ValueError("ExecInvoker requires a non-empty command list")
        self._command = list(command)
        self._timeout = timeout_seconds
        self._runner = runner or subprocess.run

    @property
    def command(self) -> list[str]:
        return list(self._command)

    def trigger(self) -> InvokeResult:
        try:
            completed = self._runner(  # type: ignore[call-arg]
                self._command,
                timeout=self._timeout,
                check=False,
                capture_output=True,
                text=True,
            )
        except subprocess.TimeoutExpired as exc:
            return InvokeResult.failed(
                f"subprocess timed out after {self._timeout}s: {exc}"
            )
        except FileNotFoundError as exc:
            return InvokeResult.failed(f"command not found: {exc}")

        rc = int(getattr(completed, "returncode", 1))
        if rc == 0:
            return InvokeResult.ok(detail="subprocess exited 0")
        stderr = (getattr(completed, "stderr", "") or "").strip()[:500]
        return InvokeResult.failed(
            f"subprocess exited {rc}: {stderr or '<no stderr>'}",
            exit_code=rc,
        )


def build_invoker(config: "SchedulerConfig") -> Invoker:  # noqa: F821 — fwd-ref to config
    """Construct the configured invoker (selected by ``config.invoke``)."""
    if config.invoke == "http":
        if not config.proxbox_api_url:
            raise ValueError("HTTP invoker requires PROXBOX_API_URL")
        return HttpInvoker(
            base_url=config.proxbox_api_url,
            api_key=config.proxbox_api_key,
            timeout_seconds=config.proxbox_api_timeout,
            verify_ssl=config.proxbox_api_verify_ssl,
        )
    if config.invoke == "exec":
        return ExecInvoker(
            command=config.exec_command,
            timeout_seconds=config.proxbox_api_timeout,
        )
    raise ValueError(f"Unknown invoker kind: {config.invoke!r}")
