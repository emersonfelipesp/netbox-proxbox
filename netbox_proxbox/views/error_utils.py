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

        return error_text, None

    status_code = getattr(response, "status_code", None)
    detail = None

    try:
        payload = response.json()
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
                detail = payload_message
            else:
                detail = payload_detail or payload_message
            python_exception = payload.get("python_exception")
            if python_exception:
                detail = (
                    f"{detail} ({python_exception})"
                    if detail
                    else str(python_exception)
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
            else str(exc)
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
