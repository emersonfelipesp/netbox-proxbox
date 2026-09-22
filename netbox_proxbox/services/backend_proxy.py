"""HTTP and SSE proxy helpers for the external ProxBox FastAPI backend."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Generator, Iterable
from dataclasses import dataclass
from typing import Literal

import requests
from pydantic import ValidationError

from netbox_proxbox.backend_errors import combine_backend_message_and_detail
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
    redact_backend_detail,
    redact_sensitive,
    redact_sensitive_text,
)


def _safe_exception_text(exc: BaseException) -> str:
    """Render an exception for logs/responses without leaking request content.

    Every place that stores or emits an exception's text goes through this one
    formatter, so a path cannot quietly regress to ``str(exc)``: the rendered
    message is swept for credential-shaped content, and the class name — the
    discriminator that survives redaction — is kept in front.
    """
    return f"{type(exc).__name__}: {redact_sensitive_text(str(exc))}"


logger = logging.getLogger(__name__)

_SYNC_STREAM_READ_TIMEOUT = (5, 3600)

# Failure provenance carried on failed stream payloads under ``failure_kind``.
# ``sync_stages._classify_stage_failure`` trusts these over any phrase in the
# detail text, which is why the producer — the only code that knows whether a
# backend body was ever received — is the one that sets them.
STAGE_FAILURE_TRANSPORT = "transport"
STAGE_FAILURE_APPLICATION = "application"
_BACKEND_JSON_METHODS = Literal["GET", "POST"]
_REDIRECT_TRANSPORT_DETAIL = "ProxBox backend redirects are not permitted."
_REDIRECT_TRANSPORT_STATUS = 502
_StreamFailure = tuple[str | None, int | None, str]


@dataclass(frozen=True)
class _StreamCandidatePass:
    """One bounded traversal of the current endpoint's URL candidates."""

    payload: dict[str, object] | None = None
    status: int | None = None
    fresh_context: BackendRequestContext | None = None
    failures: tuple[_StreamFailure, ...] = ()


def _refuse_redirect(
    response: requests.Response,
    *,
    path: str,
    url: str,
) -> tuple[str, int]:
    """Close and classify a redirect without inspecting its untrusted target."""
    actual_status = int(response.status_code)
    response.close()
    logger.error(
        "Backend redirect refused for %s via %s (HTTP %s)",
        path,
        url,
        actual_status,
    )
    return _REDIRECT_TRANSPORT_DETAIL, _REDIRECT_TRANSPORT_STATUS


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


def _redacted_mapping(payload: dict[str, object]) -> dict[str, object]:
    """Redact a backend payload, guaranteeing a mapping comes back.

    ``redact_sensitive()`` is shape-preserving, so a dict in yields a dict out —
    but its declared return type is ``object`` because it walks arbitrary JSON.
    This narrows it back for the two call sites that must hand a mapping onward
    (the SSE frame callback and the failed-stream payload). If redaction ever
    collapses the mapping (it would take a depth limit of 0), the *redacted*
    value is wrapped rather than the original being handed back — the fallback
    has to stay fail-closed, or the one path that loses its shape is the one
    path that leaks.
    """
    redacted = redact_sensitive(payload)
    return redacted if isinstance(redacted, dict) else {"detail": redacted}


def _completed_stream_result(
    last_complete: SseCompletePayload | None,
) -> tuple[dict[str, object], int]:
    """Classify a normally ended SSE iterator without replaying the request."""
    if last_complete is None:
        return (
            {
                "stream": True,
                "detail": "ProxBox backend stream ended without a complete event.",
                "failure_kind": STAGE_FAILURE_TRANSPORT,
            },
            502,
        )
    if last_complete.ok is False:
        msg = redact_backend_detail(last_complete.message or "Sync failed.")
        if last_complete.errors and last_complete.errors[0].get("detail"):
            msg = redact_backend_detail(last_complete.errors[0]["detail"])
        return (
            {
                "stream": True,
                "detail": msg,
                "response": last_complete.model_dump(),
                "failure_kind": STAGE_FAILURE_APPLICATION,
            },
            503,
        )
    return {"stream": True, "response": last_complete.model_dump()}, 200


def _consume_sse_until_complete(
    response: requests.Response,
    *,
    on_frame: Callable[[str, dict[str, object]], None] | None = None,
) -> tuple[dict[str, object], int]:
    """Read one SSE body without inferring that an unseen frame permits replay."""
    last_complete: SseCompletePayload | None = None
    try:
        for frame in _iter_sse_frames(response.iter_lines(decode_unicode=True)):
            _event = frame.event
            data = frame.data
            if on_frame is not None:
                # ``on_frame`` writes into the NetBox job log (see
                # ``sync_stages.py``), which is long-lived and readable by anyone
                # who can view jobs. A backend error frame can quote the request
                # that failed, and the preflight pushes credential payloads, so
                # the frame is redacted before it leaves this reader.
                on_frame(_event, _redacted_mapping(data))
            if _event == "complete":
                try:
                    last_complete = SseCompletePayload.model_validate(data)
                except ValidationError as exc:
                    # The backend answered — with a frame this plugin cannot
                    # read. That is a version-skew defect to act on, not a
                    # transient path failure, so it must outrank a later TLS
                    # or connection error in stage attribution.
                    return (
                        {
                            "stream": True,
                            "detail": (
                                "ProxBox backend stream sent an invalid complete event: "
                                f"{exc.errors()[0].get('msg', str(exc))}"
                            ),
                            "failure_kind": STAGE_FAILURE_APPLICATION,
                        },
                        502,
                    )
    except requests.exceptions.RequestException as exc:
        detail, _ = extract_backend_error_detail(exc)
        return (
            {
                "stream": True,
                "detail": detail,
                "failure_kind": STAGE_FAILURE_TRANSPORT,
            },
            502,
        )

    return _completed_stream_result(last_complete)


def request_backend_resource(
    context: BackendRequestContext,
    path: str,
    query_params: dict[str, str] | None = None,
    *,
    timeout: float | tuple[int, int] = 5,
) -> tuple[dict[str, object], int]:
    """GET a JSON resource from the backend, trying primary URL then IP fallback."""
    active_context = context
    http_url = active_context.http_url
    if not http_url:
        return {
            "queued": False,
            "path": path,
            "requested_urls": [],
            "detail": "No FastAPI URL found.",
        }, 503

    requested_urls: list[str] = []
    last_detail: str | None = None
    last_status: int | None = None
    auth_register_attempted = False

    while True:
        http_url = active_context.http_url
        if not http_url:
            last_detail = "No FastAPI URL found after authentication retry."
            break
        verify_ssl = bool(active_context.verify_ssl)
        backend_headers = active_context.headers or {}
        request_candidates = _build_request_candidates(
            http_url,
            active_context.ip_address_url,
            path,
            verify_ssl,
        )
        restart_candidate_selection = False

        for url, verify in request_candidates:
            requested_urls.append(url)

            try:
                response = requests.get(
                    url,
                    params=query_params,
                    headers=backend_headers,
                    verify=verify,
                    timeout=timeout,
                    allow_redirects=False,
                )
            except requests.exceptions.RequestException as exc:
                last_detail, _ = extract_backend_error_detail(exc)
                logger.error(
                    "Sync request failed for %s via %s: %s", path, url, last_detail
                )
                if getattr(exc, "response", None) is not None:
                    break
                continue
            except (KeyboardInterrupt, SystemExit, GeneratorExit):
                raise
            except OSError as exc:
                last_detail = _safe_exception_text(exc)
                logger.error(
                    "Unexpected sync error for %s via %s: %s",
                    path,
                    url,
                    last_detail,
                )
                continue

            if 300 <= response.status_code < 400:
                last_detail, last_status = _refuse_redirect(
                    response,
                    path=path,
                    url=url,
                )
                break

            if response.status_code >= 400:
                last_detail = f"HTTP {response.status_code}"
                payload, json_err = parse_requests_response_json(
                    response, log_label=f"sync:{path}"
                )
                if not json_err and isinstance(payload, dict):
                    d = payload.get("detail") or payload.get("message")
                    if d:
                        last_detail = redact_backend_detail(d)
                    if (
                        not auth_register_attempted
                        and response.status_code == 401
                        and "API key" in str(d)
                    ):
                        auth_register_attempted = True
                        response.close()
                        fresh_context = _handle_auth_registration_and_retry(
                            active_context,
                            endpoint_id=active_context.endpoint_id,
                        )
                        if fresh_context is not None:
                            active_context = fresh_context
                            restart_candidate_selection = True
                            break
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

        if restart_candidate_selection:
            continue
        break

    return {
        "queued": False,
        "path": path,
        "requested_urls": requested_urls,
        "detail": last_detail or "Unable to reach the ProxBox backend.",
    }, last_status or 503


def _send_backend_json_request(
    method: _BACKEND_JSON_METHODS,
    url: str,
    *,
    query_params: dict[str, str] | None,
    headers: dict[str, str],
    verify: bool,
    timeout: float | tuple[int, int],
) -> requests.Response:
    """Send a bounded JSON request without dynamic method dispatch."""
    if method == "GET":
        return requests.get(
            url,
            params=query_params,
            headers=headers,
            verify=verify,
            timeout=timeout,
            allow_redirects=False,
        )
    if method == "POST":
        return requests.post(
            url,
            params=query_params,
            headers=headers,
            verify=verify,
            timeout=timeout,
            allow_redirects=False,
        )
    raise ValueError(f"Unsupported backend JSON method: {method}")


def _parse_json_or_empty(
    response: requests.Response, *, log_label: str
) -> tuple[object | None, str | None]:
    """Return JSON response data, treating empty success bodies as ``{}``."""
    if response.status_code == 204:
        return {}, None
    body = getattr(response, "text", None)
    if body == "":
        return {}, None
    return parse_requests_response_json(response, log_label=log_label)


def request_backend_json(
    context: BackendRequestContext,
    path: str,
    *,
    method: _BACKEND_JSON_METHODS = "GET",
    query_params: dict[str, str] | None = None,
    timeout: float | tuple[int, int] = 5,
    endpoint_id: int | None = None,
) -> tuple[dict[str, object], int]:
    """Call a proxbox-api JSON endpoint with URL fallback and auth retry."""
    active_context = context
    http_url = active_context.http_url
    if not http_url:
        return {
            "ok": False,
            "path": path,
            "requested_urls": [],
            "detail": "No FastAPI URL found.",
        }, 503

    requested_urls: list[str] = []
    last_detail: str | None = None
    last_status: int | None = None
    auth_register_attempted = False

    while True:
        http_url = active_context.http_url
        if not http_url:
            last_detail = "No FastAPI URL found after authentication retry."
            break
        verify_ssl = bool(active_context.verify_ssl)
        backend_headers = active_context.headers or {}
        request_candidates = _build_request_candidates(
            http_url,
            active_context.ip_address_url,
            path,
            verify_ssl,
        )
        restart_candidate_selection = False

        for url, verify in request_candidates:
            requested_urls.append(url)
            try:
                response = _send_backend_json_request(
                    method,
                    url,
                    query_params=query_params,
                    headers=backend_headers,
                    verify=verify,
                    timeout=timeout,
                )
            except requests.exceptions.RequestException as exc:
                last_detail, last_status = extract_backend_error_detail(exc)
                logger.error(
                    "Backend %s request failed for %s via %s", method, path, url
                )
                if getattr(exc, "response", None) is not None:
                    return {
                        "ok": False,
                        "path": path,
                        "requested_urls": requested_urls,
                        "detail": last_detail,
                    }, last_status or 503
                break
            except (KeyboardInterrupt, SystemExit, GeneratorExit):
                raise
            except OSError as exc:
                last_detail = _safe_exception_text(exc)
                logger.error(
                    "Unexpected backend %s error for %s via %s: %s",
                    method,
                    path,
                    url,
                    last_detail,
                )
                continue

            if 300 <= response.status_code < 400:
                last_detail, last_status = _refuse_redirect(
                    response,
                    path=path,
                    url=url,
                )
                return {
                    "ok": False,
                    "path": path,
                    "requested_urls": requested_urls,
                    "status_code": last_status,
                    "detail": last_detail,
                }, last_status

            last_status = response.status_code
            if response.status_code >= 400:
                last_detail = f"HTTP {response.status_code}"
                payload, json_err = parse_requests_response_json(
                    response, log_label=f"backend-json:{path}"
                )
                if json_err:
                    last_detail = json_err
                elif isinstance(payload, dict):
                    detail = payload.get("detail") or payload.get("message")
                    if detail:
                        last_detail = redact_backend_detail(detail)
                    if (
                        not auth_register_attempted
                        and response.status_code == 401
                        and "API key" in str(detail)
                    ):
                        auth_register_attempted = True
                        response.close()
                        fresh_context = _handle_auth_registration_and_retry(
                            active_context,
                            endpoint_id=endpoint_id,
                        )
                        if fresh_context is not None:
                            active_context = fresh_context
                            restart_candidate_selection = True
                            break

                logger.error(
                    "Backend %s request failed for %s via %s: %s",
                    method,
                    path,
                    url,
                    last_detail,
                )
                if response.status_code < 500:
                    return {
                        "ok": False,
                        "path": path,
                        "requested_urls": requested_urls,
                        "status_code": response.status_code,
                        "detail": last_detail,
                    }, response.status_code
                continue

            payload, json_err = _parse_json_or_empty(
                response, log_label=f"backend-json:{path}"
            )
            if json_err:
                last_detail = json_err
                logger.error(
                    "Backend %s request returned non-JSON for %s via %s: %s",
                    method,
                    path,
                    url,
                    json_err,
                )
                continue

            return {
                "ok": True,
                "path": path,
                "requested_urls": requested_urls,
                "status_code": response.status_code,
                "response": payload if payload is not None else {},
            }, response.status_code

        if restart_candidate_selection:
            continue
        break

    return {
        "ok": False,
        "path": path,
        "requested_urls": requested_urls,
        "status_code": last_status,
        "detail": last_detail or "Unable to reach the ProxBox backend.",
    }, last_status or 503


def get_backend_bootstrap_status(
    endpoint_id: int | None = None,
) -> tuple[dict[str, object], int]:
    """Fetch proxbox-api setup/bootstrap status from ``/extras/bootstrap-status``."""
    context = get_fastapi_request_context(endpoint_id=endpoint_id)
    if context is None or not context.http_url:
        return {"ok": False, "detail": "No FastAPI URL found."}, 404
    return request_backend_json(
        context,
        "extras/bootstrap-status",
        method="GET",
        endpoint_id=endpoint_id,
    )


def reconcile_backend_custom_fields(
    endpoint_id: int | None = None,
) -> tuple[dict[str, object], int]:
    """Force-reconcile legacy Proxbox custom-field definitions on proxbox-api."""
    context = get_fastapi_request_context(endpoint_id=endpoint_id)
    if context is None or not context.http_url:
        return {"ok": False, "detail": "No FastAPI URL found."}, 404
    return request_backend_json(
        context,
        "extras/custom-fields/reconcile",
        method="POST",
        timeout=30,
        endpoint_id=endpoint_id,
    )


def _stream_candidate_context(
    context: BackendRequestContext,
    *,
    url: str,
    path: str,
    verify_ssl: bool,
) -> BackendRequestContext:
    """Bind a readiness probe to the exact candidate used by the stream."""
    suffix = f"/{path}"
    candidate_base = url[: -len(suffix)] if url.endswith(suffix) else url
    return context.model_copy(
        update={
            "http_url": candidate_base,
            "ip_address_url": None,
            "verify_ssl": verify_ssl,
        }
    )


def _consume_stream_response(
    response: requests.Response,
    *,
    path: str,
    requested_urls: list[str],
    on_frame: Callable[[str, dict[str, object]], None] | None,
) -> tuple[dict[str, object], int]:
    """Consume and close one open stream response."""
    try:
        payload, status = _consume_sse_until_complete(
            response,
            on_frame=on_frame,
        )
    finally:
        response.close()
    payload = {**payload, "path": path, "requested_urls": requested_urls}
    if status >= 400:
        payload = _redacted_mapping(payload)
    return payload, status


def _run_stream_candidate_pass(
    context: BackendRequestContext,
    *,
    path: str,
    query_params: dict[str, str] | None,
    on_frame: Callable[[str, dict[str, object]], None] | None,
    endpoint_id: int | None,
    auth_register_attempted: bool,
    requested_urls: list[str],
) -> _StreamCandidatePass:
    """Select a ready candidate, then issue exactly one mutating request."""
    failures: list[_StreamFailure] = []
    if not context.http_url:
        return _StreamCandidatePass(
            failures=(
                (
                    "No FastAPI URL found after authentication retry.",
                    None,
                    STAGE_FAILURE_APPLICATION,
                ),
            )
        )
    candidates = _build_request_candidates(
        context.http_url,
        context.ip_address_url,
        path,
        bool(context.verify_ssl),
    )
    for url, verify in candidates:
        requested_urls.append(url)
        ready, ready_msg = wait_for_backend_ready(
            _stream_candidate_context(
                context,
                url=url,
                path=path,
                verify_ssl=verify,
            )
        )
        if not ready:
            logger.error("Backend candidate not ready: %s", ready_msg)
            failures.append(
                (f"Backend not ready: {ready_msg}", 503, STAGE_FAILURE_TRANSPORT)
            )
            if ready_msg == "Backend redirects are not permitted.":
                break
            continue

        result = _try_sync_stream_url(
            url=url,
            verify=verify,
            path=path,
            query_params=query_params,
            context=context,
            on_frame=on_frame,
            endpoint_id=endpoint_id,
            auth_register_attempted=auth_register_attempted,
        )
        if not isinstance(result, tuple):
            payload, status = _consume_stream_response(
                result,
                path=path,
                requested_urls=requested_urls,
                on_frame=on_frame,
            )
            return _StreamCandidatePass(payload=payload, status=status)

        detail, _should_retry, fresh_context, http_status, failure_kind = result
        failures.append((detail, http_status, failure_kind))
        if fresh_context is not None:
            return _StreamCandidatePass(fresh_context=fresh_context)
        break
    return _StreamCandidatePass(failures=tuple(failures))


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
        # A missing configuration is deterministic: retrying cannot help and
        # a later transport error must not hide it.
        return {
            "stream": False,
            "detail": "No FastAPI URL found.",
            "failure_kind": STAGE_FAILURE_APPLICATION,
        }, 404

    active_context = context
    requested_urls: list[str] = []
    # Every candidate URL (hostname, then IP fallback) and every auth-rebound
    # pass records its failure here. The returned cause is selected
    # application-first, because a backend that answered on the hostname and
    # then could not be reached on the IP fallback has still *answered*.
    candidate_failures: list[tuple[str | None, int | None, str]] = []
    auth_register_attempted = False

    while True:
        candidate_pass = _run_stream_candidate_pass(
            active_context,
            path=path,
            query_params=query_params,
            on_frame=on_frame,
            endpoint_id=endpoint_id,
            auth_register_attempted=auth_register_attempted,
            requested_urls=requested_urls,
        )
        if candidate_pass.payload is not None and candidate_pass.status is not None:
            return candidate_pass.payload, candidate_pass.status
        if candidate_pass.fresh_context is not None:
            # A successful rebind starts a new candidate-selection epoch. Only
            # the freshly authenticated context can determine the final cause.
            candidate_failures.clear()
            auth_register_attempted = True
            active_context = candidate_pass.fresh_context
            continue
        candidate_failures.extend(candidate_pass.failures)
        break

    detail, http_status, failure_kind = _select_stream_failure(candidate_failures)
    return {
        "stream": True,
        "path": path,
        "requested_urls": requested_urls,
        "detail": detail or "Unable to reach the ProxBox backend stream.",
        "failure_kind": failure_kind,
    }, http_status or 503


def _select_stream_failure(
    failures: list[tuple[str | None, int | None, str]],
) -> tuple[str | None, int | None, str]:
    """Pick the failure ``run_sync_stream`` reports across URL candidates.

    The first backend-authored (application) failure wins; when no candidate
    reached the backend, the last transport failure is reported. This mirrors
    the per-attempt rule in ``sync_stages``: the deterministic cause outranks
    the transient one regardless of the order the candidates were tried in.
    """
    if not failures:
        return None, None, STAGE_FAILURE_TRANSPORT
    for failure in failures:
        if failure[2] == STAGE_FAILURE_APPLICATION:
            return failure
    return failures[-1]


def _try_sync_stream_url(
    url: str,
    verify: bool,
    path: str,
    query_params: dict[str, str] | None,
    context: BackendRequestContext,
    on_frame: Callable[[str, dict[str, object]], None] | None,
    endpoint_id: int | None = None,
    auth_register_attempted: bool = False,
) -> (
    tuple[str | None, bool, BackendRequestContext | None, int | None, str]
    | requests.Response
):
    """Try a single URL for sync stream request.

    Returns:
        - An open ``requests.Response`` on success -- caller MUST close it.
        - (error_detail, should_retry, fresh_context, http_status, failure_kind)
          on HTTP error.
        - (error_detail, False, None, http_status, failure_kind) on a connection
          error. Once attempted, the mutating request is never replayed through
          another candidate.

    ``failure_kind`` is the producer's own verdict on *what* failed —
    :data:`STAGE_FAILURE_APPLICATION` when the backend answered with a JSON
    body (it ran and rejected the request), :data:`STAGE_FAILURE_TRANSPORT`
    when the request never got a backend-authored answer (connection, TLS,
    timeout, refused redirect, or a non-JSON gateway error page). Consumers
    that attribute retry failures trust this over any phrase in the detail.
    """
    try:
        response = requests.get(
            url,
            params=query_params,
            headers=context.headers or {},
            verify=verify,
            timeout=_SYNC_STREAM_READ_TIMEOUT,
            stream=True,
            allow_redirects=False,
        )
        if 300 <= response.status_code < 400:
            last_detail, redirect_status = _refuse_redirect(
                response,
                path=path,
                url=url,
            )
            return last_detail, False, None, redirect_status, STAGE_FAILURE_TRANSPORT

        if response.status_code >= 400:
            return _stream_http_error(
                response,
                url=url,
                path=path,
                context=context,
                endpoint_id=endpoint_id,
                auth_register_attempted=auth_register_attempted,
            )

        # Success: return the open response for the caller to consume
        return response
    except requests.exceptions.RequestException as exc:
        last_detail, http_st = extract_backend_error_detail(exc)
        # Log the *redacted* detail, never the raw exception: `logger.exception`
        # renders `str(exc)`, and a transport error can echo request text that
        # carries pushed credentials — sanitizing the user-facing detail while
        # leaking the same secret to the application log would be no redaction
        # at all.
        logger.error(
            "Sync stream request failed for %s via %s: %s", path, url, last_detail
        )
        return last_detail, False, None, http_st, STAGE_FAILURE_TRANSPORT
    except (KeyboardInterrupt, SystemExit, GeneratorExit):
        raise
    except OSError as exc:
        last_detail = _safe_exception_text(exc)
        logger.error(
            "Unexpected sync stream error for %s via %s: %s", path, url, last_detail
        )
        return last_detail, False, None, None, STAGE_FAILURE_TRANSPORT


def _json_error_detail(payload: object) -> str | None:
    """The human-readable detail of a JSON error body of any shape.

    A dict body is proxbox-api's own ``{"message", "detail"}`` shape: both
    fields are reported (``"<message>: <detail>"``) so neither an empty
    ``detail`` nor a populated one hides the other half of the diagnosis.
    """
    if isinstance(payload, dict):
        # Structured detail is kept here: this text is redacted by the caller and
        # never reaches the retry classifier's cause scan.
        return combine_backend_message_and_detail(payload, render_structured=True)
    if isinstance(payload, list) and payload:
        first = payload[0]
        if isinstance(first, dict):
            value = first.get("detail") or first.get("msg") or first.get("message")
            return str(value) if value else str(first)
        return str(first)
    if payload is None or payload == "":
        return None
    return str(payload)


def _stream_http_error(
    response: requests.Response,
    *,
    url: str,
    path: str,
    context: BackendRequestContext,
    endpoint_id: int | None,
    auth_register_attempted: bool,
) -> tuple[str | None, bool, BackendRequestContext | None, int | None, str]:
    """Turn an HTTP error response on the stream URL into the error tuple.

    Provenance: a JSON body means proxbox-api itself answered, so the failure
    is the backend's verdict rather than the path to it — even for a 5xx it
    authored. A non-JSON 5xx is a gateway error page (transport); a non-JSON
    4xx (an nginx 404 for a missing route, say) is still an answer about the
    request, not about reaching it.
    """
    actual_status = response.status_code
    last_detail = f"HTTP {actual_status}"
    failure_kind = STAGE_FAILURE_TRANSPORT
    try:
        payload, json_err = parse_requests_response_json(
            response, log_label=f"sync-stream:{path}"
        )
        if not json_err:
            # Any JSON body — mapping, list, or scalar — is a backend-authored
            # answer; a list or scalar is usually version skew, which is
            # exactly the deterministic cause that must not be demoted.
            failure_kind = STAGE_FAILURE_APPLICATION
            d = _json_error_detail(payload)
            if d:
                last_detail = redact_backend_detail(d)
            if (
                isinstance(payload, dict)
                and not auth_register_attempted
                and actual_status == 401
                and "API key" in str(d)
            ):
                response.close()
                fresh_context = _handle_auth_registration_and_retry(
                    context,
                    endpoint_id=endpoint_id,
                )
                if fresh_context is not None:
                    return last_detail, True, fresh_context, 401, failure_kind
                return last_detail, False, None, 401, failure_kind
    except (KeyboardInterrupt, SystemExit, GeneratorExit):
        raise
    except Exception:
        logger.debug("Could not parse error JSON for %s", path)
    logger.error(
        "Sync stream HTTP %s for %s via %s: %s",
        actual_status,
        path,
        url,
        last_detail,
    )
    response.close()
    if failure_kind == STAGE_FAILURE_TRANSPORT and actual_status < 500:
        failure_kind = STAGE_FAILURE_APPLICATION
    return last_detail, actual_status >= 500, None, actual_status, failure_kind


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
        request_candidates = _build_request_candidates(
            http_url,
            context.ip_address_url,
            path,
            verify_ssl,
        )

        last_error: str | None = None
        for url, verify in request_candidates:
            try:
                with requests.get(
                    url,
                    params=query_params,
                    headers=backend_headers,
                    verify=verify,
                    timeout=_SYNC_STREAM_READ_TIMEOUT,
                    stream=True,
                    allow_redirects=False,
                ) as response:
                    if 300 <= response.status_code < 400:
                        last_error, _ = _refuse_redirect(
                            response,
                            path=path,
                            url=url,
                        )
                        break
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
                # Redacted detail only — see `_try_sync_stream_url` for why the
                # raw exception must not reach the application log.
                logger.error(
                    "Sync stream request failed for %s via %s: %s", path, url, detail
                )
                if getattr(exc, "response", None) is not None:
                    break
            except (KeyboardInterrupt, SystemExit, GeneratorExit):
                raise
            except OSError as exc:  # pragma: no cover
                last_error = _safe_exception_text(exc)
                logger.error(
                    "Unexpected sync stream error for %s via %s: %s",
                    path,
                    url,
                    last_error,
                )

        payload = last_error or "Unable to reach the ProxBox backend stream."
        yield from sse_error_frames(payload)
    except (KeyboardInterrupt, SystemExit, GeneratorExit):
        raise
    except OSError as exc:  # pragma: no cover
        safe_text = _safe_exception_text(exc)
        logger.error("Stream proxy crashed while handling %s: %s", path, safe_text)
        yield from sse_error_frames(safe_text, final_message="Stream proxy failed.")


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
