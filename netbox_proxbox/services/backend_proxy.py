"""HTTP and SSE proxy helpers for the external ProxBox FastAPI backend."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Generator, Iterable

import requests
from pydantic import ValidationError

from netbox_proxbox.schemas.backend_proxy import (
    BackendRequestContext,
    SseCompletePayload,
    SseErrorPayload,
    SseFrame,
)
from netbox_proxbox.services.backend_auth import (
    http_timeout_for_sync_path,
    wait_for_backend_ready,
)
from netbox_proxbox.services.backend_context import (
    _build_request_candidates,
    _handle_auth_registration_and_retry,
    get_fastapi_request_context,
)
from netbox_proxbox.views.error_utils import (
    extract_backend_error_detail,
    parse_requests_response_json,
)

logger = logging.getLogger(__name__)

_SYNC_STREAM_READ_TIMEOUT = (5, 3600)


def sse_error_frames(
    message: str, *, final_message: str = "Stream request failed."
) -> Generator[str, None, None]:
    """Yield SSE error and complete events for stream consumers."""
    yield "event: error\n"
    yield (
        "data: "
        f"{SseErrorPayload(step='stream', status='failed', error=message).model_dump_json()}\n\n"
    )
    yield "event: complete\n"
    yield f"data: {SseCompletePayload(ok=False, message=final_message).model_dump_json()}\n\n"


def _iter_sse_frames(
    line_iter: Iterable[str | bytes | None],
) -> Generator[SseFrame, None, None]:
    """Parse newline-delimited SSE from ``iter_lines``-style input into (event, data_dict) pairs."""
    event_name = ""
    data_lines: list[str] = []

    def flush() -> Generator[SseFrame, None, None]:
        nonlocal event_name, data_lines
        if not data_lines:
            event_name = ""
            return
        payload_str = "\n".join(data_lines)
        try:
            data_obj = json.loads(payload_str)
        except json.JSONDecodeError:
            data_obj = {"raw": payload_str}
        ev = event_name or "message"
        if not isinstance(data_obj, dict):
            data_obj = {"raw": data_obj}
        yield SseFrame(event=ev, data=data_obj)
        event_name = ""
        data_lines = []

    for raw in line_iter:
        if raw is None:
            continue
        line = (
            raw.decode("utf-8", errors="replace")
            if isinstance(raw, bytes)
            else str(raw)
        )
        if line == "":
            yield from flush()
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            yield from flush()
            event_name = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
        else:
            data_lines.append(line)

    yield from flush()


def _consume_sse_until_complete(
    response: requests.Response,
    *,
    on_frame: Callable[[str, dict[str, object]], None] | None = None,
) -> tuple[dict[str, object], int]:
    """Read an SSE body to the final ``complete`` event; return (payload, http_status_hint)."""
    last_complete: SseCompletePayload | None = None
    try:
        for frame in _iter_sse_frames(response.iter_lines(decode_unicode=True)):
            _event = frame.event
            data = frame.data
            if on_frame is not None:
                on_frame(_event, data)
            if _event == "complete":
                try:
                    last_complete = SseCompletePayload.model_validate(data)
                except ValidationError as exc:
                    return {
                        "stream": True,
                        "detail": (
                            "ProxBox backend stream sent an invalid complete event: "
                            f"{exc.errors()[0].get('msg', str(exc))}"
                        ),
                    }, 502
    except requests.exceptions.RequestException as exc:
        detail, _ = extract_backend_error_detail(exc)
        return {
            "stream": True,
            "detail": detail,
        }, 502

    if last_complete is None:
        return {
            "stream": True,
            "detail": "ProxBox backend stream ended without a complete event.",
        }, 502

    if last_complete.ok is False:
        msg = last_complete.message or "Sync failed."
        if last_complete.errors:
            first_error = last_complete.errors[0]
            if first_error.get("detail"):
                msg = str(first_error["detail"])
        return {
            "stream": True,
            "detail": msg,
            "response": last_complete.model_dump(),
        }, 503

    return {
        "stream": True,
        "response": last_complete.model_dump(),
    }, 200


def request_backend_resource(
    context: BackendRequestContext,
    path: str,
    query_params: dict[str, str] | None = None,
    *,
    timeout: float | tuple[int, int] = 5,
) -> tuple[dict[str, object], int]:
    """GET a JSON resource from the backend, trying primary URL then IP fallback."""
    http_url = context.http_url
    if not http_url:
        return {
            "queued": False,
            "path": path,
            "requested_urls": [],
            "detail": "No FastAPI URL found.",
        }, 503

    verify_ssl = bool(context.verify_ssl)
    backend_headers = context.headers or {}
    requested_urls: list[str] = []

    request_candidates = _build_request_candidates(
        http_url, context.ip_address_url, path, verify_ssl
    )

    last_detail = None
    auth_register_attempted = False

    for url, verify in request_candidates:
        requested_urls.append(url)

        try:
            response = requests.get(
                url,
                params=query_params,
                headers=backend_headers,
                verify=verify,
                timeout=timeout,
            )
        except requests.exceptions.RequestException as exc:
            last_detail, _ = extract_backend_error_detail(exc)
            logger.error("Sync request failed for %s via %s: %s", path, url, exc)
            if getattr(exc, "response", None) is not None:
                break
            continue
        except (KeyboardInterrupt, SystemExit, GeneratorExit):
            raise
        except OSError as exc:
            last_detail = str(exc)
            logger.error("Unexpected sync error for %s via %s: %s", path, url, exc)
            continue

        if response.status_code >= 400:
            last_detail = f"HTTP {response.status_code}"
            payload, json_err = parse_requests_response_json(
                response, log_label=f"sync:{path}"
            )
            if not json_err and isinstance(payload, dict):
                d = payload.get("detail") or payload.get("message")
                if d:
                    last_detail = str(d)
                if (
                    not auth_register_attempted
                    and response.status_code == 401
                    and "API key" in str(d)
                ):
                    auth_register_attempted = True
                    new_headers, should_retry = _handle_auth_registration_and_retry(
                        backend_headers
                    )
                    if should_retry:
                        backend_headers = new_headers
                        continue
            logger.error(
                "Sync request failed for %s via %s: %s",
                path,
                url,
                last_detail,
            )
            if response.status_code < 500:
                break
            continue

        payload, json_err = parse_requests_response_json(
            response, log_label=f"sync:{path}"
        )
        if json_err:
            last_detail = json_err
            logger.error(
                "Sync request returned non-JSON for %s via %s: %s",
                path,
                url,
                json_err,
            )
            continue

        return {
            "queued": True,
            "path": path,
            "requested_urls": requested_urls,
            "response": payload,
        }, 202

    return {
        "queued": False,
        "path": path,
        "requested_urls": requested_urls,
        "detail": last_detail or "Unable to reach the ProxBox backend.",
    }, 503


def run_sync_stream(
    path: str,
    query_params: dict[str, str] | None = None,
    *,
    on_frame: Callable[[str, dict[str, object]], None] | None = None,
    endpoint_id: int | None = None,
) -> tuple[dict[str, object], int]:
    """GET a backend SSE sync URL to completion (for NetBox background jobs).

    ``path`` must be the stream route (e.g. ``full-update/stream`` or
    ``dcim/devices/create/stream``). Uses the same URL fallback as
    :func:`iter_backend_sse_lines` and a long read timeout.
    """
    if endpoint_id is None:
        context = get_fastapi_request_context()
    else:
        context = get_fastapi_request_context(endpoint_id=endpoint_id)
    if context is None or not context.http_url:
        return {"stream": False, "detail": "No FastAPI URL found."}, 404

    ready, ready_msg = wait_for_backend_ready(context)
    if not ready:
        logger.error("Backend not ready: %s", ready_msg)
        return {"stream": False, "detail": f"Backend not ready: {ready_msg}"}, 503

    verify_ssl = bool(context.verify_ssl)
    request_candidates = _build_request_candidates(
        context.http_url, context.ip_address_url, path, verify_ssl
    )

    backend_headers = context.headers or {}
    requested_urls: list[str] = []
    last_detail: str | None = None
    last_http_status: int | None = None

    for url, verify in request_candidates:
        requested_urls.append(url)

        result = _try_sync_stream_url(
            url=url,
            verify=verify,
            path=path,
            query_params=query_params,
            headers=backend_headers,
            on_frame=on_frame,
            endpoint_id=endpoint_id,
        )
        if not isinstance(result, tuple):
            # Success: consume SSE from the already-open connection
            try:
                payload, status = _consume_sse_until_complete(result, on_frame=on_frame)
            finally:
                result.close()
            payload = {
                **payload,
                "path": path,
                "requested_urls": requested_urls,
            }
            return payload, status

        # Error path: result is (last_detail, should_retry, new_headers, http_status)
        last_detail, should_retry, new_headers, last_http_status = result
        if should_retry and new_headers:
            backend_headers = new_headers
            continue
        if not should_retry:
            break
        continue

    return {
        "stream": True,
        "path": path,
        "requested_urls": requested_urls,
        "detail": last_detail or "Unable to reach the ProxBox backend stream.",
    }, last_http_status or 503


def _try_sync_stream_url(
    url: str,
    verify: bool,
    path: str,
    query_params: dict[str, str] | None,
    headers: dict[str, str],
    on_frame: Callable[[str, dict[str, object]], None] | None,
    endpoint_id: int | None = None,
) -> tuple[str | None, bool, dict[str, object] | None, int | None] | requests.Response:
    """Try a single URL for sync stream request.

    Returns:
        - An open ``requests.Response`` on success -- caller MUST close it.
        - (error_detail, should_retry, new_headers, http_status) on HTTP error >= 400.
        - (error_detail, False, None, http_status) on connection error.
    """
    try:
        response = requests.get(
            url,
            params=query_params,
            headers=headers,
            verify=verify,
            timeout=_SYNC_STREAM_READ_TIMEOUT,
            stream=True,
        )
        if response.status_code >= 400:
            actual_status = response.status_code
            last_detail = f"HTTP {actual_status}"
            try:
                payload, json_err = parse_requests_response_json(
                    response, log_label=f"sync-stream:{path}"
                )
                if not json_err and isinstance(payload, dict):
                    d = payload.get("detail") or payload.get("message")
                    if d:
                        last_detail = str(d)
                    if actual_status == 401 and "API key" in str(d):
                        new_headers, should_retry = _handle_auth_registration_and_retry(
                            headers,
                            endpoint_id=endpoint_id,
                        )
                        if should_retry:
                            response.close()
                            return last_detail, True, new_headers, 401
            except Exception:
                logger.debug("Could not parse error JSON for %s", path)
            logger.error(
                "Sync stream HTTP %s for %s via %s: %s",
                actual_status,
                path,
                url,
                last_detail,
            )
            should_retry = actual_status >= 500
            response.close()
            return last_detail, should_retry, None, actual_status

        # Success: return the open response for the caller to consume
        return response
    except requests.exceptions.RequestException as exc:
        last_detail, http_st = extract_backend_error_detail(exc)
        logger.exception("Sync stream request failed for %s via %s", path, url)
        if getattr(exc, "response", None) is not None:
            return last_detail, False, None, http_st
        return (
            last_detail,
            bool(http_st and http_st >= 500),
            None,
            http_st,
        )
    except (KeyboardInterrupt, SystemExit, GeneratorExit):
        raise
    except OSError as exc:
        last_detail = str(exc)
        logger.exception(
            "Unexpected sync stream error for %s via %s: %s", path, url, exc
        )
        return last_detail, False, None, None


def iter_backend_sse_lines(
    context: BackendRequestContext,
    path: str,
    query_params: dict[str, str] | None = None,
) -> Generator[str, None, None]:
    """Stream newline-terminated SSE lines from the backend, with URL fallback."""
    try:
        backend_headers = context.headers or {}
        http_url = context.http_url
        if not http_url:
            yield from sse_error_frames("No FastAPI URL found.")
            return

        verify_ssl = bool(context.verify_ssl)
        request_candidates = [
            (f"{http_url}/{path}", verify_ssl),
        ]
        fallback_url = context.ip_address_url
        if fallback_url:
            fallback_path = f"{fallback_url}/{path}"
            if fallback_path != request_candidates[0][0]:
                request_candidates.append((fallback_path, verify_ssl))

        last_error = None
        for url, verify in request_candidates:
            try:
                with requests.get(
                    url,
                    params=query_params,
                    headers=backend_headers,
                    verify=verify,
                    timeout=_SYNC_STREAM_READ_TIMEOUT,
                    stream=True,
                ) as response:
                    response.raise_for_status()
                    for raw_line in response.iter_lines(decode_unicode=True):
                        if raw_line is None:
                            continue
                        line = str(raw_line)
                        yield f"{line}\n"
                    return
            except requests.exceptions.RequestException as exc:
                detail, _ = extract_backend_error_detail(exc)
                last_error = detail
                logger.exception("Sync stream request failed for %s via %s", path, url)
                if getattr(exc, "response", None) is not None:
                    break
            except (KeyboardInterrupt, SystemExit, GeneratorExit):
                raise
            except OSError as exc:  # pragma: no cover
                last_error = str(exc)
                logger.exception(
                    "Unexpected sync stream error for %s via %s", path, url
                )

        payload = last_error or "Unable to reach the ProxBox backend stream."
        yield from sse_error_frames(payload)
    except (KeyboardInterrupt, SystemExit, GeneratorExit):
        raise
    except OSError as exc:  # pragma: no cover
        logger.exception("Stream proxy crashed while handling %s", path)
        yield from sse_error_frames(str(exc), final_message="Stream proxy failed.")


def sync_resource(
    path: str, query_params: dict[str, str] | None = None
) -> tuple[dict[str, object], int]:
    """Queue a single backend sync path (GET) using the default FastAPI endpoint."""
    context = get_fastapi_request_context()
    if context is None or not context.http_url:
        return {"queued": False, "detail": "No FastAPI URL found."}, 404

    return request_backend_resource(
        context,
        path,
        query_params=query_params,
        timeout=http_timeout_for_sync_path(path),
    )


def sync_full_update_resource(
    query_params: dict[str, str] | None = None,
) -> tuple[dict[str, object], int]:
    """Run full update against the backend's dedicated /full-update endpoint."""
    context = get_fastapi_request_context()
    if context is None or not context.http_url:
        return {"queued": False, "detail": "No FastAPI URL found."}, 404

    return request_backend_resource(
        context,
        "full-update",
        query_params=query_params,
        timeout=http_timeout_for_sync_path("full-update"),
    )
