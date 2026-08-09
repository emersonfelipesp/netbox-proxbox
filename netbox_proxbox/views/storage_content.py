"""Bounded process-wide HTTP fan-out for live storage content reads."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
import json
import socket
import ssl
from threading import BoundedSemaphore, Condition, Event, Lock, Thread
import time
from urllib.parse import urlsplit, urlunsplit

import requests
from urllib3 import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.exceptions import HTTPError as Urllib3HTTPError
from urllib3.response import HTTPResponse
from urllib3.util import Timeout


CONTENT_FETCH_WORKERS = 4
CONTENT_FETCH_THREAD_PREFIX = "proxbox-storage-content"
CONTENT_DEADLINE_THREAD_NAME = "proxbox-storage-content-deadlines"
CONTENT_RESPONSE_MAX_BYTES = 1024 * 1024
CONTENT_STREAM_CHUNK_BYTES = 16 * 1024


class _BoundedContentFetchPool:
    """Keep running and queued work bounded to one slot per actual call."""

    def __init__(self, max_workers: int) -> None:
        self.max_workers = max_workers
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=CONTENT_FETCH_THREAD_PREFIX,
        )
        self._slots = BoundedSemaphore(max_workers)
        self._state_lock = Lock()
        self._slots_in_use = 0

    @property
    def slots_in_use(self) -> int:
        """Return the submitted calls that still own process-wide capacity."""
        with self._state_lock:
            return self._slots_in_use

    def _release_slot(self) -> None:
        with self._state_lock:
            self._slots_in_use -= 1
        self._slots.release()

    def submit(
        self,
        function: Callable[..., object],
        *args: object,
        deadline_at: float,
        wait_for_slot: bool,
        **kwargs: object,
    ) -> Future[object] | None:
        """Submit only after reserving capacity, optionally until a deadline."""
        remaining = deadline_at - time.monotonic()
        if remaining <= 0:
            return None
        if wait_for_slot:
            acquired = self._slots.acquire(timeout=remaining)
        else:
            acquired = self._slots.acquire(blocking=False)
        if not acquired:
            return None
        if time.monotonic() >= deadline_at:
            self._slots.release()
            return None

        with self._state_lock:
            self._slots_in_use += 1

        def run_with_slot() -> object:
            try:
                return function(*args, **kwargs)
            finally:
                self._release_slot()

        try:
            return self._executor.submit(run_with_slot)
        except BaseException:
            self._release_slot()
            raise


_CONTENT_FETCH_POOL = _BoundedContentFetchPool(CONTENT_FETCH_WORKERS)


def _shutdown_socket(cancel_socket: socket.socket) -> None:
    """Interrupt socket I/O using only non-buffered transport operations."""
    try:
        cancel_socket.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        cancel_socket.close()
    except OSError:
        pass


class _DeadlineCancellation:
    """Own a duplicate socket that can cancel one in-flight request."""

    def __init__(self) -> None:
        self.expired = Event()
        self._lock = Lock()
        self._cancel_socket: socket.socket | None = None

    def attach_socket(self, connected_socket: socket.socket) -> None:
        """Retain a duplicate before urllib3 starts TLS or reads headers."""
        try:
            cancel_socket = connected_socket.dup()
        except OSError:
            _shutdown_socket(connected_socket)
            raise

        shutdown_now = False
        previous_socket = None
        with self._lock:
            if self.expired.is_set():
                shutdown_now = True
            else:
                previous_socket = self._cancel_socket
                self._cancel_socket = cancel_socket
        if previous_socket is not None:
            previous_socket.close()
        if shutdown_now:
            _shutdown_socket(cancel_socket)

    def expire(self) -> None:
        """Interrupt the transport without touching buffered response objects."""
        self.expired.set()
        with self._lock:
            cancel_socket = self._cancel_socket
            self._cancel_socket = None
        if cancel_socket is not None:
            _shutdown_socket(cancel_socket)

    def release(self) -> None:
        """Discard the duplicate without disturbing a completed request."""
        with self._lock:
            cancel_socket = self._cancel_socket
            self._cancel_socket = None
        if cancel_socket is not None:
            cancel_socket.close()


class _DeadlineHTTPConnection(HTTPConnection):
    """Expose a connected HTTP socket before response headers are read."""

    def __init__(
        self,
        *args: object,
        deadline_cancellation: _DeadlineCancellation,
        **kwargs: object,
    ) -> None:
        self._deadline_cancellation = deadline_cancellation
        super().__init__(*args, **kwargs)

    def _new_conn(self) -> socket.socket:
        connected_socket = super()._new_conn()
        self._deadline_cancellation.attach_socket(connected_socket)
        return connected_socket


class _DeadlineHTTPSConnection(HTTPSConnection):
    """Expose the TCP socket before TLS and response-header reads."""

    def __init__(
        self,
        *args: object,
        deadline_cancellation: _DeadlineCancellation,
        **kwargs: object,
    ) -> None:
        self._deadline_cancellation = deadline_cancellation
        super().__init__(*args, **kwargs)

    def _new_conn(self) -> socket.socket:
        connected_socket = super()._new_conn()
        self._deadline_cancellation.attach_socket(connected_socket)
        return connected_socket


class _DeadlineHTTPConnectionPool(HTTPConnectionPool):
    ConnectionCls = _DeadlineHTTPConnection


class _DeadlineHTTPSConnectionPool(HTTPSConnectionPool):
    ConnectionCls = _DeadlineHTTPSConnection


class _SocketDeadlineWatchdog:
    """Expire every active transport from one process-wide watchdog thread."""

    def __init__(self) -> None:
        self._condition = Condition()
        self._entries: dict[int, tuple[float, _DeadlineCancellation]] = {}
        self._next_token = 0
        self._thread: Thread | None = None

    def register(self, deadline_at: float) -> tuple[int, _DeadlineCancellation]:
        cancellation = _DeadlineCancellation()
        with self._condition:
            token = self._next_token
            self._next_token += 1
            self._entries[token] = (deadline_at, cancellation)
            if self._thread is None:
                self._thread = Thread(
                    target=self._run,
                    name=CONTENT_DEADLINE_THREAD_NAME,
                    daemon=True,
                )
                self._thread.start()
            self._condition.notify()
        return token, cancellation

    def unregister(self, token: int) -> None:
        with self._condition:
            entry = self._entries.pop(token, None)
            self._condition.notify()
        if entry is not None:
            _deadline_at, cancellation = entry
            cancellation.release()

    def _run(self) -> None:
        while True:
            with self._condition:
                while not self._entries:
                    self._condition.wait()
                token, (deadline_at, cancellation) = min(
                    self._entries.items(),
                    key=lambda item: item[1][0],
                )
                remaining = deadline_at - time.monotonic()
                if remaining > 0:
                    self._condition.wait(timeout=remaining)
                    continue
                self._entries.pop(token, None)

            cancellation.expire()


_SOCKET_DEADLINE_WATCHDOG = _SocketDeadlineWatchdog()


def collect_completed_before_deadline(
    items: Sequence[object],
    fetch_one: Callable[[object, float], object],
    *,
    deadline_seconds: float,
    max_items: int,
    per_request_workers: int,
) -> tuple[list[Future[object]], int, int]:
    """Return only work completed by one page deadline without abandoning slots."""
    total_count = len(items)
    selected_items = list(items[: max(1, int(max_items))])
    selected_count = len(selected_items)
    if not selected_items:
        return [], total_count, selected_count

    worker_count = max(
        1,
        min(
            int(per_request_workers),
            CONTENT_FETCH_WORKERS,
            selected_count,
        ),
    )
    deadline_at = time.monotonic() + max(0.0, float(deadline_seconds))
    pending: set[Future[object]] = set()
    completed: list[Future[object]] = []
    next_item_index = 0

    def submit_next(*, wait_for_slot: bool) -> bool:
        nonlocal next_item_index
        if next_item_index >= selected_count:
            return False
        item = selected_items[next_item_index]
        future = _CONTENT_FETCH_POOL.submit(
            fetch_one,
            item,
            deadline_at,
            deadline_at=deadline_at,
            wait_for_slot=wait_for_slot,
        )
        if future is None:
            return False
        next_item_index += 1
        pending.add(future)
        return True

    while len(pending) < worker_count and submit_next(wait_for_slot=False):
        pass

    while pending or next_item_index < selected_count:
        remaining = deadline_at - time.monotonic()
        if remaining <= 0:
            break

        if not pending:
            if not submit_next(wait_for_slot=True):
                break
            continue

        finished, _unfinished = wait(
            tuple(pending),
            timeout=remaining,
            return_when=FIRST_COMPLETED,
        )
        if not finished:
            break
        for future in finished:
            pending.remove(future)
            completed.append(future)

        while len(pending) < worker_count and submit_next(wait_for_slot=False):
            pass

    return completed, total_count, selected_count


def format_content_detail(
    *,
    successful_nodes: int,
    selected_node_count: int,
    total_node_count: int,
    deadline_seconds: float,
    request_limit: int,
) -> str | None:
    """Build the existing partial/truncation notice for the detail template."""
    details = []
    if successful_nodes != selected_node_count:
        details.append(
            "Storage content is partial: "
            f"{successful_nodes} of {selected_node_count} node requests "
            f"completed within the {deadline_seconds:g}-second deadline."
        )
    if total_node_count > selected_node_count:
        details.append(
            "Storage content is truncated to the first "
            f"{selected_node_count} of {total_node_count} nodes (per-page "
            f"request limit {request_limit})."
        )
    return " ".join(details) or None


def _prepare_deadline_pool(
    *,
    url: str,
    query_params: dict[str, str] | None,
    auth_headers: dict[str, str],
    verify_ssl: bool,
    socket_timeout: float,
    cancellation: _DeadlineCancellation,
) -> tuple[
    HTTPConnectionPool | HTTPSConnectionPool,
    str,
    dict[str, str],
    str,
]:
    """Build a one-request pool whose connection exposes its live socket."""
    prepared = requests.Request(
        method="GET",
        url=url,
        params=query_params or None,
        headers=auth_headers,
    ).prepare()
    if prepared.url is None:
        raise requests.exceptions.InvalidURL("storage content URL is missing")

    try:
        parsed = urlsplit(prepared.url)
        port = parsed.port
    except ValueError as exc:
        raise requests.exceptions.InvalidURL("storage content URL is invalid") from exc
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or parsed.hostname is None:
        raise requests.exceptions.InvalidURL("storage content URL is invalid")

    timeout = Timeout(connect=socket_timeout, read=socket_timeout)
    common_options = {
        "host": parsed.hostname,
        "port": port,
        "timeout": timeout,
        "maxsize": 1,
        "block": True,
        "deadline_cancellation": cancellation,
    }
    if scheme == "https":
        pool: HTTPConnectionPool | HTTPSConnectionPool = _DeadlineHTTPSConnectionPool(
            **common_options,
            cert_reqs=ssl.CERT_REQUIRED if verify_ssl else ssl.CERT_NONE,
            ca_certs=requests.certs.where() if verify_ssl else None,
        )
    else:
        pool = _DeadlineHTTPConnectionPool(**common_options)

    request_target = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
    return pool, request_target, dict(prepared.headers), prepared.url


def fetch_json_with_limits(
    *,
    url: str,
    query_params: dict[str, str] | None,
    auth_headers: dict[str, str],
    verify_ssl: bool,
    request_timeout: float,
    deadline_at: float,
    max_response_bytes: int,
) -> object:
    """Stream one JSON response under absolute time and decoded-size ceilings."""
    remaining = deadline_at - time.monotonic()
    if remaining <= 0:
        raise requests.exceptions.Timeout("storage content deadline expired")
    socket_timeout = max(0.001, min(float(request_timeout), remaining))
    deadline_token, cancellation = _SOCKET_DEADLINE_WATCHDOG.register(deadline_at)
    pool: HTTPConnectionPool | HTTPSConnectionPool | None = None
    response: HTTPResponse | None = None
    try:
        pool, request_target, prepared_headers, prepared_url = _prepare_deadline_pool(
            url=url,
            query_params=query_params,
            auth_headers=auth_headers,
            verify_ssl=verify_ssl,
            socket_timeout=socket_timeout,
            cancellation=cancellation,
        )
        response = pool.urlopen(
            "GET",
            request_target,
            headers=prepared_headers,
            retries=False,
            redirect=False,
            timeout=pool.timeout,
            preload_content=False,
            decode_content=False,
            release_conn=False,
        )
        if cancellation.expired.is_set() or time.monotonic() >= deadline_at:
            raise requests.exceptions.Timeout(
                "storage content wall-clock deadline expired"
            )
        if 400 <= response.status:
            raise requests.exceptions.HTTPError(
                f"storage content request returned HTTP {response.status}",
                request=requests.Request("GET", prepared_url).prepare(),
            )

        response_limit = max(1, int(max_response_bytes))
        body = bytearray()
        for chunk in response.stream(
            CONTENT_STREAM_CHUNK_BYTES,
            decode_content=True,
        ):
            if cancellation.expired.is_set() or time.monotonic() >= deadline_at:
                raise requests.exceptions.Timeout(
                    "storage content wall-clock deadline expired"
                )
            if not chunk:
                continue
            next_size = len(body) + len(chunk)
            if next_size > response_limit:
                raise ValueError(
                    f"storage content response exceeds the {response_limit}-byte limit"
                )
            body.extend(chunk)

        if cancellation.expired.is_set() or time.monotonic() >= deadline_at:
            raise requests.exceptions.Timeout(
                "storage content wall-clock deadline expired"
            )
        try:
            return json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("storage content response is not valid JSON") from exc
    except requests.exceptions.RequestException:
        raise
    except (Urllib3HTTPError, OSError) as exc:
        if cancellation.expired.is_set() or time.monotonic() >= deadline_at:
            raise requests.exceptions.Timeout(
                "storage content wall-clock deadline expired"
            ) from exc
        raise requests.exceptions.ConnectionError(
            "storage content request failed"
        ) from exc
    finally:
        _SOCKET_DEADLINE_WATCHDOG.unregister(deadline_token)
        if response is not None:
            response.close()
        if pool is not None:
            pool.close()
