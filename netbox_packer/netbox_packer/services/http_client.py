"""HTTP client for proxbox-api /cloud/image-factory/* endpoints."""

from __future__ import annotations

import json
import logging
from typing import Any, Generator

import requests
from netbox_proxbox.services.backend_context import get_fastapi_request_context

logger = logging.getLogger("netbox_packer.http_client")

# Short connect timeout, long read timeout for SSE streams that can run hours.
_FACTORY_TIMEOUT: tuple[float, float] = (5.0, 3600.0)
# Short timeout pair for non-streaming calls.
_FACTORY_JSON_TIMEOUT: tuple[float, float] = (5.0, 60.0)


class ImageFactoryBackendError(RuntimeError):
    """Raised when the proxbox-api image factory route returns an error or is unreachable."""


def _request_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _resolve_context() -> tuple[str, dict[str, str], bool]:
    context = get_fastapi_request_context()
    if context is None or not context.http_url:
        raise ImageFactoryBackendError(
            "No FastAPIEndpoint configured; cannot reach proxbox-api /cloud/image-factory/* routes."
        )
    return (
        context.http_url,
        dict(context.headers or {}),
        bool(context.verify_ssl),
    )


def _build_payload(
    build: Any,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Assemble a PackerImageBuildRequest payload dict from a PackerImageBuild instance."""
    definition = build.definition
    payload: dict[str, Any] = {
        "endpoint_id": definition.proxmox_endpoint_id,
        "target_node": definition.target_node,
        "builder_type": definition.builder_type,
        "output_vmid": build.output_vmid,
        "output_name": build.output_name,
        "os_family": definition.os_family,
        "os_release": definition.os_release or "",
        "image_version": build.image_version,
        "vm_storage": definition.default_storage,
        "bridge": definition.default_bridge,
        "provisioner_recipe": definition.provisioner_recipe,
        "variables": definition.default_variables or {},
        "force": force,
        "dry_run": dry_run,
    }
    if definition.builder_type == "proxmox-clone":
        payload["template_vmid"] = definition.source_template_vmid
    elif definition.builder_type == "proxmox-iso":
        # Prefer explicit storage ref; fall back to URL.
        iso_file = definition.iso_storage or ""
        iso_url = definition.iso_url or ""
        payload["iso_file"] = iso_file or iso_url
        payload["iso_checksum"] = definition.iso_checksum or "none"
        if definition.iso_storage:
            payload["iso_storage"] = definition.iso_storage
    return payload


def submit_image_build(
    *,
    build: Any,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """POST a new image build to proxbox-api and return the response payload."""
    base_url, headers, verify_ssl = _resolve_context()
    url = _request_url(base_url, "cloud/image-factory/builds")
    payload = _build_payload(build, force=force, dry_run=dry_run)

    logger.debug("Submitting image build to %s payload=%s", url, payload)
    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=_FACTORY_JSON_TIMEOUT,
            verify=verify_ssl,
        )
    except requests.RequestException as exc:
        raise ImageFactoryBackendError(
            f"Image factory submit request failed: {exc}"
        ) from exc

    if response.status_code >= 400:
        raise ImageFactoryBackendError(
            f"Image factory backend returned HTTP {response.status_code} for submit: {response.text[:500]}"
        )

    try:
        return response.json()
    except ValueError as exc:
        raise ImageFactoryBackendError(
            f"Image factory backend returned non-JSON body on submit: {exc}"
        ) from exc


def stream_image_build(
    *,
    backend_build_id: str,
) -> Generator[tuple[str, dict[str, Any]], None, None]:
    """GET the SSE stream for a running build; yields (event_name, data_dict) pairs."""
    base_url, headers, verify_ssl = _resolve_context()
    url = _request_url(
        base_url, f"cloud/image-factory/builds/{backend_build_id}/stream"
    )

    logger.debug("Opening image factory SSE stream %s", url)
    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=_FACTORY_TIMEOUT,
            verify=verify_ssl,
            stream=True,
        )
    except requests.RequestException as exc:
        raise ImageFactoryBackendError(
            f"Image factory stream request failed for {backend_build_id}: {exc}"
        ) from exc

    if response.status_code >= 400:
        raise ImageFactoryBackendError(
            f"Image factory stream returned HTTP {response.status_code} for {backend_build_id}: "
            f"{response.text[:500]}"
        )

    event_name = ""
    data_lines: list[str] = []

    def _flush() -> Generator[tuple[str, dict[str, Any]], None, None]:
        nonlocal event_name, data_lines
        if not data_lines:
            event_name = ""
            return
        payload_str = "\n".join(data_lines)
        try:
            data_obj = json.loads(payload_str)
        except ValueError:
            data_obj = {"raw": payload_str}
        ev = event_name or "message"
        if not isinstance(data_obj, dict):
            data_obj = {"raw": data_obj}
        yield (ev, data_obj)
        event_name = ""
        data_lines = []

    for raw_line in response.iter_lines(decode_unicode=True):
        if raw_line is None:
            continue
        line = str(raw_line)
        if line == "":
            yield from _flush()
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            yield from _flush()
            event_name = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
        else:
            data_lines.append(line)

    yield from _flush()


def cancel_image_build(*, backend_build_id: str) -> dict[str, Any]:
    """POST to the cancel endpoint for a running backend build."""
    base_url, headers, verify_ssl = _resolve_context()
    url = _request_url(
        base_url, f"cloud/image-factory/builds/{backend_build_id}/cancel"
    )

    logger.debug("Cancelling image factory build %s", backend_build_id)
    try:
        response = requests.post(
            url,
            headers=headers,
            timeout=(5.0, 30.0),
            verify=verify_ssl,
        )
    except requests.RequestException as exc:
        raise ImageFactoryBackendError(
            f"Image factory cancel request failed for {backend_build_id}: {exc}"
        ) from exc

    if response.status_code >= 400:
        raise ImageFactoryBackendError(
            f"Image factory cancel returned HTTP {response.status_code} for {backend_build_id}: "
            f"{response.text[:500]}"
        )

    try:
        return response.json()
    except ValueError:
        return {"status": "cancelled"}
