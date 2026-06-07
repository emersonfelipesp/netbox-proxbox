"""Background job for triggering ProxBox sync operations via the FastAPI backend."""

from __future__ import annotations

import asyncio
import time
import uuid
from netbox.constants import RQ_QUEUE_DEFAULT
from netbox.jobs import JobRunner

try:
    from netbox.jobs import Job
except ImportError:  # pragma: no cover - test stubs expose only JobRunner
    # Intentional: `Job` is not always exported by NetBox (e.g. in test environments).
    # Using `Any` as a stub avoids a hard import error while keeping callers typed.
    from typing import Any

    Job = Any  # type: ignore[misc,assignment]

from netbox_proxbox.choices import SyncModeChoices, SyncTypeChoices
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
    effective_sync_modes_for_endpoint,
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
    sync_stages.effective_sync_modes_for_endpoint = effective_sync_modes_for_endpoint


async def _run_batch_selected_sync(
    *args: object, **kwargs: object
) -> dict[str, object]:
    """Compatibility wrapper for the extracted batch-sync coroutine."""
    return await sync_stages._run_batch_selected_sync(*args, **kwargs)


def _run_all_stages_sync(*args: object, **kwargs: object) -> list[dict[str, object]]:
    """Compatibility wrapper for the extracted stage runner."""
    return sync_stages._run_all_stages_sync(*args, **kwargs)


def _runtime_seconds_since(started: float) -> float:
    """Return a rounded elapsed runtime for persisted job metadata."""
    return round(max(time.monotonic() - started, 0.0), 3)


def _normalize_endpoint_id(value: object) -> int | str | None:
    """Normalize endpoint identifiers used in job metadata."""
    if value in (None, ""):
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return str(value)


def _coerce_runtime_seconds(value: object) -> float | None:
    """Return a rounded float runtime when a metadata value is numeric."""
    if value in (None, ""):
        return None
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def _endpoint_name_map(endpoint_ids: set[int | str]) -> dict[str, str]:
    """Resolve endpoint labels for runtime cards with safe fallbacks."""
    numeric_ids: list[int] = []
    for endpoint_id in endpoint_ids:
        try:
            numeric_ids.append(int(str(endpoint_id)))
        except (TypeError, ValueError):
            continue

    names: dict[str, str] = {}
    if numeric_ids:
        try:
            for endpoint in ProxmoxEndpoint.objects.filter(pk__in=numeric_ids):
                pk = _normalize_endpoint_id(getattr(endpoint, "pk", None))
                if pk is None:
                    continue
                label = getattr(endpoint, "name", None) or str(endpoint)
                names[str(pk)] = str(label)
        except Exception:  # noqa: BLE001 - runtime panel metadata must not break sync
            names = {}

    for endpoint_id in endpoint_ids:
        names.setdefault(str(endpoint_id), f"Endpoint {endpoint_id}")
    return names


def _endpoint_runtime_phase(
    *,
    endpoint_id: object,
    endpoint_name: object = "",
    kind: str,
    label: str,
    runtime_seconds: object,
    status: str,
    summary: str = "",
    sync_type: object | None = None,
    stream_path: object | None = None,
) -> dict[str, object]:
    """Build one persisted endpoint runtime phase."""
    phase: dict[str, object] = {
        "kind": kind,
        "label": label,
        "runtime_seconds": _coerce_runtime_seconds(runtime_seconds),
        "status": status,
        "summary": summary,
    }
    normalized_endpoint_id = _normalize_endpoint_id(endpoint_id)
    if normalized_endpoint_id is not None:
        phase["endpoint_id"] = normalized_endpoint_id
    if endpoint_name:
        phase["endpoint_name"] = str(endpoint_name)
    if sync_type:
        phase["sync_type"] = str(sync_type)
    if stream_path:
        phase["stream_path"] = str(stream_path)
    return phase


def _phases_from_service_result(
    result: object,
    *,
    kind: str,
    label: str,
) -> list[dict[str, object]]:
    """Convert service ``per_endpoint`` entries into runtime phases."""
    phases: list[dict[str, object]] = []
    per_endpoint = getattr(result, "per_endpoint", []) or []
    for item in per_endpoint:
        if not isinstance(item, dict):
            continue
        success = item.get("success")
        status = "success" if success is True else "warning"
        summary = str(item.get("error") or f"{label} completed")
        phases.append(
            _endpoint_runtime_phase(
                endpoint_id=item.get("endpoint_id"),
                endpoint_name=item.get("endpoint_name", ""),
                kind=kind,
                label=label,
                runtime_seconds=item.get("runtime_seconds"),
                status=status,
                summary=summary,
            )
        )
    return phases


def _phases_from_stage_results(
    stages_out: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Convert SSE stage results into endpoint runtime phases."""
    phases: list[dict[str, object]] = []
    for stage in stages_out:
        result_summary = stage.get("result_summary")
        if not isinstance(result_summary, dict):
            result_summary = {}
        ok = result_summary.get("ok")
        sync_type = stage.get("sync_type") or "sync stage"
        stream_path = stage.get("stream_path") or result_summary.get("path")
        phases.append(
            _endpoint_runtime_phase(
                endpoint_id=stage.get("endpoint_id"),
                endpoint_name=stage.get("endpoint_name", ""),
                kind="sse_stage",
                label=str(sync_type),
                runtime_seconds=stage.get("runtime_seconds"),
                status="success" if ok is True else "warning",
                summary=str(stream_path or "Backend SSE stage completed"),
                sync_type=sync_type,
                stream_path=stream_path,
            )
        )
    return phases


def _build_endpoint_runtimes(
    phases: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Group recorded runtime phases into per-endpoint cards."""
    buckets: dict[str, dict[str, object]] = {}
    endpoint_ids: set[int | str] = set()

    for phase in phases:
        endpoint_id = _normalize_endpoint_id(phase.get("endpoint_id"))
        if endpoint_id is None:
            continue
        endpoint_ids.add(endpoint_id)
        key = str(endpoint_id)
        bucket = buckets.setdefault(
            key,
            {
                "endpoint_id": endpoint_id,
                "endpoint_name": "",
                "runtime_seconds": 0.0,
                "phases": [],
            },
        )
        endpoint_name = str(phase.get("endpoint_name") or "").strip()
        if endpoint_name:
            bucket["endpoint_name"] = endpoint_name
        bucket_phases = bucket["phases"]
        if isinstance(bucket_phases, list):
            bucket_phases.append(phase)
        phase_runtime = _coerce_runtime_seconds(phase.get("runtime_seconds"))
        if phase_runtime is not None:
            bucket["runtime_seconds"] = round(
                float(bucket["runtime_seconds"]) + phase_runtime,
                3,
            )

    names = _endpoint_name_map(endpoint_ids)
    endpoint_runtimes = list(buckets.values())
    for endpoint_runtime in endpoint_runtimes:
        key = str(endpoint_runtime["endpoint_id"])
        if not endpoint_runtime.get("endpoint_name"):
            endpoint_runtime["endpoint_name"] = names.get(key, f"Endpoint {key}")
    endpoint_runtimes.sort(key=lambda item: str(item.get("endpoint_name") or ""))
    return endpoint_runtimes


def _runtime_summary(
    *,
    runtime_seconds: float,
    endpoint_runtimes: list[dict[str, object]],
) -> dict[str, object]:
    """Build whole-job summary fields for the runtime panel."""
    endpoint_runtime_seconds = round(
        sum(float(item.get("runtime_seconds") or 0.0) for item in endpoint_runtimes),
        3,
    )
    other_runtime_seconds = round(
        max(runtime_seconds - endpoint_runtime_seconds, 0.0),
        3,
    )
    return {
        "runtime_seconds": runtime_seconds,
        "endpoint_count": len(endpoint_runtimes),
        "endpoint_runtime_seconds": endpoint_runtime_seconds,
        "other_runtime_seconds": other_runtime_seconds,
    }


def _ensure_backend_endpoints(
    job: "ProxboxSyncJob",
    proxmox_endpoint_ids: list[str] | None = None,
) -> list[dict[str, object]]:
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
        return []

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
        proxmox_qs = ProxmoxEndpoint.objects.filter(
            pk__in=valid_endpoint_ids, enabled=True
        )
    else:
        proxmox_qs = ProxmoxEndpoint.objects.filter(enabled=True)

    phases: list[dict[str, object]] = []
    for px_ep in proxmox_qs:
        endpoint_started = time.monotonic()
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
        phases.append(
            _endpoint_runtime_phase(
                endpoint_id=getattr(px_ep, "pk", None),
                endpoint_name=getattr(px_ep, "name", None) or str(px_ep),
                kind="preflight",
                label="Backend endpoint push",
                runtime_seconds=_runtime_seconds_since(endpoint_started),
                status="success" if ok else "warning",
                summary=(
                    "Proxmox endpoint pushed to proxbox-api"
                    if ok
                    else f"Proxmox endpoint push failed: {err}"
                ),
            )
        )
    return phases


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
            sync_run_id = str(uuid.uuid4())
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
                "run_id": sync_run_id,
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

            endpoint_runtime_phases: list[dict[str, object]] = []

            # Push NetBox and Proxmox endpoint configuration to the proxbox-api
            # backend before any SSE stage runs.  The backend needs its own copy
            # of these records to open NetBox and Proxmox sessions; the post_save
            # signals are best-effort and may have missed a push if the backend
            # was offline when the endpoints were first saved.
            endpoint_runtime_phases.extend(
                _ensure_backend_endpoints(self, proxmox_endpoint_ids or [])
            )

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
                cluster_started = time.monotonic()
                cluster_result = sync_cluster_and_nodes(endpoint_id=eid)
                cluster_runtime = _runtime_seconds_since(cluster_started)
                if cluster_result.success:
                    cluster_summary = (
                        f"{cluster_result.clusters_created} cluster(s) created, "
                        f"{cluster_result.clusters_updated} updated, "
                        f"{cluster_result.nodes_created} node(s) created, "
                        f"{cluster_result.nodes_updated} updated"
                    )
                    self.logger.info(
                        f"Cluster/node sync for endpoint {eid}: {cluster_summary}"
                    )
                else:
                    cluster_summary = str(
                        cluster_result.error or "cluster/node sync failed"
                    )
                    self.logger.warning(
                        f"Cluster/node sync for endpoint {eid} failed: {cluster_result.error}"
                    )
                endpoint_runtime_phases.append(
                    _endpoint_runtime_phase(
                        endpoint_id=getattr(cluster_result, "endpoint_id", None) or eid,
                        endpoint_name=getattr(cluster_result, "endpoint_name", ""),
                        kind="cluster",
                        label="Cluster/node sync",
                        runtime_seconds=cluster_runtime,
                        status="success" if cluster_result.success else "warning",
                        summary=cluster_summary,
                    )
                )

            # Sync datacenter-level firewall objects (security groups, rules,
            # IP sets, aliases, options) after cluster/node records exist so
            # the endpoint lookup via ProxmoxCluster.name can resolve.
            # A failure here is logged as a warning and does not abort the run.
            from netbox_proxbox.services.sync_firewall import sync_firewall  # noqa: PLC0415

            self.logger.info("Syncing firewall objects from proxbox-api")
            fw_result = sync_firewall()
            if fw_result.success:
                self.logger.info(
                    f"Firewall sync complete: {fw_result.endpoints_processed} endpoint(s), "
                    f"{fw_result.security_groups_created} sg created, "
                    f"{fw_result.rules_created} rules created, "
                    f"{fw_result.ipsets_created} ipsets created, "
                    f"{fw_result.aliases_created} aliases created"
                )
            else:
                self.logger.warning(
                    f"Firewall sync failed or partially failed: {fw_result.error or 'see per_endpoint log'}"
                )
            endpoint_runtime_phases.extend(
                _phases_from_service_result(
                    fw_result,
                    kind="firewall",
                    label="Firewall sync",
                )
            )

            # Sync SDN objects (fabrics, route maps, prefix lists).
            from netbox_proxbox.services.sync_sdn import sync_sdn  # noqa: PLC0415

            self.logger.info("Syncing SDN objects from proxbox-api")
            sdn_result = sync_sdn()
            if sdn_result.success:
                self.logger.info(
                    f"SDN sync complete: {sdn_result.endpoints_processed} endpoint(s), "
                    f"fabrics={sdn_result.fabrics_created}/{sdn_result.fabrics_updated}, "
                    f"route_maps={sdn_result.route_maps_created}/{sdn_result.route_maps_updated}, "
                    f"prefix_lists={sdn_result.prefix_lists_created}/{sdn_result.prefix_lists_updated}"
                )
            else:
                self.logger.warning(
                    f"SDN sync failed or partially failed: {sdn_result.error or 'see per_endpoint log'}"
                )
            endpoint_runtime_phases.extend(
                _phases_from_service_result(
                    sdn_result,
                    kind="sdn",
                    label="SDN sync",
                )
            )

            # Sync datacenter CPU models.
            from netbox_proxbox.services.sync_datacenter import sync_datacenter  # noqa: PLC0415

            self.logger.info("Syncing datacenter CPU models from proxbox-api")
            dc_result = sync_datacenter()
            if dc_result.success:
                self.logger.info(
                    f"Datacenter CPU model sync complete: {dc_result.endpoints_processed} endpoint(s), "
                    f"created={dc_result.cpu_models_created}, updated={dc_result.cpu_models_updated}, "
                    f"stale={dc_result.cpu_models_stale}"
                )
            else:
                self.logger.warning(
                    f"Datacenter CPU model sync failed: {dc_result.error or 'unknown error'}"
                )
            endpoint_runtime_phases.extend(
                _phases_from_service_result(
                    dc_result,
                    kind="datacenter",
                    label="Datacenter sync",
                )
            )

            # Sync dedicated Proxmox VM template inventory after datacenter-level
            # service syncs and before VM SSE stages consume backend VM data.
            from netbox_proxbox.services.sync_vm_template import sync_vm_templates  # noqa: PLC0415

            global_vm_template_mode = sync_stages.effective_sync_modes_for_endpoint(
                None
            ).get("sync_mode_vm_template", SyncModeChoices.ALWAYS)
            if global_vm_template_mode == SyncModeChoices.DISABLED:
                self.logger.info(
                    "Skipping VM template sync: sync_mode_vm_template=disabled"
                )
            else:
                for eid in endpoint_ids_to_sync:
                    self.logger.info(f"Syncing VM templates for endpoint {eid}")
                    template_started = time.monotonic()
                    template_result = sync_vm_templates(endpoint_id=eid)
                    template_runtime = _runtime_seconds_since(template_started)
                    if template_result.success:
                        template_summary = (
                            f"{template_result.templates_created} template(s) created, "
                            f"{template_result.templates_updated} updated, "
                            f"{template_result.templates_skipped} skipped, "
                            f"{template_result.templates_deleted} deleted"
                        )
                        self.logger.info(
                            f"VM template sync for endpoint {eid}: {template_summary}"
                        )
                    else:
                        template_summary = str(
                            template_result.error or "VM template sync failed"
                        )
                        self.logger.warning(
                            f"VM template sync for endpoint {eid} failed: {template_result.error}"
                        )
                    endpoint_runtime_phases.append(
                        _endpoint_runtime_phase(
                            endpoint_id=getattr(template_result, "endpoint_id", None)
                            or eid,
                            endpoint_name=getattr(template_result, "endpoint_name", ""),
                            kind="vm_template",
                            label="VM template sync",
                            runtime_seconds=template_runtime,
                            status=(
                                "success"
                                if template_result.success is True
                                else "warning"
                            ),
                            summary=template_summary,
                        )
                    )

            stages_out = _run_all_stages_sync(self, stages, params, run_started)
            endpoint_runtime_phases.extend(_phases_from_stage_results(stages_out))

            for stage in stages_out:
                if stage.get("runtime_seconds") is None:
                    self.logger.warning(
                        f"Stage '{stage.get('sync_type')}' has runtime_seconds=None before save"
                    )

            runtime_seconds = round(time.monotonic() - run_started, 3)
            endpoint_runtimes = _build_endpoint_runtimes(endpoint_runtime_phases)
            self.job.data = {
                "proxbox_sync": {
                    "params": params,
                    "runtime_seconds": runtime_seconds,
                    "response": {
                        "stages": stages_out,
                        "endpoint_runtimes": endpoint_runtimes,
                        "runtime_summary": _runtime_summary(
                            runtime_seconds=runtime_seconds,
                            endpoint_runtimes=endpoint_runtimes,
                        ),
                    },
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
