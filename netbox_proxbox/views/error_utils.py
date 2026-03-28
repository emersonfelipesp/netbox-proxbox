"""Shared helpers for normalizing backend and Proxmox error details."""

from __future__ import annotations

import requests


def extract_backend_error_detail(
    exc: requests.exceptions.RequestException,
) -> tuple[str, int | None]:
    response = getattr(exc, "response", None)
    if response is None:
        return str(exc), None

    status_code = getattr(response, "status_code", None)
    detail = None

    try:
        payload = response.json()
        if isinstance(payload, dict):
            detail = payload.get("detail") or payload.get("message")
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

        detail = body[:500] if body else str(exc)

    return detail, status_code


def extract_proxmox_backend_error_detail(
    exc: requests.exceptions.RequestException,
    *,
    proxmox_host: str,
    proxmox_port: int | None,
    backend_url: str,
) -> tuple[str, int | None]:
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
