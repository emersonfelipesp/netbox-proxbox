"""Stage execution: batch sync, base/stage query params, and multi-stage orchestration."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable, Iterator
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
        "sync_mode_sdn",
        "sync_mode_sdn_bgp",
    )
try:
    from netbox_proxbox.constants import SYNC_MODE_HIERARCHY
except ImportError:  # pragma: no cover - compatibility for focused import stubs
    SYNC_MODE_HIERARCHY = {
        "node": "cluster",
        "vm_interface": "vm",
        "ip_address": "vm_interface",
        "mac": "vm_interface",
        "sdn_bgp": "sdn",
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
    _vm_interface_sync_strategy_setting,
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
_SDN_SYNC_TYPE = getattr(SyncTypeChoices, "SDN", "sdn")

# Phrases that mark a backend error as a transport/availability failure rather
# than a genuine client-side rejection.  proxbox-api raises ``ProxboxException``
# with a class-default HTTP 400 for *every* uncaught error, timeouts and refused
# connections included, so a cold or restarting backend can report a retryable
# condition under a status code that means "your request was wrong".  Matching on
# the reported cause lets those be retried without retrying real 4xx rejections.
# Every marker is specific enough that it cannot plausibly appear in a
# validation message: a bare ``"timeout"`` also matched the genuine rejection
# ``"timeout must be between 1 and 300"``, so the word alone is not usable.
# The list is checked against the strings the transport layer actually emits
# (requests/urllib3, httpx, the ssl module, glibc/BSD resolvers, and nginx) —
# see ``test_real_transport_failure_texts_are_matched``.  A phrase is only added
# when it cannot also complete a sentence about a *field* of that name, which is
# why ``"request timeout"`` is deliberately absent.
_TRANSPORT_FAILURE_MARKERS: tuple[str, ...] = (
    "timed out",
    "timeout error",
    "timeouterror",
    "read timeout",
    "readtimeout",
    "connecttimeout",
    "connectiontimeout",
    "pooltimeout",
    "writetimeout",
    "gateway timeout",
    # nginx spells its own 504 body "Gateway Time-out", with the hyphen. A real
    # 504 is already retryable by status; this matters when proxbox-api catches
    # an upstream 504 and re-reports the body under its default 400.
    "gateway time-out",
    "connection refused",
    "connection reset",
    "connection aborted",
    "connection error",
    "cannot connect",
    "bad gateway",
    "server disconnected",
    "temporarily unavailable",
    "service unavailable",
    "network is unreachable",
    # DNS. The first is glibc's EAI_AGAIN and is the common one when a container
    # starts before its resolver is ready — precisely the cold-start case here.
    "name or service not known",
    "temporary failure in name resolution",
    "nodename nor servname provided",
    # urllib3 wraps the resolver error in its own NameResolutionError text, which
    # survives even when the inner errno string is truncated away.
    "failed to resolve",
    # urllib3's outermost wrapper for a retry-exhausted connection attempt. It
    # prefixes most transport failures, so it catches the ones whose inner cause
    # was trimmed before proxbox-api re-reported it.
    "max retries exceeded",
    # TLS handshake aborted mid-way, e.g. the backend restarting behind HTTPS.
    "eof occurred in violation of protocol",
    "remote end closed connection",
)
# Payload keys that describe *why* a request failed.  Only these are searched for
# the markers above: scanning the whole payload would let unrelated content — a
# ``"timeout": 30`` config value, a VM named "connection-reset" — turn a genuine
# client rejection into a retry.  ``python_exception`` is included because
# proxbox-api reports the underlying exception there and
# ``_extract_backend_error_text()`` does not read it.
_ERROR_CAUSE_KEYS: tuple[str, ...] = (
    "python_exception",
    "exception",
    "detail",
    "message",
    "error",
)
# The same keys, plus FastAPI's per-error ``msg``, used when descending into a
# *nested* error body.  A FastAPI validation/dependency failure reports
# ``detail`` as a list of ``{"loc": [...], "msg": ..., "input": {...}}`` objects,
# so the cause can be one level down.  ``input`` is deliberately absent: it
# echoes the submitted request body, which for endpoint pushes contains
# credentials.
_NESTED_CAUSE_KEYS: tuple[str, ...] = _ERROR_CAUSE_KEYS + ("msg",)
_CAUSE_RECURSION_LIMIT = 4
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
sync_mode_sdn = SyncModeChoices.DISABLED
sync_mode_sdn_bgp = SyncModeChoices.DISABLED


def _default_sync_mode(field_name: str) -> str:
    if field_name in {"sync_mode_sdn", "sync_mode_sdn_bgp"}:
        return getattr(SyncModeChoices, "DISABLED", "disabled")
    return getattr(SyncModeChoices, "ALWAYS", "always")


# Stages that are supplementary/optional: a failure logs a warning and the sync
# continues.  Required stages (devices, VMs, storage, interfaces, IPs) are NOT
# in this set and still abort the run on failure.
_SKIPPABLE_STAGES: frozenset[str] = frozenset(
    {
        SyncTypeChoices.VIRTUAL_MACHINES_BACKUPS,  # "vm-backups"
        SyncTypeChoices.VIRTUAL_MACHINES_SNAPSHOTS,  # "vm-snapshots"
        SyncTypeChoices.TASK_HISTORY,  # "task-history"
        _SDN_SYNC_TYPE,  # read-only SDN inventory; old clusters may not support it
    }
)


def _set_sync_mode_vars(modes: dict[str, str]) -> None:
    """Update module-level sync-mode vars for the active endpoint scope."""
    for field_name in SYNC_MODE_FIELDS:
        globals()[field_name] = str(
            modes.get(field_name) or _default_sync_mode(field_name)
        )


def _active_sync_modes() -> dict[str, str]:
    """Return the current module-level sync modes after parent-child cascade."""
    raw_modes = {
        field_name: str(globals().get(field_name) or _default_sync_mode(field_name))
        for field_name in SYNC_MODE_FIELDS
    }
    return _effective_sync_modes(raw_modes)


def _resource_mode(raw_modes: dict[str, str], resource_type: str) -> str:
    """Return a normalized raw mode value for a resource type."""
    field_name = f"sync_mode_{resource_type}"
    return str(raw_modes.get(field_name) or _default_sync_mode(field_name))


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
        _SDN_SYNC_TYPE: "sdn",
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
    fastapi_endpoint_id: int | None = None,
    proxmox_wire_endpoint_ids: str | None = None,
    proxmox_wire_endpoint_by_pk: dict[str, str] | None = None,
) -> dict[str, object]:
    """Run selected object syncs concurrently with asyncio.gather.

    ``fastapi_endpoint_id`` pins every per-object call to the backend the job
    selected and preflighted. Without it each call resolves the *first* enabled
    backend independently, so on a multi-backend install a batch run could
    validate one backend and then sync against another.

    ``proxmox_wire_endpoint_ids`` pins the *Proxmox* side the same way: a
    comma-separated list of backend endpoint ids, already resolved by the
    caller. The individual-sync routes resolve their Proxmox sessions through
    the same dependency the streaming stages use, and that dependency treats an
    absent filter as "every endpoint I hold" — so omitting the scope widens the
    run to endpoints the operator disabled in NetBox rather than narrowing it.

    ``proxmox_wire_endpoint_by_pk`` narrows it the rest of the way, per object.
    The job-wide scope stops the backend reaching endpoints this NetBox
    disabled, but it still asks *all* the enabled ones — and a selected-object
    request names only a cluster/node/VMID, which are unique per endpoint and
    not across the estate. Two Proxmox installations each holding a
    ``cluster01/pve1/100`` would both answer, and whichever the backend picked
    would be written into this object's NetBox row. So each object is pinned to
    the single backend id its own ``ProxmoxCluster → ProxmoxEndpoint`` chain
    names. An object whose owner is known but is *not* in the map — its endpoint
    drifted and was skipped from the scope — is failed explicitly rather than
    being asked of the remaining endpoints, which is precisely the case that
    would otherwise sync from the wrong estate. So is an object whose cluster is
    claimed by *two* endpoints: that is proof the duplicated namespace exists
    here, so widening would ask both and keep whichever answered. An owner that
    cannot be determined **at all** — nothing has reflected this cluster yet —
    falls back to the job-wide scope only while that scope names a *single*
    endpoint, where falling back and pinning are the same request; a run
    spanning two or more refuses the object instead. That keeps first-ever
    syncs working on the installs the fallback was written for — one endpoint,
    nothing reflected yet — without letting "unknown" widen in the very estate
    where a duplicated identifier is possible.
    """
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

    # Resolve every object's owning endpoint in one query, here rather than
    # inside `run_one()`: the batch can carry hundreds of objects and this is
    # the same place the object fetch already happens.
    #
    # The map is object id → *set* of claiming endpoint pks, deliberately kept
    # tri-state (see `_owner_endpoint_pks_by_cluster_id()`): one claimant pins,
    # two or more refuses the object, and none widens to the job-wide scope —
    # but only while that scope names a single endpoint.
    owner_pks_by_object_id: dict[str, set[str]] = {}
    if proxmox_wire_endpoint_by_pk:
        cluster_id_by_object_id = {
            object_id: _batch_object_core_cluster_id(obj, batch_object_type)
            for object_id, obj in object_by_id.items()
        }
        owner_by_cluster = _owner_endpoint_pks_by_cluster_id(
            [cid for cid in cluster_id_by_object_id.values() if cid]
        )
        owner_pks_by_object_id = {
            object_id: owner_by_cluster[cluster_id]
            for object_id, cluster_id in cluster_id_by_object_id.items()
            if cluster_id and cluster_id in owner_by_cluster
        }

    # The unknown-owner fallback in `run_one()` widens an object back to the
    # whole run's scope. That is only safe while the run names **one** endpoint,
    # where "the job-wide scope" and "one specific endpoint" are the same
    # request. Count the ids once here rather than re-splitting per object.
    job_scope_wire_ids = [
        wire_id.strip()
        for wire_id in (proxmox_wire_endpoint_ids or "").split(",")
        if wire_id.strip()
    ]

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

            # Pin to this object's own endpoint when we can name it. Two of the
            # three outcomes refuse rather than widen, because a cluster/node/
            # VMID is unique only *per endpoint*: asking a set of endpoints for
            # an identifier another estate also uses is how the wrong estate's
            # data ends up written into this row.
            owner_pks = owner_pks_by_object_id.get(str(object_id)) or set()
            object_wire_scope = proxmox_wire_endpoint_ids
            if len(owner_pks) > 1:
                # Ambiguous: two endpoints have both reflected this cluster, so
                # the estate provably *has* the duplicated namespace. Falling
                # back to the job-wide scope here would ask both of them and
                # write whichever answered first — the exact defect per-object
                # pinning exists to close. Unknown ownership may widen;
                # ambiguous ownership may not.
                claimants = ", ".join(sorted(owner_pks))
                return {
                    "batch_object_type": batch_object_type,
                    "object_id": str(object_id),
                    "status": 424,
                    "error": (
                        "This object's Proxmox cluster is claimed by more than "
                        f"one Proxmox endpoint (ids {claimants}), so the "
                        "endpoint that owns it cannot be determined and it was "
                        "not synced. Syncing it against every claimant could "
                        "match another cluster/node/VMID with the same name. "
                        "Remove the duplicate reflected cluster, then retry."
                    ),
                }
            if len(owner_pks) == 1:
                owner_pk = next(iter(owner_pks))
                pinned = (proxmox_wire_endpoint_by_pk or {}).get(owner_pk)
                if not pinned:
                    # Resolved, but its endpoint drifted and was dropped from
                    # the scope. Same refusal, same reason.
                    return {
                        "batch_object_type": batch_object_type,
                        "object_id": str(object_id),
                        "status": 424,
                        "error": (
                            "The Proxmox endpoint this object belongs to "
                            f"(id {owner_pk}) is not in this run's endpoint "
                            "scope, so it was not synced. Syncing it against "
                            "the remaining endpoints could match another "
                            "cluster/node/VMID with the same name."
                        ),
                    }
                object_wire_scope = pinned
            elif not owner_pks and len(job_scope_wire_ids) > 1:
                # Unknown owner: nothing has reflected this object's cluster
                # yet. Widening to the job-wide scope is what makes a
                # first-ever sync possible at all, and it costs nothing while
                # the run names a single endpoint — that request is already
                # pinned. With two or more in scope it is a guess, and the
                # identifiers being guessed with (cluster/node/VMID) are unique
                # only per endpoint, so the wrong estate can answer and its
                # data lands in this row with no error raised.
                #
                # Refusing the object is recoverable: a staged sync reflects
                # the clusters, ownership becomes resolvable, and the retry
                # pins. Widening is not — the wrong data is already written.
                return {
                    "batch_object_type": batch_object_type,
                    "object_id": str(object_id),
                    "status": 424,
                    "error": (
                        "The Proxmox endpoint this object belongs to could not "
                        "be determined — no reflected cluster names an owner — "
                        f"and this run spans {len(job_scope_wire_ids)} Proxmox "
                        "endpoints, so it was not synced. Syncing it against "
                        "all of them could match another cluster/node/VMID "
                        "with the same name. Run a staged sync first so the "
                        "cluster is reflected, or retry with a single endpoint "
                        "selected."
                    ),
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
            # WHY: the branch schema id has to travel as an argument, not only as
            # a query param on this first call. `_sync_dependency()` builds its
            # params dict from scratch out of `_CONTEXT_KEYS`, which does not
            # include `netbox_branch_schema_id` — so a dependency resolved off
            # this object would be written to the *main* schema while the object
            # itself went to the branch.
            branch_schema_id = (
                str(netbox_branch_schema_id) if netbox_branch_schema_id else None
            )
            if branch_schema_id:
                query_params["netbox_branch_schema_id"] = branch_schema_id
            # Same argument-not-just-query-param rule as the branch schema, and
            # for the same reason: an unscoped individual sync is a *wider*
            # request than a scoped one, so a scope that got dropped somewhere
            # in the dependency recursion silently re-widens to every endpoint
            # the backend holds instead of failing.
            if object_wire_scope:
                query_params["proxmox_endpoint_ids"] = object_wire_scope

            def _call_sync() -> tuple[dict, int, list[dict]]:
                return sync_individual_with_dependencies(
                    path,
                    query_params,
                    netbox_branch_schema_id=branch_schema_id,
                    fastapi_endpoint_id=fastapi_endpoint_id,
                    proxmox_endpoint_ids=object_wire_scope,
                )

            response, status, dependencies = await asyncio.to_thread(_call_sync)

            if batch_object_type == "virtual-machine" and 200 <= int(status) < 300:
                from netbox_proxbox.services.tenant_assignment import (
                    maybe_assign_tenant_from_cluster,
                    maybe_assign_tenant_from_regex,
                    maybe_assign_tenant_from_tags,
                )

                def _post_sync_assign() -> None:
                    obj.refresh_from_db()
                    maybe_assign_tenant_from_regex(obj)
                    maybe_assign_tenant_from_tags(obj)
                    maybe_assign_tenant_from_cluster(obj)

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
    base_query["vm_interface_sync_strategy"] = _vm_interface_sync_strategy_setting()
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


def _iter_cause_strings(value: object, depth: int = 0) -> Iterator[str]:
    """Yield the error-describing strings reachable from ``value``.

    FastAPI reports validation and dependency errors as a *list* under
    ``detail`` (``[{"loc": [...], "msg": "...", "input": {...}}]``), so a
    transport failure surfaced through that shape is invisible to a flat
    ``payload["detail"]`` read. Recursion is therefore necessary — but it stays
    keyed on ``_NESTED_CAUSE_KEYS`` so submitted ``input`` (which echoes the
    request body, credentials included) is never scanned.
    """
    if depth > _CAUSE_RECURSION_LIMIT:
        return
    if isinstance(value, str):
        yield value
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _iter_cause_strings(item, depth + 1)
    elif isinstance(value, dict):
        for key in _NESTED_CAUSE_KEYS:
            if key in value:
                yield from _iter_cause_strings(value[key], depth + 1)


def _names_transport_failure(payload: object) -> bool:
    """Return ``True`` when the payload's *cause* names a transport failure.

    Only the error-describing fields are searched (``_NESTED_CAUSE_KEYS``),
    never the payload as a whole, so ordinary data that happens to contain a
    marker word cannot make a real rejection look retryable. A non-dict body is
    matched whole because then the body *is* the error text.
    """
    if isinstance(payload, dict):
        parts = [_extract_backend_error_text(payload) or ""]
        for key in _ERROR_CAUSE_KEYS:
            if key in payload:
                parts.extend(_iter_cause_strings(payload[key]))
        haystack = " ".join(parts)
    else:
        haystack = str(payload)
    lowered = haystack.lower()
    return any(marker in lowered for marker in _TRANSPORT_FAILURE_MARKERS)


def _is_retryable_stage_failure(status: int, payload: object) -> bool:
    """Return ``True`` when a failed stage is worth retrying.

    5xx and 429 are retryable by definition. A 400 is retryable only when the
    reported cause names a transport failure — see ``_TRANSPORT_FAILURE_MARKERS``
    for why proxbox-api can report one under a 400.
    """
    if status >= 500 or status == 429:
        return True
    if status != 400:
        return False
    return _names_transport_failure(payload)


def _execute_stage_sync(
    job: "ProxboxSyncJob",
    sync_type: str,
    stream_path: str,
    query_params: dict[str, str] | None,
    on_frame: Callable[[str, dict[str, object]], None],
    endpoint_id: int | None = None,
    preflight_hint: str | None = None,
) -> tuple[dict[str, object], float]:
    """Execute a single stage sync and return payload.

    ``preflight_hint`` carries non-fatal warnings from the pre-sync preflight so
    a stage failure can name the earlier problem that likely caused it, instead
    of leaving the operator with only whatever error the backend surfaced.
    """
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

        if (
            _is_retryable_stage_failure(last_status, last_payload)
            and _attempt < _STAGE_RETRY_MAX
        ):
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
    if preflight_hint:
        # The backend often reports a generic downstream symptom (a failed tag,
        # a missing object) when the real cause was an earlier preflight problem.
        # Say so, so the operator fixes the cause instead of the symptom.
        job.logger.error(
            f"Stage '{sync_type}' likely failed because of an earlier "
            f"problem. {preflight_hint}"
        )
        user_detail = f"{user_detail} {preflight_hint}"
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
    # No enabled endpoint means *no scope*, never the empty scope. An empty scope
    # reaches the backend as a request with no ``proxmox_endpoint_ids`` at all,
    # which the backend reads as "sync every endpoint you hold" — so disabling the
    # last ProxmoxEndpoint would have widened the sync to whatever proxbox-api
    # still had registered, instead of stopping it. The caller turns an empty
    # scope list into a fail-loud endpoint-scope record.
    return [[endpoint_id] for endpoint_id in endpoint_ids]


def _resolve_wire_endpoint_ids(
    endpoint_scopes: list[list[str]],
    fastapi_endpoint_id: int | None = None,
) -> tuple[dict[str, str], str | None]:
    """Map plugin ``ProxmoxEndpoint`` pks (used in scopes) to backend database ids.

    The backend's ``proxmox_sessions`` dependency filters on its *own* endpoint
    ids, which differ from NetBox plugin primary keys. Returns
    ``({plugin_pk_str: backend_id_str}, error)``; ``error`` is set only when the
    backend endpoint list could not be fetched. Plugin pks with no backend match
    are omitted so the caller can fail loud per endpoint rather than syncing an
    unscoped (all-endpoint) request.

    ``fastapi_endpoint_id`` must be the *same* backend the stages will run
    against: the ids returned here are that backend's own primary keys and are
    meaningless — or worse, wrong but valid — against a different one.
    """
    plugin_pks = {
        scope[0] for scope in endpoint_scopes if scope and str(scope[0]).strip()
    }
    if not plugin_pks:
        return {}, None

    from netbox_proxbox.models import ProxmoxEndpoint
    from netbox_proxbox.services.backend_proxy import get_fastapi_request_context
    from netbox_proxbox.views.backend_sync import resolve_backend_endpoint_ids

    ctx = get_fastapi_request_context(endpoint_id=fastapi_endpoint_id)
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


def _no_endpoint_scope_reason(requested_endpoint_ids: object) -> str:
    """Explain why a run resolved *no* Proxmox endpoint scope at all.

    Shared by the staged and the selected-object paths so both refuse in the
    same words. The two cases read very differently to an operator — a stale
    selection on this one run, versus an estate with nothing enabled — and the
    second has to say out loud that dropping the filter is not the safe
    degradation, because "just sync everything then" is exactly the fix the
    message would otherwise invite.
    """
    if requested_endpoint_ids:
        return (
            "every Proxmox endpoint selected for this run is disabled or no "
            "longer exists, so there was nothing to sync"
        )
    return (
        "no enabled Proxmox endpoint exists in NetBox, so there was "
        "nothing to sync. Syncing without an endpoint filter is not a "
        "fallback: the backend would sync every endpoint it still holds, "
        "including ones disabled here"
    )


def _batch_wire_endpoint_scope(
    requested_endpoint_ids: object,
    fastapi_endpoint_id: int | None = None,
) -> tuple[str, list[str], str | None, dict[str, str]]:
    """Resolve the backend Proxmox endpoint scope for a selected-object run.

    Returns ``(comma_separated_backend_ids, skipped_plugin_pks, error,
    wire_id_by_plugin_pk)``.

    The trailing map is what lets the caller narrow *per object* instead of
    sending the whole job-wide scope with every request. The job-wide scope is
    still the right answer when an object's own endpoint cannot be determined,
    so both are returned rather than one replacing the other.

    The selected-object path reaches proxbox-api through ``sync_individual()``
    rather than the SSE stage loop, but both land on the same
    ``ProxmoxSessionsDep`` — and that dependency reads a *missing*
    ``proxmox_endpoint_ids`` as "use every endpoint I hold". So the batch path
    needs exactly the resolution and the fail-loud behaviour the staged path
    already has; without it, a selected-object sync against a NetBox whose
    endpoints are all disabled still reaches whatever the backend kept.

    A *partially* resolvable scope is not an error: the resolved endpoints are
    returned and the rest are reported as ``skipped_plugin_pks`` for the caller
    to log. Failing the whole run because one unrelated endpoint drifted would
    be a regression, while the narrowed scope is still strictly safer than the
    unscoped request this replaces.

    What the narrowed scope does **not** do on its own is guarantee that an
    object living on a skipped endpoint fails loudly. It only does so when no
    other in-scope endpoint can answer for it — and Proxmox identifiers are not
    globally unique, so a cluster name, node name or VMID duplicated across two
    estates would be answered by the wrong one. Per-object pinning through
    ``_owner_endpoint_pks_by_cluster_id()`` is what closes that gap; this map is
    the input it needs.
    """
    endpoint_scopes = _proxmox_endpoint_scopes(requested_endpoint_ids)
    if not endpoint_scopes:
        return "", [], _no_endpoint_scope_reason(requested_endpoint_ids), {}

    wire_ids, error = _resolve_wire_endpoint_ids(
        endpoint_scopes, fastapi_endpoint_id=fastapi_endpoint_id
    )
    if error:
        return (
            "",
            [],
            (
                "the enabled Proxmox endpoints could not be resolved to ProxBox "
                f"backend ids, so this sync would not have been scoped to them: {error}"
            ),
            {},
        )

    plugin_pks = [scope[0] for scope in endpoint_scopes if scope]
    resolved = {str(pk): str(wire_ids[pk]) for pk in plugin_pks if pk in wire_ids}
    scope_ids = [wire_ids[pk] for pk in plugin_pks if pk in wire_ids]
    skipped = [pk for pk in plugin_pks if pk not in wire_ids]
    if not scope_ids:
        return (
            "",
            skipped,
            (
                "none of the enabled Proxmox endpoints is registered with this "
                "ProxBox backend under a matching connection target, so this "
                "sync would not have been scoped to them"
            ),
            {},
        )
    return ",".join(scope_ids), skipped, None, resolved


def _batch_object_core_cluster_id(obj: object, batch_object_type: str) -> int | None:
    """Return the core ``virtualization.Cluster`` id a selected object belongs to.

    All five batch object types converge on a core cluster, though by different
    routes: a VM and a ``ProxmoxStorage`` carry it directly (``ProxmoxStorage``
    FKs to ``virtualization.Cluster``, not to ``ProxmoxCluster``), while backups,
    snapshots and task-history rows reach it through the object they describe.
    The backup case prefers its storage because that is the cluster its own sync
    parameters are built from — using the VM's would resolve an owner the
    request itself does not name.
    """

    def _cluster_id_of(candidate: object) -> int | None:
        value = getattr(candidate, "cluster_id", None)
        try:
            return int(value) if value else None
        except (TypeError, ValueError):
            return None

    if batch_object_type in {"virtual-machine", "proxmox-storage"}:
        return _cluster_id_of(obj)
    if batch_object_type == "vm-backup":
        return _cluster_id_of(getattr(obj, "proxmox_storage", None)) or _cluster_id_of(
            getattr(obj, "virtual_machine", None)
        )
    if batch_object_type in {"vm-snapshot", "vm-task-history"}:
        return _cluster_id_of(getattr(obj, "virtual_machine", None)) or _cluster_id_of(
            getattr(obj, "proxmox_storage", None)
        )
    return None


def _batch_object_owner_endpoint_pks(obj: object, batch_object_type: str) -> set[str]:
    """Return every plugin ``ProxmoxEndpoint`` pk that claims ``obj``'s cluster.

    Proxmox identifiers are scoped to an endpoint, not to the estate: two
    unrelated Proxmox installations can each have a ``cluster01`` with a node
    ``pve1`` running VMID ``100``. A selected-object request carries only those
    names, so sending it with the job-wide endpoint scope asks *every* in-scope
    endpoint and takes whichever answers — which on a duplicate is silently the
    wrong estate's data, written into this object's NetBox row.

    ``ProxmoxCluster`` is the join that settles it: it FKs to both the core
    cluster the object hangs off and the ``ProxmoxEndpoint`` it was reflected
    from. This mirrors ``views/vm_sync_now.py::_endpoint_ids_for_vm()``.

    The result is a **set**, not a single pk, because the caller has to keep
    three outcomes apart: exactly one claimant is the owner and the object pins
    there; an empty set is *unknown* (no cluster, or nothing reflected yet) and
    may widen to the job-wide scope so a first-ever sync can still discover its
    endpoint; two or more claimants is *ambiguous* and must fail the object,
    because a duplicated namespace is precisely where widening would let the
    wrong estate answer. Do not collapse ambiguous into unknown here — that
    reintroduces the cross-estate write this resolution exists to prevent.

    ``_run_batch_selected_sync()`` does not call this per object; it runs
    ``_owner_endpoint_pks_by_cluster_id()`` once for the whole batch and
    classifies the same three ways. This is the single-object equivalent.
    """
    cluster_id = _batch_object_core_cluster_id(obj, batch_object_type)
    if not cluster_id:
        return set()
    return _owner_endpoint_pks_by_cluster_id([cluster_id]).get(cluster_id, set())


def _owner_endpoint_pks_by_cluster_id(cluster_ids: list[int]) -> dict[int, set[str]]:
    """Map core cluster id → the set of ``ProxmoxEndpoint`` pks claiming it.

    One query for the whole batch: a selected-object run can carry hundreds of
    objects, and resolving each one's owner separately would put a query per
    object in front of a sync that is already doing one HTTP call per object.

    The **whole claim set** is returned, not just the unambiguous singletons,
    because the caller needs to tell three states apart and collapsing them here
    would destroy the distinction. A cluster absent from the map is *unknown* —
    nothing has reflected it yet — and may safely widen to the job-wide scope. A
    cluster mapping to two or more pks is *ambiguous*: we know the estate has a
    duplicated namespace, which is the one case where widening is actively
    dangerous. See ``_batch_object_owner_endpoint_pks()``.
    """
    if not cluster_ids:
        return {}

    from netbox_proxbox.models import ProxmoxCluster

    seen: dict[int, set[str]] = {}
    rows = (
        ProxmoxCluster.objects.filter(netbox_cluster_id__in=set(cluster_ids))
        .exclude(endpoint__isnull=True)
        .values_list("netbox_cluster_id", "endpoint_id")
        .distinct()
    )
    for cluster_id, endpoint_pk in rows:
        seen.setdefault(int(cluster_id), set()).add(str(endpoint_pk))
    return seen


def _run_all_stages_sync(
    job: "ProxboxSyncJob",
    stages: list[str],
    params: dict[str, object],
    run_started: float,
    preflight_hint: str | None = None,
) -> list[dict[str, object]]:
    """Run all sync stages in order and return stage results.

    ``preflight_hint`` is forwarded to every stage so a failure can point back at
    a non-fatal preflight problem that plausibly caused it.
    """
    endpoint_scopes = _proxmox_endpoint_scopes(params.get("proxmox_endpoint_ids"))
    if not endpoint_scopes:
        # Nothing enabled to sync. Returning here — rather than falling through to
        # a stage loop that never iterates — is what makes the run *fail loud*:
        # an empty ``stages_out`` finishes green, having synced nothing, which is
        # the silent no-op this preflight work exists to eliminate. The caller
        # turns this record into a "No sync stage ran" error.
        reason = _no_endpoint_scope_reason(params.get("proxmox_endpoint_ids"))
        job.logger.error(f"Skipping SSE sync entirely: {reason}")
        return [
            {
                "sync_type": "endpoint-scope",
                "endpoint_id": None,
                "stream_path": None,
                "runtime_seconds": 0.0,
                "result_summary": {"ok": False, "error": reason},
            }
        ]

    # Read before resolving: the backend-local ids below are only valid against
    # the backend the stages will actually run on.
    fastapi_endpoint_id = params.get("fastapi_endpoint_id")
    backend_id_by_pk, wire_resolve_error = _resolve_wire_endpoint_ids(
        endpoint_scopes,
        fastapi_endpoint_id=fastapi_endpoint_id,  # type: ignore[arg-type]
    )

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
                # An unresolved endpoint is only a *failure* if it had work to do.
                # Sync modes are normally applied further down, inside the stage
                # loop — which this branch never reaches — so resolve them here
                # first. Otherwise a run whose every selected stage is disabled
                # (``sync_type=sdn`` with the default ``sync_mode_sdn=disabled``,
                # say) would hard-fail as "No sync stage ran" on an endpoint that
                # was never going to sync anything. Nothing was lost, so nothing
                # is wrong. ``_build_base_query_params()`` re-sets these globals
                # for every endpoint that does run, so scribbling on them here is
                # the established pattern, not a leak.
                _set_sync_mode_vars(effective_sync_modes_for_endpoint(endpoint_id))
                mode_skips = {st: _stage_skip_reason(st) for st in stages}
                if all(reason is not None for reason in mode_skips.values()):
                    job.logger.info(
                        f"Proxmox endpoint {endpoint_id} is not registered on the "
                        "ProxBox backend, but every selected stage is disabled by "
                        "its sync modes — recording skips instead of failing"
                    )
                    for st, skip_reason in mode_skips.items():
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
                reason = (
                    wire_resolve_error
                    # Two distinct causes land here and the message covers both:
                    # the backend has never seen this endpoint, or it holds a row
                    # under this endpoint's name that points at a *different*
                    # host — a retarget whose preflight push failed. The second
                    # is why "skipping to avoid syncing the wrong endpoint" is
                    # literal rather than defensive phrasing. The specific cause
                    # is logged by resolve_backend_endpoint_ids().
                    or f"Proxmox endpoint {endpoint_id} could not be resolved to "
                    "a current ProxBox backend endpoint (not registered, or the "
                    "backend's stored copy points at a different host or port); "
                    "skipping to avoid syncing the wrong endpoint"
                )
                job.logger.error(
                    f"Skipping SSE sync for Proxmox endpoint {endpoint_id}: {reason}"
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
                f"Running SSE sync for Proxmox endpoint {endpoint_id} "
                f"(backend id {backend_id})"
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
                    f"Skipping stage {st} for endpoint "
                    f"{endpoint_id or 'unscoped'}: {skip_reason}"
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
                        preflight_hint=preflight_hint,
                    )
                except RuntimeError as exc:
                    if st in _SKIPPABLE_STAGES:
                        job.logger.warning(
                            f"Optional stage '{st}' failed and was skipped: {exc}"
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
