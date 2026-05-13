"""Invoker tests — HTTP and exec, with no live proxbox-api required."""

from __future__ import annotations

import subprocess
from dataclasses import replace
from typing import Iterator

import pytest
import requests

from proxbox_scheduler.config import SchedulerConfig
from proxbox_scheduler.invoker import (
    ExecInvoker,
    HttpInvoker,
    InvokeResult,
    build_invoker,
)


class _FakeResponse:
    def __init__(self, *, status_code: int, lines: list[str]) -> None:
        self.status_code = status_code
        self._lines = lines
        self.text = "\n".join(lines)
        self.closed = False

    def iter_lines(self, decode_unicode: bool = False) -> Iterator[str]:
        for line in self._lines:
            yield line

    def close(self) -> None:
        self.closed = True


class _FakeSession:
    def __init__(self, response: _FakeResponse | Exception) -> None:
        self._response = response
        self.requests: list[tuple[str, dict[str, str], dict[str, object]]] = []

    def get(self, url: str, **kwargs: object) -> _FakeResponse:
        headers = kwargs.get("headers") or {}
        self.requests.append((url, dict(headers), dict(kwargs)))
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class TestHttpInvoker:
    def test_terminal_complete_event_succeeds(self) -> None:
        response = _FakeResponse(
            status_code=200,
            lines=[
                "event: progress",
                "data: {}",
                "",
                "event: complete",
                "data: {}",
                "",
            ],
        )
        session = _FakeSession(response)
        inv = HttpInvoker(
            base_url="http://proxbox-api.test",
            api_key="abc",
            timeout_seconds=5,
            verify_ssl=False,
            session=session,  # type: ignore[arg-type]
        )

        result = inv.trigger()

        assert result.success is True
        assert "complete" in result.detail
        url, headers, _ = session.requests[0]
        assert url == "http://proxbox-api.test/full-update/stream"
        assert headers["X-Proxbox-API-Key"] == "abc"
        assert headers["Accept"] == "text/event-stream"
        assert response.closed is True

    def test_terminal_error_event_fails(self) -> None:
        response = _FakeResponse(
            status_code=200,
            lines=["event: progress", "data: {}", "", "event: error", "data: boom", ""],
        )
        inv = HttpInvoker(
            base_url="http://x.test",
            api_key=None,
            timeout_seconds=5,
            verify_ssl=True,
            session=_FakeSession(response),  # type: ignore[arg-type]
        )

        result = inv.trigger()

        assert result.success is False
        assert "error" in result.detail

    def test_http_error_status_fails(self) -> None:
        response = _FakeResponse(status_code=500, lines=["upstream blew up"])
        inv = HttpInvoker(
            base_url="http://x.test",
            api_key=None,
            timeout_seconds=5,
            verify_ssl=True,
            session=_FakeSession(response),  # type: ignore[arg-type]
        )

        result = inv.trigger()

        assert result.success is False
        assert "HTTP 500" in result.detail
        assert result.exit_code == 500

    def test_connection_error_fails_gracefully(self) -> None:
        session = _FakeSession(requests.ConnectionError("refused"))
        inv = HttpInvoker(
            base_url="http://x.test",
            api_key=None,
            timeout_seconds=5,
            verify_ssl=True,
            session=session,  # type: ignore[arg-type]
        )

        result = inv.trigger()

        assert result.success is False
        assert "connection" in result.detail.lower()

    def test_stream_without_terminal_event_fails(self) -> None:
        response = _FakeResponse(
            status_code=200,
            lines=["", ""],  # no events
        )
        inv = HttpInvoker(
            base_url="http://x.test",
            api_key=None,
            timeout_seconds=5,
            verify_ssl=True,
            session=_FakeSession(response),  # type: ignore[arg-type]
        )

        result = inv.trigger()

        assert result.success is False
        assert "before any SSE event" in result.detail

    def test_omits_api_key_header_when_missing(self) -> None:
        response = _FakeResponse(
            status_code=200, lines=["event: completed", "data: {}", ""]
        )
        session = _FakeSession(response)
        inv = HttpInvoker(
            base_url="http://x.test",
            api_key=None,
            timeout_seconds=5,
            verify_ssl=True,
            session=session,  # type: ignore[arg-type]
        )

        inv.trigger()

        _, headers, _ = session.requests[0]
        assert "X-Proxbox-API-Key" not in headers


class _FakeCompleted:
    def __init__(self, returncode: int, stderr: str = "") -> None:
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = ""


class TestExecInvoker:
    def test_zero_exit_succeeds(self) -> None:
        calls: list[list[str]] = []

        def runner(cmd: list[str], **kwargs: object) -> _FakeCompleted:
            calls.append(cmd)
            return _FakeCompleted(returncode=0)

        inv = ExecInvoker(command=["echo", "ok"], timeout_seconds=5, runner=runner)
        result = inv.trigger()

        assert result.success is True
        assert calls == [["echo", "ok"]]

    def test_nonzero_exit_fails(self) -> None:
        def runner(cmd: list[str], **kwargs: object) -> _FakeCompleted:
            return _FakeCompleted(returncode=2, stderr="bad config")

        inv = ExecInvoker(
            command=["python", "manage.py", "proxbox_sync"],
            timeout_seconds=5,
            runner=runner,
        )
        result = inv.trigger()

        assert result.success is False
        assert result.exit_code == 2
        assert "bad config" in result.detail

    def test_timeout_returns_failed_result(self) -> None:
        def runner(cmd: list[str], **kwargs: object) -> _FakeCompleted:
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=1)

        inv = ExecInvoker(command=["sleep", "10"], timeout_seconds=1, runner=runner)
        result = inv.trigger()

        assert result.success is False
        assert "timed out" in result.detail

    def test_file_not_found_returns_failed_result(self) -> None:
        def runner(cmd: list[str], **kwargs: object) -> _FakeCompleted:
            raise FileNotFoundError(2, "no such file or directory", cmd[0])

        inv = ExecInvoker(command=["nope"], timeout_seconds=5, runner=runner)
        result = inv.trigger()

        assert result.success is False
        assert "not found" in result.detail.lower()

    def test_empty_command_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ExecInvoker(command=[], timeout_seconds=5)


class TestBuildInvoker:
    def test_http_invoker_built(self, base_config: SchedulerConfig) -> None:
        inv = build_invoker(base_config)
        assert isinstance(inv, HttpInvoker)

    def test_exec_invoker_built(self, base_config: SchedulerConfig) -> None:
        config = replace(base_config, invoke="exec")
        inv = build_invoker(config)
        assert isinstance(inv, ExecInvoker)

    def test_http_invoker_requires_url(self, base_config: SchedulerConfig) -> None:
        config = replace(base_config, proxbox_api_url=None)
        with pytest.raises(ValueError, match="PROXBOX_API_URL"):
            build_invoker(config)


def test_invoke_result_helpers() -> None:
    ok = InvokeResult.ok("yay")
    fail = InvokeResult.failed("nope", exit_code=7)
    assert ok.success is True
    assert ok.exit_code == 0
    assert fail.success is False
    assert fail.exit_code == 7
