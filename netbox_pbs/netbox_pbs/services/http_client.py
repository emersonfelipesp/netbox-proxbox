"""Thin HTTP/SSE client for the proxbox-api ``/pbs/sync/*`` surface.

PBS sync is orchestrated by ``PBSSyncJob`` (see ``netbox_pbs.jobs``). For each
stage in :data:`PBS_STAGES_FULL` the job calls :func:`run_pbs_sync_stage`,
which streams the proxbox-api SSE response and returns a structured result.

The backend base URL is resolved from ``netbox_proxbox.FastAPIEndpoint`` via
``netbox_proxbox.services.backend_context.get_fastapi_request_context()``.
netbox_proxbox is a hard dependency declared in
``PBSConfig.required_plugins``, so the import is unconditional.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import requests

from netbox_proxbox.services.backend_context import get_fastapi_request_context

logger = logging.getLogger("netbox_pbs.http_client")


PBS_STAGE_DATASTORES = "datastores"
PBS_STAGE_SNAPSHOTS = "snapshots"
PBS_STAGE_JOBS = "jobs"
PBS_STAGE_NODE = "node"

PBS_STAGES_FULL: tuple[str, ...] = (
    PBS_STAGE_DATASTORES,
    PBS_STAGE_SNAPSHOTS,
    PBS_STAGE_JOBS,
    PBS_STAGE_NODE,
)

# Long read timeout between SSE chunks — PBS syncs may pause while the
# backend walks every snapshot in a large datastore.
PBS_SSE_READ_TIMEOUT_SECONDS = 3600


@dataclass
class PBSStageResult:
    """Outcome of a single ``/pbs/sync/<stage>`` SSE run."""

    stage: str
    success: bool
    events: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


def _resolve_backend_context() -> Any | None:
    """Return a ``BackendRequestContext`` from netbox_proxbox, or ``None``.

    PBS reuses the single ``FastAPIEndpoint`` row owned by netbox_proxbox.
    Returns ``None`` if the row is missing or unreachable; the caller emits
    a failed :class:`PBSStageResult` rather than raising.
    """
    try:
        return get_fastapi_request_context()
    except Exception:
        logger.exception("Failed to resolve FastAPI request context for PBS sync")
        return None


def _build_query_params(params: dict[str, Any]) -> dict[str, str]:
    """Project the job params dict into the query string sent to proxbox-api."""
    qs: dict[str, str] = {}
    schema_id = params.get("netbox_branch_schema_id")
    if schema_id:
        qs["netbox_branch_schema_id"] = str(schema_id)
    endpoint_ids = params.get("pbs_endpoint_ids") or []
    if endpoint_ids:
        qs["pbs_endpoint_ids"] = ",".join(str(x) for x in endpoint_ids if str(x))
    return qs


def run_pbs_sync_stage(
    stage: str,
    params: dict[str, Any],
    *,
    logger_: logging.Logger | None = None,
) -> PBSStageResult:
    """Hit ``/pbs/sync/<stage>`` (SSE) and accumulate events into a result.

    ``params`` carries the orchestration context built by ``PBSSyncJob.run``;
    notably it must contain ``netbox_branch_schema_id`` (or ``None``) so the
    backend writes through the same NetBox branch as the rest of the job.
    """
    log = logger_ or logger

    if stage not in PBS_STAGES_FULL:
        return PBSStageResult(
            stage=stage,
            success=False,
            error=f"Unknown PBS sync stage: {stage!r}",
        )

    context = _resolve_backend_context()
    if context is None or not getattr(context, "http_url", None):
        return PBSStageResult(
            stage=stage,
            success=False,
            error="No FastAPIEndpoint configured for PBS sync.",
        )

    base_url = str(context.http_url).rstrip("/")
    url = f"{base_url}/pbs/sync/{stage}"
    query = _build_query_params(params)
    headers = {
        "Accept": "text/event-stream",
        **dict(getattr(context, "headers", {}) or {}),
    }
    verify_ssl = bool(getattr(context, "verify_ssl", True))

    log.info("PBS sync stage start: stage=%s url=%s", stage, url)

    events: list[dict[str, Any]] = []
    try:
        response = requests.get(
            url,
            params=query,
            headers=headers,
            verify=verify_ssl,
            stream=True,
            timeout=(30, PBS_SSE_READ_TIMEOUT_SECONDS),
        )
        response.raise_for_status()
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            if line.startswith("data:"):
                payload = line[len("data:") :].strip()
                if not payload:
                    continue
                try:
                    event = json.loads(payload)
                except json.JSONDecodeError:
                    event = {"raw": payload}
                events.append(event)
                if isinstance(event, dict) and event.get("event") == "complete":
                    break
    except requests.RequestException as exc:
        log.exception("PBS sync stage failed: stage=%s", stage)
        return PBSStageResult(
            stage=stage,
            success=False,
            events=events,
            error=str(exc),
        )

    log.info("PBS sync stage complete: stage=%s events=%d", stage, len(events))
    return PBSStageResult(stage=stage, success=True, events=events)
