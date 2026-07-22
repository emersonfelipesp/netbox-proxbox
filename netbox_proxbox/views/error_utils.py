"""Shared helpers for normalizing backend and Proxmox error details."""

from __future__ import annotations

import json
import logging
import re

import requests

logger = logging.getLogger(__name__)

try:
    _JSON_DECODE_ERROR: type[BaseException] = requests.exceptions.JSONDecodeError
except AttributeError:
    _JSON_DECODE_ERROR = json.JSONDecodeError

# Substrings that mark a JSON key as carrying a secret.  Backend error bodies are
# not sanitised at the source: a FastAPI 422 echoes the submitted request body
# back under ``input``, and the endpoint pushes this plugin performs submit API
# tokens (``token``/``token_key``) and Proxmox credentials
# (``password``/``token_value``).  The extracted detail is written to job logs and
# the ``Job.error`` field, which are long-lived and readable by any user with
# permission to view jobs — so redaction happens here, on the way out.
_SENSITIVE_KEY_MARKERS: tuple[str, ...] = (
    "token",
    "password",
    "passwd",
    "secret",
    "apikey",
    "privatekey",
    "sshkeys",
    "authorization",
    "credential",
)
_REDACTED = "[redacted]"
_REDACTION_DEPTH_LIMIT = 6
# Past the depth limit the value is returned *redacted*, not raw.  Returning the
# original object was the whole hole: a payload nested deeper than the limit
# skipped redaction entirely and went to the job log verbatim.
_REDACTED_DEEP = "[redacted: nesting depth limit]"

# FastAPI reports a validation error as ``{"loc": [...], "msg": ..., "input": ...}``
# where ``input`` echoes the *submitted value* for the field named by ``loc``.
# When that field is a credential the secret lands in a **scalar** ``input``, with
# nothing sensitive in its own key — key-only matching never sees it.  These are
# the sibling keys whose value is redacted when ``loc`` names a sensitive field.
_LOC_ECHO_KEYS: frozenset[str] = frozenset({"input", "input_value"})

# Credential assignments embedded in a *string* — Pydantic renders the rejected
# object into ``msg``/``python_exception`` text (``input_value={'token': 'nbt_…'}``),
# which no amount of key matching can reach because there is no mapping left.
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"""(?ix)
    (?P<key>[a-z0-9_\-]*
        (?:token|password|passwd|secret|api[_\-\s]?key|private[_\-\s]?key
           |sshkeys|authorization|credential)
        [a-z0-9_\-]*)
    (?P<quote_end>['"]?)
    (?P<sep>\s*[:=]\s*)
    # The scheme alternative must come first.  ``Authorization: Bearer <jwt>``
    # otherwise matches with the value ``Bearer`` alone, which redacts the
    # *keyword* and leaves the token behind it in the clear — and, worse, then
    # hides it from the bearer sweep below, which no longer sees a scheme to
    # anchor on.
    (?P<value>(?:bearer|basic)\s+[^\s,;)}\]]+|'[^']*'|"[^"]*"|[^\s,;)}\]]+)
    """
)
# ``Bearer <jwt>`` rendered into a message with no credential-named key in front
# of it — a quoted request header, say.  The assignment sweep cannot see those.
_BEARER_RE = re.compile(r"(?i)\b(bearer|basic)\s+([a-z0-9._\-+/=]{8,})")


def _normalize_key(key: str) -> str:
    """Fold a key to a separator-free lowercase form for marker matching.

    ``x-proxbox-api-key``, ``api_key``, and ``ApiKey`` are the same field wearing
    three spellings; only the underscore variant used to match, so the HTTP header
    form sailed through unredacted.
    """
    return re.sub(r"[-_\s]+", "", key.lower())


def _is_sensitive_key(key: object) -> bool:
    """Return ``True`` when a mapping key names a credential-bearing field."""
    if not isinstance(key, str):
        return False
    normalized = _normalize_key(key)
    return any(marker in normalized for marker in _SENSITIVE_KEY_MARKERS)


def _loc_names_sensitive_field(loc: object) -> bool:
    """Return ``True`` when a FastAPI ``loc`` path names a credential field."""
    if not isinstance(loc, (list, tuple)):
        return False
    return any(_is_sensitive_key(part) for part in loc)


def redact_sensitive_text(value: str) -> str:
    """Redact credential assignments and bearer tokens inside a free-text string.

    Structural redaction cannot reach a secret that has already been rendered
    into prose, and both Pydantic and proxbox-api do exactly that.
    """
    redacted = _SENSITIVE_ASSIGNMENT_RE.sub(
        lambda m: (
            f"{m.group('key')}{m.group('quote_end')}{m.group('sep')}"
            + (
                f"{m.group('value')[0]}{_REDACTED}{m.group('value')[0]}"
                if m.group("value")[:1] in {"'", '"'}
                else _REDACTED
            )
        ),
        value,
    )
    return _BEARER_RE.sub(lambda m: f"{m.group(1)} {_REDACTED}", redacted)


def redact_sensitive(value: object, _depth: int = 0) -> object:
    """Recursively replace credential-bearing values with ``[redacted]``.

    Keys are matched first, so a redacted payload keeps its shape and remains
    diagnosable — an operator still sees *which* field the backend rejected, just
    not its contents.  Key matching alone is not sufficient, so two more passes
    run alongside it: a FastAPI ``loc``/``input`` pair redacts the echoed value
    when the sibling ``loc`` names a credential field, and every string is swept
    for credential assignments that were already rendered into prose.
    """
    if _depth > _REDACTION_DEPTH_LIMIT:
        return _REDACTED_DEEP
    if isinstance(value, dict):
        echo_is_sensitive = _loc_names_sensitive_field(value.get("loc"))
        return {
            key: (
                _REDACTED
                if _is_sensitive_key(key)
                or (
                    echo_is_sensitive and isinstance(key, str) and key in _LOC_ECHO_KEYS
                )
                else redact_sensitive(item, _depth + 1)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive(item, _depth + 1) for item in value]
    if isinstance(value, tuple):
        return [redact_sensitive(item, _depth + 1) for item in value]
    if isinstance(value, str):
        return redact_sensitive_text(value)
    return value


def _detail_to_text(value: object) -> str:
    """Render an already-redacted ``detail`` as a string.

    FastAPI reports validation errors as a *list* of objects, so ``detail`` is
    not always a string. Returning it unconverted broke this function's
    ``-> str`` contract and pushed a raw ``list`` into f-strings and log records.
    """
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):  # pragma: no cover - json.dumps is total here
        return str(value)


def redact_backend_detail(value: object) -> str:
    """Redact a backend-supplied error detail and render it as text.

    The public one-call form of ``redact_sensitive()`` + ``_detail_to_text()``,
    for the code paths that mint an error string straight from a parsed backend
    body instead of going through ``extract_backend_error_detail()`` — the SSE
    stream reader and the ``status >= 400`` branches in
    ``services/backend_proxy.py``. Those strings end up in ``job.logger`` calls
    and in the ``RuntimeError`` a failed stage raises, both of which are
    persisted on the Job row, so they need the same redaction as every other
    error detail. Accepts any JSON value because FastAPI reports ``detail`` as a
    list of objects at least as often as a string.
    """
    return _detail_to_text(redact_sensitive(value))


def _extract_host_port_from_request_error(
    message: str,
) -> tuple[str | None, str | None]:
    """Best-effort parse of host/port from requests connection error strings."""
    host_match = re.search(r"host='([^']+)'", message)
    port_match = re.search(r"port=(\d+)", message)
    host = host_match.group(1) if host_match else None
    port = port_match.group(1) if port_match else None
    return host, port


def parse_requests_response_json(
    response: requests.Response,
    *,
    log_label: str = "backend",
) -> tuple[object | None, str | None]:
    """Parse JSON from an HTTP response after ``raise_for_status``.

    Returns ``(data, None)`` on success, or ``(None, user_facing_detail)`` when the body
    is not valid JSON (avoids uncaught decode errors in Django views).
    """
    try:
        return response.json(), None
    except (_JSON_DECODE_ERROR, ValueError) as exc:
        url = getattr(response, "url", "") or ""
        logger.warning(
            "Non-JSON HTTP %s body from %s (%s): %s",
            getattr(response, "status_code", "?"),
            log_label,
            url,
            exc,
        )
        detail = (
            "ProxBox backend returned a response that is not valid JSON. "
            "Check that the FastAPI URL points to proxbox-api, not another service."
        )
        return None, detail


def extract_backend_error_detail(
    exc: requests.exceptions.RequestException,
) -> tuple[str, int | None]:
    """Normalize a requests error into a user-facing message and HTTP status if known."""
    response = getattr(exc, "response", None)
    if response is None:
        error_text = str(exc)
        lowered = error_text.lower()

        if isinstance(exc, requests.exceptions.ConnectionError) or (
            "connection refused" in lowered
            or "failed to establish a new connection" in lowered
            or "max retries exceeded" in lowered
        ):
            host, port = _extract_host_port_from_request_error(error_text)
            target = (
                f"{host}:{port}"
                if host and port
                else (host or "configured FastAPI endpoint")
            )
            return (
                "Unable to reach ProxBox backend at "
                f"{target}. Connection was refused. "
                "Verify proxbox-api is running and listening on the configured host/port, "
                "then confirm the plugin FastAPI endpoint settings."
            ), None

        if isinstance(exc, requests.exceptions.Timeout) or "timed out" in lowered:
            host, port = _extract_host_port_from_request_error(error_text)
            target = (
                f"{host}:{port}" if host and port else "configured FastAPI endpoint"
            )
            return (
                "Timed out while connecting to ProxBox backend at "
                f"{target}. Verify network reachability and that proxbox-api is healthy."
            ), None

        # A transport exception carries no parsed body to key-match against, but
        # its rendered text can still quote the request that failed.
        return redact_sensitive_text(error_text), None

    status_code = getattr(response, "status_code", None)
    detail = None

    try:
        payload = redact_sensitive(response.json())
        if isinstance(payload, dict):
            payload_detail = payload.get("detail")
            payload_message = payload.get("message")
            generic_detail = {
                "internal server error",
                "server error",
            }
            if (
                isinstance(payload_detail, str)
                and payload_detail.strip().lower() in generic_detail
                and payload_message
            ):
                detail = _detail_to_text(payload_message)
            elif payload_detail:
                detail = _detail_to_text(payload_detail)
            elif payload_message:
                detail = _detail_to_text(payload_message)
            python_exception = payload.get("python_exception")
            if python_exception:
                detail = (
                    f"{detail} ({_detail_to_text(python_exception)})"
                    if detail
                    else _detail_to_text(python_exception)
                )
    except Exception:
        detail = None

    if not detail:
        body = (getattr(response, "text", "") or "").strip()
        content_type = (getattr(response, "headers", {}) or {}).get("Content-Type", "")
        response_url = getattr(response, "url", "") or ""
        body_lower = body.lower()

        if (
            "text/html" in content_type.lower() or "<html" in body_lower
        ) and status_code in {400, 401, 403, 404}:
            detail = (
                "Backend returned HTML instead of ProxBox API JSON"
                f" (HTTP {status_code})."
            )
            if response_url:
                detail += f" URL: {response_url}."
            detail += (
                " Check FastAPI endpoint host/port; it may be pointing to NetBox UI "
                "instead of proxbox-api."
            )
            return detail, status_code

        detail = (
            f"Backend returned HTTP {status_code} without a JSON error detail."
            if status_code
            else redact_sensitive_text(str(exc))
        )

    return detail, status_code


def extract_proxmox_backend_error_detail(
    exc: requests.exceptions.RequestException,
    *,
    proxmox_host: str,
    proxmox_port: int | None,
    backend_url: str,
) -> tuple[str, int | None]:
    """Like extract_backend_error_detail, but adds Proxmox target context when there is no response."""
    response = getattr(exc, "response", None)
    if response is not None:
        return extract_backend_error_detail(exc)

    target = proxmox_host
    if proxmox_port:
        target = f"{target}:{proxmox_port}"

    detail = (
        "ProxBox backend could not connect to the configured Proxmox endpoint"
        f" ({target}). Backend route: {backend_url}. Upstream error: {exc}"
    )
    return detail, None
