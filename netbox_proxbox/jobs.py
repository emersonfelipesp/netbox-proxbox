"""Background job for triggering ProxBox sync operations via the FastAPI backend."""

from __future__ import annotations

import asyncio
import time
from netbox.constants import RQ_QUEUE_DEFAULT
from netbox.jobs import JobRunner

try:
    from netbox.jobs import Job
except ImportError:  # pragma: no cover - test stubs expose only JobRunner
    # Intentional: `Job` is not always exported by NetBox (e.g. in test environments).
    # Using `Any` as a stub avoids a hard import error while keeping callers typed.
    from typing import Any

    Job = Any  # type: ignore[misc,assignment]

from netbox_proxbox.choices import SyncTypeChoices
from netbox_proxbox.models import ProxmoxEndpoint
from netbox_proxbox.schemas import SyncJobData
from netbox_proxbox.sync_types import (
    _TARGETED_VM_JOB_NAME_RE,
    expanded_sync_stages,
    normalize_sync_types,
)
from netbox_proxbox.sync_params import (
    _ignore_ipv6_link_local_addresses_setting,
    _primary_ip_preference_setting,
    _infer_targeted_vm_job_params,
    _normalize_batch_object_ids,
    _proxbox_fetch_max_concurrency_setting,
    _serialize_sync_params,
    _use_guest_agent_interface_name_setting,
)
import netbox_proxbox.sync_stages as sync_stages
from netbox_proxbox.sync_ownership import (
    _claim_rq_sync_ownership,
    _release_rq_sync_ownership,
)

# Use NetBox's default RQ queue so a stock ``manage.py rqworker`` (no args) picks up jobs.
# Plugin-only queues such as ``netbox_proxbox.sync`` are not in that default worker list.
PROXBOX_SYNC_QUEUE_NAME = RQ_QUEUE_DEFAULT

# Rows created before this change may still have ``queue_name`` set to the legacy queue.
LEGACY_PROXBOX_RQ_QUEUE = "netbox_proxbox.sync"

# RQ wall-clock limit for the whole job. Must exceed NetBox's default ``RQ_DEFAULT_TIMEOUT``
# (often 300s) and the HTTP stream read budget between chunks (3600s in ``run_sync_stream``).
# Override per enqueue via ``job_timeout=...`` if needed.
PROXBOX_SYNC_JOB_TIMEOUT = 7200

__all__ = (
    "LEGACY_PROXBOX_RQ_QUEUE",
    "PROXBOX_SYNC_QUEUE_NAME",
    "PROXBOX_SYNC_JOB_TIMEOUT",
    "ProxboxSyncJob",
    "is_proxbox_sync_job",
    "normalize_sync_types",
    "proxbox_sync_params_from_job",
)


def proxbox_sync_params_from_job(job: Job) -> dict[str, object]:
    """Rebuild ProxboxSyncJob.enqueue kwargs from job.data (with safe fallbacks)."""
    raw_data = getattr(job, "data", None)
    raw_params = {}
    if isinstance(raw_data, dict):
        raw_block = raw_data.get("proxbox_sync")
        if isinstance(raw_block, dict) and isinstance(raw_block.get("params"), dict):
            raw_params = raw_block["params"]

    data = SyncJobData.from_job(job)
    params = data.params
    if params.sync_types:
        sync_types = normalize_sync_types(params.sync_types)
    elif isinstance(raw_params, dict) and raw_params.get("sync_type"):
        sync_types = normalize_sync_types([str(raw_params.get("sync_type"))])
    else:
        sync_types = [SyncTypeChoices.ALL]
    params = {
        "sync_types": sync_types,
        "proxmox_endpoint_ids": params.proxmox_endpoint_ids,
        "netbox_endpoint_ids": params.netbox_endpoint_ids,
        "netbox_vm_ids": params.netbox_vm_ids,
        "batch_object_type": params.batch_object_type,
        "batch_object_ids": params.batch_object_ids,
    }
    if params["sync_types"] == [SyncTypeChoices.ALL] and not params["netbox_vm_ids"]:
        inferred = _infer_targeted_vm_job_params(job)
        if inferred is not None:
            return inferred
    return params


def _sync_stage_settings() -> None:
    """Keep extracted stage helpers patchable through the legacy jobs module."""
    sync_stages._use_guest_agent_interface_name_setting = (
        _use_guest_agent_interface_name_setting
    )
    sync_stages._proxbox_fetch_max_concurrency_setting = (
        _proxbox_fetch_max_concurrency_setting
    )
    sync_stages._ignore_ipv6_link_local_addresses_setting = (
        _ignore_ipv6_link_local_addresses_setting
    )
    sync_stages._primary_ip_preference_setting = _primary_ip_preference_setting


async def _run_batch_selected_sync(
    *args: object, **kwargs: object
) -> dict[str, object]:
    """Compatibility wrapper for the extracted batch-sync coroutine."""
    return await sync_stages._run_batch_selected_sync(*args, **kwargs)


def _run_all_stages_sync(*args: object, **kwargs: object) -> list[dict[str, object]]:
    """Compatibility wrapper for the extracted stage runner."""
    return sync_stages._run_all_stages_sync(*args, **kwargs)


def _ensure_backend_endpoints(
    job: "ProxboxSyncJob",
    proxmox_endpoint_ids: list[str] | None = None,
) -> None:
    """Push NetBox and Proxmox endpoint data to the proxbox-api backend before sync.

    Best-effort — logs warnings on failure but never raises so the sync can still
    proceed (the endpoint may already exist in the backend from a previous push or
    manual creation via the Next.js UI).
    """
    from netbox_proxbox.models import NetBoxEndpoint  # noqa: PLC0415
    from netbox_proxbox.services.backend_auth import ensure_backend_key_registered  # noqa: PLC0415
    from netbox_proxbox.services.backend_context import get_fastapi_request_context  # noqa: PLC0415
    from netbox_proxbox.views.backend_sync import (  # noqa: PLC0415
        sync_netbox_endpoint_to_backend,
        sync_proxmox_endpoint_to_backend,
    )

    # Ensure the API key is registered before making authenticated requests.
    key_ok, key_msg = ensure_backend_key_registered()
    if key_ok:
        job.logger.info("Preflight: API key verified — %s", key_msg)
    else:
        job.logger.warning("Preflight: API key registration failed — %s", key_msg)

    context = get_fastapi_request_context()
    if context is None or not context.http_url:
        job.logger.warning(
            "No FastAPIEndpoint configured — cannot push endpoint data to backend"
        )
        return

    base_url = context.http_url.rstrip("/")
    auth_headers = dict(context.headers or {})
    backend_verify_ssl = bool(context.verify_ssl)

    # Push all enabled NetBox endpoints (singleton in practice).
    for nb_ep in NetBoxEndpoint.objects.filter(enabled=True):
        ok, err, _ = sync_netbox_endpoint_to_backend(
            nb_ep,
            base_url=base_url,
            auth_headers=auth_headers,
            backend_verify_ssl=backend_verify_ssl,
        )
        if ok:
            job.logger.info(
                "Preflight: synced NetBox endpoint '%s' to proxbox-api backend",
                getattr(nb_ep, "name", nb_ep.pk),
            )
        else:
            job.logger.warning(
                "Preflight: could not sync NetBox endpoint '%s' to proxbox-api: %s",
                getattr(nb_ep, "name", nb_ep.pk),
                err,
            )

    # Push Proxmox endpoints — filter by IDs if the job was scoped to specific ones.
    if proxmox_endpoint_ids:
        valid_endpoint_ids = _coerce_endpoint_ids(
            proxmox_endpoint_ids,
            logger=job.logger,
            context="preflight endpoint push",
        )
        proxmox_qs = ProxmoxEndpoint.objects.filter(pk__in=valid_endpoint_ids, enabled=True)
    else:
        proxmox_qs = ProxmoxEndpoint.objects.filter(enabled=True)

    for px_ep in proxmox_qs:
        ok, err, _ = sync_proxmox_endpoint_to_backend(
            px_ep,
            base_url=base_url,
            auth_headers=auth_headers,
            backend_verify_ssl=backend_verify_ssl,
        )
        if ok:
            job.logger.info(
                "Preflight: synced Proxmox endpoint '%s' to proxbox-api backend",
                getattr(px_ep, "name", px_ep.pk),
            )
        else:
            job.logger.warning(
                "Preflight: could not sync Proxmox endpoint '%s' to proxbox-api: %s",
                getattr(px_ep, "name", px_ep.pk),
                err,
            )


def _coerce_endpoint_ids(
    raw_ids: list[str] | None,
    *,
    logger: object | None = None,
    context: str = "sync",
) -> list[int]:
    """Return valid integer endpoint IDs and log skipped malformed values."""
    endpoint_ids: list[int] = []
    for raw_id in raw_ids or []:
        value = str(raw_id).strip()
        if not value:
            continue
        try:
            endpoint_ids.append(int(value))
        except (TypeError, ValueError):
            if logger is not None and hasattr(logger, "warning"):
                logger.warning(
                    "Skipping invalid Proxmox endpoint id %r during %s",
                    raw_id,
                    context,
                )
    return endpoint_ids


class ProxboxSyncJob(JobRunner):
    """Trigger a ProxBox sync operation against the FastAPI backend."""

    class Meta:
        name = "Proxbox Sync"

    @classmethod
    def enqueue(cls, *args: object, **kwargs: object) -> Job:
        """Enqueue like other ``JobRunner`` jobs, but with a long RQ ``job_timeout`` by default."""
        kwargs.setdefault("job_timeout", PROXBOX_SYNC_JOB_TIMEOUT)
        sync_types_kw = kwargs.pop("sync_types", None)
        sync_type_kw = kwargs.pop("sync_type", None)
        batch_object_type_kw = kwargs.pop("batch_object_type", None)
        batch_object_ids_kw = kwargs.pop("batch_object_ids", None)
        if sync_types_kw is not None:
            normalized = normalize_sync_types(list(sync_types_kw))
        elif sync_type_kw is not None:
            normalized = normalize_sync_types([str(sync_type_kw)])
        else:
            normalized = [SyncTypeChoices.ALL]
        kwargs["sync_types"] = normalized

        batch_object_ids = _normalize_batch_object_ids(batch_object_ids_kw)
        if batch_object_type_kw is not None:
            kwargs["batch_object_type"] = str(batch_object_type_kw)
        if batch_object_ids:
            kwargs["batch_object_ids"] = batch_object_ids

        job = super().enqueue(*args, **kwargs)

        params = {
            "sync_types": normalized,
            "proxmox_endpoint_ids": [
                str(x) for x in list(kwargs.get("proxmox_endpoint_ids") or []) if str(x)
            ],
            "netbox_endpoint_ids": [
                str(x) for x in list(kwargs.get("netbox_endpoint_ids") or []) if str(x)
            ],
            "netbox_vm_ids": [
                str(x) for x in list(kwargs.get("netbox_vm_ids") or []) if str(x)
            ],
            "batch_object_type": kwargs.get("batch_object_type"),
            "batch_object_ids": [
                str(x) for x in list(kwargs.get("batch_object_ids") or []) if str(x)
            ],
        }
        job.data = {
            "proxbox_sync": {
                "params": _serialize_sync_params(**params),
            }
        }
        job.save(update_fields=["data"])
        return job

    def run(
        self,
        sync_types: list[str] | None = None,
        sync_type: str | None = None,
        proxmox_endpoint_ids: list[str] | None = None,
        netbox_endpoint_ids: list[str] | None = None,
        netbox_vm_ids: list[str] | None = None,
        batch_object_type: str | None = None,
        batch_object_ids: list[str] | None = None,
        fastapi_endpoint_id: int | None = None,
        **kwargs: object,
    ) -> None:
        """Run one or more proxbox-api SSE streams in dependency order."""
        fastapi_endpoint_id = fastapi_endpoint_id

        if not _claim_rq_sync_ownership(self.job):
            self.logger.info(
                "Sync ownership already claimed by SSE stream, RQ job skipping sync execution"
            )
            return

        try:
            if sync_types:
                types = normalize_sync_types([str(x) for x in sync_types])
            elif sync_type is not None:
                types = normalize_sync_types([str(sync_type)])
            else:
                types = [SyncTypeChoices.ALL]

            batch_object_type = (
                str(batch_object_type).strip() if batch_object_type else None
            )
            batch_object_ids = _normalize_batch_object_ids(batch_object_ids)
            run_started = time.monotonic()
            _sync_stage_settings()

            try:
                from netbox_proxbox.services.branch_lifecycle import (  # noqa: PLC0415
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
                branch_name = (
                    f"{branch_config['prefix']}-{self.job.pk}-{int(run_started)}"
                )
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

            stages = expanded_sync_stages(types)

            netbox_branch_schema_id = branch.schema_id if branch is not None else None
            params: dict[str, object] = {
                "sync_types": types,
                "proxmox_endpoint_ids": [
                    str(x) for x in list(proxmox_endpoint_ids or []) if str(x)
                ],
                "netbox_endpoint_ids": [
                    str(x) for x in list(netbox_endpoint_ids or []) if str(x)
                ],
                "netbox_vm_ids": [str(x) for x in list(netbox_vm_ids or []) if str(x)],
                "batch_object_type": batch_object_type,
                "batch_object_ids": batch_object_ids,
                "fastapi_endpoint_id": fastapi_endpoint_id,
            }
            self.job.data = {
                "proxbox_sync": {
                    "params": _serialize_sync_params(**params),
                }
            }
            self.job.save(update_fields=["data"])

            params["netbox_branch_schema_id"] = netbox_branch_schema_id

            if batch_object_type and batch_object_ids:
                self.logger.info(
                    f"Starting batch sync for {len(batch_object_ids)} selected {batch_object_type} records"
                )
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                if loop and loop.is_running():
                    import concurrent.futures

                    with concurrent.futures.ThreadPoolExecutor(
                        max_workers=1
                    ) as executor:
                        future = executor.submit(
                            asyncio.run,
                            _run_batch_selected_sync(
                                self,
                                batch_object_type=batch_object_type,
                                batch_object_ids=batch_object_ids,
                                netbox_branch_schema_id=netbox_branch_schema_id,
                            ),
                        )
                        batch_result = future.result()
                else:
                    batch_result = asyncio.run(
                        _run_batch_selected_sync(
                            self,
                            batch_object_type=batch_object_type,
                            batch_object_ids=batch_object_ids,
                            netbox_branch_schema_id=netbox_branch_schema_id,
                        )
                    )
                runtime_seconds = round(time.monotonic() - run_started, 3)
                self.job.data = {
                    "proxbox_sync": {
                        "params": params,
                        "runtime_seconds": runtime_seconds,
                        "response": {"batch": batch_result},
                    }
                }
                self.job.save(update_fields=["data"])
                self.logger.info(
                    "Batch sync completed for "
                    f"{batch_result['batch_object_label']} "
                    f"({batch_result['total']} total, "
                    f"{batch_result['succeeded']} succeeded, "
                    f"{batch_result['failed']} failed)"
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
                return

            self.logger.info(f"Starting Proxbox sync stages: {', '.join(stages)}")
            if proxmox_endpoint_ids:
                self.logger.info(f"Proxmox endpoints: {proxmox_endpoint_ids}")
            if netbox_endpoint_ids:
                self.logger.info(f"NetBox endpoints: {netbox_endpoint_ids}")
            if netbox_vm_ids:
                self.logger.info(f"NetBox virtual machines: {netbox_vm_ids}")

            # Push NetBox and Proxmox endpoint configuration to the proxbox-api
            # backend before any SSE stage runs.  The backend needs its own copy
            # of these records to open NetBox and Proxmox sessions; the post_save
            # signals are best-effort and may have missed a push if the backend
            # was offline when the endpoints were first saved.
            _ensure_backend_endpoints(self, proxmox_endpoint_ids or [])

            # Sync cluster and node data before SSE stages so cluster/node records
            # are populated regardless of which stages are selected.
            # Lazy import to avoid a circular import through services → views → jobs.
            from netbox_proxbox.services.sync_cluster import sync_cluster_and_nodes  # noqa: PLC0415

            endpoint_ids_to_sync = (
                _coerce_endpoint_ids(
                    proxmox_endpoint_ids,
                    logger=self.logger,
                    context="cluster/node sync",
                )
                if proxmox_endpoint_ids
                else list(ProxmoxEndpoint.objects.values_list("pk", flat=True))
            )
            for eid in endpoint_ids_to_sync:
                self.logger.info(f"Syncing cluster/nodes for endpoint {eid}")
                cluster_result = sync_cluster_and_nodes(endpoint_id=eid)
                if cluster_result.success:
                    self.logger.info(
                        f"Cluster/node sync for endpoint {eid}: "
                        f"{cluster_result.clusters_created} cluster(s) created, "
                        f"{cluster_result.clusters_updated} updated, "
                        f"{cluster_result.nodes_created} node(s) created, "
                        f"{cluster_result.nodes_updated} updated"
                    )
                else:
                    self.logger.warning(
                        f"Cluster/node sync for endpoint {eid} failed: {cluster_result.error}"
                    )

            stages_out = _run_all_stages_sync(self, stages, params, run_started)

            for stage in stages_out:
                if stage.get("runtime_seconds") is None:
                    self.logger.warning(
                        f"Stage '{stage.get('sync_type')}' has runtime_seconds=None before save"
                    )

            runtime_seconds = round(time.monotonic() - run_started, 3)
            self.job.data = {
                "proxbox_sync": {
                    "params": params,
                    "runtime_seconds": runtime_seconds,
                    "response": {"stages": stages_out},
                }
            }
            self.job.save(update_fields=["data"])
            self.job.refresh_from_db(fields=["data"])
            stored_stages = (
                (self.job.data or {})
                .get("proxbox_sync", {})
                .get("response", {})
                .get("stages", [])
            )
            missing_rt = [
                s.get("sync_type")
                for s in stored_stages
                if s.get("runtime_seconds") is None
            ]
            if missing_rt:
                self.logger.error(
                    f"runtime_seconds lost after DB round-trip for stages: {missing_rt}"
                )
            self.logger.info(
                f"All sync stages completed ({len(stages_out)}), runtime {runtime_seconds:.3f}s"
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
        finally:
            _release_rq_sync_ownership(self.job)


def is_proxbox_sync_job(job: Job) -> bool:
    """True if this core Job row is a Proxbox sync (including user-defined job names)."""
    data = getattr(job, "data", None)
    if isinstance(data, dict) and "proxbox_sync" in data:
        return True
    qn = getattr(job, "queue_name", None) or ""
    if qn == LEGACY_PROXBOX_RQ_QUEUE:
        return True
    name = str(getattr(job, "name", None) or "").strip()
    default_label = getattr(ProxboxSyncJob.Meta, "name", "Proxbox Sync")
    allowed_queue_names = {
        "",
        PROXBOX_SYNC_QUEUE_NAME,
        LEGACY_PROXBOX_RQ_QUEUE,
    }
    if name == default_label and qn in allowed_queue_names:
        return True
    return bool(_TARGETED_VM_JOB_NAME_RE.match(name))
