"""Dry-run Proxmox apply executor for merged NetBox intent branches."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from django.utils import timezone
from netbox.constants import RQ_QUEUE_DEFAULT
from netbox.jobs import JobRunner

try:
    from netbox.jobs import Job
except ImportError:  # pragma: no cover - test stubs expose only JobRunner
    Job = Any  # type: ignore[misc,assignment]

from netbox_proxbox.models import ProxmoxApplyJob as ProxmoxApplyJobModel

PROXBOX_APPLY_JOB_TIMEOUT = 3600

__all__ = ("PROXBOX_APPLY_JOB_TIMEOUT", "ProxmoxApplyJob")

logger = logging.getLogger(__name__)

_VM_MODEL = "virtualmachine"
_INTENT_ACTIONS = {"create", "update", "delete"}


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


def _result_from_changediff(row: Any, fallback: int) -> dict[str, object]:
    op = getattr(row, "action", None)
    if op not in _INTENT_ACTIONS:
        op = "update"
    vmid_or_name = _diff_identifier(row, fallback)
    return {
        "op": op,
        "vmid_or_name": vmid_or_name,
        "status": "intent-logged",
        "message": (
            "Dry-run executor recorded the merged intent; no Proxmox API call "
            "was dispatched."
        ),
    }


class ProxmoxApplyJob(JobRunner):
    """Record merged branch intent without dispatching Proxmox writes."""

    class Meta:
        name = "Proxmox Apply Dry Run"

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
            "Queued Proxmox apply dry-run %s for branch %s as NetBox Job %s.",
            normalized_uuid,
            getattr(branch, "pk", None),
            getattr(job, "pk", None),
        )
        return job

    def run(self, run_uuid: str, **kwargs: object) -> None:
        """Record branch VM ChangeDiffs as per-VM intent stubs."""
        apply_job = ProxmoxApplyJobModel.objects.select_related("branch").get(
            run_uuid=_normalize_run_uuid(run_uuid)
        )
        apply_job.state = ProxmoxApplyJobModel.State.running
        apply_job.started_at = timezone.now()
        apply_job.save(update_fields=["state", "started_at"])

        branch = apply_job.branch
        logger.info(
            "Starting Proxmox apply dry-run %s for branch %s.",
            apply_job.run_uuid,
            getattr(branch, "pk", None),
        )

        results: dict[str, dict[str, object]] = {}
        for index, row in enumerate(_virtualmachine_changediffs(branch), start=1):
            result = _result_from_changediff(row, index)
            results[str(result["vmid_or_name"])] = result

        apply_job.per_vm_results = results
        apply_job.state = ProxmoxApplyJobModel.State.succeeded
        apply_job.finished_at = timezone.now()
        apply_job.save(update_fields=["per_vm_results", "state", "finished_at"])

        logger.info(
            "Finished Proxmox apply dry-run %s: recorded %s VM intent result(s).",
            apply_job.run_uuid,
            len(results),
        )
