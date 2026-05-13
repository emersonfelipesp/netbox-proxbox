"""Background job for triggering PBS sync via the proxbox-api backend.

``PBSSyncJob`` mirrors the six-step pattern used by
``netbox_proxbox.jobs.ProxboxSyncJob``:

1. Resolve sync stages from params (defaults to the full :data:`PBS_STAGES_FULL`).
2. Read :func:`branching_enabled_settings`; if branching is enabled, create
   and provision a fresh ``netbox-branching`` Branch.
3. Thread ``netbox_branch_schema_id`` into the params dict so every backend
   call writes into the same schema.
4. Run each stage via :func:`run_pbs_sync_stage` (SSE to ``/pbs/sync/<stage>``).
5. On success, merge the branch back into main (subject to the configured
   conflict policy).
6. Persist a structured result on ``job.data["pbs_sync"]``.

The branching plugin is optional. When ``netbox-branching`` is not installed
the job simply runs against ``main`` — exactly like the existing
``ProxboxSyncJob`` fallback.
"""

from __future__ import annotations

import time
from typing import Any

from netbox.constants import RQ_QUEUE_DEFAULT
from netbox.jobs import JobRunner

try:
    from netbox.jobs import Job
except ImportError:  # pragma: no cover - test stubs expose only JobRunner
    Job = Any  # type: ignore[misc,assignment]

from netbox_pbs.services.http_client import (
    PBS_STAGES_FULL,
    PBSStageResult,
    run_pbs_sync_stage,
)

# Use NetBox's default RQ queue so a stock ``manage.py rqworker`` picks up jobs.
PBS_SYNC_QUEUE_NAME = RQ_QUEUE_DEFAULT

# RQ wall-clock limit for the whole job. Must exceed NetBox's default
# RQ_DEFAULT_TIMEOUT (often 300s) and the SSE read budget between chunks.
PBS_SYNC_JOB_TIMEOUT = 7200

__all__ = (
    "PBS_SYNC_JOB_TIMEOUT",
    "PBS_SYNC_QUEUE_NAME",
    "PBSSyncJob",
)


def _normalize_stages(stages: list[str] | None) -> tuple[str, ...]:
    """Coerce a user-supplied stage list into a tuple of known stage names."""
    if not stages:
        return PBS_STAGES_FULL
    normalized = tuple(str(s).strip() for s in stages if str(s).strip())
    valid = tuple(s for s in normalized if s in PBS_STAGES_FULL)
    return valid or PBS_STAGES_FULL


def _normalize_endpoint_ids(raw_ids: list[Any] | None) -> list[str]:
    """Return the string-coerced endpoint IDs, dropping empty values."""
    out: list[str] = []
    for raw in raw_ids or []:
        value = str(raw).strip()
        if value:
            out.append(value)
    return out


class PBSSyncJob(JobRunner):
    """Trigger a PBS sync operation against the proxbox-api backend."""

    class Meta:
        name = "PBS Sync"

    @classmethod
    def enqueue(cls, *args: object, **kwargs: object) -> Job:
        """Enqueue like other ``JobRunner`` jobs, with a long default timeout."""
        kwargs.setdefault("job_timeout", PBS_SYNC_JOB_TIMEOUT)
        return super().enqueue(*args, **kwargs)

    def run(
        self,
        stages: list[str] | None = None,
        pbs_endpoint_ids: list[str] | None = None,
        **kwargs: object,
    ) -> None:
        """Run the configured PBS sync stages, optionally inside a NetBox branch."""
        resolved_stages = _normalize_stages(stages)
        endpoint_ids = _normalize_endpoint_ids(pbs_endpoint_ids)
        run_started = time.monotonic()

        try:
            from netbox_pbs.services.branch_lifecycle import (  # noqa: PLC0415
                branching_enabled_settings,
                create_and_provision_branch,
                merge_branch,
            )
        except ModuleNotFoundError:
            branching_enabled_settings = lambda: None  # noqa: E731
            create_and_provision_branch = None  # type: ignore[assignment]
            merge_branch = None  # type: ignore[assignment]

        branch = None
        branch_config = branching_enabled_settings()
        if branch_config is not None:
            branch_name = f"{branch_config['prefix']}-{self.job.pk}-{int(run_started)}"
            self.logger.info(
                f"NetBox branching enabled — creating branch {branch_name!r}"
            )
            try:
                branch = create_and_provision_branch(
                    name=branch_name,
                    user=getattr(self.job, "user", None),
                )
                self.logger.info(
                    f"Branch {branch.name} ready (schema_id={branch.schema_id})"
                )
            except Exception as exc:
                self.logger.error(
                    f"Failed to create/provision NetBox branch {branch_name}: {exc}"
                )
                raise

        netbox_branch_schema_id = branch.schema_id if branch is not None else None
        params: dict[str, Any] = {
            "stages": list(resolved_stages),
            "pbs_endpoint_ids": endpoint_ids,
            "netbox_branch_schema_id": netbox_branch_schema_id,
        }

        self.logger.info(f"Starting PBS sync stages: {', '.join(resolved_stages)}")
        if endpoint_ids:
            self.logger.info(f"PBS endpoints: {endpoint_ids}")

        stage_results: list[dict[str, Any]] = []
        for stage in resolved_stages:
            result: PBSStageResult = run_pbs_sync_stage(
                stage,
                params,
                logger_=self.logger,
            )
            stage_results.append(
                {
                    "stage": result.stage,
                    "success": result.success,
                    "error": result.error,
                    "event_count": len(result.events),
                }
            )
            if not result.success:
                self.logger.error(
                    f"PBS sync stage {result.stage!r} failed: {result.error}"
                )
                self._persist_result(
                    params=params,
                    stages=stage_results,
                    run_started=run_started,
                )
                raise RuntimeError(
                    f"PBS sync stage {result.stage!r} failed: {result.error}"
                )

        self._persist_result(
            params=params,
            stages=stage_results,
            run_started=run_started,
        )
        self.logger.info(f"All PBS sync stages completed ({len(stage_results)})")

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

    def _persist_result(
        self,
        *,
        params: dict[str, Any],
        stages: list[dict[str, Any]],
        run_started: float,
    ) -> None:
        """Write the structured sync result onto ``job.data``."""
        runtime_seconds = round(time.monotonic() - run_started, 3)
        self.job.data = {
            "pbs_sync": {
                "params": params,
                "runtime_seconds": runtime_seconds,
                "response": {"stages": stages},
            }
        }
        self.job.save(update_fields=["data"])
