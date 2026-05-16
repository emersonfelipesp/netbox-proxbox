"""Background sync job for netbox-pbs."""

from __future__ import annotations

import logging
import time
from typing import Any

from netbox.constants import RQ_QUEUE_DEFAULT
from netbox.jobs import JobRunner

try:
    from netbox.jobs import Job
except ImportError:  # pragma: no cover - test stubs may not export Job
    from typing import Any as _Any

    Job = _Any  # type: ignore[misc,assignment]

from netbox_pbs.services.branch_lifecycle import (
    branching_enabled_settings,
    create_and_provision_branch,
    merge_branch,
)
from netbox_pbs.services.http_client import (
    PBS_SYNC_RESOURCES,
    PBSBackendError,
    sync_pbs_resource,
)

logger = logging.getLogger("netbox_pbs.jobs")

PBS_SYNC_QUEUE_NAME = RQ_QUEUE_DEFAULT
PBS_SYNC_JOB_TIMEOUT = 7200
DEFAULT_SYNC_RESOURCES: tuple[str, ...] = ("full",)


def _normalize_resources(resources: list[str] | None) -> list[str]:
    if not resources:
        return list(DEFAULT_SYNC_RESOURCES)
    normalized: list[str] = []
    for raw in resources:
        value = str(raw).strip().lower()
        if not value:
            continue
        if value not in PBS_SYNC_RESOURCES:
            raise ValueError(
                f"Unknown PBS sync resource {value!r}; expected one of {PBS_SYNC_RESOURCES}"
            )
        if value not in normalized:
            normalized.append(value)
    return normalized or list(DEFAULT_SYNC_RESOURCES)


class PBSSyncJob(JobRunner):
    """Trigger a PBS reflection sync through proxbox-api."""

    class Meta:
        name = "PBS Sync"

    @classmethod
    def enqueue(cls, *args: object, **kwargs: object) -> Job:
        """Enqueue with a long ``job_timeout`` so slow PBS syncs can finish."""

        kwargs.setdefault("job_timeout", PBS_SYNC_JOB_TIMEOUT)
        resources_kw = kwargs.pop("resources", None)
        try:
            resources = _normalize_resources(
                list(resources_kw) if resources_kw is not None else None
            )
        except ValueError as exc:
            raise ValueError(f"Cannot enqueue PBSSyncJob: {exc}") from exc
        kwargs["resources"] = resources

        job = super().enqueue(*args, **kwargs)
        job.data = {"pbs_sync": {"params": {"resources": resources}}}
        job.save(update_fields=["data"])
        return job

    def run(
        self,
        resources: list[str] | None = None,
        **_kwargs: object,
    ) -> None:
        """Run one or more proxbox-api PBS sync calls."""

        run_started = time.monotonic()
        try:
            normalized_resources = _normalize_resources(resources)
        except ValueError as exc:
            self.logger.error(str(exc))
            raise

        branch = None
        branch_config = branching_enabled_settings()
        if branch_config is not None:
            branch_name = f"{branch_config['prefix']}-{self.job.pk}-{int(run_started)}"
            self.logger.info(
                "NetBox branching enabled; creating branch %r for PBS sync",
                branch_name,
            )
            try:
                branch = create_and_provision_branch(
                    name=branch_name,
                    user=getattr(self.job, "user", None),
                )
                self.logger.info(
                    "Branch %s ready (schema_id=%s)", branch.name, branch.schema_id
                )
            except Exception as exc:
                self.logger.error(
                    "Failed to create/provision NetBox branch %s: %s",
                    branch_name,
                    exc,
                )
                raise

        netbox_branch_schema_id = str(branch.schema_id) if branch is not None else None

        params: dict[str, Any] = {
            "resources": normalized_resources,
            "netbox_branch_schema_id": netbox_branch_schema_id,
        }
        self.job.data = {"pbs_sync": {"params": params}}
        self.job.save(update_fields=["data"])

        stage_results: list[dict[str, Any]] = []
        had_error = False
        for resource in normalized_resources:
            stage_started = time.monotonic()
            self.logger.info("Calling proxbox-api /pbs/sync/%s", resource)
            try:
                payload = sync_pbs_resource(
                    None,
                    resource,
                    netbox_branch_schema_id=netbox_branch_schema_id,
                )
                stage_results.append(
                    {
                        "resource": resource,
                        "status": "ok",
                        "runtime_seconds": round(time.monotonic() - stage_started, 3),
                        "response": payload,
                    }
                )
            except (PBSBackendError, ValueError) as exc:
                had_error = True
                self.logger.error("PBS sync resource %s failed: %s", resource, exc)
                stage_results.append(
                    {
                        "resource": resource,
                        "status": "error",
                        "runtime_seconds": round(time.monotonic() - stage_started, 3),
                        "error": str(exc),
                    }
                )

        runtime_seconds = round(time.monotonic() - run_started, 3)
        self.job.data = {
            "pbs_sync": {
                "params": params,
                "runtime_seconds": runtime_seconds,
                "response": {"stages": stage_results},
            }
        }
        self.job.save(update_fields=["data"])
        self.logger.info(
            "PBS sync finished in %.3fs (%d stage(s), errors=%s)",
            runtime_seconds,
            len(stage_results),
            had_error,
        )

        if had_error:
            if branch is not None:
                self.logger.warning(
                    "Leaving branch %s open because one or more PBS stages failed",
                    branch.name,
                )
            raise RuntimeError(
                "One or more PBS sync stages failed; see job log for details."
            )

        if branch is not None and branch_config is not None:
            merged, message = merge_branch(
                branch=branch,
                user=getattr(self.job, "user", None),
                on_conflict=branch_config["on_conflict"],
            )
            if merged:
                self.logger.info(message)
            else:
                self.logger.error(message)
                raise RuntimeError(message)


__all__ = (
    "DEFAULT_SYNC_RESOURCES",
    "PBS_SYNC_JOB_TIMEOUT",
    "PBS_SYNC_QUEUE_NAME",
    "PBSSyncJob",
)
