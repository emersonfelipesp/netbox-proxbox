"""Fetch repository markdown content from GitHub for plugin pages."""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = (5, 30)


def get(**kwargs: object) -> str | None:
    """Download markdown text for ``filename`` from the upstream netbox-proxbox repo."""
    owner = "netdevopsbr"
    repo = "netbox-proxbox"

    filename = kwargs.get("filename")
    if not filename:
        return None

    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{filename}"

    try:
        response = requests.get(url, timeout=_REQUEST_TIMEOUT)
    except requests.exceptions.RequestException as exc:
        logger.warning("GitHub API request failed for %s: %s", url, exc)
        return None

    if response.status_code != 200:
        detail = _safe_github_error_message(response)
        logger.warning(
            "GitHub API returned HTTP %s for %s: %s",
            response.status_code,
            url,
            detail,
        )
        return None

    try:
        payload: dict[str, Any] = response.json()
    except (ValueError, requests.exceptions.JSONDecodeError):
        logger.warning("GitHub API returned non-JSON for %s", url)
        return None

    content_url = payload.get("download_url")
    if not content_url:
        return None

    try:
        markdown_content = requests.get(content_url, timeout=_REQUEST_TIMEOUT)
    except requests.exceptions.RequestException as exc:
        logger.warning("GitHub raw download failed for %s: %s", content_url, exc)
        return None

    if markdown_content.status_code == 200:
        return markdown_content.text
    logger.warning(
        "GitHub raw download returned HTTP %s for %s",
        markdown_content.status_code,
        content_url,
    )
    return None


def _safe_github_error_message(response: requests.Response) -> str:
    """Return a short error string from a failed GitHub API response body."""
    try:
        body = response.json()
        if isinstance(body, dict) and body.get("message"):
            return str(body["message"])
    except (ValueError, requests.exceptions.JSONDecodeError, TypeError):
        pass
    text = (response.text or "").strip()
    return text[:500] if text else f"HTTP {response.status_code}"
