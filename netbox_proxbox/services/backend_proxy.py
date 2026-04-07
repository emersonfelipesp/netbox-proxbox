"""HTTP and SSE proxy helpers for the external ProxBox FastAPI backend."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Generator, Iterable

import requests

from netbox_proxbox.models import FastAPIEndpoint
from netbox_proxbox.schemas.backend_proxy import (
    BackendRequestContext,
    SseCompletePayload,
    SseErrorPayload,
    SseFrame,
)
from netbox_proxbox.utils import get_backend_auth_headers, get_fastapi_url
from netbox_proxbox.views.error_utils import (
    extract_backend_error_detail,
    parse_requests_response_json,
)

logger = logging.getLogger(__name__)

# Long read timeout for consuming proxbox-api SSE sync streams from background jobs.
_SYNC_STREAM_READ_TIMEOUT = (5, 3600)

# proxbox-api awaits the full backup sync in one GET; allow long read like the stream proxy.
_LONG_RUNNING_BACKUP_PATH_MARKER = "virtualization/virtual-machines/backups/all/create"
_LONG_RUNNING_SNAPSHOT_PATH_MARKER = (
    "virtualization/virtual-machines/snapshots/all/create"
)
_LONG_HTTP_READ_TIMEOUT = (5, 3600)


def http_timeout_for_sync_path(path: str) -> float | tuple[int, int]:
    """Return read timeout for a backend sync path (long for backup/snapshot bulk ops)."""
    if _LONG_RUNNING_BACKUP_PATH_MARKER in path:
        return _LONG_HTTP_READ_TIMEOUT
    if _LONG_RUNNING_SNAPSHOT_PATH_MARKER in path:
        return _LONG_HTTP_READ_TIMEOUT
    return 5


def _try_register_key(context: BackendRequestContext, token: str) -> tuple[bool, str]:
    """Attempt to register the API key with the backend if not already registered.

    Returns (success, message) tuple.
    """
    import requests

    if not context or not context.http_url:
        return False, "No FastAPI URL configured"

    base_url = context.http_url.rstrip("/")
    verify_ssl = bool(context.verify_ssl)

    try:
        status_response = requests.get(
            f"{base_url}/auth/bootstrap-status",
            verify=verify_ssl,
            timeout=5,
        )
        if status_response.status_code != 200:
            return (
                False,
                f"Bootstrap status check failed: HTTP {status_response.status_code}",
            )

        status_data = status_response.json()
        if not status_data.get("needs_bootstrap", False):
            return True, "Key already registered"

    except requests.exceptions.RequestException as exc:
        return False, f"Could not check bootstrap status: {exc}"

    try:
        register_response = requests.post(
            f"{base_url}/auth/register-key",
            json={"api_key": token, "label": "netbox-proxbox-plugin"},
            verify=verify_ssl,
            timeout=10,
        )
        if register_response.status_code == 201:
            return True, "Key registered successfully"
        if register_response.status_code == 409:
            return True, "Key already exists"
        return False, f"Registration failed: HTTP {register_response.status_code}"

    except requests.exceptions.RequestException as exc:
        return False, f"Could not register key: {exc}"


def _try_register_key_fallback() -> tuple[bool, str]:
    """Try registering keys from all FastAPIEndpoints with fallback.

    Iterates through all endpoints and attempts to register each token.
    Returns (success, message) tuple showing the last attempt result.
    """
    from netbox_proxbox.utils import get_fastapi_context

    endpoints = FastAPIEndpoint.objects.order_by("pk").all()
    if not endpoints:
        return False, "No FastAPI endpoints configured"

    last_message = "No keys attempted"
    for endpoint in endpoints:
        token = (getattr(endpoint, "token", "") or "").strip()
        if not token:
            last_message = f"Endpoint {endpoint.pk} has no token, skipping"
            logger.debug(last_message)
            continue

        context = get_fastapi_context(endpoint)
        if not context:
            last_message = f"Endpoint {endpoint.pk} has no context, skipping"
            logger.debug(last_message)
            continue

        success, message = _try_register_key(
            BackendRequestContext(
                detail=context,
                http_url=context.get("http_url"),
                ip_address_url=context.get("ip_address_url"),
                verify_ssl=context.get("verify_ssl", True),
                headers=context.get("headers", {}),
            ),
            token,
        )
        if success:
            return True, f"Registered endpoint {endpoint.pk}: {message}"
        last_message = f"Endpoint {endpoint.pk} failed: {message}"
        logger.warning(
            "Token registration failed for endpoint %s: %s", endpoint.pk, message
        )

    return False, last_message


def wait_for_backend_ready(
    context: BackendRequestContext,
    max_retries: int = 30,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
) -> tuple[bool, str]:
    """Wait for the FastAPI backend to be ready before starting sync.

    Returns:
        tuple of (success, message)
    """
    import time as time_module

    if not context or not context.http_url:
        return False, "No FastAPI URL configured"

    backend_url = context.http_url.rstrip("/")
    health_url = f"{backend_url}/health"
    verify_ssl = bool(context.verify_ssl)
    headers = context.headers or {}

    delay = initial_delay
    for attempt in range(max_retries):
        try:
            response = requests.get(
                health_url,
                headers=headers,
                verify=verify_ssl,
                timeout=5,
            )
            if response.status_code == 200:
                try:
                    data = response.json()
                    init_ok = data.get("init_ok", False)
                    if init_ok:
                        return True, "Backend is ready"
                    status = data.get("status", "unknown")
                    if status == "ready":
                        return True, "Backend is ready"
                except Exception:
                    pass
                if attempt < max_retries - 1:
                    logger.info(
                        "Backend health check returned but init not complete (attempt %s/%s), retrying in %ss",
                        attempt + 1,
                        max_retries,
                        delay,
                    )
                    time_module.sleep(delay)
                    delay = min(delay * 1.5, max_delay)
                    continue
            else:
                if attempt < max_retries - 1:
                    logger.info(
                        "Backend health check failed with HTTP %s (attempt %s/%s), retrying in %ss",
                        response.status_code,
                        attempt + 1,
                        max_retries,
                        delay,
                    )
                    time_module.sleep(delay)
                    delay = min(delay * 1.5, max_delay)
                    continue
        except requests.exceptions.RequestException as exc:
            if attempt < max_retries - 1:
                logger.info(
                    "Backend health check request failed (attempt %s/%s): %s, retrying in %ss",
                    attempt + 1,
                    max_retries,
                    str(exc)[:100],
                    delay,
                )
                time_module.sleep(delay)
                delay = min(delay * 1.5, max_delay)
                continue

    return False, f"Backend not ready after {max_retries} attempts"


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


def get_fastapi_request_context() -> BackendRequestContext | None:
    """Build auth headers and URLs for the first configured FastAPI endpoint, if any."""
    from netbox_proxbox.utils import get_first_fastapi_context

    context = get_first_fastapi_context()
    if context is None:
        return None

    return BackendRequestContext(
        detail=context,
        http_url=context.get("http_url"),
        ip_address_url=context.get("ip_address_url"),
        verify_ssl=context.get("verify_ssl", True),
        headers=context.get("headers", {}),
    )


def get_fastapi_endpoint_with_token(
    endpoint_id: int | None = None,
) -> tuple[object | None, BackendRequestContext | None]:
    """Get the FastAPIEndpoint model and its request context.

    Args:
        endpoint_id: Optional specific endpoint ID. If not provided, selects by ID
            when multiple endpoints exist, or returns the only endpoint when only one exists.

    Returns (endpoint, context) tuple. Either may be None.
    """
    from netbox_proxbox.utils import get_fastapi_context_by_id

    if endpoint_id is not None:
        endpoint = FastAPIEndpoint.objects.filter(pk=endpoint_id).first()
        if endpoint is None:
            return None, None
        context = get_fastapi_request_context()
        return endpoint, context

    count = FastAPIEndpoint.objects.count()
    if count == 0:
        return None, None
    if count == 1:
        endpoint = FastAPIEndpoint.objects.first()
        context = get_fastapi_request_context()
        return endpoint, context

    endpoint = FastAPIEndpoint.objects.order_by("pk").first()
    if endpoint is None:
        return None, None
    context = get_fastapi_request_context()
    return endpoint, context


def ensure_backend_key_registered() -> tuple[bool, str]:
    """Check if the API key is registered with the backend, register if needed.

    Returns (success, message) tuple.
    """
    endpoint, context = get_fastapi_endpoint_with_token()
    if endpoint is None:
        return False, "No FastAPI endpoint configured"

    if context is None or not context.http_url:
        return False, "No FastAPI URL configured"

    token = (getattr(endpoint, "token", "") or "").strip()
    if not token:
        return False, "No API token configured on FastAPI endpoint"

    return _try_register_key(context, token)


def _build_request_candidates(
    http_url: str,
    ip_address_url: str | None,
    path: str,
    verify_ssl: bool,
) -> list[tuple[str, bool]]:
    """Build list of (url, verify_ssl) candidates for backend requests with fallback."""
    main_url = f"{http_url}/{path}"
    candidates = [(main_url, verify_ssl)]
    if ip_address_url:
        fallback_path = f"{ip_address_url}/{path}"
        if fallback_path != main_url:
            candidates.append((fallback_path, verify_ssl))
    return candidates


def _handle_auth_registration_and_retry(
    context: BackendRequestContext,
    backend_headers: dict,
) -> tuple[dict, bool]:
    """Attempt API key registration with the backend.

    Returns (new_headers, retry_flag). If registration succeeds, returns new headers
    and True to indicate the caller should retry the request.
    """
    logger.info("Backend returned 'no API key' error; attempting key registration")
    reg_ok, reg_msg = ensure_backend_key_registered()
    if reg_ok:
        logger.info("Key registration succeeded: %s", reg_msg)
        new_context = get_fastapi_request_context()
        if new_context and new_context.headers:
            return new_context.headers, True
    else:
        logger.warning("Key registration failed: %s", reg_msg)
    return backend_headers, False


def request_backend_resource(
    context: BackendRequestContext,
    path: str,
    query_params: dict | None = None,
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
                        context, backend_headers
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
        line = str(raw)
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
                last_complete = SseCompletePayload.model_validate(data)
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


def run_sync_stream(
    path: str,
    query_params: dict | None = None,
    *,
    on_frame: Callable[[str, dict[str, object]], None] | None = None,
) -> tuple[dict[str, object], int]:
    """GET a backend SSE sync URL to completion (for NetBox background jobs).

    ``path`` must be the stream route (e.g. ``full-update/stream`` or
    ``dcim/devices/create/stream``). Uses the same URL fallback as
    :func:`iter_backend_sse_lines` and a long read timeout.
    """
    context = get_fastapi_request_context()
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

    for url, verify in request_candidates:
        requested_urls.append(url)

        result = _try_sync_stream_url(
            url=url,
            verify=verify,
            path=path,
            query_params=query_params,
            headers=backend_headers,
            on_frame=on_frame,
        )
        if result is not None:
            last_detail, should_retry, new_headers = result
            if should_retry and new_headers:
                backend_headers = new_headers
                continue
            if last_detail is None:
                return {
                    "stream": True,
                    "path": path,
                    "requested_urls": requested_urls,
                }, 200
            if not should_retry:
                break
            continue

        payload, status = _make_request_and_consume_sse(
            url, verify, query_params, backend_headers, on_frame
        )
        payload = {
            **payload,
            "path": path,
            "requested_urls": requested_urls,
        }
        return payload, status

    return {
        "stream": True,
        "path": path,
        "requested_urls": requested_urls,
        "detail": last_detail or "Unable to reach the ProxBox backend stream.",
    }, 503


def _try_sync_stream_url(
    url: str,
    verify: bool,
    path: str,
    query_params: dict | None,
    headers: dict,
    on_frame: Callable[[str, dict[str, object]], None] | None,
) -> tuple[str | None, bool, dict | None] | None:
    """Try a single URL for sync stream request.

    Returns:
        - None if request succeeded (caller should consume SSE)
        - (error_detail, should_retry, new_headers) on HTTP error >= 400
        - (error_detail, False, None) on connection error
    """
    try:
        with requests.get(
            url,
            params=query_params,
            headers=headers,
            verify=verify,
            timeout=_SYNC_STREAM_READ_TIMEOUT,
            stream=True,
        ) as response:
            if response.status_code >= 400:
                last_detail = f"HTTP {response.status_code}"
                try:
                    payload, json_err = parse_requests_response_json(
                        response, log_label=f"sync-stream:{path}"
                    )
                    if not json_err and isinstance(payload, dict):
                        d = payload.get("detail") or payload.get("message")
                        if d:
                            last_detail = str(d)
                        if response.status_code == 401 and "API key" in str(d):
                            new_headers, should_retry = (
                                _handle_auth_registration_and_retry(
                                    BackendRequestContext(
                                        http_url=url.rsplit("/", 1)[0], headers=headers
                                    ),
                                    headers,
                                )
                            )
                            if should_retry:
                                return last_detail, True, new_headers
                except Exception:
                    logger.debug("Could not parse error JSON for %s", path)
                logger.error(
                    "Sync stream HTTP %s for %s via %s: %s",
                    response.status_code,
                    path,
                    url,
                    last_detail,
                )
                should_retry = response.status_code >= 500
                return last_detail, should_retry, None

            return None
    except requests.exceptions.RequestException as exc:
        last_detail, http_st = extract_backend_error_detail(exc)
        logger.exception("Sync stream request failed for %s via %s", path, url)
        if getattr(exc, "response", None) is not None:
            return last_detail, False, None
        return (
            last_detail,
            http_st and http_st >= 500,
            None if http_st and http_st >= 500 else None,
        )
    except (KeyboardInterrupt, SystemExit, GeneratorExit):
        raise
    except OSError as exc:
        last_detail = str(exc)
        logger.exception(
            "Unexpected sync stream error for %s via %s: %s", path, url, exc
        )
        return last_detail, False, None


def _consume_sse_from_response(
    response: requests.Response,
    on_frame: Callable[[str, dict[str, object]], None] | None,
) -> tuple[dict[str, object], int]:
    """Read an SSE body from an existing response to the final ``complete`` event."""
    last_complete: SseCompletePayload | None = None
    try:
        for frame in _iter_sse_frames(response.iter_lines(decode_unicode=True)):
            _event = frame.event
            data = frame.data
            if on_frame is not None:
                on_frame(_event, data)
            if _event == "complete":
                last_complete = SseCompletePayload.model_validate(data)
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


def _make_request_and_consume_sse(
    url: str,
    verify: bool,
    query_params: dict | None,
    headers: dict,
    on_frame: Callable[[str, dict[str, object]], None] | None,
) -> tuple[dict[str, object], int]:
    """Make HTTP request and consume SSE stream to completion."""
    try:
        with requests.get(
            url,
            params=query_params,
            headers=headers,
            verify=verify,
            timeout=_SYNC_STREAM_READ_TIMEOUT,
            stream=True,
        ) as response:
            return _consume_sse_from_response(response, on_frame)
    except requests.exceptions.RequestException as exc:
        detail, _ = extract_backend_error_detail(exc)
        return {
            "stream": True,
            "detail": detail,
        }, 502


def iter_backend_sse_lines(
    context: BackendRequestContext,
    path: str,
    query_params: dict | None = None,
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
    path: str, query_params: dict | None = None
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
    query_params: dict | None = None,
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
