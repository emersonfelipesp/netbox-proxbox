"""Bounded process-wide HTTP fan-out for live storage content reads."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
import json
from threading import BoundedSemaphore, Condition, Event, Lock, Thread
import time

import requests


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


class _ResponseDeadlineCloser:
    """Close every active response from one process-wide watchdog thread."""

    def __init__(self) -> None:
        self._condition = Condition()
        self._entries: dict[int, tuple[float, object, Event]] = {}
        self._next_token = 0
        self._thread: Thread | None = None

    def register(self, response: object, deadline_at: float) -> tuple[int, Event]:
        expired = Event()
        with self._condition:
            token = self._next_token
            self._next_token += 1
            self._entries[token] = (deadline_at, response, expired)
            if self._thread is None:
                self._thread = Thread(
                    target=self._run,
                    name=CONTENT_DEADLINE_THREAD_NAME,
                    daemon=True,
                )
                self._thread.start()
            self._condition.notify()
        return token, expired

    def unregister(self, token: int) -> None:
        with self._condition:
            self._entries.pop(token, None)
            self._condition.notify()

    def _run(self) -> None:
        while True:
            with self._condition:
                while not self._entries:
                    self._condition.wait()
                token, (deadline_at, response, expired) = min(
                    self._entries.items(),
                    key=lambda item: item[1][0],
                )
                remaining = deadline_at - time.monotonic()
                if remaining > 0:
                    self._condition.wait(timeout=remaining)
                    continue
                self._entries.pop(token, None)

            expired.set()
            try:
                response.close()
            except Exception:
                continue


_RESPONSE_DEADLINE_CLOSER = _ResponseDeadlineCloser()


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
    response = requests.get(
        url,
        params=query_params or None,
        headers=auth_headers,
        verify=verify_ssl,
        timeout=socket_timeout,
        stream=True,
        allow_redirects=False,
    )
    remaining = deadline_at - time.monotonic()
    if remaining <= 0:
        response.close()
        raise requests.exceptions.Timeout("storage content deadline expired")
    deadline_token, expired = _RESPONSE_DEADLINE_CLOSER.register(
        response,
        deadline_at,
    )

    response_limit = max(1, int(max_response_bytes))
    body = bytearray()
    try:
        response.raise_for_status()
        for chunk in response.iter_content(chunk_size=CONTENT_STREAM_CHUNK_BYTES):
            if expired.is_set() or time.monotonic() >= deadline_at:
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

        if expired.is_set() or time.monotonic() >= deadline_at:
            raise requests.exceptions.Timeout(
                "storage content wall-clock deadline expired"
            )
        try:
            return json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("storage content response is not valid JSON") from exc
    finally:
        _RESPONSE_DEADLINE_CLOSER.unregister(deadline_token)
        response.close()
