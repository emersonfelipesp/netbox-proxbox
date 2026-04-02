"""Sync service for Proxmox backup routines from proxbox-api."""

from __future__ import annotations

import logging

import requests

from django.db import transaction

from netbox_proxbox.choices import BackupRoutineStatusChoices
from netbox_proxbox.models import (
    BackupRoutine,
    ProxmoxEndpoint,
    ProxmoxNode,
    ProxmoxStorage,
)
from netbox_proxbox.schemas.backup_routine import (
    BackupRoutineSchema,
    GetClusterBackupIdResponse,
)
from netbox_proxbox.services.backend_proxy import get_fastapi_request_context

logger = logging.getLogger(__name__)

SYNC_TIMEOUT = 30


def _get_backup_routine_id_from_job_id(job_id: str) -> str | None:
    """Extract the numeric ID part from a job_id like 'local:123'."""
    if ":" in job_id:
        return job_id.split(":", 1)[1]
    return job_id


def sync_backup_routines(
    endpoint_id: int,
    fastapi_url: str | None = None,
    auth_headers: dict | None = None,
) -> dict:
    """
    Sync backup routines for a Proxmox endpoint from proxbox-api.

    Fetches the list of backup job IDs from GET /api2/json/cluster/backup, then
    fetches full details for each job from GET /api2/json/cluster/backup/{id},
    and creates/updates BackupRoutine records. Routines that no longer exist in
    Proxmox are marked as stale.

    Args:
        endpoint_id: ProxmoxEndpoint ID to sync.
        fastapi_url: Optional FastAPI base URL override.
        auth_headers: Optional auth headers override.

    Returns:
        dict with sync status and counts.
    """
    try:
        endpoint = ProxmoxEndpoint.objects.get(pk=endpoint_id)
    except ProxmoxEndpoint.DoesNotExist:
        logger.error("ProxmoxEndpoint %s not found", endpoint_id)
        return {"success": False, "error": "Endpoint not found"}

    if not fastapi_url:
        ctx = get_fastapi_request_context()
        if ctx is None or not ctx.http_url:
            logger.error("FastAPI endpoint not configured or has no URL")
            return {"success": False, "error": "FastAPI URL not configured"}
        fastapi_url = ctx.http_url
        verify_ssl = bool(ctx.verify_ssl)
        if auth_headers is None:
            auth_headers = ctx.headers or {}
    else:
        verify_ssl = True

    if auth_headers is None:
        auth_headers = {}

    result = {
        "success": False,
        "endpoint_id": endpoint_id,
        "routines_created": 0,
        "routines_updated": 0,
        "routines_stale": 0,
        "error": None,
    }

    try:
        list_resp = requests.get(
            f"{fastapi_url}/proxmox/api2/cluster/backup",
            headers=auth_headers,
            verify=verify_ssl,
            timeout=SYNC_TIMEOUT,
        )
        list_resp.raise_for_status()
        job_list = list_resp.json()
    except requests.RequestException as exc:
        error_msg = f"HTTP error fetching backup routine list: {exc}"
        logger.error(error_msg)
        result["error"] = error_msg
        return result

    if not isinstance(job_list, list):
        job_list = []

    job_ids = [item.get("id") for item in job_list if item.get("id")]

    with transaction.atomic():
        existing_job_ids = set(
            BackupRoutine.objects.filter(endpoint=endpoint).values_list(
                "job_id", flat=True
            )
        )
        synced_job_ids: set[str] = set()

        for job_id in job_ids:
            synced_job_ids.add(job_id)

            detail_resp = None
            try:
                detail_resp = requests.get(
                    f"{fastapi_url}/proxmox/api2/cluster/backup/{job_id}",
                    headers=auth_headers,
                    verify=verify_ssl,
                    timeout=SYNC_TIMEOUT,
                )
                detail_resp.raise_for_status()
                detail_data = detail_resp.json()
            except requests.RequestException as exc:
                logger.warning(
                    "Failed to fetch backup routine detail for %s (endpoint %s): %s",
                    job_id,
                    endpoint_id,
                    exc,
                )
                continue

            if isinstance(detail_data, dict):
                detail_data = [detail_data]
            elif not isinstance(detail_data, list):
                logger.warning(
                    "Unexpected backup routine detail response type for %s: %s",
                    job_id,
                    type(detail_data).__name__,
                )
                continue

            for raw_detail in detail_data:
                try:
                    validated = GetClusterBackupIdResponse.model_validate(raw_detail)
                except Exception as exc:
                    logger.warning(
                        "Failed to validate backup routine detail for %s: %s",
                        job_id,
                        exc,
                    )
                    continue

                schema = BackupRoutineSchema.from_proxmox_response(
                    validated.model_dump(by_alias=True), cluster_name=str(endpoint)
                )

                node_obj = None
                if schema.node:
                    try:
                        node_obj = ProxmoxNode.objects.get(
                            endpoint=endpoint, name=schema.node
                        )
                    except ProxmoxNode.DoesNotExist:
                        pass

                storage_obj = None
                if schema.storage:
                    try:
                        storage_obj = ProxmoxStorage.objects.filter(
                            name=schema.storage
                        ).first()
                    except Exception:
                        pass

                fleecing_storage_obj = None
                raw_fleecing_storage = raw_detail.get(
                    "fleecing-storage"
                ) or raw_detail.get("fleecing_storage")
                if raw_fleecing_storage:
                    try:
                        fleecing_storage_obj = ProxmoxStorage.objects.filter(
                            name=raw_fleecing_storage
                        ).first()
                    except Exception:
                        pass

                routine_defaults = {
                    "enabled": schema.enabled,
                    "schedule": schema.schedule or "",
                    "next_run": schema.next_run,
                    "node": node_obj,
                    "storage": storage_obj,
                    "selection": schema.selection,
                    "comment": schema.comment,
                    "status": BackupRoutineStatusChoices.ACTIVE,
                    "keep_last": schema.keep_last,
                    "keep_daily": schema.keep_daily,
                    "keep_weekly": schema.keep_weekly,
                    "keep_monthly": schema.keep_monthly,
                    "keep_yearly": schema.keep_yearly,
                    "keep_all": schema.keep_all,
                    "notes_template": schema.notes_template or "",
                    "bwlimit": schema.bwlimit,
                    "zstd": schema.zstd,
                    "io_workers": schema.io_workers,
                    "fleecing": schema.fleecing or "",
                    "fleecing_storage": fleecing_storage_obj,
                    "repeat_missed": schema.repeat_missed,
                    "pbs_change_detection_mode": schema.pbs_change_detection_mode or "",
                    "raw_config": raw_detail,
                }

                routine, created = BackupRoutine.objects.update_or_create(
                    endpoint=endpoint,
                    job_id=job_id,
                    defaults=routine_defaults,
                )

                if created:
                    result["routines_created"] += 1
                    logger.info(
                        "Created backup routine %s for endpoint %s", job_id, endpoint_id
                    )
                else:
                    result["routines_updated"] += 1

        stale_job_ids = existing_job_ids - synced_job_ids
        if stale_job_ids:
            stale_count, _ = BackupRoutine.objects.filter(
                endpoint=endpoint, job_id__in=stale_job_ids
            ).update(status=BackupRoutineStatusChoices.STALE)
            result["routines_stale"] = stale_count
            logger.info(
                "Marked %s stale backup routines for endpoint %s",
                stale_count,
                endpoint_id,
            )

    result["success"] = True
    logger.info(
        "Successfully synced backup routines for endpoint %s: %s created, %s updated, %s stale",
        endpoint_id,
        result["routines_created"],
        result["routines_updated"],
        result["routines_stale"],
    )
    return result
