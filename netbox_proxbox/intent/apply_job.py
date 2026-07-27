"""Proxmox apply executor for merged NetBox intent branches."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import requests
from django.utils import timezone
from netbox.constants import RQ_QUEUE_DEFAULT
from netbox.jobs import JobRunner

try:
    from netbox.jobs import Job
except ImportError:  # pragma: no cover - test stubs expose only JobRunner
    Job = Any  # type: ignore[misc,assignment]

from netbox_proxbox.intent.cf_writes import stamp_intent_state
from netbox_proxbox.intent.diff_classify import classify_diff
from netbox_proxbox.intent.firewall_common import save_status_for_firewall_object
from netbox_proxbox.intent.firewall_payload import (
    build_firewall_apply_diff,
    default_proxmox_endpoint_id,
    firewall_changediffs,
    firewall_result_key,
    unsupported_firewall_diff_message,
)
from netbox_proxbox.intent.payload import (
    build_lxc_payload,
    build_update_delta,
    build_vm_payload,
)
from netbox_proxbox.intent.proxmox_tags import tag_pending_deletion
from netbox_proxbox.intent.snapshot import build_metadata_snapshot
from netbox_proxbox.models import (
    DeletionRequest,
    ProxmoxApplyJob as ProxmoxApplyJobModel,
)
from netbox_proxbox.services.backend_context import get_fastapi_request_context
from netbox_proxbox.views.error_utils import extract_backend_error_detail

PROXBOX_APPLY_JOB_TIMEOUT = 3600

__all__ = ("PROXBOX_APPLY_JOB_TIMEOUT", "ProxmoxApplyJob")

logger = logging.getLogger(__name__)

_VM_MODEL = "virtualmachine"
_CREATE_PERMISSIONS = {
    "qemu": "netbox_proxbox.intent_create_vm",
    "lxc": "netbox_proxbox.intent_create_lxc",
}
_UPDATE_PERMISSIONS = {
    "qemu": "netbox_proxbox.intent_update_vm",
    "lxc": "netbox_proxbox.intent_update_lxc",
}
_DELETE_PERMISSIONS = {
    "qemu": "netbox_proxbox.intent_delete_vm",
    "lxc": "netbox_proxbox.intent_delete_lxc",
}
_SUCCESS_STATUSES = {
    "succeeded",
    "success",
    "applied",
    "intent-logged",
    "delete-pending-approval",
}
_FAILED_STATUSES = {"failed"}


def _normalize_run_uuid(value: uuid.UUID | str | None) -> uuid.UUID:
    if value is None:
        return uuid.uuid4()
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _virtualmachine_changediffs(branch: Any) -> Any:
    changediff_qs = getattr(branch, "changediff_set", None)
    if changediff_qs is None:
        return []
    return changediff_qs.filter(object_type__model=_VM_MODEL)


def _diff_identifier(row: Any, fallback: int) -> str:
    for attr in ("object_repr", "object_id", "pk"):
        value = getattr(row, attr, None)
        if value not in (None, ""):
            return str(value)
    return f"changediff-{fallback}"


def _changediff_vm(row: Any) -> Any:
    vm = getattr(row, "object", None)
    if vm is not None:
        return vm

    object_id = getattr(row, "object_id", None)
    if object_id is None:
        return None

    from virtualization.models import VirtualMachine  # noqa: PLC0415

    return VirtualMachine.objects.get(pk=object_id)


def _call_apply_endpoint(
    payload: dict[str, Any],
    *,
    actor_username: str | None,
    endpoint_id: int | None = None,
    timeout: float = PROXBOX_APPLY_JOB_TIMEOUT,
) -> dict[str, Any]:
    context = get_fastapi_request_context()
    if context is None:
        raise RuntimeError("No FastAPIEndpoint is configured; cannot apply intent.")

    http_url = context.http_url
    if not http_url:
        raise RuntimeError("FastAPIEndpoint has no resolvable http_url.")

    url = f"{http_url.rstrip('/')}/intent/apply"
    if endpoint_id is not None:
        url = f"{url}?endpoint_id={int(endpoint_id)}"
    headers = dict(context.headers or {})
    headers.setdefault("Content-Type", "application/json")
    headers["X-Proxbox-Actor"] = actor_username or ""
    request_payload = dict(payload)
    request_payload.setdefault("actor", actor_username)

    try:
        response = requests.post(
            url,
            json=request_payload,
            headers=headers,
            timeout=timeout,
            verify=bool(context.verify_ssl),
            allow_redirects=False,
        )
    except requests.exceptions.SSLError as exc:
        raise RuntimeError(f"TLS error reaching {url}: {exc}") from exc
    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(f"Cannot reach proxbox-api at {url}: {exc}") from exc
    except requests.exceptions.Timeout as exc:
        raise RuntimeError(
            f"Apply request timed out after {timeout}s against {url}."
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Apply request failed: {exc}") from exc

    if response.status_code >= 400:
        try:
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            detail, _status = extract_backend_error_detail(exc)
        else:
            detail = f"Backend returned HTTP {response.status_code} without a JSON error detail."
        raise RuntimeError(
            f"proxbox-api returned HTTP {response.status_code} for /intent/apply: "
            f"{detail}"
        )

    try:
        body = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"proxbox-api returned a non-JSON body for /intent/apply: {exc}"
        ) from exc

    if not isinstance(body, dict):
        raise RuntimeError(
            f"proxbox-api returned an unexpected body for /intent/apply: {body!r}"
        )
    return body


def _first_apply_result(body: dict[str, Any]) -> dict[str, Any]:
    results = body.get("results") or []
    if isinstance(results, list) and results and isinstance(results[0], dict):
        return results[0]

    return {
        "status": "failed",
        "message": "proxbox-api returned no ApplyResultItem for the CREATE diff.",
    }


def _result_entry(
    *,
    vmid: Any,
    op: str,
    kind: str,
    status: str,
    message: str,
    proxmox_upid: Any = None,
) -> dict[str, object]:
    return {
        "vmid": vmid,
        "op": op,
        "kind": kind,
        "status": status,
        "message": message,
        "proxmox_upid": proxmox_upid,
    }


def _result_key(row: Any, vm: Any, vmid: Any, fallback: int) -> str:
    for value in (vmid, getattr(vm, "pk", None), getattr(vm, "id", None)):
        if value not in (None, ""):
            return str(value)
    return _diff_identifier(row, fallback)


def _status_is_success(status: str) -> bool:
    return status.lower() in _SUCCESS_STATUSES


def _state_from_results(results: dict[str, dict[str, object]]) -> str:
    statuses = [str(result.get("status") or "").lower() for result in results.values()]
    if not statuses or all(status in _SUCCESS_STATUSES for status in statuses):
        return ProxmoxApplyJobModel.State.succeeded
    if all(status in _FAILED_STATUSES for status in statuses):
        return ProxmoxApplyJobModel.State.failed
    return ProxmoxApplyJobModel.State.partial


class ProxmoxApplyJob(JobRunner):
    """Dispatch supported merged branch intent diffs to proxbox-api."""

    class Meta:
        name = "Proxmox Apply"

    @classmethod
    def enqueue(
        cls,
        *,
        branch: Any,
        user: Any,
        run_uuid: uuid.UUID | str | None = None,
        job_timeout: int = PROXBOX_APPLY_JOB_TIMEOUT,
    ) -> Job:
        """Create the apply model row and enqueue the NetBox default RQ job."""
        normalized_uuid = _normalize_run_uuid(run_uuid)
        branch_pk = getattr(branch, "pk", None)
        branch_name_value = str(getattr(branch, "name", "") or "")
        branch_label = branch_name_value or branch_pk or "unknown"
        apply_job = ProxmoxApplyJobModel.objects.create(
            branch_id=branch_pk,
            branch_name=branch_name_value,
            user=user,
            run_uuid=normalized_uuid,
            state=ProxmoxApplyJobModel.State.queued,
            name=f"Proxmox apply for branch {branch_label}",
        )

        job = super().enqueue(
            instance=None,
            user=user,
            queue_name=RQ_QUEUE_DEFAULT,
            job_timeout=job_timeout,
            name=apply_job.name,
            run_uuid=str(normalized_uuid),
        )
        job.data = {
            "proxbox_apply": {
                "apply_job_id": apply_job.pk,
                "branch_id": getattr(branch, "pk", None),
                "run_uuid": str(normalized_uuid),
            }
        }
        job.save(update_fields=["data"])
        logger.info(
            "Queued Proxmox apply %s for branch %s as NetBox Job %s.",
            normalized_uuid,
            getattr(branch, "pk", None),
            getattr(job, "pk", None),
        )
        return job

    def run(self, run_uuid: str, **kwargs: object) -> None:
        """Dispatch CREATE intent diffs to proxbox-api and record per-VM results."""
        del kwargs
        apply_job = None
        try:
            normalized_uuid = _normalize_run_uuid(run_uuid)
            apply_job = ProxmoxApplyJobModel.objects.select_related("user").get(
                run_uuid=normalized_uuid
            )
            apply_job.state = ProxmoxApplyJobModel.State.running
            apply_job.started_at = timezone.now()
            apply_job.save(update_fields=["state", "started_at"])

            branch = apply_job.branch
            actor = apply_job.user
            actor_username = getattr(actor, "username", None)
            logger.info(
                "Starting Proxmox apply %s for branch %s.",
                apply_job.run_uuid,
                getattr(branch, "pk", None),
            )

            results: dict[str, dict[str, object]] = {}
            for index, row in enumerate(_virtualmachine_changediffs(branch), start=1):
                vm = None
                vmid = None
                key = _diff_identifier(row, index)
                op = "update"
                kind = "qemu"
                try:
                    op, kind = classify_diff(row)
                    vm = _changediff_vm(row)
                    build_payload = (
                        build_lxc_payload if kind == "lxc" else build_vm_payload
                    )
                    payload = build_payload(vm) if vm is not None else {}
                    vmid = payload.get("vmid")
                    key = _result_key(row, vm, vmid, index)

                    if vm is None:
                        results[key] = _result_entry(
                            vmid=vmid,
                            op=op,
                            kind=kind,
                            status="failed",
                            message=(
                                "Could not resolve NetBox VM for ChangeDiff "
                                f"{_diff_identifier(row, index)}."
                            ),
                        )
                        continue

                    if op == "delete":
                        branch_custom_fields = (
                            getattr(branch, "custom_field_data", None) or {}
                        )
                        if (
                            not isinstance(branch_custom_fields, dict)
                            or branch_custom_fields.get("apply_destroy_confirmed")
                            is not True
                        ):
                            results[key] = _result_entry(
                                vmid=vmid,
                                op=op,
                                kind=kind,
                                status="skipped",
                                message="apply_destroy_confirmed not set",
                            )
                            continue

                        permission = _DELETE_PERMISSIONS.get(
                            kind, _DELETE_PERMISSIONS["qemu"]
                        )
                        has_perm = getattr(actor, "has_perm", None)
                        if (
                            actor is None
                            or not callable(has_perm)
                            or not has_perm(permission)
                        ):
                            results[key] = _result_entry(
                                vmid=vmid,
                                op=op,
                                kind=kind,
                                status="skipped",
                                message=f"permission denied: {permission}",
                            )
                            continue

                        snapshot = build_metadata_snapshot(vm)
                        snapshot_vmid = snapshot.get("vmid")
                        snapshot_node = snapshot.get("node")
                        deletion_request = DeletionRequest(
                            branch_id=getattr(branch, "pk", None),
                            branch_name=str(getattr(branch, "name", "") or ""),
                            requested_by=actor,
                            state=DeletionRequest.State.PENDING,
                            vmid=snapshot_vmid,
                            node=snapshot_node or "",
                            kind=kind,
                            metadata_snapshot=snapshot,
                            requested_at=timezone.now(),
                        )
                        deletion_request.save()

                        endpoint = get_fastapi_request_context()
                        tagged = tag_pending_deletion(
                            endpoint,
                            vmid=snapshot_vmid,
                            node=snapshot_node,
                            kind=kind,
                        )
                        if not tagged:
                            logger.warning(
                                "DeletionRequest %s created, but VM %s on node %s "
                                "was not tagged %s.",
                                deletion_request.pk,
                                snapshot_vmid,
                                snapshot_node,
                                "proxbox-pending-deletion",
                            )

                        results[key] = {
                            "vmid": snapshot_vmid,
                            "op": "delete",
                            "kind": kind,
                            "status": "delete-pending-approval",
                            "deletion_request_id": deletion_request.pk,
                            "message": "pending authorization",
                        }
                        continue

                    if op == "update":
                        prev_state = getattr(row, "prechange_data", None) or {}
                        delta = build_update_delta(vm, prev_state)
                        if not delta:
                            results[key] = _result_entry(
                                vmid=vmid,
                                op=op,
                                kind=kind,
                                status="skipped",
                                message="no real change",
                            )
                            continue
                        permission = _UPDATE_PERMISSIONS.get(
                            kind, _UPDATE_PERMISSIONS["qemu"]
                        )
                        has_perm = getattr(actor, "has_perm", None)
                        if (
                            actor is None
                            or not callable(has_perm)
                            or not has_perm(permission)
                        ):
                            results[key] = _result_entry(
                                vmid=vmid,
                                op=op,
                                kind=kind,
                                status="skipped",
                                message=f"permission denied: {permission}",
                            )
                            continue
                        apply_payload = {
                            "diffs": [
                                {
                                    "op": "update",
                                    "kind": kind,
                                    "payload": delta,
                                }
                            ],
                            "run_uuid": str(normalized_uuid),
                        }
                        body = _call_apply_endpoint(
                            apply_payload,
                            actor_username=actor_username,
                            endpoint_id=default_proxmox_endpoint_id(),
                        )
                        item = _first_apply_result(body)
                        status = str(item.get("status") or "failed")
                        proxmox_upid = item.get("proxmox_upid") or item.get("upid")
                        result_vmid = item.get("vmid", vmid)
                        results[key] = _result_entry(
                            vmid=result_vmid,
                            op=op,
                            kind=kind,
                            status=status,
                            message=str(item.get("message") or ""),
                            proxmox_upid=proxmox_upid,
                        )
                        if _status_is_success(status):
                            stamp_intent_state(
                                vm, "applied", run_uuid=str(normalized_uuid)
                            )
                        continue

                    permission = _CREATE_PERMISSIONS.get(
                        kind, _CREATE_PERMISSIONS["qemu"]
                    )
                    has_perm = getattr(actor, "has_perm", None)
                    if (
                        actor is None
                        or not callable(has_perm)
                        or not has_perm(permission)
                    ):
                        results[key] = _result_entry(
                            vmid=vmid,
                            op=op,
                            kind=kind,
                            status="skipped",
                            message=f"permission denied: {permission}",
                        )
                        continue

                    apply_payload = {
                        "diffs": [
                            {
                                "op": "create",
                                "kind": kind,
                                "payload": payload,
                            }
                        ],
                        "run_uuid": str(normalized_uuid),
                    }
                    body = _call_apply_endpoint(
                        apply_payload,
                        actor_username=actor_username,
                        endpoint_id=default_proxmox_endpoint_id(),
                    )
                    item = _first_apply_result(body)
                    status = str(item.get("status") or "failed")
                    proxmox_upid = item.get("proxmox_upid") or item.get("upid")
                    result_vmid = item.get("vmid", vmid)

                    results[key] = _result_entry(
                        vmid=result_vmid,
                        op=op,
                        kind=kind,
                        status=status,
                        message=str(item.get("message") or ""),
                        proxmox_upid=proxmox_upid,
                    )
                    if _status_is_success(status):
                        stamp_intent_state(vm, "applied", run_uuid=str(normalized_uuid))
                except Exception as exc:  # noqa: BLE001
                    logger.exception(
                        "Proxmox apply %s failed for ChangeDiff %s: %s",
                        run_uuid,
                        key,
                        exc,
                    )
                    results[key] = _result_entry(
                        vmid=vmid,
                        op=op,
                        kind=kind,
                        status="failed",
                        message=str(exc),
                    )

            for index, row in enumerate(firewall_changediffs(branch), start=1):
                key = firewall_result_key(row, index)
                op = "update"
                try:
                    apply_diff = build_firewall_apply_diff(row)
                    if apply_diff is None:
                        results[key] = _result_entry(
                            vmid=0,
                            op=getattr(row, "action", None) or op,
                            kind="firewall",
                            status="skipped",
                            message=unsupported_firewall_diff_message(row),
                        )
                        continue

                    op = str(apply_diff.diff.get("op") or op)
                    apply_payload = {
                        "diffs": [apply_diff.diff],
                        "run_uuid": str(normalized_uuid),
                    }
                    body = _call_apply_endpoint(
                        apply_payload,
                        actor_username=actor_username,
                        endpoint_id=apply_diff.endpoint_id,
                    )
                    item = _first_apply_result(body)
                    status = str(item.get("status") or "failed")
                    proxmox_upid = item.get("proxmox_upid") or item.get("upid")
                    results[key] = _result_entry(
                        vmid=item.get("vmid", 0),
                        op=op,
                        kind="firewall",
                        status=status,
                        message=str(item.get("message") or ""),
                        proxmox_upid=proxmox_upid,
                    )
                    if _status_is_success(status) and apply_diff.obj is not None:
                        save_status_for_firewall_object(apply_diff.obj, "active")
                except Exception as exc:  # noqa: BLE001
                    logger.exception(
                        "Proxmox apply %s failed for firewall ChangeDiff %s: %s",
                        run_uuid,
                        key,
                        exc,
                    )
                    results[key] = _result_entry(
                        vmid=0,
                        op=op,
                        kind="firewall",
                        status="failed",
                        message=str(exc),
                    )

            state = _state_from_results(results)
            apply_job.per_vm_results = results
            apply_job.state = state
            apply_job.finished_at = timezone.now()
            apply_job.save(update_fields=["per_vm_results", "state", "finished_at"])

            successes = sum(
                1
                for result in results.values()
                if _status_is_success(str(result.get("status") or ""))
            )

            logger.info(
                "Finished Proxmox apply %s for branch %s: %s (%s/%s succeeded).",
                apply_job.run_uuid,
                getattr(branch, "pk", None),
                state,
                successes,
                len(results),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Proxmox apply job %s failed: %s", run_uuid, exc)
            if apply_job is not None:
                try:
                    apply_job.state = ProxmoxApplyJobModel.State.failed
                    apply_job.finished_at = timezone.now()
                    apply_job.save(update_fields=["state", "finished_at"])
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "Failed to mark Proxmox apply job %s as failed.",
                        run_uuid,
                    )
            return
