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
from netbox_proxbox.intent.payload import build_lxc_payload, build_vm_payload
from netbox_proxbox.models import ProxmoxApplyJob as ProxmoxApplyJobModel
from netbox_proxbox.services.backend_context import get_fastapi_request_context

PROXBOX_APPLY_JOB_TIMEOUT = 3600

__all__ = ("PROXBOX_APPLY_JOB_TIMEOUT", "ProxmoxApplyJob")

logger = logging.getLogger(__name__)

_VM_MODEL = "virtualmachine"
_CREATE_PERMISSIONS = {
    "qemu": "netbox_proxbox.intent_create_vm",
    "lxc": "netbox_proxbox.intent_create_lxc",
}
_SUCCESS_STATUSES = {"succeeded", "success", "applied", "intent-logged"}
_FAILED_STATUSES = {"failed"}
_NOT_IMPLEMENTED_MESSAGE = "Sub-PR G/H lands this"


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
    timeout: float = PROXBOX_APPLY_JOB_TIMEOUT,
) -> dict[str, Any]:
    context = get_fastapi_request_context()
    if context is None:
        raise RuntimeError("No FastAPIEndpoint is configured; cannot apply intent.")

    http_url = context.http_url
    if not http_url:
        raise RuntimeError("FastAPIEndpoint has no resolvable http_url.")

    url = f"{http_url.rstrip('/')}/intent/apply"
    headers = dict(context.headers or {})
    headers.setdefault("Content-Type", "application/json")
    headers["X-Proxbox-Actor"] = actor_username or ""

    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=timeout,
            verify=bool(context.verify_ssl),
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
        raise RuntimeError(
            f"proxbox-api returned HTTP {response.status_code} for /intent/apply: "
            f"{response.text[:500]}"
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
        branch_label = getattr(branch, "name", None) or getattr(branch, "pk", "unknown")
        apply_job = ProxmoxApplyJobModel.objects.create(
            branch=branch,
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
            apply_job = ProxmoxApplyJobModel.objects.select_related(
                "branch", "user"
            ).get(run_uuid=normalized_uuid)
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

                    if op in {"update", "delete"}:
                        results[key] = _result_entry(
                            vmid=vmid,
                            op=op,
                            kind=kind,
                            status="not_implemented",
                            message=_NOT_IMPLEMENTED_MESSAGE,
                        )
                        continue

                    permission = _CREATE_PERMISSIONS.get(
                        kind, _CREATE_PERMISSIONS["qemu"]
                    )
                    has_perm = getattr(actor, "has_perm", None)
                    if actor is None or not callable(has_perm) or not has_perm(
                        permission
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
