"""Stage execution: batch sync, base/stage query params, and multi-stage orchestration."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

try:
    from netbox_proxbox.choices import SyncModeChoices, SyncTypeChoices
except ImportError:  # pragma: no cover - compatibility for focused import stubs
    from netbox_proxbox.choices import SyncTypeChoices

    class SyncModeChoices:  # type: ignore[no-redef]
        ALWAYS = "always"
        BOOTSTRAP_ONLY = "bootstrap_only"
        DISABLED = "disabled"


try:
    from netbox_proxbox.constants import SYNC_MODE_FIELDS
except ImportError:  # pragma: no cover - compatibility for focused import stubs
    SYNC_MODE_FIELDS = (
        "sync_mode_vm",
        "sync_mode_vm_template",
        "sync_mode_vm_interface",
        "sync_mode_mac",
        "sync_mode_cluster",
        "sync_mode_node",
        "sync_mode_storage",
        "sync_mode_ip_address",
    )
try:
    from netbox_proxbox.constants import SYNC_MODE_HIERARCHY
except ImportError:  # pragma: no cover - compatibility for focused import stubs
    SYNC_MODE_HIERARCHY = {
        "node": "cluster",
        "vm_interface": "vm",
        "ip_address": "vm_interface",
        "mac": "vm_interface",
    }
from netbox_proxbox.sync_types import (
    _format_seconds,
    _extract_backend_error_text,
    _format_stage_sync_error,
    _sync_stream_paths_for_stage,
    expanded_sync_stages,
    normalize_sync_types,
)
from netbox_proxbox.sync_params import (
    _normalize_batch_object_ids,
    _resolve_vm_batch_params,
    _resolve_vm_backup_batch_params,
    _resolve_vm_snapshot_batch_params,
    _resolve_storage_batch_params,
    _resolve_task_history_batch_params,
    _parse_description_metadata_setting,
    _proxbox_fetch_max_concurrency_setting,
    _use_guest_agent_interface_name_setting,
    _ignore_ipv6_link_local_addresses_setting,
    _primary_ip_preference_setting,
    _serialize_sync_params,
    effective_overwrites_for_endpoint,
    effective_sync_modes_for_endpoint,
)
from netbox_proxbox.sync_ownership import (
    _claim_rq_sync_ownership,
    _release_rq_sync_ownership,
)

if TYPE_CHECKING:
    from netbox_proxbox.jobs import ProxboxSyncJob

_HEARTBEAT_SECONDS = 20.0
_STAGE_RETRY_MAX = 2
_STAGE_RETRY_DELAY = 8.0
try:
    from netbox_proxbox.netbox_bootstrap import BOOTSTRAP_ONLY_TAG_SLUG
except ImportError:  # pragma: no cover - compatibility for focused import stubs
    BOOTSTRAP_ONLY_TAG_SLUG = "bootstrap-only"

sync_mode_vm = SyncModeChoices.ALWAYS
sync_mode_vm_template = SyncModeChoices.ALWAYS
sync_mode_vm_interface = SyncModeChoices.ALWAYS
sync_mode_mac = SyncModeChoices.ALWAYS
sync_mode_cluster = SyncModeChoices.ALWAYS
sync_mode_node = SyncModeChoices.ALWAYS
sync_mode_storage = SyncModeChoices.ALWAYS
sync_mode_ip_address = SyncModeChoices.ALWAYS

# Stages that are supplementary/optional: a failure logs a warning and the sync
# continues.  Required stages (devices, VMs, storage, interfaces, IPs) are NOT
# in this set and still abort the run on failure.
_SKIPPABLE_STAGES: frozenset[str] = frozenset(
    {
        SyncTypeChoices.VIRTUAL_MACHINES_BACKUPS,  # "vm-backups"
        SyncTypeChoices.VIRTUAL_MACHINES_SNAPSHOTS,  # "vm-snapshots"
        SyncTypeChoices.TASK_HISTORY,  # "task-history"
    }
)


def _set_sync_mode_vars(modes: dict[str, str]) -> None:
    """Update module-level sync-mode vars for the active endpoint scope."""
    for field_name in SYNC_MODE_FIELDS:
        globals()[field_name] = str(
            modes.get(field_name) or getattr(SyncModeChoices, "ALWAYS", "always")
        )


def _active_sync_modes() -> dict[str, str]:
    """Return the current module-level sync modes after parent-child cascade."""
    raw_modes = {
        field_name: str(
            globals().get(field_name) or getattr(SyncModeChoices, "ALWAYS", "always")
        )
        for field_name in SYNC_MODE_FIELDS
    }
    return _effective_sync_modes(raw_modes)


def _resource_mode(raw_modes: dict[str, str], resource_type: str) -> str:
    """Return a normalized raw mode value for a resource type."""
    field_name = f"sync_mode_{resource_type}"
    return str(
        raw_modes.get(field_name) or getattr(SyncModeChoices, "ALWAYS", "always")
    )


def _vm_parent_disabled(raw_modes: dict[str, str]) -> bool:
    """Return whether VM descendants should be disabled by the VM parent."""
    disabled = SyncModeChoices.DISABLED
    return (
        _resource_mode(raw_modes, "vm") == disabled
        and _resource_mode(raw_modes, "vm_template") == disabled
    )


def _effective_resource_mode(
    raw_modes: dict[str, str],
    resource_type: str,
    seen: set[str] | None = None,
) -> str:
    """Resolve a resource mode, forcing disabled when any ancestor is disabled."""
    disabled = SyncModeChoices.DISABLED
    raw_mode = _resource_mode(raw_modes, resource_type)
    if raw_mode == disabled:
        return disabled

    seen = set(seen or ())
    if resource_type in seen:
        return raw_mode
    seen.add(resource_type)

    parent = SYNC_MODE_HIERARCHY.get(resource_type)
    if not parent:
        return raw_mode
    if parent == "vm":
        return disabled if _vm_parent_disabled(raw_modes) else raw_mode
    if _effective_resource_mode(raw_modes, parent, seen) == disabled:
        return disabled
    return raw_mode


def _effective_sync_modes(raw_modes: dict[str, str]) -> dict[str, str]:
    """Return raw sync modes with declarative parent-child disabled cascade applied."""
    return {
        field_name: _effective_resource_mode(
            raw_modes, field_name.removeprefix("sync_mode_")
        )
        for field_name in SYNC_MODE_FIELDS
    }


def _sync_mode_for_resource(resource_type: str) -> str:
    field_name = f"sync_mode_{resource_type}"
    return _active_sync_modes().get(field_name, SyncModeChoices.ALWAYS)


def _has_bootstrap_only_tag(obj: object) -> bool:
    """Return True when a NetBox object already has the bootstrap-only tag."""
    tags = getattr(obj, "tags", None)
    if tags is None:
        return False
    try:
        return bool(tags.filter(slug=BOOTSTRAP_ONLY_TAG_SLUG).exists())
    except Exception:  # noqa: BLE001 - tag managers vary across NetBox/test stubs
        return False


def _get_bootstrap_only_tag() -> object | None:
    """Return the bootstrap-only Tag, creating it when NetBox's Tag model exists."""
    try:
        from netbox_proxbox.netbox_bootstrap import ensure_bootstrap_only_tag
    except (ImportError, RuntimeError):
        return None
    try:
        return ensure_bootstrap_only_tag()
    except Exception:  # noqa: BLE001 - bootstrap tagging must not abort sync
        return None


def _add_bootstrap_only_tag(obj: object) -> None:
    """Attach the bootstrap-only tag to a newly created object when possible."""
    tag = _get_bootstrap_only_tag()
    tags = getattr(obj, "tags", None)
    if tag is None or tags is None:
        return
    try:
        tags.add(tag)
    except Exception:  # noqa: BLE001 - bootstrap tagging must not abort sync
        return


def _bootstrap_only_should_skip_existing(obj: object, mode: str) -> bool:
    """Gate updates/deletes for objects already tagged bootstrap-only."""
    return mode == SyncModeChoices.BOOTSTRAP_ONLY and _has_bootstrap_only_tag(obj)


def _stage_skip_reason(sync_type: str) -> str | None:
    """Return why a stage should be skipped for the active sync modes."""
    disabled = SyncModeChoices.DISABLED
    vm_disabled = _sync_mode_for_resource("vm") == disabled
    template_disabled = _sync_mode_for_resource("vm_template") == disabled
    stage_resource_map = {
        SyncTypeChoices.DEVICES: "node",
        SyncTypeChoices.NETWORK_INTERFACES: "node",
        SyncTypeChoices.STORAGE: "storage",
        SyncTypeChoices.VM_INTERFACES: "vm_interface",
        SyncTypeChoices.IP_ADDRESSES: "ip_address",
    }
    resource_type = stage_resource_map.get(sync_type)
    if resource_type and _sync_mode_for_resource(resource_type) == disabled:
        return f"sync_mode_{resource_type}=disabled"
    if sync_type == SyncTypeChoices.VIRTUAL_MACHINES and (
        vm_disabled and template_disabled
    ):
        return "sync_mode_vm=disabled and sync_mode_vm_template=disabled"
    if sync_type in {
        SyncTypeChoices.VIRTUAL_MACHINES_DISKS,
        SyncTypeChoices.VIRTUAL_MACHINES_BACKUPS,
        SyncTypeChoices.VIRTUAL_MACHINES_SNAPSHOTS,
    } and (vm_disabled and template_disabled):
        return "VM and VM template sync modes are disabled"
    return None


async def _run_batch_selected_sync(
    self: "ProxboxSyncJob",
    *,
    batch_object_type: str,
    batch_object_ids: list[str],
    netbox_branch_schema_id: str | None = None,
) -> dict[str, object]:
    """Run selected object syncs concurrently with asyncio.gather."""
    from virtualization.models import VirtualMachine

    from netbox_proxbox.models import (
        ProxmoxStorage,
        VMBackup,
        VMSnapshot,
        VMTaskHistory,
    )
    from netbox_proxbox.services.individual_sync import (
        sync_individual_with_dependencies,
    )

    model_map = {
        "virtual-machine": VirtualMachine.objects.select_related(
            "cluster", "device", "site", "role", "tenant", "platform"
        ),
        "vm-backup": VMBackup.objects.select_related(
            "virtual_machine", "proxmox_storage", "proxmox_storage__cluster"
        ),
        "vm-snapshot": VMSnapshot.objects.select_related(
            "virtual_machine", "proxmox_storage", "proxmox_storage__cluster"
        ),
        "proxmox-storage": ProxmoxStorage.objects.select_related("cluster"),
        "vm-task-history": VMTaskHistory.objects.select_related("virtual_machine"),
    }

    queryset = model_map.get(batch_object_type)
    if queryset is None:
        raise ValueError(f"Unsupported batch object type: {batch_object_type!r}")

    object_ids = _normalize_batch_object_ids(batch_object_ids)
    objects = list(queryset.filter(pk__in=object_ids))
    object_by_id = {str(getattr(obj, "pk", "")): obj for obj in objects}

    semaphore = asyncio.Semaphore(_proxbox_fetch_max_concurrency_setting())

    async def run_one(object_id: str) -> dict[str, object]:
        async with semaphore:
            obj = object_by_id.get(str(object_id))
            if obj is None:
                return {
                    "batch_object_type": batch_object_type,
                    "object_id": str(object_id),
                    "status": 404,
                    "error": "Selected object was not found.",
                }

            if batch_object_type == "virtual-machine":
                params = _resolve_vm_batch_params(obj)
            elif batch_object_type == "vm-backup":
                params = _resolve_vm_backup_batch_params(obj)
            elif batch_object_type == "vm-snapshot":
                params = _resolve_vm_snapshot_batch_params(obj)
            elif batch_object_type == "proxmox-storage":
                params = _resolve_storage_batch_params(obj)
            elif batch_object_type == "vm-task-history":
                params = _resolve_task_history_batch_params(obj)
            else:
                return {
                    "batch_object_type": batch_object_type,
                    "object_id": str(object_id),
                    "status": 422,
                    "error": f"Unsupported batch object type: {batch_object_type}",
                }

            if params.get("error"):
                return {
                    "batch_object_type": batch_object_type,
                    "object_id": str(object_id),
                    "status": int(params.get("status") or 422),
                    "error": str(params.get("error")),
                }

            path = str(params["path"])
            query_params = dict(params.get("query_params") or {})
            if netbox_branch_schema_id:
                query_params["netbox_branch_schema_id"] = str(netbox_branch_schema_id)

            def _call_sync() -> tuple[dict, int, list[dict]]:
                return sync_individual_with_dependencies(path, query_params)

            response, status, dependencies = await asyncio.to_thread(_call_sync)

            if batch_object_type == "virtual-machine" and 200 <= int(status) < 300:
                from netbox_proxbox.services.tenant_assignment import (
                    maybe_assign_tenant_from_regex,
                    maybe_assign_tenant_from_tags,
                )

                def _post_sync_assign() -> None:
                    obj.refresh_from_db()
                    maybe_assign_tenant_from_regex(obj)
                    maybe_assign_tenant_from_tags(obj)

                await asyncio.to_thread(_post_sync_assign)

            return {
                "batch_object_type": batch_object_type,
                "object_id": str(object_id),
                "status": status,
                "response": response,
                "dependencies": dependencies,
                "error": response.get("error") if isinstance(response, dict) else None,
            }

    results = await asyncio.gather(*(run_one(object_id) for object_id in object_ids))
    succeeded = sum(1 for item in results if int(item.get("status", 500)) < 400)
    failed = len(results) - succeeded
    return {
        "batch_object_type": batch_object_type,
        "batch_object_label": batch_object_type.replace("-", " ").title(),
        "total": len(results),
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
    }


def _build_base_query_params(
    proxmox_endpoint_ids: list[str] | None,
    netbox_endpoint_ids: list[str] | None,
    wire_proxmox_endpoint_ids: list[str] | None = None,
) -> dict[str, str]:
    """Build base query parameters for sync stages.

    Overwrite flags resolve per-endpoint when exactly one Proxmox endpoint is in
    scope. Full syncs split multiple Proxmox endpoints into separate one-
    endpoint SSE requests before calling this helper, because the backend
    accepts one flat overwrite flag group per request. Direct helper calls
    without a concrete endpoint fall back to the global
    ``ProxboxPluginSettings`` singleton.

    ``proxmox_endpoint_ids`` are **plugin** ``ProxmoxEndpoint`` primary keys and
    are used only to resolve plugin-side per-endpoint overwrite flags and sync
    modes. ``wire_proxmox_endpoint_ids`` are the **backend** database ids the
    proxbox-api ``proxmox_sessions`` dependency filters on; they are what gets
    sent on the wire. When the backend ids are not supplied the plugin pks are
    used as-is (legacy single-id-space callers/tests).
    """
    base_query: dict[str, str] = {}
    base_query["use_guest_agent_interface_name"] = (
        "true" if _use_guest_agent_interface_name_setting() else "false"
    )
    base_query["fetch_max_concurrency"] = str(_proxbox_fetch_max_concurrency_setting())
    base_query["ignore_ipv6_link_local_addresses"] = (
        "true" if _ignore_ipv6_link_local_addresses_setting() else "false"
    )
    base_query["primary_ip_preference"] = _primary_ip_preference_setting()
    base_query["parse_description_metadata"] = (
        "true" if _parse_description_metadata_setting() else "false"
    )

    single_endpoint_id = (
        proxmox_endpoint_ids[0]
        if proxmox_endpoint_ids and len(proxmox_endpoint_ids) == 1
        else None
    )
    overwrites = effective_overwrites_for_endpoint(single_endpoint_id)
    for name, value in overwrites.items():
        base_query[name] = "true" if value else "false"

    sync_modes = effective_sync_modes_for_endpoint(single_endpoint_id)
    _set_sync_mode_vars(sync_modes)
    for name, value in _active_sync_modes().items():
        base_query[name] = value

    wire_ids = (
        wire_proxmox_endpoint_ids
        if wire_proxmox_endpoint_ids is not None
        else proxmox_endpoint_ids
    )
    if wire_ids:
        base_query["proxmox_endpoint_ids"] = ",".join(wire_ids)
    if netbox_endpoint_ids:
        base_query["netbox_endpoint_ids"] = ",".join(netbox_endpoint_ids)
    return base_query


def _build_stage_query_params(
    base_query: dict[str, str],
    sync_type: str,
    target_vm_ids: list[str],
    disable_vm_network_on_vm_stage: bool = False,
    iface_disabled: bool = False,
    ip_disabled: bool = False,
    mac_disabled: bool = False,
    run_id: str | None = None,
) -> dict[str, str]:
    """Build query parameters for a specific sync stage."""
    query_params = dict(base_query)
    if sync_type == SyncTypeChoices.VIRTUAL_MACHINES_BACKUPS:
        query_params["delete_nonexistent_backup"] = "true"
    if sync_type == SyncTypeChoices.VIRTUAL_MACHINES_SNAPSHOTS:
        query_params["delete_nonexistent_snapshot"] = "true"
    if sync_type == SyncTypeChoices.VIRTUAL_MACHINES:
        if disable_vm_network_on_vm_stage:
            # Dedicated stages or disabled interfaces own network sync behavior.
            query_params["sync_vm_network"] = "false"
        else:
            if ip_disabled:
                query_params["assign_vm_interface_ips"] = "false"
            if mac_disabled:
                query_params["sync_vm_interface_macs"] = "false"
    if sync_type == SyncTypeChoices.VM_INTERFACES and mac_disabled:
        query_params["sync_vm_interface_macs"] = "false"
    if sync_type == SyncTypeChoices.VIRTUAL_MACHINES and run_id:
        query_params["run_id"] = run_id
    if target_vm_ids:
        query_params["netbox_vm_ids"] = ",".join(target_vm_ids)
    return query_params


def _execute_stage_sync(
    job: "ProxboxSyncJob",
    sync_type: str,
    stream_path: str,
    query_params: dict[str, str] | None,
    on_frame: Callable[[str, dict[str, object]], None],
    endpoint_id: int | None = None,
) -> tuple[dict[str, object], float]:
    """Execute a single stage sync and return payload."""
    from netbox_proxbox.services import run_sync_stream

    job.logger.info(f"Starting stage: {sync_type} ({stream_path})")
    stage_started = time.monotonic()
    last_heartbeat = stage_started

    def _heartbeat() -> None:
        nonlocal last_heartbeat
        now = time.monotonic()
        if now - last_heartbeat < _HEARTBEAT_SECONDS:
            return
        elapsed = _format_seconds(now - stage_started)
        job.logger.info(
            f"Stage '{sync_type}' still running on '{stream_path}' (elapsed {elapsed})"
        )
        last_heartbeat = now

    def _on_frame_with_heartbeat(
        event: str,
        data: dict[str, object],
        forward: Callable[[str, dict[str, object]], None],
    ) -> None:
        forward(event, data)
        _heartbeat()

    last_payload: dict[str, object] = {}
    last_status: int = 0
    for _attempt in range(_STAGE_RETRY_MAX + 1):
        job.logger.info(f"Checking backend readiness for stage '{sync_type}'...")
        last_payload, last_status = run_sync_stream(
            stream_path,
            query_params=query_params,
            on_frame=lambda e, d: _on_frame_with_heartbeat(e, d, on_frame),
            endpoint_id=endpoint_id,
        )
        elapsed = _format_seconds(time.monotonic() - stage_started)
        job.job.save(update_fields=["log_entries"])

        if last_status < 400:
            stage_runtime = round(time.monotonic() - stage_started, 3)
            job.logger.info(
                f"Stage completed: {sync_type} ({stream_path}) HTTP {last_status} in {elapsed}"
            )
            return last_payload, stage_runtime

        if (last_status >= 500 or last_status == 429) and _attempt < _STAGE_RETRY_MAX:
            retry_detail = _extract_backend_error_text(last_payload) or str(
                last_payload
            )
            job.logger.warning(
                f"Stage {sync_type} failed (HTTP {last_status}): {retry_detail} "
                f"-- retrying in {_STAGE_RETRY_DELAY:.0f}s "
                f"(attempt {_attempt + 1}/{_STAGE_RETRY_MAX})"
            )
            job.job.save(update_fields=["log_entries"])
            time.sleep(_STAGE_RETRY_DELAY)
            continue

        # 4xx (not retryable) or all retries exhausted
        break

    detail = _extract_backend_error_text(last_payload) or str(last_payload)
    user_detail = _format_stage_sync_error(
        sync_type=sync_type,
        status=last_status,
        payload=last_payload,
    )
    if last_status in (503, 404) and "init_ok" in detail:
        job.logger.error(
            f"Backend not ready for stage '{sync_type}': {detail}. "
            "Check proxbox-api bootstrap logs and verify NetBox connectivity."
        )
    else:
        job.logger.error(f"Stage {sync_type} failed (HTTP {last_status}): {detail}")
    raise RuntimeError(user_detail)


def _proxmox_endpoint_scopes(
    proxmox_endpoint_ids: object,
) -> list[list[str]]:
    """Return one flat-query endpoint scope per backend SSE run."""
    requested: list[str] = []
    for value in list(proxmox_endpoint_ids or []):
        endpoint_id = str(value).strip()
        if not endpoint_id:
            continue
        try:
            int(endpoint_id)
        except (TypeError, ValueError):
            continue
        requested.append(endpoint_id)
    if requested:
        try:
            from netbox_proxbox.models import ProxmoxEndpoint

            enabled_ids = {
                str(pk)
                for pk in ProxmoxEndpoint.objects.filter(
                    pk__in=[int(endpoint_id) for endpoint_id in requested],
                    enabled=True,
                ).values_list("pk", flat=True)
            }
        except (ImportError, RuntimeError, AttributeError, ValueError):
            enabled_ids = set(requested)
        return [
            [endpoint_id] for endpoint_id in requested if endpoint_id in enabled_ids
        ]

    try:
        from netbox_proxbox.models import ProxmoxEndpoint

        endpoint_ids = [
            str(pk)
            for pk in ProxmoxEndpoint.objects.filter(enabled=True).values_list(
                "pk", flat=True
            )
        ]
    except (ImportError, RuntimeError, AttributeError):
        endpoint_ids = []
    if not endpoint_ids:
        return [[]]
    return [[endpoint_id] for endpoint_id in endpoint_ids]


def _resolve_wire_endpoint_ids(
    endpoint_scopes: list[list[str]],
) -> tuple[dict[str, str], str | None]:
    """Map plugin ``ProxmoxEndpoint`` pks (used in scopes) to backend database ids.

    The backend's ``proxmox_sessions`` dependency filters on its *own* endpoint
    ids, which differ from NetBox plugin primary keys. Returns
    ``({plugin_pk_str: backend_id_str}, error)``; ``error`` is set only when the
    backend endpoint list could not be fetched. Plugin pks with no backend match
    are omitted so the caller can fail loud per endpoint rather than syncing an
    unscoped (all-endpoint) request.
    """
    plugin_pks = {
        scope[0] for scope in endpoint_scopes if scope and str(scope[0]).strip()
    }
    if not plugin_pks:
        return {}, None

    from netbox_proxbox.models import ProxmoxEndpoint
    from netbox_proxbox.services.backend_proxy import get_fastapi_request_context
    from netbox_proxbox.views.backend_sync import resolve_backend_endpoint_ids

    ctx = get_fastapi_request_context()
    if ctx is None or not ctx.http_url:
        return (
            {},
            "FastAPI endpoint not configured; cannot resolve backend endpoint ids",
        )

    endpoints = list(
        ProxmoxEndpoint.objects.filter(
            pk__in=[int(pk) for pk in plugin_pks], enabled=True
        )
    )
    if not endpoints:
        return {}, None
    mapping, error = resolve_backend_endpoint_ids(
        endpoints,
        base_url=ctx.http_url,
        auth_headers=ctx.headers or {},
        backend_verify_ssl=bool(ctx.verify_ssl),
    )
    if error:
        return {}, error
    return {str(pk): str(backend_id) for pk, backend_id in mapping.items()}, None


def _run_all_stages_sync(
    job: "ProxboxSyncJob",
    stages: list[str],
    params: dict[str, object],
    run_started: float,
) -> list[dict[str, object]]:
    """Run all sync stages in order and return stage results."""
    endpoint_scopes = _proxmox_endpoint_scopes(params.get("proxmox_endpoint_ids"))
    backend_id_by_pk, wire_resolve_error = _resolve_wire_endpoint_ids(endpoint_scopes)

    flush_interval = 2.0
    log_throttle = 1.5
    last_flush = time.monotonic()
    last_progress_log = time.monotonic()

    def on_frame(event: str, data: dict[str, object]) -> None:
        nonlocal last_flush, last_progress_log
        if event == "complete":
            return
        now = time.monotonic()
        line = json.dumps(data, default=str)
        if len(line) > 600:
            line = line[:600] + "…"
        if event == "error" or now - last_progress_log >= log_throttle:
            job.logger.info("[proxbox-stream] {}: {}".format(event, line))
            last_progress_log = now
        if now - last_flush >= flush_interval:
            job.job.save(update_fields=["log_entries"])
            last_flush = now

    stages_out: list[dict[str, object]] = []

    target_vm_ids = [str(x) for x in list(params.get("netbox_vm_ids") or []) if str(x)]
    fastapi_endpoint_id = params.get("fastapi_endpoint_id")
    netbox_branch_schema_id = params.get("netbox_branch_schema_id")
    sync_run_id = str(params.get("run_id") or "").strip() or None
    for endpoint_scope in endpoint_scopes:
        endpoint_id = endpoint_scope[0] if endpoint_scope else None
        wire_scope: list[str] | None = None
        if endpoint_scope:
            # Translate the plugin endpoint pk to the backend's own database id so
            # the SSE stages sync ONLY this endpoint. Failing to resolve must skip
            # this endpoint, never fall back to an unscoped (all-endpoint) request.
            backend_id = backend_id_by_pk.get(str(endpoint_id))
            if backend_id is None:
                reason = (
                    wire_resolve_error
                    or f"Proxmox endpoint {endpoint_id} is not registered on the "
                    "ProxBox backend; skipping to avoid syncing the wrong endpoint"
                )
                job.logger.error(
                    "Skipping SSE sync for Proxmox endpoint %s: %s",
                    endpoint_id,
                    reason,
                )
                stages_out.append(
                    {
                        "sync_type": "endpoint-scope",
                        "endpoint_id": endpoint_id,
                        "stream_path": None,
                        "runtime_seconds": 0.0,
                        "result_summary": {"ok": False, "error": reason},
                    }
                )
                continue
            wire_scope = [backend_id]
            job.logger.info(
                "Running SSE sync for Proxmox endpoint %s (backend id %s)",
                endpoint_id,
                backend_id,
            )
        else:
            job.logger.info("Running SSE sync with no Proxmox endpoint filter")
        base_query = _build_base_query_params(
            endpoint_scope,
            params.get("netbox_endpoint_ids"),
            wire_proxmox_endpoint_ids=wire_scope,
        )
        if netbox_branch_schema_id:
            base_query["netbox_branch_schema_id"] = str(netbox_branch_schema_id)

        iface_disabled = (
            _sync_mode_for_resource("vm_interface") == SyncModeChoices.DISABLED
        )
        ip_disabled = _sync_mode_for_resource("ip_address") == SyncModeChoices.DISABLED
        mac_disabled = _sync_mode_for_resource("mac") == SyncModeChoices.DISABLED
        dedicated_network_stage_present = (
            SyncTypeChoices.VM_INTERFACES in stages
            or SyncTypeChoices.IP_ADDRESSES in stages
        )
        disable_vm_network_on_vm_stage = (
            SyncTypeChoices.VIRTUAL_MACHINES in stages
            and (dedicated_network_stage_present or iface_disabled)
        )

        for st in stages:
            skip_reason = _stage_skip_reason(st)
            if skip_reason:
                job.logger.info(
                    "Skipping stage %s for endpoint %s: %s",
                    st,
                    endpoint_id or "unscoped",
                    skip_reason,
                )
                stages_out.append(
                    {
                        "sync_type": st,
                        "endpoint_id": endpoint_id,
                        "stream_path": None,
                        "runtime_seconds": 0.0,
                        "result_summary": {
                            "ok": True,
                            "skipped": True,
                            "reason": skip_reason,
                        },
                    }
                )
                continue
            query_params = _build_stage_query_params(
                base_query,
                st,
                target_vm_ids,
                disable_vm_network_on_vm_stage=disable_vm_network_on_vm_stage,
                iface_disabled=iface_disabled,
                ip_disabled=ip_disabled,
                mac_disabled=mac_disabled,
                run_id=sync_run_id,
            )
            stage_paths = _sync_stream_paths_for_stage(st, target_vm_ids)

            for stream_path in stage_paths:
                try:
                    payload, stage_runtime = _execute_stage_sync(
                        job,
                        st,
                        stream_path,
                        query_params,
                        on_frame,
                        fastapi_endpoint_id,
                    )
                except RuntimeError as exc:
                    if st in _SKIPPABLE_STAGES:
                        job.logger.warning(
                            "Optional stage '%s' failed and was skipped: %s", st, exc
                        )
                        job.job.save(update_fields=["log_entries"])
                        continue
                    raise
                response = payload.get("response") or {}
                stages_out.append(
                    {
                        "sync_type": st,
                        "endpoint_id": endpoint_id,
                        "stream_path": stream_path,
                        "runtime_seconds": stage_runtime,
                        "result_summary": {
                            "path": payload.get("path"),
                            "ok": response.get("ok"),
                        },
                    }
                )

    return stages_out
