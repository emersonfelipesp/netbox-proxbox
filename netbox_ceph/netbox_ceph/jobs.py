"""Background sync job for netbox-ceph.

``CephSyncJob`` queues onto NetBox's default RQ queue (the same queue
``ProxboxSyncJob`` uses) and calls proxbox-api's read-only ``/ceph/sync/*``
routes. When branching is enabled on ``CephPluginSettings``, the job
provisions a netbox-branching branch around the sync, threads the
branch's ``schema_id`` through to proxbox-api, and merges the branch
back on success.

v1 is reflection-only: there is no Ceph-side write path. Failures leave
the branch open (default policy ``fail``) so an operator can inspect
``ChangeDiff`` conflicts before merging by hand.
"""

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

from netbox_ceph.services.branch_lifecycle import (
    branching_enabled_settings,
    create_and_provision_branch,
    merge_branch,
)
from netbox_ceph.services.http_client import (
    CEPH_SYNC_RESOURCES,
    CephBackendError,
    fetch_ceph_sync,
)

logger = logging.getLogger("netbox_ceph.jobs")

CEPH_SYNC_QUEUE_NAME = RQ_QUEUE_DEFAULT

# Match ProxboxSyncJob's long RQ wall-clock so a slow Ceph cluster does not
# get killed by NetBox's 300s default RQ timeout.
CEPH_SYNC_JOB_TIMEOUT = 7200

DEFAULT_SYNC_RESOURCES: tuple[str, ...] = ("full",)


def _normalize_resources(resources: list[str] | None) -> list[str]:
    if not resources:
        return list(DEFAULT_SYNC_RESOURCES)
    normalized: list[str] = []
    for raw in resources:
        value = str(raw).strip().lower()
        if not value:
            continue
        if value not in CEPH_SYNC_RESOURCES:
            raise ValueError(
                f"Unknown Ceph sync resource {value!r}; expected one of {CEPH_SYNC_RESOURCES}"
            )
        if value not in normalized:
            normalized.append(value)
    return normalized or list(DEFAULT_SYNC_RESOURCES)


class CephSyncJob(JobRunner):
    """Trigger a Ceph reflection sync against proxbox-api."""

    class Meta:
        name = "Ceph Sync"

    @classmethod
    def enqueue(cls, *args: object, **kwargs: object) -> Job:
        """Enqueue with a long ``job_timeout`` so slow Ceph clusters don't get killed."""
        kwargs.setdefault("job_timeout", CEPH_SYNC_JOB_TIMEOUT)
        resources_kw = kwargs.pop("resources", None)
        try:
            resources = _normalize_resources(
                list(resources_kw) if resources_kw is not None else None
            )
        except ValueError as exc:
            raise ValueError(f"Cannot enqueue CephSyncJob: {exc}") from exc
        kwargs["resources"] = resources

        job = super().enqueue(*args, **kwargs)
        job.data = {
            "ceph_sync": {
                "params": {"resources": resources},
            }
        }
        job.save(update_fields=["data"])
        return job

    def run(
        self,
        resources: list[str] | None = None,
        **_kwargs: object,
    ) -> None:
        """Run one or more proxbox-api Ceph sync calls."""
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
                "NetBox branching enabled — creating branch %r for Ceph sync",
                branch_name,
            )
            try:
                branch = create_and_provision_branch(
                    name=branch_name,
                    user=getattr(self.job, "user", None),
                )
                self.logger.info("Branch %s ready (schema_id=%s)", branch.name, branch.schema_id)
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
        self.job.data = {"ceph_sync": {"params": params}}
        self.job.save(update_fields=["data"])

        stage_results: list[dict[str, Any]] = []
        had_error = False
        for resource in normalized_resources:
            stage_started = time.monotonic()
            self.logger.info("Calling proxbox-api /ceph/sync/%s", resource)
            try:
                payload = fetch_ceph_sync(
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
            except (CephBackendError, ValueError) as exc:
                had_error = True
                self.logger.error("Ceph sync resource %s failed: %s", resource, exc)
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
            "ceph_sync": {
                "params": params,
                "runtime_seconds": runtime_seconds,
                "response": {"stages": stage_results},
            }
        }
        self.job.save(update_fields=["data"])
        self.logger.info(
            "Ceph sync finished in %.3fs (%d stage(s), errors=%s)",
            runtime_seconds,
            len(stage_results),
            had_error,
        )

        if had_error:
            if branch is not None:
                self.logger.warning(
                    "Leaving branch %s open because one or more Ceph stages failed",
                    branch.name,
                )
            raise RuntimeError("One or more Ceph sync stages failed; see job log for details.")

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
    "CEPH_SYNC_JOB_TIMEOUT",
    "CEPH_SYNC_QUEUE_NAME",
    "CephSyncJob",
    "DEFAULT_SYNC_RESOURCES",
)
