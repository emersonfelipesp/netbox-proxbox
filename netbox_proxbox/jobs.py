"""Background job for triggering ProxBox sync operations via the FastAPI backend."""

from __future__ import annotations

import asyncio
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


def _ensure_backend_endpoints(
    job: "ProxboxSyncJob",
    proxmox_endpoint_ids: list[str] | None = None,
    fastapi_endpoint_id: int | None = None,
) -> PreflightResult:
    """Push NetBox and Proxmox endpoint data to the proxbox-api backend before sync.

    Mostly best-effort: a Proxmox endpoint push failure is recorded as a warning
    phase and the run continues, because the backend may already hold that row
    from an earlier push or from manual creation in the Next.js UI.

    Two cases are fatal. Without *any* FastAPI backend there is nothing to sync
    through at all. And proxbox-api writes NetBox objects with the credentials
    the NetBox-endpoint push installs, so when that push fails **and** the
    backend confirms it holds no NetBox endpoint, no stage can succeed either.
    Continuing anyway is what turned a cold-start timeout into an unrelated
    "Error ensuring Proxbox tag" several minutes and several wasted stages later,
    so both are reported as blocking errors instead.

    ``fastapi_endpoint_id`` selects *which* backend to check. It must be the one
    the stages will run against: checking a different enabled backend can both
    block a run that would have worked and pass a run that cannot.
    """
    from netbox_proxbox.services.backend_context import get_fastapi_request_context  # noqa: PLC0415

    context = get_fastapi_request_context(endpoint_id=fastapi_endpoint_id)
    if context is None or not context.http_url:
        selected = (
            f" (selected endpoint id {fastapi_endpoint_id})"
            if fastapi_endpoint_id is not None
            else ""
        )
        blocking_error = (
            "Proxbox preflight failed: no usable proxbox-api backend is "
            f"configured in NetBox{selected}. Every sync stage runs through that "
            "backend, so none of them can run. Add an enabled FastAPI endpoint "
            "under Proxbox → Endpoints → FastAPI, then run the sync again."
        )
        job.logger.error(blocking_error)
        return PreflightResult(
            blocking_error=blocking_error,
            hint=_preflight_hint(
                ["no enabled FastAPI endpoint is configured in NetBox"]
            ),
        )

    # Imported after the guard above: with no backend configured there is nothing
    # for these to talk to, and the early return must not depend on them.
    from netbox_proxbox.models import NetBoxEndpoint  # noqa: PLC0415
    from netbox_proxbox.services.backend_auth import (  # noqa: PLC0415
        PREFLIGHT_READY_INITIAL_DELAY,
        PREFLIGHT_READY_MAX_DELAY,
        PREFLIGHT_READY_MAX_RETRIES,
        ensure_backend_key_registered,
        wait_for_backend_ready,
    )
    from netbox_proxbox.views.backend_sync import (  # noqa: PLC0415
        PREFLIGHT_ENDPOINT_PUSH_BUDGET,
        PREFLIGHT_ENDPOINT_PUSH_HARD_CEILING,
        backend_holds_netbox_endpoint,
        backend_holds_proxmox_endpoint,
        list_backend_netbox_endpoints,
        list_backend_proxmox_endpoints,
        netbox_push_credentials_unchanged,
        proxmox_endpoint_credentials_rotated_since_last_push,
        sync_netbox_endpoint_to_backend,
        sync_proxmox_endpoint_to_backend,
    )

    notes: list[str] = []

    # Give a cold backend a bounded chance to answer before the first
    # authenticated call.  A freshly started proxbox-api spends its first seconds
    # opening SQLite and resolving the NetBox OpenAPI schema, and without this the
    # preflight raced that start-up and failed on timeouts alone.
    ready, ready_msg = wait_for_backend_ready(
        context,
        max_retries=PREFLIGHT_READY_MAX_RETRIES,
        initial_delay=PREFLIGHT_READY_INITIAL_DELAY,
        max_delay=PREFLIGHT_READY_MAX_DELAY,
    )
    if ready:
        job.logger.info(f"Preflight: backend reachable — {ready_msg}")
    else:
        job.logger.warning(f"Preflight: backend not reachable — {ready_msg}")
        notes.append(f"the proxbox-api backend failed its health check ({ready_msg})")

    # Ensure the API key is registered before making authenticated requests.
    key_ok, key_msg = ensure_backend_key_registered(endpoint_id=fastapi_endpoint_id)
    if key_ok:
        job.logger.info(f"Preflight: API key verified — {key_msg}")
    else:
        job.logger.warning(f"Preflight: API key registration failed — {key_msg}")
        notes.append(f"the proxbox-api API key was not registered ({key_msg})")

    base_url = context.http_url.rstrip("/")
    auth_headers = dict(context.headers or {})
    backend_verify_ssl = bool(context.verify_ssl)

    # Push all enabled NetBox endpoints (singleton in practice).
    netbox_push_failures: list[str] = []
    netbox_push_succeeded = False
    netbox_endpoint_count = 0
    enabled_netbox_endpoints: list[object] = []
    for nb_ep in NetBoxEndpoint.objects.filter(enabled=True):
        netbox_endpoint_count += 1
        enabled_netbox_endpoints.append(nb_ep)
        ok, err, _ = sync_netbox_endpoint_to_backend(
            nb_ep,
            base_url=base_url,
            auth_headers=auth_headers,
            backend_verify_ssl=backend_verify_ssl,
        )
        nb_label = getattr(nb_ep, "name", nb_ep.pk)
        if ok:
            netbox_push_succeeded = True
            job.logger.info(
                f"Preflight: synced NetBox endpoint '{nb_label}' to proxbox-api backend"
            )
        else:
            job.logger.warning(
                f"Preflight: could not sync NetBox endpoint "
                f"'{nb_label}' to proxbox-api: {err}"
            )
            netbox_push_failures.append(f"'{nb_label}': {err}")

    if netbox_endpoint_count == 0:
        # Zero enabled rows is not a failed push — it is this NetBox declining to
        # be written to at all. A disabled (or absent) NetBoxEndpoint is the
        # documented hard no-connection gate, so it blocks unconditionally and
        # the backend's stored rows are deliberately *not* consulted: proxbox-api
        # may still hold credentials from before the row was disabled, or for an
        # entirely different NetBox instance, and honouring those would let the
        # sync keep writing with exactly the authorization the operator revoked.
        blocking_error = (
            "Proxbox preflight failed: this NetBox has no enabled NetBox endpoint, "
            "so proxbox-api is not authorized to write to it. A disabled or missing "
            "NetBox endpoint is a hard stop, not a warning — any credentials the "
            "backend still holds are stale or belong to another NetBox instance, and "
            "syncing with them would write outside this instance's control. Enable "
            "(or create) the NetBox endpoint under Proxbox → Endpoints, then run the "
            "sync again."
        )
        job.logger.error(blocking_error)
        notes.append("no enabled NetBox endpoint exists in this NetBox instance")
        return PreflightResult(
            blocking_error=blocking_error,
            hint=_preflight_hint(notes),
        )

    # Only reachable with at least one enabled local row, so the backend's stored
    # configuration is a legitimate fallback for a *transient* push failure here.
    if netbox_push_failures:
        failure_text = "; ".join(netbox_push_failures)
        notes.append(
            f"the NetBox endpoint was not pushed to proxbox-api ({failure_text})"
        )
        # Distinguish "the backend has no NetBox credentials at all" (fatal) from
        # "the push failed but the backend still holds a usable record" (not).
        backend_rows, list_err = list_backend_netbox_endpoints(
            base_url=base_url,
            auth_headers=auth_headers,
            backend_verify_ssl=backend_verify_ssl,
        )
        if backend_rows is None and netbox_push_succeeded:
            # Another enabled row *did* reach proxbox-api, so the backend
            # provably holds this NetBox's credentials whatever the listing
            # call could not tell us. Nothing to verify.
            job.logger.warning(
                "Preflight: could not verify which NetBox endpoint proxbox-api "
                f"holds — {list_err}. Another enabled NetBox endpoint was pushed "
                "successfully, so continuing."
            )
        elif backend_rows is None:
            # Nothing was pushed and nothing can be read back, so there is no
            # evidence at all that proxbox-api holds *this* NetBox's
            # credentials — only that it may hold somebody's. Continuing here
            # would reintroduce exactly the cross-instance write this preflight
            # exists to block, just through an ambiguous read instead of a
            # mismatched row. "Unknown" is not "ours": fail closed.
            blocking_error = (
                "Proxbox preflight failed: this run could not push its NetBox "
                f"endpoint ({failure_text}), and could not read back which NetBox "
                f"endpoint proxbox-api holds either ({list_err}). Without one of "
                "those two the backend's credentials cannot be shown to belong to "
                "this NetBox, and syncing with somebody else's would write this "
                "estate's Proxmox inventory into their instance. Check that "
                f"proxbox-api is running and reachable at {base_url} and that the "
                "FastAPI endpoint token in NetBox matches the one it expects, then "
                "run the sync again."
            )
            job.logger.error(blocking_error)
            return PreflightResult(
                blocking_error=blocking_error,
                hint=_preflight_hint(notes),
            )
        elif not backend_rows:
            blocking_error = (
                "Proxbox preflight failed: proxbox-api holds no NetBox endpoint and "
                f"this run could not push one ({failure_text}). Without it the "
                "backend has no credentials to write to NetBox, so every sync stage "
                "would fail with an unrelated-looking error. Check that proxbox-api "
                f"is running and reachable at {base_url}, that the FastAPI endpoint "
                "token in NetBox matches the one it expects, then run the sync again."
            )
            job.logger.error(blocking_error)
            return PreflightResult(
                blocking_error=blocking_error,
                hint=_preflight_hint(notes),
            )
        else:
            # Three-way, because "a stored row points at this NetBox" and "that
            # row carries the credentials NetBox currently holds" are different
            # questions with different answers after an in-place token rotation.
            # `backend_holds_netbox_endpoint()` can only compare what
            # `NetBoxEndpointResponse` gives back, and it withholds
            # `token`/`token_key` — so the *secret* is checked here instead,
            # against the fingerprint the last successful push recorded locally.
            held = [
                nb_ep
                for nb_ep in enabled_netbox_endpoints
                if backend_holds_netbox_endpoint(nb_ep, backend_rows)
            ]
            vouched = [
                nb_ep for nb_ep in held if netbox_push_credentials_unchanged(nb_ep)
            ]
            if vouched:
                job.logger.warning(
                    "Preflight: the NetBox endpoint push failed, but proxbox-api "
                    f"already holds {len(backend_rows)} NetBox endpoint record(s) "
                    "pointing at this NetBox; continuing with the backend's stored "
                    "configuration, which may be stale."
                )
            elif held:
                # A row names this NetBox and reports the posture we push, but
                # the credential itself has moved on since the last successful
                # push — a rotated v1 token, or a re-issued v2 secret under the
                # same scheme. proxbox-api would keep writing with the token the
                # operator has already revoked, which is a write this NetBox no
                # longer authorizes; the whole point of rotating is that the old
                # value stops working. An *empty* stored fingerprint lands here
                # too (never pushed, or first run after upgrading into this
                # check), and blocking is the fail-closed reading: one successful
                # push clears it permanently.
                blocking_error = (
                    "Proxbox preflight failed: this run could not push its NetBox "
                    f"endpoint ({failure_text}), and the NetBox endpoint record "
                    "proxbox-api holds was written with different credentials than "
                    "this NetBox endpoint now carries (its API token was rotated, "
                    "or has never been pushed successfully). Continuing would let "
                    "the backend keep writing with a credential this NetBox has "
                    "replaced. Check that proxbox-api is running and reachable at "
                    f"{base_url} and that the FastAPI endpoint token in NetBox "
                    "matches the one it expects, then run the sync again so the "
                    "current token is pushed."
                )
                job.logger.error(blocking_error)
                return PreflightResult(
                    blocking_error=blocking_error,
                    hint=_preflight_hint(notes),
                )
            else:
                # Rows exist but none of them points at this NetBox. That is
                # worse than an empty backend, not better: proxbox-api would keep
                # writing with credentials for *somewhere else*, so the run would
                # look healthy while reconciling another instance's objects.
                # Presence is not identity — the backend's NetBox endpoint is a
                # singleton that every push overwrites, so a row can easily
                # belong to a previous deployment or to a different NetBox
                # sharing this backend.
                blocking_error = (
                    "Proxbox preflight failed: this run could not push its NetBox "
                    f"endpoint ({failure_text}), and the "
                    f"{len(backend_rows)} NetBox endpoint record(s) proxbox-api "
                    "already holds do not point at this NetBox. Continuing would "
                    "let the backend write to whichever NetBox those stored "
                    "credentials belong to instead of this one. Check that "
                    f"proxbox-api is reachable at {base_url} and that its NetBox "
                    "endpoint matches this instance's domain/IP and port, then run "
                    "the sync again."
                )
                job.logger.error(blocking_error)
                return PreflightResult(
                    blocking_error=blocking_error,
                    hint=_preflight_hint(notes),
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

    # Fetch the backend's Proxmox rows once and reuse them for every push. Each
    # push would otherwise re-list them, which on a slow or hanging backend costs
    # a full timeout per endpoint on top of the write itself.
    existing_proxmox, existing_err = list_backend_proxmox_endpoints(
        base_url=base_url,
        auth_headers=auth_headers,
        backend_verify_ssl=backend_verify_ssl,
    )
    if existing_proxmox is None:
        job.logger.warning(
            "Preflight: could not list the Proxmox endpoints proxbox-api holds "
            f"— {existing_err}. Each endpoint push will list them itself."
        )

    phases: list[dict[str, object]] = []
    push_started = time.monotonic()
    skipped_for_budget: list[str] = []
    for px_ep in proxmox_qs:
        px_label = getattr(px_ep, "name", px_ep.pk)
        elapsed = time.monotonic() - push_started
        # Preflight must not be able to consume the whole job timeout. But the
        # budget is only allowed to skip a push that is a *refresh* — skipping an
        # endpoint proxbox-api has never seen leaves it with no backend id, and
        # the run then fails on exactly the endpoint the budget "saved" time on.
        # Past the hard ceiling everything is skipped, because at that point the
        # backend is not slow, it is hung, and no amount of waiting resolves it.
        over_ceiling = elapsed >= PREFLIGHT_ENDPOINT_PUSH_HARD_CEILING
        already_registered = backend_holds_proxmox_endpoint(px_ep, existing_proxmox)
        if over_ceiling or (
            elapsed >= PREFLIGHT_ENDPOINT_PUSH_BUDGET and already_registered
        ):
            skipped_for_budget.append(str(px_label))
            skip_summary = (
                "Skipped: the preflight endpoint-push hard ceiling of "
                f"{PREFLIGHT_ENDPOINT_PUSH_HARD_CEILING:.0f}s was reached"
                if over_ceiling
                else (
                    "Skipped: the preflight endpoint-push budget of "
                    f"{PREFLIGHT_ENDPOINT_PUSH_BUDGET:.0f}s was exhausted and "
                    "proxbox-api already holds this endpoint"
                )
            )
            phases.append(
                _endpoint_runtime_phase(
                    endpoint_id=getattr(px_ep, "pk", None),
                    endpoint_name=getattr(px_ep, "name", None) or str(px_ep),
                    kind="preflight",
                    label="Backend endpoint push",
                    runtime_seconds=0.0,
                    status="warning",
                    summary=skip_summary,
                )
            )
            continue
        if elapsed >= PREFLIGHT_ENDPOINT_PUSH_BUDGET:
            job.logger.info(
                f"Preflight: past the {PREFLIGHT_ENDPOINT_PUSH_BUDGET:.0f}s push "
                f"budget, but proxbox-api does not yet hold '{px_label}' — pushing "
                "anyway so the endpoint can resolve to a backend id"
            )
        endpoint_started = time.monotonic()
        ok, err, _ = sync_proxmox_endpoint_to_backend(
            px_ep,
            base_url=base_url,
            auth_headers=auth_headers,
            backend_verify_ssl=backend_verify_ssl,
            existing_endpoints=existing_proxmox,
        )
        if ok:
            job.logger.info(
                f"Preflight: synced Proxmox endpoint '{px_label}' to proxbox-api backend"
            )
        else:
            rotated_note = ""
            try:
                if proxmox_endpoint_credentials_rotated_since_last_push(px_ep):
                    # "May" is deliberate: a failed push does not prove the
                    # backend kept the old secret — proxbox-api can commit the
                    # update and the client still time out reading the
                    # response. What the fingerprint does prove is that no
                    # *confirmed* push has delivered the current secret.
                    rotated_note = (
                        " This endpoint's credentials changed since the last "
                        "confirmed push, so proxbox-api may still be holding "
                        "the previous secret — if so, Proxmox reads for this "
                        "endpoint will fail to authenticate until a push "
                        "succeeds."
                    )
                    notes.append(
                        f"Proxmox endpoint '{px_label}' push failed after an "
                        "in-place credential change; proxbox-api may still "
                        "hold the previous secret."
                    )
            except Exception as attribution_exc:  # noqa: BLE001
                # Attribution must never fail the push loop, but a swallowed
                # decryption or DB error would silently delete the hint on the
                # runs that most need it — so the suppression is logged,
                # type-only (the exception could render decrypted material).
                rotated_note = ""
                job.logger.warning(
                    f"Could not evaluate credential rotation for Proxmox endpoint "
                    f"{getattr(px_ep, 'pk', None)}: {type(attribution_exc).__name__}"
                )
            job.logger.warning(
                f"Preflight: could not sync Proxmox endpoint "
                f"'{px_label}' to proxbox-api: {err}{rotated_note}"
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
    if skipped_for_budget:
        skipped_text = ", ".join(skipped_for_budget)
        job.logger.warning(
            f"Preflight: the {PREFLIGHT_ENDPOINT_PUSH_BUDGET:.0f}s endpoint-push "
            f"budget was exhausted; skipped pushing {len(skipped_for_budget)} "
            f"Proxmox endpoint(s) to proxbox-api ({skipped_text}). Continuing — "
            "each skipped endpoint was either already held by the backend or "
            f"skipped past the {PREFLIGHT_ENDPOINT_PUSH_HARD_CEILING:.0f}s hard "
            "ceiling."
        )
        notes.append(
            f"{len(skipped_for_budget)} Proxmox endpoint(s) were not pushed to "
            "proxbox-api because the preflight push budget was exhausted "
            f"({skipped_text})"
        )
    return PreflightResult(phases=phases, hint=_preflight_hint(notes))


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
            try:
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

        # Coerce the backend pin **before** the job is queued. The raw kwarg is
        # what RQ carries into ``run()``, so normalising it only on the way into
        # ``job.data`` left the two disagreeing: ``True`` is an ``int`` in
        # Python, so it survives to ``run()`` and Django matches ``pk=True``
        # against primary key 1, while the stored record says "unpinned". An
        # unusable value is dropped entirely rather than half-parsed, so
        # ``run()`` falls back to its own default — which is exactly what the
        # queued record now claims happened.
        if "fastapi_endpoint_id" in kwargs:
            backend_pin = _coerce_fastapi_endpoint_id(kwargs.pop("fastapi_endpoint_id"))
            if backend_pin is not None:
                kwargs["fastapi_endpoint_id"] = backend_pin
        else:
            backend_pin = None

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
            # Persisted so a replay (Run now, or a recurring schedule re-enqueueing
            # itself) targets the same proxbox-api the original run was pinned to.
            # ``run()`` accepts the kwarg and it reaches RQ either way; it is
            # ``job.data`` that outlives the RQ payload and is what
            # ``proxbox_sync_params_from_job()`` reads back. Same coerced value
            # the queued kwargs carry — see above.
            "fastapi_endpoint_id": backend_pin,
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
        # Coerced again here, not only in ``enqueue()``: direct callers, and RQ
        # payloads queued by a release that predates that normalisation, can
        # still hand this a bool or an unparseable string. Every backend lookup
        # below is a ``pk=`` filter, and ``pk=True`` silently resolves to the
        # first backend rather than failing.
        fastapi_endpoint_id = _coerce_fastapi_endpoint_id(fastapi_endpoint_id)

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
                # The batch path writes NetBox objects through proxbox-api just
                # like the SSE stages do, so it needs the same preflight. It ran
                # without one until now, which meant selected-object runs skipped
                # every hard gate below — including the "no enabled NetBox
                # endpoint" stop — and could sync using whatever credentials the
                # backend happened to still hold.
                batch_preflight = _ensure_backend_endpoints(
                    self,
                    proxmox_endpoint_ids=proxmox_endpoint_ids,
                    fastapi_endpoint_id=fastapi_endpoint_id,
                )
                if batch_preflight.blocking_error:
                    # Same exception type as the stage path, so a blocked batch
                    # run is classified and reported identically.
                    raise ProxboxPreflightError(batch_preflight.blocking_error)

                # The preflight validates the *NetBox* side; it does not decide
                # which Proxmox endpoints this run may touch. The staged path
                # settles that separately, and the batch path has to as well:
                # every individual-sync route resolves its Proxmox sessions
                # through the same dependency the stage routes use, and that
                # dependency reads a *missing* `proxmox_endpoint_ids` as "use
                # every endpoint I hold". So an unscoped selected-object sync is
                # not a narrower request than a staged one — it is the widest
                # request the backend accepts, reaching endpoints this NetBox has
                # disabled. Resolve the scope here and refuse the run outright if
                # there is none, exactly as `_run_all_stages_sync()` does.
                batch_wire_scope, skipped_scope_pks, scope_error, batch_wire_by_pk = (
                    _batch_wire_endpoint_scope(
                        params["proxmox_endpoint_ids"],
                        fastapi_endpoint_id=fastapi_endpoint_id,
                    )
                )
                if scope_error:
                    self.logger.error(f"Skipping selected-object sync: {scope_error}")
                    raise ProxboxPreflightError(
                        f"Selected-object sync did not run: {scope_error}"
                    )
                if skipped_scope_pks:
                    # Visible rather than silent: the run is scoped to fewer
                    # endpoints than the operator has enabled. A selected object
                    # that belongs to one of the skipped ones is refused by name
                    # in `_run_batch_selected_sync()` rather than asked of the
                    # remaining endpoints, and this line is what explains why.
                    self.logger.warning(
                        "Selected-object sync is scoped to "
                        f"{len(skipped_scope_pks)} fewer Proxmox endpoint(s) than "
                        "are enabled; unresolved endpoint id(s): "
                        f"{', '.join(skipped_scope_pks)}"
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
                                fastapi_endpoint_id=fastapi_endpoint_id,
                                proxmox_wire_endpoint_ids=batch_wire_scope,
                                proxmox_wire_endpoint_by_pk=batch_wire_by_pk,
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
                            fastapi_endpoint_id=fastapi_endpoint_id,
                            proxmox_wire_endpoint_ids=batch_wire_scope,
                            proxmox_wire_endpoint_by_pk=batch_wire_by_pk,
                        )
                    )
                runtime_seconds = round(time.monotonic() - run_started, 3)
                self.job.data = {
                    "proxbox_sync": {
                        "params": params,
                        "runtime_seconds": runtime_seconds,
                        "response": {
                            "batch": batch_result,
                            # Same key and builder as the stage path, so the
                            # per-endpoint breakdown renders identically.
                            "endpoint_runtimes": _build_endpoint_runtimes(
                                batch_preflight.phases
                            ),
                        },
                    }
                }
                self.job.save(update_fields=["data"])
                batch_summary = (
                    f"{batch_result['batch_object_label']} "
                    f"({batch_result['total']} total, "
                    f"{batch_result['succeeded']} succeeded, "
                    f"{batch_result['failed']} failed)"
                )
                # A selected-object run is hand-picked: every object in it was
                # named by an operator, so an object that did not sync is a
                # failed run, not a partial success. Persisting `job.data`
                # first keeps the per-object statuses and errors readable on
                # the failed row; raising *before* the branch merge keeps a
                # partial result from being promoted into main.
                if int(batch_result.get("failed") or 0) > 0:
                    batch_error = (
                        f"Batch sync failed for {batch_summary} — "
                        f"{_failed_batch_object_detail(batch_result)}"
                    )
                    self.logger.error(batch_error)
                    raise RuntimeError(batch_error)
                self.logger.info(f"Batch sync completed for {batch_summary}")
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

            # A targeted run syncs specific VirtualMachine rows (the per-VM
            # "Sync now" button). The estate-wide datacenter passes below —
            # firewall objects, datacenter CPU models, VM template inventory —
            # are irrelevant to reconciling one VM, take no scoping argument at
            # all, and were the bulk of the wall-clock in targeted runs:
            # operators syncing a single VM saw all endpoints' clusters,
            # firewalls, SDN, CPU models, and templates sync first. Skip them
            # here; a full/scheduled sync still runs them.
            targeted_vm_run = bool(netbox_vm_ids)

            # Push NetBox and Proxmox endpoint configuration to the proxbox-api
            # backend before any SSE stage runs.  The backend needs its own copy
            # of these records to open NetBox and Proxmox sessions; the post_save
            # signals are best-effort and may have missed a push if the backend
            # was offline when the endpoints were first saved.
            preflight = _ensure_backend_endpoints(
                self,
                proxmox_endpoint_ids or [],
                fastapi_endpoint_id=fastapi_endpoint_id,
            )
            endpoint_runtime_phases.extend(preflight.phases)
            if preflight.blocking_error:
                # Fail here rather than burning several minutes of doomed stages
                # and reporting whichever backend error happens to surface first.
                raise ProxboxPreflightError(preflight.blocking_error)

            # Sync cluster and node data before SSE stages so cluster/node records
            # are populated regardless of which stages are selected.
            # Lazy import to avoid a circular import through services → views → jobs.
            from netbox_proxbox.services.sync_cluster import sync_cluster_and_nodes  # noqa: PLC0415

            endpoint_ids_to_sync = (
                _enabled_endpoint_ids(
                    proxmox_endpoint_ids,
                    logger=self.logger,
                    context="cluster/node sync",
                )
                if proxmox_endpoint_ids
                else _enabled_endpoint_ids(
                    logger=self.logger,
                    context="cluster/node sync",
                )
            )
            for eid in endpoint_ids_to_sync:
                self.logger.info(f"Syncing cluster/nodes for endpoint {eid}")
                cluster_started = time.monotonic()
                cluster_result = sync_cluster_and_nodes(
                    endpoint_id=eid,
                    fastapi_endpoint_id=fastapi_endpoint_id,
                )
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
            if targeted_vm_run:
                self.logger.info(
                    "Skipping firewall sync: targeted virtual-machine run "
                    f"({', '.join(netbox_vm_ids)})"
                )
            else:
                from netbox_proxbox.services.sync_firewall import sync_firewall  # noqa: PLC0415

                self.logger.info("Syncing firewall objects from proxbox-api")
                # Scoped to this run's endpoints for the same reason the stage
                # loop is: an *absent* endpoint filter is the widest request
                # proxbox-api accepts, not a narrower one.
                fw_result = sync_firewall(
                    fastapi_endpoint_id=fastapi_endpoint_id,
                    endpoint_ids=endpoint_ids_to_sync,
                )
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

            # Sync datacenter CPU models.
            if targeted_vm_run:
                self.logger.info(
                    "Skipping datacenter CPU model sync: targeted virtual-machine run "
                    f"({', '.join(netbox_vm_ids)})"
                )
            else:
                from netbox_proxbox.services.sync_datacenter import sync_datacenter  # noqa: PLC0415

                self.logger.info("Syncing datacenter CPU models from proxbox-api")
                dc_result = sync_datacenter(
                    fastapi_endpoint_id=fastapi_endpoint_id,
                    endpoint_ids=endpoint_ids_to_sync,
                )
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
            if targeted_vm_run:
                self.logger.info(
                    "Skipping VM template sync: targeted virtual-machine run "
                    f"({', '.join(netbox_vm_ids)})"
                )
            elif (
                sync_stages.effective_sync_modes_for_endpoint(None).get(
                    "sync_mode_vm_template", SyncModeChoices.ALWAYS
                )
                == SyncModeChoices.DISABLED
            ):
                self.logger.info(
                    "Skipping VM template sync: sync_mode_vm_template=disabled"
                )
            else:
                from netbox_proxbox.services.sync_vm_template import (  # noqa: PLC0415
                    sync_vm_templates,
                )

                for eid in endpoint_ids_to_sync:
                    self.logger.info(f"Syncing VM templates for endpoint {eid}")
                    template_started = time.monotonic()
                    template_result = sync_vm_templates(
                        endpoint_id=eid,
                        fastapi_endpoint_id=fastapi_endpoint_id,
                    )
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

            stages_out = _run_all_stages_sync(
                self,
                stages,
                params,
                run_started,
                preflight_hint=preflight.hint,
            )
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

            # An endpoint whose backend id could not be resolved never reached a
            # stage at all: ``_run_all_stages_sync()`` records the reason and moves
            # on so the *other* endpoints still sync. Nothing downstream read those
            # records, though, so a run in which every selected endpoint was skipped
            # finished as **completed** having synced nothing — the exact silent
            # no-op this preflight work exists to eliminate. Raise here, after
            # ``job.data`` is saved, so the per-endpoint reasons survive on the job
            # and the JobRunner still marks the run errored.
            failed_scopes = [
                stage
                for stage in stages_out
                if stage.get("sync_type") == "endpoint-scope"
                and not (stage.get("result_summary") or {}).get("ok", True)
            ]
            if failed_scopes:
                # A record with no endpoint_id is the whole-run scope failure
                # (nothing enabled to sync at all), not a per-endpoint skip —
                # prefixing it with "endpoint None:" would read as a bug.
                skipped_detail = "; ".join(
                    (
                        f"endpoint {stage.get('endpoint_id')}: {stage_error}"
                        if stage.get("endpoint_id") is not None
                        else stage_error
                    )
                    for stage in failed_scopes
                    for stage_error in [
                        (stage.get("result_summary") or {}).get("error")
                        or "unknown error"
                    ]
                )
                # "A stage ran" means one actually executed — a stage recorded as
                # skipped by its sync mode did not, and counting it would make the
                # "No sync stage ran" message unreachable whenever any endpoint
                # contributed sync-mode skips.
                ran_any_stage = any(
                    stage.get("sync_type") != "endpoint-scope"
                    and not (stage.get("result_summary") or {}).get("skipped")
                    for stage in stages_out
                )
                if ran_any_stage:
                    scope_error = (
                        f"{len(failed_scopes)} Proxmox endpoint(s) were skipped and "
                        f"did not sync — {skipped_detail}"
                    )
                else:
                    scope_error = (
                        "No sync stage ran: every selected Proxmox endpoint was "
                        f"skipped — {skipped_detail}"
                    )
                self.logger.error(scope_error)
                raise RuntimeError(scope_error)

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
