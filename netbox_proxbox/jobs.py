"""Background job for triggering ProxBox sync operations via the FastAPI backend."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from datetime import datetime, timedelta
import time
import uuid
from netbox.constants import RQ_QUEUE_DEFAULT
from netbox.jobs import JobRunner

try:
    from netbox.jobs import system_job
except ImportError:  # pragma: no cover - older/test NetBox stubs

    def system_job(*_args: object, **_kwargs: object):
        def decorator(cls):
            return cls

        return decorator


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
    _coerce_fastapi_endpoint_id,
    _ignore_ipv6_link_local_addresses_setting,
    _primary_ip_preference_setting,
    _infer_targeted_vm_job_params,
    _normalize_batch_object_ids,
    _proxbox_fetch_max_concurrency_setting,
    _serialize_sync_params,
    _use_guest_agent_interface_name_setting,
    _vm_interface_sync_strategy_setting,
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
    "PreflightResult",
    "ProxboxPreflightError",
    "ProxboxSyncJob",
    "ProxmoxServiceMonitoringJob",
    "is_proxbox_sync_job",
    "normalize_sync_types",
    "proxbox_sync_params_from_job",
    "service_monitoring_collection_due",
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
    # Captured before ``params`` is rebound to a plain dict below.  The backend
    # pin has to survive a replay: ``run()`` takes ``fastapi_endpoint_id`` and
    # threads it through the preflight, key registration, wire-id resolution, and
    # the four pre-SSE service passes, so dropping it here re-elects "first
    # enabled backend" on the rerun and can point the whole job at a different
    # proxbox-api than the original.  Applied to *both* return paths — the legacy
    # targeted-VM name inference below rebuilds the params from scratch and would
    # otherwise lose it.
    fastapi_endpoint_id = params.fastapi_endpoint_id
    params = {
        "sync_types": sync_types,
        "proxmox_endpoint_ids": params.proxmox_endpoint_ids,
        "netbox_endpoint_ids": params.netbox_endpoint_ids,
        "netbox_vm_ids": params.netbox_vm_ids,
        "batch_object_type": params.batch_object_type,
        "batch_object_ids": params.batch_object_ids,
    }
    if fastapi_endpoint_id is not None:
        params["fastapi_endpoint_id"] = fastapi_endpoint_id
    if params["sync_types"] == [SyncTypeChoices.ALL] and not params["netbox_vm_ids"]:
        inferred = _infer_targeted_vm_job_params(job)
        if inferred is not None:
            if fastapi_endpoint_id is not None:
                inferred["fastapi_endpoint_id"] = fastapi_endpoint_id
            return inferred
    return params


def _sync_stage_settings() -> None:
    """Keep extracted stage helpers patchable through the legacy jobs module."""
    sync_stages._use_guest_agent_interface_name_setting = (
        _use_guest_agent_interface_name_setting
    )
    sync_stages._vm_interface_sync_strategy_setting = (
        _vm_interface_sync_strategy_setting
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


def _batch_wire_endpoint_scope(
    *args: object, **kwargs: object
) -> tuple[str, list[str], str | None, dict[str, str]]:
    """Compatibility wrapper for the extracted batch endpoint-scope resolver."""
    return sync_stages._batch_wire_endpoint_scope(*args, **kwargs)


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
    aggregate_failed = getattr(result, "success", False) is not True
    if not phases or (
        aggregate_failed and all(phase.get("status") == "success" for phase in phases)
    ):
        phases.append(
            _endpoint_runtime_phase(
                endpoint_id=getattr(result, "endpoint_id", None),
                endpoint_name=getattr(result, "endpoint_name", ""),
                kind=kind,
                label=label,
                runtime_seconds=getattr(result, "runtime_seconds", None),
                status="warning" if aggregate_failed else "success",
                summary=str(getattr(result, "error", None) or f"{label} completed"),
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


#: How many failed selected objects the job-log line names before summarising
#: the rest. A batch can carry hundreds of objects, and a job-log entry that
#: names every one of them is unreadable — the full per-object status and error
#: is already persisted on ``job.data['proxbox_sync']['response']['batch']``.
BATCH_FAILURE_DETAIL_LIMIT = 10


def _failed_batch_object_detail(batch_result: dict[str, object]) -> str:
    """Summarise which selected objects failed, for the job-log error line.

    Reads the same ``results`` list that is persisted on the job, so the log
    line and the stored record can never disagree about which objects failed.
    """
    results = batch_result.get("results")
    failures: list[str] = []
    if isinstance(results, list):
        for item in results:
            if not isinstance(item, dict):
                continue
            try:
                status = int(item.get("status", 500))
            except (TypeError, ValueError):
                status = 500
            if status < 400:
                continue
            object_id = str(item.get("object_id") or "?")
            error = str(item.get("error") or "").strip()
            failures.append(f"{object_id} ({status}{': ' + error if error else ''})")

    if not failures:
        # `failed` was non-zero but no result row explains it — report that
        # rather than an empty message, so the job never fails wordlessly.
        return "no per-object detail was recorded; see the job data for the raw result"

    shown = failures[:BATCH_FAILURE_DETAIL_LIMIT]
    detail = "; ".join(shown)
    remaining = len(failures) - len(shown)
    if remaining > 0:
        detail = f"{detail}; and {remaining} more"
    return f"failed object(s): {detail}"


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


class ProxboxPreflightError(RuntimeError):
    """The pre-sync preflight left proxbox-api unable to write to NetBox.

    Raised instead of letting the run continue into stages that cannot possibly
    succeed, so the job fails with the real cause rather than with whatever
    unrelated-looking error the first stage happens to produce.
    """


class PreflightResult:
    """Outcome of :func:`_ensure_backend_endpoints`.

    ``phases`` are the persisted endpoint runtime phases, ``blocking_error`` is
    set when the run must not continue, and ``hint`` carries non-fatal preflight
    warnings forward so a later stage failure can be attributed to them.

    Deliberately a plain class rather than a ``@dataclasses.dataclass``: this
    module has ``from __future__ import annotations``, and on Python 3.14
    ``dataclasses`` resolves those string annotations through
    ``sys.modules[cls.__module__]``. The test suite loads plugin modules by file
    path (``spec_from_file_location`` + ``exec_module``) without registering them
    in ``sys.modules``, so that lookup returns ``None`` and decorating this class
    would make ``jobs.py`` unimportable under the stub-loader harness.
    """

    __slots__ = ("phases", "blocking_error", "hint")

    def __init__(
        self,
        phases: list[dict[str, object]] | None = None,
        blocking_error: str | None = None,
        hint: str | None = None,
    ) -> None:
        self.phases = phases if phases is not None else []
        self.blocking_error = blocking_error
        self.hint = hint

    def __repr__(self) -> str:
        return (
            f"PreflightResult(phases={self.phases!r}, "
            f"blocking_error={self.blocking_error!r}, hint={self.hint!r})"
        )


def _preflight_hint(notes: list[str]) -> str | None:
    """Join preflight warnings into one sentence for later stage errors."""
    if not notes:
        return None
    return "Preflight reported: " + "; ".join(notes) + "."


class _BackendPreflightState:
    """Connection data and warnings shared by endpoint-preflight helpers."""

    __slots__ = ("auth_headers", "base_url", "context", "job", "notes", "verify_ssl")

    def __init__(self, job: "ProxboxSyncJob", context: object) -> None:
        self.job = job
        self.context = context
        self.base_url = context.http_url.rstrip("/")
        self.auth_headers = dict(context.headers or {})
        self.verify_ssl = bool(context.verify_ssl)
        self.notes: list[str] = []


class _NetBoxEndpointPush:
    """Outcomes from pushing this NetBox's enabled endpoint rows."""

    __slots__ = ("endpoints", "failures", "succeeded")

    def __init__(self) -> None:
        self.endpoints: list[object] = []
        self.failures: list[str] = []
        self.succeeded = False


def _blocking_preflight(
    state: _BackendPreflightState,
    message: str,
) -> PreflightResult:
    """Log and return a blocking endpoint-preflight result."""
    state.job.logger.error(message)
    return PreflightResult(blocking_error=message, hint=_preflight_hint(state.notes))


def _missing_backend_preflight(
    job: "ProxboxSyncJob", fastapi_endpoint_id: int | None
) -> PreflightResult:
    """Return the fatal result for a missing selected backend."""
    selected = (
        f" (selected endpoint id {fastapi_endpoint_id})"
        if fastapi_endpoint_id is not None
        else ""
    )
    message = (
        "Proxbox preflight failed: no usable proxbox-api backend is "
        f"configured in NetBox{selected}. Every sync stage runs through that "
        "backend, so none of them can run. Add an enabled FastAPI endpoint "
        "under Proxbox → Endpoints → FastAPI, then run the sync again."
    )
    job.logger.error(message)
    hint = _preflight_hint(["no enabled FastAPI endpoint is configured in NetBox"])
    return PreflightResult(blocking_error=message, hint=hint)


def _resolve_backend_preflight_state(
    job: "ProxboxSyncJob", fastapi_endpoint_id: int | None
) -> tuple[_BackendPreflightState | None, PreflightResult | None]:
    """Resolve the selected backend without importing transport helpers early."""
    from netbox_proxbox.services.backend_context import get_fastapi_request_context  # noqa: PLC0415

    context = get_fastapi_request_context(endpoint_id=fastapi_endpoint_id)
    if context is None or not context.http_url:
        return None, _missing_backend_preflight(job, fastapi_endpoint_id)
    return _BackendPreflightState(job, context), None


def _probe_backend_preflight(
    state: _BackendPreflightState,
    fastapi_endpoint_id: int | None,
) -> None:
    """Record bounded reachability and API-key checks as preflight hints."""
    from netbox_proxbox.services.backend_auth import (  # noqa: PLC0415
        PREFLIGHT_READY_INITIAL_DELAY,
        PREFLIGHT_READY_MAX_DELAY,
        PREFLIGHT_READY_MAX_RETRIES,
        ensure_backend_key_registered,
        wait_for_backend_ready,
    )

    ready, ready_msg = wait_for_backend_ready(
        state.context,
        max_retries=PREFLIGHT_READY_MAX_RETRIES,
        initial_delay=PREFLIGHT_READY_INITIAL_DELAY,
        max_delay=PREFLIGHT_READY_MAX_DELAY,
    )
    _record_backend_reachability(state, ready, ready_msg)
    key_ok, key_msg = ensure_backend_key_registered(endpoint_id=fastapi_endpoint_id)
    _record_backend_key_check(state, key_ok, key_msg)


def _record_backend_reachability(
    state: _BackendPreflightState, ready: bool, message: str
) -> None:
    """Record one proxbox-api health-check outcome."""
    if ready:
        state.job.logger.info(f"Preflight: backend reachable — {message}")
        return
    state.job.logger.warning(f"Preflight: backend not reachable — {message}")
    state.notes.append(f"the proxbox-api backend failed its health check ({message})")


def _record_backend_key_check(
    state: _BackendPreflightState, key_ok: bool, message: str
) -> None:
    """Record one proxbox-api key-registration outcome."""
    if key_ok:
        state.job.logger.info(f"Preflight: API key verified — {message}")
        return
    state.job.logger.warning(f"Preflight: API key registration failed — {message}")
    state.notes.append(f"the proxbox-api API key was not registered ({message})")


def _push_one_netbox_endpoint(
    state: _BackendPreflightState,
    push: _NetBoxEndpointPush,
    endpoint: object,
    push_endpoint: object,
) -> None:
    """Push one local NetBox endpoint and record its exact outcome."""
    push.endpoints.append(endpoint)
    ok, error, _ = push_endpoint(
        endpoint,
        base_url=state.base_url,
        auth_headers=state.auth_headers,
        backend_verify_ssl=state.verify_ssl,
    )
    label = getattr(endpoint, "name", endpoint.pk)
    if ok:
        push.succeeded = True
        state.job.logger.info(
            f"Preflight: synced NetBox endpoint '{label}' to proxbox-api backend"
        )
        return
    state.job.logger.warning(
        f"Preflight: could not sync NetBox endpoint '{label}' to proxbox-api: {error}"
    )
    push.failures.append(f"'{label}': {error}")


def _push_enabled_netbox_endpoints(
    state: _BackendPreflightState,
) -> _NetBoxEndpointPush:
    """Push all enabled local NetBox endpoints to the selected backend."""
    from netbox_proxbox.models import NetBoxEndpoint  # noqa: PLC0415
    from netbox_proxbox.views.backend_sync import (  # noqa: PLC0415
        sync_netbox_endpoint_to_backend,
    )

    push = _NetBoxEndpointPush()
    for endpoint in NetBoxEndpoint.objects.filter(enabled=True):
        _push_one_netbox_endpoint(
            state, push, endpoint, sync_netbox_endpoint_to_backend
        )
    return push


def _no_enabled_netbox_endpoint(
    state: _BackendPreflightState,
) -> PreflightResult:
    """Block when this NetBox has revoked every writable endpoint row."""
    message = (
        "Proxbox preflight failed: this NetBox has no enabled NetBox endpoint, "
        "so proxbox-api is not authorized to write to it. A disabled or missing "
        "NetBox endpoint is a hard stop, not a warning — any credentials the "
        "backend still holds are stale or belong to another NetBox instance, and "
        "syncing with them would write outside this instance's control. Enable "
        "(or create) the NetBox endpoint under Proxbox → Endpoints, then run the "
        "sync again."
    )
    state.notes.append("no enabled NetBox endpoint exists in this NetBox instance")
    return _blocking_preflight(state, message)


def _unverifiable_netbox_endpoint(
    state: _BackendPreflightState,
    failure_text: str,
    list_error: object,
) -> PreflightResult:
    """Block when neither a push nor an identity read can prove ownership."""
    message = (
        "Proxbox preflight failed: this run could not push its NetBox "
        f"endpoint ({failure_text}), and could not read back which NetBox "
        f"endpoint proxbox-api holds either ({list_error}). Without one of "
        "those two the backend's credentials cannot be shown to belong to "
        "this NetBox, and syncing with somebody else's would write this "
        "estate's Proxmox inventory into their instance. Check that "
        f"proxbox-api is running and reachable at {state.base_url} and that the "
        "FastAPI endpoint token in NetBox matches the one it expects, then "
        "run the sync again."
    )
    return _blocking_preflight(state, message)


def _empty_backend_netbox_endpoints(
    state: _BackendPreflightState,
    failure_text: str,
) -> PreflightResult:
    """Block when a failed push leaves proxbox-api without a NetBox row."""
    message = (
        "Proxbox preflight failed: proxbox-api holds no NetBox endpoint and "
        f"this run could not push one ({failure_text}). Without it the "
        "backend has no credentials to write to NetBox, so every sync stage "
        "would fail with an unrelated-looking error. Check that proxbox-api "
        f"is running and reachable at {state.base_url}, that the FastAPI endpoint "
        "token in NetBox matches the one it expects, then run the sync again."
    )
    return _blocking_preflight(state, message)


def _rotated_backend_netbox_endpoint(
    state: _BackendPreflightState,
    failure_text: str,
) -> PreflightResult:
    """Block a stored NetBox row whose locally attested credential changed."""
    message = (
        "Proxbox preflight failed: this run could not push its NetBox "
        f"endpoint ({failure_text}), and the NetBox endpoint record "
        "proxbox-api holds was written with different credentials than "
        "this NetBox endpoint now carries (its API token was rotated, "
        "or has never been pushed successfully). Continuing would let "
        "the backend keep writing with a credential this NetBox has "
        "replaced. Check that proxbox-api is running and reachable at "
        f"{state.base_url} and that the FastAPI endpoint token in NetBox "
        "matches the one it expects, then run the sync again so the "
        "current token is pushed."
    )
    return _blocking_preflight(state, message)


def _foreign_backend_netbox_endpoint(
    state: _BackendPreflightState,
    failure_text: str,
    backend_rows: list[object],
) -> PreflightResult:
    """Block stored backend credentials that do not identify this NetBox."""
    message = (
        "Proxbox preflight failed: this run could not push its NetBox "
        f"endpoint ({failure_text}), and the "
        f"{len(backend_rows)} NetBox endpoint record(s) proxbox-api "
        "already holds do not point at this NetBox. Continuing would "
        "let the backend write to whichever NetBox those stored "
        "credentials belong to instead of this one. Check that "
        f"proxbox-api is reachable at {state.base_url} and that its NetBox "
        "endpoint matches this instance's domain/IP and port, then run "
        "the sync again."
    )
    return _blocking_preflight(state, message)


def _verify_stored_netbox_endpoints(
    state: _BackendPreflightState,
    push: _NetBoxEndpointPush,
    failure_text: str,
    backend_rows: list[object],
) -> PreflightResult | None:
    """Classify stored proxbox-api NetBox rows after a failed local push."""
    from netbox_proxbox.views.backend_sync import (  # noqa: PLC0415
        backend_holds_netbox_endpoint,
        netbox_push_credentials_unchanged,
    )

    held = [
        endpoint
        for endpoint in push.endpoints
        if backend_holds_netbox_endpoint(endpoint, backend_rows)
    ]
    vouched = [
        endpoint for endpoint in held if netbox_push_credentials_unchanged(endpoint)
    ]
    if vouched:
        state.job.logger.warning(
            "Preflight: the NetBox endpoint push failed, but proxbox-api "
            f"already holds {len(backend_rows)} NetBox endpoint record(s) "
            "pointing at this NetBox; continuing with the backend's stored "
            "configuration, which may be stale."
        )
        return None
    if held:
        return _rotated_backend_netbox_endpoint(state, failure_text)
    return _foreign_backend_netbox_endpoint(state, failure_text, backend_rows)


def _classify_failed_netbox_push(
    state: _BackendPreflightState,
    push: _NetBoxEndpointPush,
) -> PreflightResult | None:
    """Require positive ownership evidence after any NetBox endpoint push fails."""
    from netbox_proxbox.views.backend_sync import (  # noqa: PLC0415
        list_backend_netbox_endpoints,
    )

    failure_text = "; ".join(push.failures)
    state.notes.append(
        f"the NetBox endpoint was not pushed to proxbox-api ({failure_text})"
    )
    backend_rows, list_error = list_backend_netbox_endpoints(
        base_url=state.base_url,
        auth_headers=state.auth_headers,
        backend_verify_ssl=state.verify_ssl,
    )
    if backend_rows is None and push.succeeded:
        state.job.logger.warning(
            "Preflight: could not verify which NetBox endpoint proxbox-api "
            f"holds — {list_error}. Another enabled NetBox endpoint was pushed "
            "successfully, so continuing."
        )
        return None
    if backend_rows is None:
        return _unverifiable_netbox_endpoint(state, failure_text, list_error)
    if not backend_rows:
        return _empty_backend_netbox_endpoints(state, failure_text)
    return _verify_stored_netbox_endpoints(state, push, failure_text, backend_rows)


def _verify_netbox_endpoint_push(
    state: _BackendPreflightState,
    push: _NetBoxEndpointPush,
) -> PreflightResult | None:
    """Return a blocking result unless this NetBox's write identity is proven."""
    if not push.endpoints:
        return _no_enabled_netbox_endpoint(state)
    if push.failures:
        return _classify_failed_netbox_push(state, push)
    return None


def _selected_proxmox_endpoints(
    state: _BackendPreflightState,
    proxmox_endpoint_ids: list[str] | None,
):
    """Return enabled Proxmox endpoints within the requested local scope."""
    if not proxmox_endpoint_ids:
        return ProxmoxEndpoint.objects.filter(enabled=True)
    endpoint_ids = _coerce_endpoint_ids(
        proxmox_endpoint_ids,
        logger=state.job.logger,
        context="preflight endpoint push",
    )
    return ProxmoxEndpoint.objects.filter(pk__in=endpoint_ids, enabled=True)


def _proxmox_skip_summary(
    elapsed: float,
    already_registered: bool,
    budget: float,
    hard_ceiling: float,
) -> str | None:
    """Return why one endpoint push must be skipped, or ``None`` to push."""
    if elapsed >= hard_ceiling:
        return (
            "Skipped: the preflight endpoint-push hard ceiling of "
            f"{hard_ceiling:.0f}s was reached"
        )
    if elapsed >= budget and already_registered:
        return (
            "Skipped: the preflight endpoint-push budget of "
            f"{budget:.0f}s was exhausted and proxbox-api already holds this endpoint"
        )
    return None


def _skipped_proxmox_phase(endpoint: object, summary: str) -> dict[str, object]:
    """Build a zero-runtime warning phase for a budget-skipped endpoint."""
    return _endpoint_runtime_phase(
        endpoint_id=getattr(endpoint, "pk", None),
        endpoint_name=getattr(endpoint, "name", None) or str(endpoint),
        kind="preflight",
        label="Backend endpoint push",
        runtime_seconds=0.0,
        status="warning",
        summary=summary,
    )


def _proxmox_rotation_note(
    state: _BackendPreflightState,
    endpoint: object,
    label: object,
) -> str:
    """Attribute a failed push to credential rotation without exposing secrets."""
    from netbox_proxbox.views.backend_sync import (  # noqa: PLC0415
        proxmox_endpoint_credentials_rotated_since_last_push,
    )

    try:
        rotated = proxmox_endpoint_credentials_rotated_since_last_push(endpoint)
    except Exception as exc:  # noqa: BLE001
        state.job.logger.warning(
            f"Could not evaluate credential rotation for Proxmox endpoint "
            f"{getattr(endpoint, 'pk', None)}: {type(exc).__name__}"
        )
        return ""
    if not rotated:
        return ""
    state.notes.append(
        f"Proxmox endpoint '{label}' push failed after an in-place credential "
        "change; proxbox-api may still hold the previous secret."
    )
    return (
        " This endpoint's credentials changed since the last confirmed push, "
        "so proxbox-api may still be holding the previous secret — if so, "
        "Proxmox reads for this endpoint will fail to authenticate until a push "
        "succeeds."
    )


def _push_one_proxmox_endpoint(
    state: _BackendPreflightState,
    endpoint: object,
    existing_endpoints: list[object] | None,
) -> dict[str, object]:
    """Push one Proxmox endpoint and return its runtime phase."""
    from netbox_proxbox.views.backend_sync import (  # noqa: PLC0415
        sync_proxmox_endpoint_to_backend,
    )

    label = getattr(endpoint, "name", endpoint.pk)
    started = time.monotonic()
    ok, error, _ = sync_proxmox_endpoint_to_backend(
        endpoint,
        base_url=state.base_url,
        auth_headers=state.auth_headers,
        backend_verify_ssl=state.verify_ssl,
        existing_endpoints=existing_endpoints,
    )
    if ok:
        state.job.logger.info(
            f"Preflight: synced Proxmox endpoint '{label}' to proxbox-api backend"
        )
    else:
        rotation_note = _proxmox_rotation_note(state, endpoint, label)
        state.job.logger.warning(
            f"Preflight: could not sync Proxmox endpoint "
            f"'{label}' to proxbox-api: {error}{rotation_note}"
        )
    return _proxmox_push_phase(endpoint, started, ok, error)


def _proxmox_push_phase(
    endpoint: object,
    started: float,
    ok: bool,
    error: object,
) -> dict[str, object]:
    """Build one completed Proxmox endpoint-push runtime phase."""
    summary = (
        "Proxmox endpoint pushed to proxbox-api"
        if ok
        else f"Proxmox endpoint push failed: {error}"
    )
    return _endpoint_runtime_phase(
        endpoint_id=getattr(endpoint, "pk", None),
        endpoint_name=getattr(endpoint, "name", None) or str(endpoint),
        kind="preflight",
        label="Backend endpoint push",
        runtime_seconds=_runtime_seconds_since(started),
        status="success" if ok else "warning",
        summary=summary,
    )


def _record_skipped_proxmox_pushes(
    state: _BackendPreflightState,
    skipped: list[str],
    budget: float,
    hard_ceiling: float,
) -> None:
    """Carry endpoint-push budget exhaustion into logs and later stage hints."""
    if not skipped:
        return
    skipped_text = ", ".join(skipped)
    state.job.logger.warning(
        f"Preflight: the {budget:.0f}s endpoint-push budget was exhausted; "
        f"skipped pushing {len(skipped)} Proxmox endpoint(s) to proxbox-api "
        f"({skipped_text}). Continuing — each skipped endpoint was either already "
        f"held by the backend or skipped past the {hard_ceiling:.0f}s hard ceiling."
    )
    state.notes.append(
        f"{len(skipped)} Proxmox endpoint(s) were not pushed to proxbox-api "
        f"because the preflight push budget was exhausted ({skipped_text})"
    )


def _push_proxmox_endpoints(
    state: _BackendPreflightState,
    proxmox_endpoint_ids: list[str] | None,
) -> PreflightResult:
    """Push selected Proxmox endpoints within the bounded preflight budget."""
    from netbox_proxbox.views.backend_sync import (  # noqa: PLC0415
        PREFLIGHT_ENDPOINT_PUSH_BUDGET,
        PREFLIGHT_ENDPOINT_PUSH_HARD_CEILING,
        backend_holds_proxmox_endpoint,
        list_backend_proxmox_endpoints,
    )

    endpoints = _selected_proxmox_endpoints(state, proxmox_endpoint_ids)
    existing, error = list_backend_proxmox_endpoints(
        base_url=state.base_url,
        auth_headers=state.auth_headers,
        backend_verify_ssl=state.verify_ssl,
    )
    if existing is None:
        state.job.logger.warning(
            "Preflight: could not list the Proxmox endpoints proxbox-api holds "
            f"— {error}. Each endpoint push will list them itself."
        )
    phases: list[dict[str, object]] = []
    skipped: list[str] = []
    started = time.monotonic()
    for endpoint in endpoints:
        elapsed = time.monotonic() - started
        registered = backend_holds_proxmox_endpoint(endpoint, existing)
        summary = _proxmox_skip_summary(
            elapsed,
            registered,
            PREFLIGHT_ENDPOINT_PUSH_BUDGET,
            PREFLIGHT_ENDPOINT_PUSH_HARD_CEILING,
        )
        if summary is not None:
            skipped.append(str(getattr(endpoint, "name", endpoint.pk)))
            phases.append(_skipped_proxmox_phase(endpoint, summary))
            continue
        _log_over_budget_unregistered(
            state, endpoint, elapsed, PREFLIGHT_ENDPOINT_PUSH_BUDGET
        )
        phases.append(_push_one_proxmox_endpoint(state, endpoint, existing))
    _record_skipped_proxmox_pushes(
        state,
        skipped,
        PREFLIGHT_ENDPOINT_PUSH_BUDGET,
        PREFLIGHT_ENDPOINT_PUSH_HARD_CEILING,
    )
    return PreflightResult(phases=phases, hint=_preflight_hint(state.notes))


def _log_over_budget_unregistered(
    state: _BackendPreflightState,
    endpoint: object,
    elapsed: float,
    budget: float,
) -> None:
    """Explain why an unregistered endpoint still pushes after budget expiry."""
    if elapsed < budget:
        return
    label = getattr(endpoint, "name", endpoint.pk)
    state.job.logger.info(
        f"Preflight: past the {budget:.0f}s push budget, but proxbox-api does not "
        f"yet hold '{label}' — pushing anyway so the endpoint can resolve to a "
        "backend id"
    )


def _ensure_backend_endpoints(
    job: "ProxboxSyncJob",
    proxmox_endpoint_ids: list[str] | None = None,
    fastapi_endpoint_id: int | None = None,
) -> PreflightResult:
    """Validate backend identity and push endpoint data before reconciliation."""
    state, blocking = _resolve_backend_preflight_state(job, fastapi_endpoint_id)
    if blocking is not None or state is None:
        return blocking or _missing_backend_preflight(job, fastapi_endpoint_id)
    _probe_backend_preflight(state, fastapi_endpoint_id)
    netbox_push = _push_enabled_netbox_endpoints(state)
    blocking = _verify_netbox_endpoint_push(state, netbox_push)
    if blocking is not None:
        return blocking
    return _push_proxmox_endpoints(state, proxmox_endpoint_ids)


class BackendKeyPreflightError(RuntimeError):
    """Raised when a sync job cannot prove its stored backend key."""


def _require_backend_key(
    job: "ProxboxSyncJob",
    endpoint_id: int | None = None,
) -> None:
    """Abort the entire job unless one stored key authenticates read-only."""
    from netbox_proxbox.services.backend_auth import ensure_backend_key_registered  # noqa: PLC0415

    key_ok, key_msg = ensure_backend_key_registered(endpoint_id=endpoint_id)
    if not key_ok:
        job.logger.error(f"Preflight: API key verification failed — {key_msg}")
        raise BackendKeyPreflightError(
            "Backend API-key preflight failed; no sync stage was started."
        )
    job.logger.info(f"Preflight: API key verified — {key_msg}")


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


def _enabled_endpoint_ids(
    raw_ids: list[str] | None = None,
    *,
    logger: object | None = None,
    context: str = "sync",
) -> list[int]:
    """Return enabled Proxmox endpoint ids, optionally constrained to requested ids."""
    if raw_ids:
        requested_ids = _coerce_endpoint_ids(raw_ids, logger=logger, context=context)
        if not requested_ids:
            return []
        qs = ProxmoxEndpoint.objects.filter(pk__in=requested_ids, enabled=True)
    else:
        qs = ProxmoxEndpoint.objects.filter(enabled=True)
    return list(qs.values_list("pk", flat=True))


def _now_for_service_monitoring() -> datetime:
    """Return a timezone-aware timestamp when Django is available."""
    try:
        from django.utils import timezone
    except Exception:  # noqa: BLE001 - isolated tests may not stub Django
        return datetime.now()
    return timezone.now()


def service_monitoring_collection_due(
    endpoint: object,
    *,
    latest_collected_at: datetime | None = None,
    now: datetime | None = None,
) -> bool:
    """Return whether an endpoint is due for a service-monitoring collection."""
    if not getattr(endpoint, "service_monitoring_enabled", False):
        return False
    if not getattr(endpoint, "service_monitoring_eligible", False):
        return False
    # Disabled endpoints are never contacted (inlined endpoint_is_enabled).
    if not bool(getattr(endpoint, "enabled", True)):
        return False
    try:
        interval_minutes = int(
            getattr(endpoint, "service_monitoring_interval_minutes", 5) or 5
        )
    except (TypeError, ValueError):
        interval_minutes = 5
    interval_minutes = max(interval_minutes, 1)

    if latest_collected_at is None:
        return True
    current_time = now or _now_for_service_monitoring()
    return latest_collected_at <= current_time - timedelta(minutes=interval_minutes)


def _record_service_monitoring_tick_error(endpoint: object, error: str) -> None:
    """Persist scheduler collection failures on the endpoint heartbeat fields."""
    setattr(endpoint, "service_monitoring_last_status", "failed")
    setattr(endpoint, "service_monitoring_last_error", error)
    save = getattr(endpoint, "save", None)
    if callable(save):
        try:
            save(
                update_fields=[
                    "service_monitoring_last_status",
                    "service_monitoring_last_error",
                ]
            )
        except TypeError:
            save()


# NetBox system-job intervals are in MINUTES (INTERVAL_MINUTELY=1). This is a
# 1-minute base tick; each endpoint is then collected only once its own
# service_monitoring_interval_minutes has elapsed (default 5).
@system_job(interval=1)
class ProxmoxServiceMonitoringJob(JobRunner):
    """Periodic (1-minute) tick for async Proxmox endpoint service monitoring."""

    class Meta:
        name = "Proxmox Service Monitoring"

    def run(self, **kwargs: object) -> None:
        """Project finished collections and enqueue due service-monitoring RPCs."""
        del kwargs
        from django.db.models import Max

        from netbox_proxbox.integrations.rpc import (
            collect_systemctl_services,
            project_completed_collections,
        )
        from netbox_proxbox.models import ProxmoxServiceCollection
        from netbox_proxbox.models.service_monitoring import (
            SERVICE_COLLECTION_STATUS_PENDING,
        )

        projected_count = project_completed_collections()
        logger = getattr(self, "logger", None)
        if logger is not None and projected_count:
            logger.info(
                "Projected %s completed Proxmox service collection(s).",
                projected_count,
            )

        endpoints = list(
            ProxmoxEndpoint.objects.filter(
                service_monitoring_enabled=True, enabled=True
            )
        )
        if not endpoints:
            return

        endpoint_ids = [endpoint.pk for endpoint in endpoints]
        latest_by_endpoint = {
            row["endpoint_id"]: row["last_collected_at"]
            for row in ProxmoxServiceCollection.objects.filter(
                endpoint_id__in=endpoint_ids
            )
            .values("endpoint_id")
            .annotate(last_collected_at=Max("collected_at"))
        }
        pending_endpoint_ids = set(
            ProxmoxServiceCollection.objects.filter(
                endpoint_id__in=endpoint_ids,
                status=SERVICE_COLLECTION_STATUS_PENDING,
            ).values_list("endpoint_id", flat=True)
        )
        now = _now_for_service_monitoring()
        requested_by = getattr(getattr(self, "job", None), "user", None)

        for endpoint in endpoints:
            try:
                if not getattr(endpoint, "service_monitoring_eligible", False):
                    _record_service_monitoring_tick_error(
                        endpoint,
                        (
                            "Service monitoring is enabled but the endpoint is no "
                            "longer eligible; check allow_writes, API + SSH access, "
                            "endpoint SSH credentials, and netbox-rpc enablement."
                        ),
                    )
                    continue
                if not service_monitoring_collection_due(
                    endpoint,
                    latest_collected_at=latest_by_endpoint.get(endpoint.pk),
                    now=now,
                ):
                    continue
                if endpoint.pk in pending_endpoint_ids:
                    if logger is not None:
                        logger.info(
                            "Skipping Proxmox service monitoring for endpoint %s; "
                            "a prior collection is still pending.",
                            getattr(endpoint, "pk", endpoint),
                        )
                    continue
                collect_systemctl_services(
                    endpoint,
                    requested_by=requested_by,
                    trigger="scheduled",
                )
            except Exception as exc:  # noqa: BLE001 - keep ticking other endpoints
                if logger is not None:
                    logger.exception(
                        "Failed to collect service status for endpoint %s.",
                        getattr(endpoint, "pk", endpoint),
                    )
                _record_service_monitoring_tick_error(endpoint, str(exc))


class _SyncRunContext:
    """Normalized inputs and mutable state for one Proxbox sync run."""

    __slots__ = (
        "batch_object_ids",
        "batch_object_type",
        "branch",
        "branch_config",
        "fastapi_endpoint_id",
        "job",
        "netbox_endpoint_ids",
        "netbox_vm_ids",
        "params",
        "proxmox_endpoint_ids",
        "run_started",
        "stages",
        "types",
    )

    def __init__(
        self,
        *,
        job: "ProxboxSyncJob",
        branch_config: dict[str, str] | None,
        types: list[str],
        proxmox_endpoint_ids: list[str] | None,
        netbox_endpoint_ids: list[str] | None,
        netbox_vm_ids: list[str] | None,
        batch_object_type: str | None,
        batch_object_ids: list[str],
        fastapi_endpoint_id: int | None,
    ) -> None:
        self.job = job
        self.branch_config = branch_config
        self.types = types
        self.proxmox_endpoint_ids = proxmox_endpoint_ids
        self.netbox_endpoint_ids = netbox_endpoint_ids
        self.netbox_vm_ids = netbox_vm_ids
        self.batch_object_type = batch_object_type
        self.batch_object_ids = batch_object_ids
        self.fastapi_endpoint_id = fastapi_endpoint_id
        self.run_started = time.monotonic()
        self.stages = expanded_sync_stages(types)
        self.branch: object | None = None
        self.params = _build_sync_run_params(self)


class _StagedSyncState:
    """Preflight state accumulated before the estate-wide service phases."""

    __slots__ = ("endpoint_ids", "phases", "preflight")

    def __init__(
        self,
        *,
        endpoint_ids: list[int],
        phases: list[dict[str, object]],
        preflight: PreflightResult,
    ) -> None:
        self.endpoint_ids = endpoint_ids
        self.phases = phases
        self.preflight = preflight


def _branching_failure_stage(message: str) -> dict[str, object]:
    """Build the stable persisted record for one isolation failure."""
    return {
        "sync_type": "branch-isolation",
        "endpoint_id": None,
        "stream_path": None,
        "runtime_seconds": 0.0,
        "result_summary": {"ok": False, "error": message},
    }


def _branching_failure_response(
    sync_data: dict[str, object], message: str
) -> dict[str, object]:
    """Append an isolation failure without discarding earlier run evidence."""
    raw_response = sync_data.get("response")
    response = dict(raw_response) if isinstance(raw_response, dict) else {}
    raw_stages = response.get("stages")
    stages = list(raw_stages) if isinstance(raw_stages, list) else []
    stages = [stage for stage in stages if stage.get("sync_type") != "branch-isolation"]
    stages.append(_branching_failure_stage(message))
    response["stages"] = stages
    response.setdefault("endpoint_runtimes", [])
    response.setdefault(
        "runtime_summary",
        _runtime_summary(runtime_seconds=0.0, endpoint_runtimes=[]),
    )
    return response


def _record_branching_failure(job: "ProxboxSyncJob", message: str) -> None:
    """Persist an unavailable-branching failure in the normal stage result shape."""
    raw_data = getattr(job.job, "data", None)
    data = dict(raw_data) if isinstance(raw_data, dict) else {}
    raw_sync = data.get("proxbox_sync")
    sync_data = dict(raw_sync) if isinstance(raw_sync, dict) else {}
    sync_data.setdefault("runtime_seconds", 0.0)
    sync_data["response"] = _branching_failure_response(sync_data, message)
    data["proxbox_sync"] = sync_data
    job.job.data = data
    job.job.save(update_fields=["data"])


def _resolve_branching_config(job: "ProxboxSyncJob") -> dict[str, str] | None:
    """Resolve the owned run's immutable branch-isolation settings snapshot."""
    from netbox_proxbox.services.branch_lifecycle import (  # noqa: PLC0415
        BranchingDecisionState,
        require_branch_isolation_or_raise,
    )

    decision = require_branch_isolation_or_raise()
    if decision.state is BranchingDecisionState.DISABLED:
        return None
    return decision.settings


def _normalize_run_types(
    sync_types: list[str] | None,
    sync_type: str | None,
) -> list[str]:
    """Normalize legacy and multi-stage job inputs into one ordered type list."""
    if sync_types:
        return normalize_sync_types([str(value) for value in sync_types])
    if sync_type is not None:
        return normalize_sync_types([str(sync_type)])
    return [SyncTypeChoices.ALL]


def _prepare_sync_run(
    job: "ProxboxSyncJob",
    *,
    branch_config: dict[str, str] | None,
    sync_types: list[str] | None,
    sync_type: str | None,
    proxmox_endpoint_ids: list[str] | None,
    netbox_endpoint_ids: list[str] | None,
    netbox_vm_ids: list[str] | None,
    batch_object_type: str | None,
    batch_object_ids: list[str] | None,
    fastapi_endpoint_id: int | None,
) -> _SyncRunContext:
    """Normalize job inputs and create the run context after ownership is claimed."""
    normalized_batch_type = (
        str(batch_object_type).strip() if batch_object_type else None
    )
    return _SyncRunContext(
        job=job,
        branch_config=branch_config,
        types=_normalize_run_types(sync_types, sync_type),
        proxmox_endpoint_ids=proxmox_endpoint_ids,
        netbox_endpoint_ids=netbox_endpoint_ids,
        netbox_vm_ids=netbox_vm_ids,
        batch_object_type=normalized_batch_type,
        batch_object_ids=_normalize_batch_object_ids(batch_object_ids),
        fastapi_endpoint_id=fastapi_endpoint_id,
    )


def _build_sync_run_params(context: _SyncRunContext) -> dict[str, object]:
    """Build persisted and backend parameters shared by batch and staged runs."""
    return {
        "sync_types": context.types,
        "proxmox_endpoint_ids": [
            str(value)
            for value in list(context.proxmox_endpoint_ids or [])
            if str(value)
        ],
        "netbox_endpoint_ids": [
            str(value)
            for value in list(context.netbox_endpoint_ids or [])
            if str(value)
        ],
        "netbox_vm_ids": [
            str(value) for value in list(context.netbox_vm_ids or []) if str(value)
        ],
        "batch_object_type": context.batch_object_type,
        "batch_object_ids": context.batch_object_ids,
        "fastapi_endpoint_id": context.fastapi_endpoint_id,
        "run_id": str(uuid.uuid4()),
    }


def _create_sync_branch(context: _SyncRunContext) -> object | None:
    """Create and provision the configured isolation branch for this run."""
    if context.branch_config is None:
        return None
    from netbox_proxbox.services.branch_lifecycle import (  # noqa: PLC0415
        BranchingUnavailableError,
        create_and_provision_branch,
    )

    branch_name = (
        f"{context.branch_config['prefix']}-{context.job.job.pk}-"
        f"{int(context.run_started)}"
    )
    context.job.logger.info(
        f"NetBox branching enabled — creating branch {branch_name!r}"
    )
    try:
        branch = create_and_provision_branch(
            name=branch_name,
            user=getattr(context.job.job, "user", None),
        )
    except BranchingUnavailableError:
        raise
    except Exception as exc:
        message = (
            f"Proxbox sync refused: failed to create/provision NetBox branch "
            f"{branch_name}: {exc}"
        )
        context.job.logger.error(message)
        _record_branching_failure(context.job, message)
        raise
    context.job.logger.info(
        f"Branch {branch.name} ready (schema_id={branch.schema_id})"
    )
    return branch


def _merge_sync_branch(context: _SyncRunContext) -> None:
    """Merge a successful isolation branch using the configured conflict policy."""
    if context.branch is None or context.branch_config is None:
        return
    from netbox_proxbox.services.branch_lifecycle import merge_branch  # noqa: PLC0415

    merged, message, disposition = merge_branch(
        branch=context.branch,
        user=getattr(context.job.job, "user", None),
        on_conflict=context.branch_config["on_conflict"],
    )
    if merged:
        if disposition is not None:
            _persist_branch_disposition(context, disposition)
        context.job.logger.info(message)
        return
    context.job.logger.error(message)
    _record_branching_failure(context.job, message)
    raise RuntimeError(message)


def _branch_identity(branch: object | None) -> dict[str, object] | None:
    """Return the durable identity of a provisioned isolation branch."""
    if branch is None:
        return None
    return {
        "id": getattr(branch, "pk", getattr(branch, "id", None)),
        "name": str(getattr(branch, "name", "<unknown>")),
        "schema_id": str(getattr(branch, "schema_id", "")),
    }


def _sync_data_with_branch(context: _SyncRunContext) -> dict[str, object]:
    """Build sync data that always retains the provisioned branch identity."""
    sync_data: dict[str, object] = {"params": context.params}
    identity = _branch_identity(context.branch)
    if identity is not None:
        sync_data["branch"] = identity
    return sync_data


def _persist_initial_sync_data(context: _SyncRunContext) -> None:
    """Persist normalized parameters before any backend reconciliation starts."""
    sync_data = _sync_data_with_branch(context)
    sync_data["params"] = _serialize_sync_params(**context.params)
    context.job.job.data = {"proxbox_sync": sync_data}
    context.job.job.save(update_fields=["data"])


def _persist_branch_disposition(context: _SyncRunContext, status: str) -> None:
    """Add a final left-open branch disposition without losing run evidence."""
    data = dict(context.job.job.data or {})
    sync_data = dict(data.get("proxbox_sync") or {})
    response = dict(sync_data.get("response") or {})
    identity = _branch_identity(context.branch) or {}
    response["branch_disposition"] = {
        "status": status,
        "branch_id": identity.get("id"),
        "branch_name": identity.get("name"),
    }
    sync_data["response"] = response
    data["proxbox_sync"] = sync_data
    context.job.job.data = data
    context.job.job.save(update_fields=["data"])


def _bootstrap_backend_endpoints(context: _SyncRunContext) -> PreflightResult:
    """Push endpoint configuration and stop when the backend cannot write safely."""
    preflight = _ensure_backend_endpoints(
        context.job,
        context.proxmox_endpoint_ids or [],
        fastapi_endpoint_id=context.fastapi_endpoint_id,
    )
    if preflight.blocking_error:
        raise ProxboxPreflightError(preflight.blocking_error)
    return preflight


def _resolve_batch_endpoint_scope(
    context: _SyncRunContext,
) -> tuple[str, dict[str, str]]:
    """Resolve the selected-object run's bounded Proxmox backend scope."""
    wire_scope, skipped_pks, scope_error, wire_by_pk = _batch_wire_endpoint_scope(
        context.params["proxmox_endpoint_ids"],
        fastapi_endpoint_id=context.fastapi_endpoint_id,
    )
    if scope_error:
        context.job.logger.error(f"Skipping selected-object sync: {scope_error}")
        raise ProxboxPreflightError(f"Selected-object sync did not run: {scope_error}")
    if skipped_pks:
        context.job.logger.warning(
            "Selected-object sync is scoped to "
            f"{len(skipped_pks)} fewer Proxmox endpoint(s) than are enabled; "
            f"unresolved endpoint id(s): {', '.join(skipped_pks)}"
        )
    return wire_scope, wire_by_pk


def _run_batch_coroutine(
    coroutine: Coroutine[object, object, dict[str, object]],
) -> dict[str, object]:
    """Run the batch coroutine from ordinary or already-async worker contexts."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None or not loop.is_running():
        return asyncio.run(coroutine)
    import concurrent.futures  # noqa: PLC0415

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coroutine).result()


def _execute_batch_sync(
    context: _SyncRunContext,
    wire_scope: str,
    wire_by_pk: dict[str, str],
) -> dict[str, object]:
    """Execute one selected-object batch with branch and endpoint scopes."""
    return _run_batch_coroutine(
        _run_batch_selected_sync(
            context.job,
            batch_object_type=context.batch_object_type,
            batch_object_ids=context.batch_object_ids,
            netbox_branch_schema_id=context.params["netbox_branch_schema_id"],
            fastapi_endpoint_id=context.fastapi_endpoint_id,
            proxmox_wire_endpoint_ids=wire_scope,
            proxmox_wire_endpoint_by_pk=wire_by_pk,
        )
    )


def _batch_result_summary(batch_result: dict[str, object]) -> str:
    """Return the stable human-readable selected-object result summary."""
    return (
        f"{batch_result['batch_object_label']} "
        f"({batch_result['total']} total, "
        f"{batch_result['succeeded']} succeeded, "
        f"{batch_result['failed']} failed)"
    )


def _persist_batch_result(
    context: _SyncRunContext,
    batch_result: dict[str, object],
    preflight: PreflightResult,
) -> None:
    """Persist selected-object output before classifying any object failures."""
    sync_data = _sync_data_with_branch(context)
    sync_data.update(
        {
            "runtime_seconds": _runtime_seconds_since(context.run_started),
            "response": {
                "batch": batch_result,
                "endpoint_runtimes": _build_endpoint_runtimes(preflight.phases),
            },
        }
    )
    context.job.job.data = {
        "proxbox_sync": sync_data,
    }
    context.job.job.save(update_fields=["data"])


def _raise_for_batch_failures(
    job: "ProxboxSyncJob",
    batch_result: dict[str, object],
    summary: str,
) -> None:
    """Fail a selected-object run after its per-object details are persisted."""
    if int(batch_result.get("failed") or 0) <= 0:
        return
    message = (
        f"Batch sync failed for {summary} — {_failed_batch_object_detail(batch_result)}"
    )
    job.logger.error(message)
    raise RuntimeError(message)


def _run_batch_phase(context: _SyncRunContext) -> bool:
    """Run and finalize selected-object work, returning whether it applied."""
    if not context.batch_object_type or not context.batch_object_ids:
        return False
    context.job.logger.info(
        f"Starting batch sync for {len(context.batch_object_ids)} selected "
        f"{context.batch_object_type} records"
    )
    preflight = _bootstrap_backend_endpoints(context)
    wire_scope, wire_by_pk = _resolve_batch_endpoint_scope(context)
    batch_result = _execute_batch_sync(context, wire_scope, wire_by_pk)
    _persist_batch_result(context, batch_result, preflight)
    summary = _batch_result_summary(batch_result)
    _raise_for_batch_failures(context.job, batch_result, summary)
    context.job.logger.info(f"Batch sync completed for {summary}")
    _merge_sync_branch(context)
    return True


def _log_staged_sync_start(context: _SyncRunContext) -> None:
    """Log the selected stages and optional object scopes."""
    context.job.logger.info(
        f"Starting Proxbox sync stages: {', '.join(context.stages)}"
    )
    if context.proxmox_endpoint_ids:
        context.job.logger.info(f"Proxmox endpoints: {context.proxmox_endpoint_ids}")
    if context.netbox_endpoint_ids:
        context.job.logger.info(f"NetBox endpoints: {context.netbox_endpoint_ids}")
    if context.netbox_vm_ids:
        context.job.logger.info(f"NetBox virtual machines: {context.netbox_vm_ids}")


def _staged_endpoint_ids(context: _SyncRunContext) -> list[int]:
    """Resolve enabled plugin endpoint IDs for pre-SSE service passes."""
    return _enabled_endpoint_ids(
        context.proxmox_endpoint_ids or None,
        logger=context.job.logger,
        context="cluster/node sync",
    )


def _sync_cluster_phase(
    context: _SyncRunContext,
    endpoint_ids: list[int],
    branch: object | None,
) -> list[dict[str, object]]:
    """Synchronize cluster/node inventory and record per-endpoint runtimes."""
    from netbox_proxbox.services.branch_lifecycle import (  # noqa: PLC0415
        activate_sync_branch,
    )
    from netbox_proxbox.services.sync_cluster import sync_cluster_and_nodes  # noqa: PLC0415

    with activate_sync_branch(branch):
        return _sync_cluster_endpoints(context, endpoint_ids, sync_cluster_and_nodes)


def _sync_cluster_endpoints(
    context: _SyncRunContext,
    endpoint_ids: list[int],
    sync_cluster_and_nodes: object,
) -> list[dict[str, object]]:
    """Run cluster/node reconciliation while its caller holds branch activation."""
    phases: list[dict[str, object]] = []
    for endpoint_id in endpoint_ids:
        context.job.logger.info(f"Syncing cluster/nodes for endpoint {endpoint_id}")
        started = time.monotonic()
        result = sync_cluster_and_nodes(
            endpoint_id=endpoint_id,
            fastapi_endpoint_id=context.fastapi_endpoint_id,
        )
        summary = _cluster_result_summary(context.job, endpoint_id, result)
        phases.append(
            _endpoint_runtime_phase(
                endpoint_id=getattr(result, "endpoint_id", None) or endpoint_id,
                endpoint_name=getattr(result, "endpoint_name", ""),
                kind="cluster",
                label="Cluster/node sync",
                runtime_seconds=_runtime_seconds_since(started),
                status="success" if result.success else "warning",
                summary=summary,
            )
        )
    return phases


def _cluster_result_summary(
    job: "ProxboxSyncJob",
    endpoint_id: int,
    result: object,
) -> str:
    """Log and return one cluster/node service result summary."""
    if result.success:
        summary = (
            f"{result.clusters_created} cluster(s) created, "
            f"{result.clusters_updated} updated, "
            f"{result.nodes_created} node(s) created, "
            f"{result.nodes_updated} updated"
        )
        job.logger.info(f"Cluster/node sync for endpoint {endpoint_id}: {summary}")
        return summary
    summary = str(result.error or "cluster/node sync failed")
    job.logger.warning(
        f"Cluster/node sync for endpoint {endpoint_id} failed: {result.error}"
    )
    return summary


def sync_firewall(
    context: _SyncRunContext,
    endpoint_ids: list[int],
    branch: object | None,
) -> list[dict[str, object]]:
    """Synchronize datacenter firewall inventory for a non-targeted run."""
    from netbox_proxbox.services.branch_lifecycle import (  # noqa: PLC0415
        activate_sync_branch,
    )
    from netbox_proxbox.services.sync_firewall import (  # noqa: PLC0415
        sync_firewall as run_firewall_sync,
    )

    context.job.logger.info("Syncing firewall objects from proxbox-api")
    with activate_sync_branch(branch):
        result = run_firewall_sync(
            fastapi_endpoint_id=context.fastapi_endpoint_id,
            endpoint_ids=endpoint_ids,
        )
    _log_firewall_result(context.job, result)
    return _phases_from_service_result(result, kind="firewall", label="Firewall sync")


def _log_firewall_result(job: "ProxboxSyncJob", result: object) -> None:
    """Log the aggregate firewall service result."""
    if result.success:
        job.logger.info(
            f"Firewall sync complete: {result.endpoints_processed} endpoint(s), "
            f"{result.security_groups_created} sg created, "
            f"{result.rules_created} rules created, "
            f"{result.ipsets_created} ipsets created, "
            f"{result.aliases_created} aliases created"
        )
        return
    job.logger.warning(
        "Firewall sync failed or partially failed: "
        f"{result.error or 'see per_endpoint log'}"
    )


def sync_datacenter(
    context: _SyncRunContext,
    endpoint_ids: list[int],
    branch: object | None,
) -> list[dict[str, object]]:
    """Synchronize datacenter CPU models for a non-targeted run."""
    from netbox_proxbox.services.branch_lifecycle import (  # noqa: PLC0415
        activate_sync_branch,
    )
    from netbox_proxbox.services.sync_datacenter import (  # noqa: PLC0415
        sync_datacenter as run_datacenter_sync,
    )

    context.job.logger.info("Syncing datacenter CPU models from proxbox-api")
    with activate_sync_branch(branch):
        result = run_datacenter_sync(
            fastapi_endpoint_id=context.fastapi_endpoint_id,
            endpoint_ids=endpoint_ids,
        )
    _log_datacenter_result(context.job, result)
    return _phases_from_service_result(
        result,
        kind="datacenter",
        label="Datacenter sync",
    )


def _log_datacenter_result(job: "ProxboxSyncJob", result: object) -> None:
    """Log the aggregate datacenter service result."""
    if result.success:
        job.logger.info(
            f"Datacenter CPU model sync complete: {result.endpoints_processed} "
            f"endpoint(s), created={result.cpu_models_created}, "
            f"updated={result.cpu_models_updated}, stale={result.cpu_models_stale}"
        )
        return
    job.logger.warning(
        f"Datacenter CPU model sync failed: {result.error or 'unknown error'}"
    )


def _vm_template_sync_disabled() -> bool:
    """Return whether the effective global VM-template mode disables the phase."""
    modes = sync_stages.effective_sync_modes_for_endpoint(None)
    return modes.get("sync_mode_vm_template", SyncModeChoices.ALWAYS) == (
        SyncModeChoices.DISABLED
    )


def sync_vm_templates(
    context: _SyncRunContext,
    endpoint_ids: list[int],
    branch: object | None,
) -> list[dict[str, object]]:
    """Synchronize dedicated VM-template inventory when its mode allows it."""
    if _vm_template_sync_disabled():
        context.job.logger.info(
            "Skipping VM template sync: sync_mode_vm_template=disabled"
        )
        return []
    from netbox_proxbox.services.branch_lifecycle import (  # noqa: PLC0415
        activate_sync_branch,
    )

    with activate_sync_branch(branch):
        return _sync_vm_templates_for_endpoints(context, endpoint_ids)


def _sync_vm_templates_for_endpoints(
    context: _SyncRunContext,
    endpoint_ids: list[int],
) -> list[dict[str, object]]:
    """Run the VM-template service once for each selected endpoint."""
    from netbox_proxbox.services.sync_vm_template import sync_vm_templates  # noqa: PLC0415

    phases: list[dict[str, object]] = []
    for endpoint_id in endpoint_ids:
        context.job.logger.info(f"Syncing VM templates for endpoint {endpoint_id}")
        started = time.monotonic()
        result = sync_vm_templates(
            endpoint_id=endpoint_id,
            fastapi_endpoint_id=context.fastapi_endpoint_id,
        )
        summary = _vm_template_result_summary(context.job, endpoint_id, result)
        phases.append(
            _endpoint_runtime_phase(
                endpoint_id=getattr(result, "endpoint_id", None) or endpoint_id,
                endpoint_name=getattr(result, "endpoint_name", ""),
                kind="vm_template",
                label="VM template sync",
                runtime_seconds=_runtime_seconds_since(started),
                status="success" if result.success is True else "warning",
                summary=summary,
            )
        )
    return phases


def _vm_template_result_summary(
    job: "ProxboxSyncJob",
    endpoint_id: int,
    result: object,
) -> str:
    """Log and return one VM-template service result summary."""
    if result.success:
        summary = (
            f"{result.templates_created} template(s) created, "
            f"{result.templates_updated} updated, "
            f"{result.templates_skipped} skipped, "
            f"{result.templates_deleted} deleted"
        )
        job.logger.info(f"VM template sync for endpoint {endpoint_id}: {summary}")
        return summary
    summary = str(result.error or "VM template sync failed")
    job.logger.warning(
        f"VM template sync for endpoint {endpoint_id} failed: {result.error}"
    )
    return summary


def _warn_for_missing_stage_runtimes(
    job: "ProxboxSyncJob",
    stages: list[dict[str, object]],
) -> None:
    """Log any in-memory stage result missing its runtime."""
    for stage in stages:
        if stage.get("runtime_seconds") is None:
            job.logger.warning(
                f"Stage '{stage.get('sync_type')}' has runtime_seconds=None before save"
            )


_LOCAL_PHASE_KINDS = frozenset({"cluster", "firewall", "datacenter", "vm_template"})


def _local_phases(phases: list[dict[str, object]]) -> list[dict[str, object]]:
    """Return persisted classifications for every selected local service pass."""
    return [phase for phase in phases if phase.get("kind") in _LOCAL_PHASE_KINDS]


def _failed_local_phases(
    phases: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Return local service passes that did not report success."""
    return [
        phase for phase in _local_phases(phases) if phase.get("status") != "success"
    ]


def _local_failure_detail(phases: list[dict[str, object]]) -> str:
    """Render local service failures with endpoint context when available."""
    details: list[str] = []
    for phase in phases:
        label = str(phase.get("label") or phase.get("kind") or "Local sync")
        endpoint_id = phase.get("endpoint_id")
        scope = f" for endpoint {endpoint_id}" if endpoint_id is not None else ""
        summary = str(phase.get("summary") or "unknown error")
        details.append(f"{label}{scope}: {summary}")
    return "; ".join(details)


def _local_failure_disposition(
    context: _SyncRunContext,
    phases: list[dict[str, object]],
) -> dict[str, object] | None:
    """Describe the unmerged branch retained after local reconciliation fails."""
    if context.branch is None or not _failed_local_phases(phases):
        return None
    return {
        "status": "left_open",
        "branch_name": str(getattr(context.branch, "name", "<unknown>")),
        "reason": "local_reconciliation_failed",
    }


def _sse_failure_disposition(
    context: _SyncRunContext,
    phases: list[dict[str, object]],
) -> dict[str, object] | None:
    """Describe the open isolation branch retained after an SSE exception."""
    disposition = _local_failure_disposition(context, phases)
    if disposition is not None or context.branch is None:
        return disposition
    return {
        "status": "left_open",
        "branch_name": str(getattr(context.branch, "name", "<unknown>")),
        "reason": "sse_failed",
    }


def _persist_staged_result(
    context: _SyncRunContext,
    stages: list[dict[str, object]],
    phases: list[dict[str, object]],
    branch_disposition: dict[str, object] | None = None,
) -> float:
    """Persist staged output and return the rounded whole-run duration."""
    runtime_seconds = _runtime_seconds_since(context.run_started)
    endpoint_runtimes = _build_endpoint_runtimes(phases)
    response: dict[str, object] = {
        "stages": stages,
        "local_phases": _local_phases(phases),
        "endpoint_runtimes": endpoint_runtimes,
        "runtime_summary": _runtime_summary(
            runtime_seconds=runtime_seconds,
            endpoint_runtimes=endpoint_runtimes,
        ),
    }
    disposition = branch_disposition or _local_failure_disposition(context, phases)
    if disposition is not None:
        response["branch_disposition"] = disposition
    sync_data = _sync_data_with_branch(context)
    sync_data.update({"runtime_seconds": runtime_seconds, "response": response})
    context.job.job.data = {"proxbox_sync": sync_data}
    context.job.job.save(update_fields=["data"])
    return runtime_seconds


def _stored_stages(job: "ProxboxSyncJob") -> list[dict[str, object]]:
    """Refresh and return the stages persisted by the just-finished run."""
    job.job.refresh_from_db(fields=["data"])
    raw_stages = (
        (job.job.data or {})
        .get("proxbox_sync", {})
        .get("response", {})
        .get("stages", [])
    )
    return raw_stages if isinstance(raw_stages, list) else []


def _check_stored_stage_runtimes(
    job: "ProxboxSyncJob",
    stages: list[dict[str, object]],
) -> None:
    """Report runtimes lost during the job-data database round trip."""
    missing = [
        stage.get("sync_type")
        for stage in stages
        if stage.get("runtime_seconds") is None
    ]
    if missing:
        job.logger.error(
            f"runtime_seconds lost after DB round-trip for stages: {missing}"
        )


def _failed_endpoint_scopes(
    stages: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Return endpoint-scope records that prevented selected work from running."""
    return [
        stage
        for stage in stages
        if stage.get("sync_type") == "endpoint-scope"
        and not (stage.get("result_summary") or {}).get("ok", True)
    ]


def _failed_scope_detail(stages: list[dict[str, object]]) -> str:
    """Join endpoint-scope errors without labeling whole-run failures as None."""
    details: list[str] = []
    for stage in stages:
        result = stage.get("result_summary") or {}
        error = result.get("error") or "unknown error"
        if stage.get("endpoint_id") is None:
            details.append(str(error))
        else:
            details.append(f"endpoint {stage.get('endpoint_id')}: {error}")
    return "; ".join(details)


def _any_sync_stage_ran(stages: list[dict[str, object]]) -> bool:
    """Return whether any non-scope, non-skipped stage actually executed."""
    return any(
        stage.get("sync_type") != "endpoint-scope"
        and not (stage.get("result_summary") or {}).get("skipped")
        for stage in stages
    )


def _raise_for_failed_endpoint_scopes(
    job: "ProxboxSyncJob",
    stages: list[dict[str, object]],
) -> None:
    """Fail after persisting any endpoint scopes that could not be resolved."""
    failed = _failed_endpoint_scopes(stages)
    if not failed:
        return
    detail = _failed_scope_detail(failed)
    if _any_sync_stage_ran(stages):
        message = (
            f"{len(failed)} Proxmox endpoint(s) were skipped and did not sync — "
            f"{detail}"
        )
    else:
        message = (
            f"No sync stage ran: every selected Proxmox endpoint was skipped — {detail}"
        )
    job.logger.error(message)
    raise RuntimeError(message)


def _raise_for_failed_local_phases(
    context: _SyncRunContext,
    phases: list[dict[str, object]],
) -> None:
    """Fail after persisting any unsuccessful local reconciliation phase."""
    failed = _failed_local_phases(phases)
    if not failed:
        return
    message = f"Local reconciliation failed: {_local_failure_detail(failed)}"
    if context.branch is not None:
        name = getattr(context.branch, "name", "<unknown>")
        message = f"{message}. Branch {name} was left open for operator inspection."
    context.job.logger.error(message)
    raise RuntimeError(message)


def _begin_sync_run(context: _SyncRunContext) -> None:
    """Create and record the optional branch before backend authentication."""
    _sync_stage_settings()
    context.branch = _create_sync_branch(context)
    _persist_initial_sync_data(context)
    context.params["netbox_branch_schema_id"] = getattr(
        context.branch,
        "schema_id",
        None,
    )
    _require_backend_key(context.job, context.fastapi_endpoint_id)


def _extend_and_checkpoint_local_phases(
    context: _SyncRunContext,
    state: _StagedSyncState,
    phases: list[dict[str, object]],
) -> None:
    """Persist each completed local phase before another phase can start."""
    state.phases.extend(phases)
    _persist_staged_result(context, [], state.phases)


def _start_staged_sync(context: _SyncRunContext) -> _StagedSyncState:
    """Run endpoint bootstrap and the always-applicable cluster/node phase."""
    _log_staged_sync_start(context)
    preflight = _bootstrap_backend_endpoints(context)
    endpoint_ids = _staged_endpoint_ids(context)
    state = _StagedSyncState(
        endpoint_ids=endpoint_ids,
        phases=list(preflight.phases),
        preflight=preflight,
    )
    phases = _sync_cluster_phase(context, endpoint_ids, context.branch)
    _extend_and_checkpoint_local_phases(context, state, phases)
    return state


def _run_sse_stages(
    context: _SyncRunContext,
    state: _StagedSyncState,
) -> list[dict[str, object]]:
    """Checkpoint accumulated local evidence if the SSE run does not return."""
    try:
        return _run_all_stages_sync(
            context.job,
            context.stages,
            context.params,
            context.run_started,
            preflight_hint=state.preflight.hint,
        )
    except BaseException:
        disposition = _sse_failure_disposition(context, state.phases)
        _persist_staged_result(
            context,
            [],
            state.phases,
            branch_disposition=disposition,
        )
        raise


def _finish_staged_sync(
    context: _SyncRunContext,
    state: _StagedSyncState,
) -> None:
    """Run SSE stages, persist their results, classify errors, and merge."""
    stages = _run_sse_stages(context, state)
    state.phases.extend(_phases_from_stage_results(stages))
    _warn_for_missing_stage_runtimes(context.job, stages)
    runtime_seconds = _persist_staged_result(context, stages, state.phases)
    _check_stored_stage_runtimes(context.job, _stored_stages(context.job))
    _raise_for_failed_endpoint_scopes(context.job, stages)
    _raise_for_failed_local_phases(context, state.phases)
    context.job.logger.info(
        f"All sync stages completed ({len(stages)}), runtime {runtime_seconds:.3f}s"
    )
    _merge_sync_branch(context)


def _pop_enqueued_sync_types(kwargs: dict[str, object]) -> list[str]:
    """Remove legacy sync-type inputs and return their normalized replacement."""
    sync_types = kwargs.pop("sync_types", None)
    sync_type = kwargs.pop("sync_type", None)
    if sync_types is not None:
        return normalize_sync_types(list(sync_types))
    if sync_type is not None:
        return normalize_sync_types([str(sync_type)])
    return [SyncTypeChoices.ALL]


def _normalize_enqueued_batch(kwargs: dict[str, object]) -> None:
    """Normalize selected-object inputs in the queued RQ payload."""
    batch_object_type = kwargs.pop("batch_object_type", None)
    batch_object_ids = _normalize_batch_object_ids(kwargs.pop("batch_object_ids", None))
    if batch_object_type is not None:
        kwargs["batch_object_type"] = str(batch_object_type)
    if batch_object_ids:
        kwargs["batch_object_ids"] = batch_object_ids


def _normalize_enqueued_backend_pin(kwargs: dict[str, object]) -> int | None:
    """Keep the RQ payload and persisted backend pin identical."""
    if "fastapi_endpoint_id" not in kwargs:
        return None
    backend_pin = _coerce_fastapi_endpoint_id(kwargs.pop("fastapi_endpoint_id"))
    if backend_pin is not None:
        kwargs["fastapi_endpoint_id"] = backend_pin
    return backend_pin


def _stringified_values(values: object) -> list[str]:
    """Return non-empty queued identifier values as strings."""
    return [str(value) for value in list(values or []) if str(value)]


def _enqueued_sync_params(
    kwargs: dict[str, object],
    sync_types: list[str],
    backend_pin: int | None,
) -> dict[str, object]:
    """Build the canonical persisted parameter record for an enqueued job."""
    return {
        "sync_types": sync_types,
        "proxmox_endpoint_ids": _stringified_values(kwargs.get("proxmox_endpoint_ids")),
        "netbox_endpoint_ids": _stringified_values(kwargs.get("netbox_endpoint_ids")),
        "netbox_vm_ids": _stringified_values(kwargs.get("netbox_vm_ids")),
        "batch_object_type": kwargs.get("batch_object_type"),
        "batch_object_ids": _stringified_values(kwargs.get("batch_object_ids")),
        "fastapi_endpoint_id": backend_pin,
    }


def _persist_enqueued_sync_params(job: Job, params: dict[str, object]) -> None:
    """Store replay-safe sync parameters on the NetBox Job row."""
    job.data = {"proxbox_sync": {"params": _serialize_sync_params(**params)}}
    job.save(update_fields=["data"])


class ProxboxSyncJob(JobRunner):
    """Trigger a ProxBox sync operation against the FastAPI backend."""

    class Meta:
        name = "Proxbox Sync"

    @classmethod
    def enqueue(cls, *args: object, **kwargs: object) -> Job:
        """Enqueue like other ``JobRunner`` jobs, but with a long RQ ``job_timeout`` by default."""
        kwargs.setdefault("job_timeout", PROXBOX_SYNC_JOB_TIMEOUT)
        normalized = _pop_enqueued_sync_types(kwargs)
        kwargs["sync_types"] = normalized
        _normalize_enqueued_batch(kwargs)
        backend_pin = _normalize_enqueued_backend_pin(kwargs)
        job = super().enqueue(*args, **kwargs)
        params = _enqueued_sync_params(kwargs, normalized, backend_pin)
        _persist_enqueued_sync_params(job, params)
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
        """Run one owned sync against one immutable settings snapshot.

        Ownership is claimed before branch settings are read or audit data is
        written. The owned run then resolves branching once and retains that
        branch configuration through finalization; settings changed during the
        run apply only to the next owner.
        """
        del kwargs
        fastapi_endpoint_id = _coerce_fastapi_endpoint_id(fastapi_endpoint_id)
        if not _claim_rq_sync_ownership(self.job):
            self.logger.info(
                "Sync ownership already claimed by SSE stream, RQ job skipping sync execution"
            )
            return
        from netbox_proxbox.services.branch_lifecycle import (  # noqa: PLC0415
            BranchingUnavailableError,
        )

        try:
            branch_config = _resolve_branching_config(self)
            context = _prepare_sync_run(
                self,
                branch_config=branch_config,
                sync_types=sync_types,
                sync_type=sync_type,
                proxmox_endpoint_ids=proxmox_endpoint_ids,
                netbox_endpoint_ids=netbox_endpoint_ids,
                netbox_vm_ids=netbox_vm_ids,
                batch_object_type=batch_object_type,
                batch_object_ids=batch_object_ids,
                fastapi_endpoint_id=fastapi_endpoint_id,
            )
            _begin_sync_run(context)
            if _run_batch_phase(context):
                return
            staged_state = _start_staged_sync(context)
            targeted_vm_run = bool(netbox_vm_ids)
            if targeted_vm_run:
                target_ids = ", ".join(netbox_vm_ids or [])
                self.logger.info(
                    "Skipping firewall sync: targeted virtual-machine run "
                    f"({target_ids})"
                )
                self.logger.info(
                    "Skipping datacenter CPU model sync: targeted virtual-machine "
                    f"run ({target_ids})"
                )
                self.logger.info(
                    "Skipping VM template sync: targeted virtual-machine run "
                    f"({target_ids})"
                )
            else:
                _extend_and_checkpoint_local_phases(
                    context,
                    staged_state,
                    sync_firewall(context, staged_state.endpoint_ids, context.branch),
                )
                _extend_and_checkpoint_local_phases(
                    context,
                    staged_state,
                    sync_datacenter(context, staged_state.endpoint_ids, context.branch),
                )
                _extend_and_checkpoint_local_phases(
                    context,
                    staged_state,
                    sync_vm_templates(
                        context, staged_state.endpoint_ids, context.branch
                    ),
                )
            _finish_staged_sync(context, staged_state)
        except BranchingUnavailableError as exc:
            message = str(exc)
            self.logger.error(message)
            _record_branching_failure(self, message)
            raise
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


def proxbox_sync_job_q():
    """Return a ``Q`` selecting the same rows :func:`is_proxbox_sync_job` accepts.

    The Python predicate answers "is *this* row ours?" one object at a time,
    which a list view cannot use -- it needs the question pushed into SQL. The
    two must agree, so both are built from the same constants and
    ``tests/test_proxbox_job_filter.py`` asserts parity over a row matrix
    rather than trusting that they were written to match.

    Two translation details are easy to get wrong:

    * ``queue_name`` is normalised by the predicate as ``queue_name or ""``, so
      the SQL ``NULL`` case must be spelled out. A bare ``__in`` list never
      matches ``NULL``, which would silently drop every job whose queue was
      never recorded.
    * The predicate compares ``name.strip()``, so both name tests are anchored
      regexes tolerating surrounding whitespace rather than plain equality.

    Note that ``queue_name`` alone is not a discriminator: ``PROXBOX_SYNC_QUEUE_NAME``
    is NetBox's shared ``default`` queue, so it only counts alongside a name match.
    """
    import re

    from django.db.models import Q

    default_label = getattr(ProxboxSyncJob.Meta, "name", "Proxbox Sync")
    allowed_queue = (
        Q(queue_name__isnull=True)
        | Q(queue_name="")
        | Q(queue_name=PROXBOX_SYNC_QUEUE_NAME)
        | Q(queue_name=LEGACY_PROXBOX_RQ_QUEUE)
    )
    # Reuse the targeted-VM pattern itself, minus its anchors, so a change to
    # the job-name format cannot leave this filter behind.
    targeted_inner = _TARGETED_VM_JOB_NAME_RE.pattern.removeprefix("^").removesuffix(
        "$"
    )

    # ``has_key`` alone is *not* the predicate's test. It compiles to jsonb's
    # ``?`` operator, which is also true for a top-level **array** containing
    # the string -- ``data == ["proxbox_sync"]`` -- while the predicate requires
    # a dict. Pairing it with the key transform restores object semantics:
    # ``'["proxbox_sync"]'::jsonb -> 'proxbox_sync'`` is SQL NULL, so an array
    # is excluded, while ``{"proxbox_sync": null}`` yields JSON null (not SQL
    # NULL) and is still matched -- which is what ``"proxbox_sync" in data``
    # does.
    has_proxbox_sync_object = Q(data__has_key="proxbox_sync") & Q(
        data__proxbox_sync__isnull=False
    )

    return (
        has_proxbox_sync_object
        | Q(queue_name=LEGACY_PROXBOX_RQ_QUEUE)
        | (Q(name__regex=rf"^\s*{re.escape(default_label)}\s*$") & allowed_queue)
        | Q(name__regex=rf"^\s*{targeted_inner}\s*$")
    )
