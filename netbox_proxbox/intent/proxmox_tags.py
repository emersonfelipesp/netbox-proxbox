"""Best-effort Proxmox tag helpers for safe-delete requests."""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

PENDING_DELETION_TAG = "proxbox-pending-deletion"
TAG_REQUEST_TIMEOUT_SECONDS = 30


def _endpoint_value(endpoint: Any, name: str, default: Any = None) -> Any:
    if isinstance(endpoint, dict):
        return endpoint.get(name, default)
    return getattr(endpoint, name, default)


def tag_pending_deletion(endpoint: Any, vmid: Any, node: Any, kind: Any) -> bool:
    """Ask proxbox-api to add the pending-delete tag without destroying the VM."""
    try:
        http_url = _endpoint_value(endpoint, "http_url") or _endpoint_value(
            endpoint, "url"
        )
        if not http_url:
            logger.warning(
                "Cannot tag VM %s pending deletion: FastAPI endpoint has no URL.",
                vmid,
            )
            return False

        url = f"{str(http_url).rstrip('/')}/intent/tag-pending-deletion"
        response = requests.put(
            url,
            json={
                "vmid": vmid,
                "node": node or "",
                "kind": kind,
                "tag": PENDING_DELETION_TAG,
            },
            headers=dict(_endpoint_value(endpoint, "headers", {}) or {}),
            timeout=TAG_REQUEST_TIMEOUT_SECONDS,
            verify=bool(_endpoint_value(endpoint, "verify_ssl", True)),
        )
        response.raise_for_status()
        body = response.json()
        if isinstance(body, dict) and body.get("ok") is False:
            logger.warning(
                "proxbox-api declined pending-deletion tag for VM %s on node %s: %s",
                vmid,
                node,
                body,
            )
            return False
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to tag VM %s on node %s as pending deletion: %s",
            vmid,
            node,
            exc,
        )
        return False

    return True


def untag_pending_deletion(endpoint: Any, vmid: Any, node: Any, kind: Any) -> bool:
    """Ask proxbox-api to remove the pending-delete tag without destroying the VM."""
    try:
        http_url = _endpoint_value(endpoint, "http_url") or _endpoint_value(
            endpoint, "url"
        )
        if not http_url:
            logger.warning(
                "Cannot untag VM %s pending deletion: FastAPI endpoint has no URL.",
                vmid,
            )
            return False

        url = f"{str(http_url).rstrip('/')}/intent/untag-pending-deletion"
        response = requests.put(
            url,
            json={
                "vmid": vmid,
                "node": node or "",
                "kind": kind,
                "tag": PENDING_DELETION_TAG,
            },
            headers=dict(_endpoint_value(endpoint, "headers", {}) or {}),
            timeout=TAG_REQUEST_TIMEOUT_SECONDS,
            verify=bool(_endpoint_value(endpoint, "verify_ssl", True)),
        )
        response.raise_for_status()
        body = response.json()
        if isinstance(body, dict) and body.get("ok") is False:
            logger.warning(
                "proxbox-api declined pending-deletion untag for VM %s on node %s: %s",
                vmid,
                node,
                body,
            )
            return False
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to remove pending-deletion tag from VM %s on node %s: %s",
            vmid,
            node,
            exc,
        )
        return False

    return True


__all__ = (
    "PENDING_DELETION_TAG",
    "tag_pending_deletion",
    "untag_pending_deletion",
)
