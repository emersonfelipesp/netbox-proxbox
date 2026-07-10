"""Optional integration with the **netbox-rpc** plugin.

netbox-rpc is one of the *Additional Optional Plugins* in the Proxbox family. When
it is installed, netbox-proxbox can run audited SSH procedures against Proxmox
hosts through the netbox-rpc engine instead of handling SSH itself — for example
installing an SSH public key on a Proxmox node so the Proxbox **cloud image build
pipeline** (proxbox-api) can reach that node.

The dependency is *soft*: netbox-rpc is never imported at module import time and is
not listed in ``pyproject.toml`` dependencies. Every helper here detects netbox-rpc
at call time with ``try/except ImportError`` (the same pattern netbox-proxbox uses
for ``netbox_branching`` and ``netbox_pbs``) and degrades cleanly when it is absent.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
from typing import Any

logger = logging.getLogger("netbox_proxbox.integrations.rpc")

# Canonical procedure name seeded by netbox-rpc migration 0006.
INSTALL_SSH_KEY_PROCEDURE = "os.linux.ubuntu.24.install_ssh_key"
SYSTEMCTL_SERVICES_PROCEDURE = "os.linux.proxmox.show_systemctl_services"

_RPC_SUCCESS_STATUSES = {"succeeded", "success", "completed", "complete", "finished"}
_RPC_FAILURE_STATUSES = {
    "failed",
    "failure",
    "errored",
    "error",
    "canceled",
    "cancelled",
}
_PENDING_COLLECTION_TIMEOUT = timedelta(minutes=30)

__all__ = (
    "is_netbox_rpc_installed",
    "install_ssh_key_via_rpc",
    "collect_systemctl_services",
    "project_completed_collections",
    "rpc_dashboard_context",
    "INSTALL_SSH_KEY_PROCEDURE",
    "SYSTEMCTL_SERVICES_PROCEDURE",
)

# netbox-rpc mounts its UI under base_url "rpc"; the landing page is the plugin
# root. Kept as a stable literal so this soft integration does not depend on the
# companion plugin's internal URL names.
NETBOX_RPC_HOME_URL = "/plugins/rpc/"


def is_netbox_rpc_installed() -> bool:
    """Return ``True`` when the netbox-rpc plugin is enabled in this NetBox."""
    try:
        from django.conf import settings
    except Exception:  # noqa: BLE001 - Django not ready
        return False
    return "netbox_rpc" in (getattr(settings, "PLUGINS", []) or [])


def install_ssh_key_via_rpc(
    *,
    target: Any,
    public_key: str,
    backend: Any,
    requested_by: Any | None = None,
    username: str | None = None,
) -> Any | None:
    """Queue a netbox-rpc ``install_ssh_key`` execution against *target*.

    Args:
        target: the NetBox object the key is installed on (``dcim.Device`` or
            ``virtualization.VirtualMachine``) — usually the Proxmox host.
        public_key: OpenSSH public key string to append to the host's
            ``authorized_keys`` (e.g. the proxbox-api cloud-image-build key).
        backend: the ``netbox_nms.NMSBackend`` record that executes the procedure.
        requested_by: the NetBox user requesting the execution (optional).
        username: POSIX user on the host; defaults to the SSH credential's user.

    Returns:
        The created ``RPCExecution`` (status ``queued``), or ``None`` when
        netbox-rpc is not installed or the procedure is unavailable. Never raises
        on a missing optional dependency.
    """
    try:
        from netbox_rpc.jobs import RPCExecutionJob
        from netbox_rpc.models import RPCExecution, RPCProcedure
    except ImportError:
        logger.info(
            "netbox-rpc is not installed; skipping SSH key install for %r.", target
        )
        return None

    procedure = RPCProcedure.objects.filter(
        name=INSTALL_SSH_KEY_PROCEDURE, enabled=True
    ).first()
    if procedure is None:
        logger.warning(
            "netbox-rpc procedure %s not found/enabled; cannot install SSH key.",
            INSTALL_SSH_KEY_PROCEDURE,
        )
        return None

    params: dict[str, str] = {"public_key": public_key}
    if username:
        params["username"] = username

    execution = RPCExecution.objects.create(
        procedure=procedure,
        assigned_object=target,
        backend=backend,
        requested_by=requested_by,
        params=params,
        status="queued",
    )

    try:
        RPCExecutionJob.enqueue(
            execution_pk=execution.pk,
            instance=None,
            user=requested_by,
            backend_pk=getattr(backend, "pk", None),
        )
    except Exception:  # noqa: BLE001 - enqueue failures must not crash the caller
        logger.exception(
            "Failed to enqueue netbox-rpc execution #%s for %r", execution.pk, target
        )

    return execution


def _coerce_units(value: object) -> list[str]:
    """Normalize configured unit names into the RPC parameter shape."""
    if value in (None, ""):
        return []
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
            except ValueError:
                return [raw]
            return _coerce_units(parsed)
        return [raw]
    if isinstance(value, (list, tuple, set)):
        units = []
        for item in value:
            unit = str(item or "").strip()
            if unit:
                units.append(unit)
        return units
    return []


def _resolve_rpc_backend(backend: Any | None) -> Any | None:
    """Return an active netbox-nms backend when that optional plugin is present."""
    if backend is not None:
        return backend
    try:
        from netbox_nms.backend import get_backend
    except ImportError:
        return None
    try:
        return get_backend()
    except Exception:  # noqa: BLE001 - backend lookup is best-effort
        logger.exception("Failed to resolve a netbox-nms backend for netbox-rpc.")
        return None


def _update_endpoint_service_monitoring_heartbeat(
    endpoint: Any,
    *,
    status: str,
    error: str = "",
    success_at: Any | None = None,
) -> None:
    """Update endpoint heartbeat fields without leaking credential values."""
    update_fields = [
        "service_monitoring_last_status",
        "service_monitoring_last_error",
    ]
    setattr(endpoint, "service_monitoring_last_status", status)
    setattr(endpoint, "service_monitoring_last_error", error)
    if success_at is not None:
        setattr(endpoint, "service_monitoring_last_success_at", success_at)
        update_fields.append("service_monitoring_last_success_at")
    save = getattr(endpoint, "save", None)
    if callable(save):
        try:
            save(update_fields=update_fields)
        except TypeError:
            save()
        except Exception:  # noqa: BLE001 - heartbeat updates must not crash projection
            logger.exception(
                "Failed to update service monitoring heartbeat for endpoint %r.",
                getattr(endpoint, "pk", endpoint),
            )


def collect_systemctl_services(
    endpoint: Any,
    *,
    units: list[str] | tuple[str, ...] | None = None,
    requested_by: Any | None = None,
    trigger: str = "scheduled",
    backend: Any | None = None,
) -> Any | None:
    """Create and enqueue an async netbox-rpc systemctl service collection.

    This is phase 1 of service monitoring. It creates an ``RPCExecution`` and a
    pending ``ProxmoxServiceCollection`` row, then enqueues the netbox-rpc RQ job.
    It never attempts a synchronous run or polls for the result.
    """
    if not getattr(endpoint, "service_monitoring_enabled", False):
        _update_endpoint_service_monitoring_heartbeat(
            endpoint,
            status="disabled",
            error="Service monitoring is disabled for this endpoint.",
        )
        return None

    # Disabled endpoint rows are a hard no-connection gate: never dispatch an
    # RPC (which SSHes to the host) for an inventory-disabled endpoint, even if
    # monitoring is still configured. This choke point covers every trigger
    # (scheduler, Services-tab refresh, API refresh). Inlined equivalent of
    # services.endpoint_enabled.endpoint_is_enabled to keep the no-NetBox unit
    # tests import-light.
    if not bool(getattr(endpoint, "enabled", True)):
        _update_endpoint_service_monitoring_heartbeat(
            endpoint,
            status="endpoint_disabled",
            error="Endpoint is disabled; disabled endpoints are never contacted.",
        )
        return None

    if not getattr(endpoint, "service_monitoring_eligible", False):
        _update_endpoint_service_monitoring_heartbeat(
            endpoint,
            status="ineligible",
            error=(
                "Service monitoring requires allow_writes, API + SSH access, "
                "and complete endpoint SSH credentials."
            ),
        )
        return None

    try:
        from netbox_rpc.jobs import RPCExecutionJob
        from netbox_rpc.models import RPCExecution, RPCProcedure
    except ImportError:
        logger.info(
            "netbox-rpc is not installed; skipping systemctl service collection "
            "for endpoint %r.",
            endpoint,
        )
        _update_endpoint_service_monitoring_heartbeat(
            endpoint,
            status="unavailable",
            error="netbox-rpc is not installed.",
        )
        return None

    procedure = RPCProcedure.objects.filter(
        name=SYSTEMCTL_SERVICES_PROCEDURE,
        enabled=True,
    ).first()
    if procedure is None:
        logger.warning(
            "netbox-rpc procedure %s not found/enabled; cannot collect services.",
            SYSTEMCTL_SERVICES_PROCEDURE,
        )
        _update_endpoint_service_monitoring_heartbeat(
            endpoint,
            status="unavailable",
            error=f"netbox-rpc procedure {SYSTEMCTL_SERVICES_PROCEDURE} is not enabled.",
        )
        return None

    from netbox_proxbox.models import ProxmoxServiceCollection
    from netbox_proxbox.models.service_monitoring import (
        SERVICE_COLLECTION_STATUS_FAILED,
        SERVICE_COLLECTION_STATUS_PENDING,
        SERVICE_COLLECTION_TRIGGER_ON_DEMAND,
        SERVICE_COLLECTION_TRIGGER_SCHEDULED,
    )

    normalized_trigger = (
        SERVICE_COLLECTION_TRIGGER_ON_DEMAND
        if trigger == SERVICE_COLLECTION_TRIGGER_ON_DEMAND
        else SERVICE_COLLECTION_TRIGGER_SCHEDULED
    )
    backend_obj = _resolve_rpc_backend(backend)
    params = {
        "proxmox_endpoint_id": getattr(endpoint, "pk", None),
        "units": _coerce_units(
            units if units is not None else getattr(endpoint, "service_monitoring_units", [])
        ),
    }
    execution = RPCExecution.objects.create(
        procedure=procedure,
        assigned_object=endpoint,
        backend=backend_obj,
        requested_by=requested_by,
        params=params,
        status="queued",
    )
    collection = ProxmoxServiceCollection.objects.create(
        endpoint=endpoint,
        trigger=normalized_trigger,
        rpc_execution_id=getattr(execution, "pk", None),
        status=SERVICE_COLLECTION_STATUS_PENDING,
    )

    try:
        RPCExecutionJob.enqueue(
            execution_pk=execution.pk,
            instance=None,
            user=requested_by,
            backend_pk=getattr(backend_obj, "pk", None),
        )
    except Exception as exc:  # noqa: BLE001 - enqueue failures should be visible locally
        logger.exception(
            "Failed to enqueue netbox-rpc systemctl collection execution #%s.",
            getattr(execution, "pk", None),
        )
        collection.status = SERVICE_COLLECTION_STATUS_FAILED
        collection.error_message = str(exc)
        collection.save(update_fields=["status", "error_message", "last_updated"])
        _update_endpoint_service_monitoring_heartbeat(
            endpoint,
            status="enqueue_failed",
            error=str(exc),
        )
        return None

    return execution


def _result_dict(raw_result: object) -> dict[str, Any]:
    """Return an execution result dict, accepting JSON strings defensively."""
    if isinstance(raw_result, dict):
        return raw_result
    if isinstance(raw_result, str) and raw_result.strip():
        try:
            parsed = json.loads(raw_result)
        except ValueError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def _int_or_none(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _duration_ms_from_execution(execution: Any) -> int | None:
    for attr in ("duration_ms", "runtime_ms", "elapsed_ms"):
        value = _int_or_none(getattr(execution, attr, None))
        if value is not None:
            return value
    duration = getattr(execution, "duration", None)
    try:
        if duration is not None:
            return int(float(duration) * 1000)
    except (TypeError, ValueError):
        return None
    started = getattr(execution, "started", None) or getattr(
        execution,
        "started_at",
        None,
    )
    completed = getattr(execution, "completed", None) or getattr(
        execution,
        "completed_at",
        None,
    )
    if started is not None and completed is not None:
        try:
            return int((completed - started).total_seconds() * 1000)
        except Exception:  # noqa: BLE001 - optional metadata only
            return None
    return None


def _utcnow() -> datetime:
    """Return an aware UTC timestamp without importing Django at module load."""
    return datetime.now(timezone.utc)


def _execution_finished_at(execution: Any) -> Any | None:
    """Return the best available terminal timestamp from a netbox-rpc execution."""
    for attr in (
        "completed_at",
        "completed",
        "finished_at",
        "finished",
        "ended_at",
        "ended",
    ):
        value = getattr(execution, attr, None)
        if value is not None:
            return value
    return None


def _collection_pending_timed_out(collection: Any, now: datetime) -> bool:
    """Return whether a pending collection has aged past the orphan timeout."""
    collected_at = getattr(collection, "collected_at", None)
    if collected_at is None:
        return False
    try:
        if getattr(collected_at, "tzinfo", None) is None:
            collected_at = collected_at.replace(tzinfo=timezone.utc)
        return collected_at <= now - _PENDING_COLLECTION_TIMEOUT
    except Exception:  # noqa: BLE001 - malformed timestamps should not crash projection
        return False


def _status_is_current_or_newer(incoming: Any, current: Any) -> bool:
    """Return whether an incoming status timestamp may update latest state."""
    if current is None:
        return True
    if incoming is None:
        return False
    try:
        return incoming >= current
    except TypeError:
        return True


def _service_defaults(service: dict[str, Any]) -> dict[str, Any]:
    """Map one netbox-rpc service row into model fields."""
    return {
        "service_id": str(service.get("id") or ""),
        "load_state": str(service.get("load_state") or ""),
        "active_state": str(service.get("active_state") or ""),
        "sub_state": str(service.get("sub_state") or ""),
        "result": str(service.get("result") or ""),
        "main_pid": _int_or_none(service.get("main_pid")),
        "exec_main_code": _int_or_none(service.get("exec_main_code")),
        "exec_main_status": _int_or_none(service.get("exec_main_status")),
        "n_restarts": _int_or_none(service.get("n_restarts")),
        "active_enter_timestamp": str(service.get("active_enter_timestamp") or ""),
        "unit_file_state": str(service.get("unit_file_state") or ""),
    }


def _service_is_healthy(
    *,
    active_state: str,
    expected_active: bool,
) -> bool:
    is_active = active_state == "active"
    return is_active if expected_active else not is_active


def _project_service_rows(collection: Any, services: object, seen_at: Any) -> int:
    """Project raw service rows into samples and latest-status upserts."""
    from django.db.models import Q
    from netbox_proxbox.models import ProxmoxServiceSample, ProxmoxServiceStatus

    if not isinstance(services, list):
        return 0

    projected = 0
    endpoint = collection.endpoint
    for service in services:
        if not isinstance(service, dict):
            continue
        unit = str(service.get("unit") or service.get("id") or "").strip()
        if not unit:
            continue
        defaults = _service_defaults(service)
        ProxmoxServiceSample.objects.update_or_create(
            collection=collection,
            unit=unit,
            defaults=defaults,
        )
        status_obj, _created = ProxmoxServiceStatus.objects.get_or_create(
            endpoint=endpoint,
            unit=unit,
            defaults={
                **defaults,
                "last_seen_at": seen_at,
                "expected_active": True,
                "is_healthy": _service_is_healthy(
                    active_state=str(defaults["active_state"]),
                    expected_active=True,
                ),
            },
        )
        projected += 1
        if _created:
            continue
        expected_active = bool(getattr(status_obj, "expected_active", True))
        values = {
            **defaults,
            "last_seen_at": seen_at,
            "is_healthy": _service_is_healthy(
                active_state=str(defaults["active_state"]),
                expected_active=expected_active,
            ),
            "last_updated": _utcnow(),
        }
        ProxmoxServiceStatus.objects.filter(pk=status_obj.pk).filter(
            Q(last_seen_at__isnull=True) | Q(last_seen_at__lt=seen_at)
        ).update(**values)
    return projected


def _mark_collection_failed(collection: Any, execution: Any, error: str) -> None:
    from netbox_proxbox.models.service_monitoring import SERVICE_COLLECTION_STATUS_FAILED

    collection.status = SERVICE_COLLECTION_STATUS_FAILED
    collection.reachable = False
    collection.duration_ms = _duration_ms_from_execution(execution)
    collection.error_message = error
    collection.save(
        update_fields=[
            "status",
            "reachable",
            "duration_ms",
            "error_message",
            "last_updated",
        ]
    )
    _update_endpoint_service_monitoring_heartbeat(
        collection.endpoint,
        status="failed",
        error=error,
    )


def _mark_collection_succeeded(
    collection: Any,
    execution: Any,
    *,
    reachable: bool,
    error_message: str = "",
    success_at: Any | None = None,
) -> None:
    from netbox_proxbox.models.service_monitoring import (
        SERVICE_COLLECTION_STATUS_SUCCEEDED,
    )

    collection.status = SERVICE_COLLECTION_STATUS_SUCCEEDED
    collection.reachable = reachable
    collection.duration_ms = _duration_ms_from_execution(execution)
    collection.error_message = error_message
    collection.save(
        update_fields=[
            "status",
            "reachable",
            "duration_ms",
            "error_message",
            "last_updated",
        ]
    )
    if reachable:
        _update_endpoint_service_monitoring_heartbeat(
            collection.endpoint,
            status="succeeded",
            error="",
            success_at=success_at or _execution_finished_at(execution) or _utcnow(),
        )
    else:
        _update_endpoint_service_monitoring_heartbeat(
            collection.endpoint,
            status="unreachable",
            error=error_message,
        )


def project_completed_collections(*, limit: int = 100) -> int:
    """Project finished netbox-rpc service collections into local status rows.

    This is phase 2 of service monitoring. It looks for pending collection rows
    whose linked ``RPCExecution`` is already terminal, reconciles the result into
    samples/latest status, and updates endpoint heartbeat fields. It never blocks
    waiting for a queued or running RPC execution.
    """
    try:
        from netbox_rpc.models import RPCExecution
    except ImportError:
        logger.info("netbox-rpc is not installed; skipping service projection.")
        return 0

    from netbox_proxbox.models import ProxmoxServiceCollection
    from netbox_proxbox.models.service_monitoring import SERVICE_COLLECTION_STATUS_PENDING

    pending = list(
        ProxmoxServiceCollection.objects.filter(
            status=SERVICE_COLLECTION_STATUS_PENDING,
        )
        .select_related("endpoint")
        .order_by("collected_at", "pk")
    )
    if not pending:
        return 0

    execution_ids = [
        collection.rpc_execution_id
        for collection in pending
        if collection.rpc_execution_id is not None
    ]
    executions = {
        execution.pk: execution
        for execution in RPCExecution.objects.filter(pk__in=execution_ids)
    }

    projected = 0
    stale_failures = 0
    now = _utcnow()
    for collection in pending:
        execution = executions.get(collection.rpc_execution_id)
        if execution is None:
            if (
                stale_failures < limit
                and _collection_pending_timed_out(collection, now)
            ):
                _mark_collection_failed(
                    collection,
                    None,
                    (
                        "RPC execution is missing and the pending collection "
                        "exceeded the 30 minute timeout."
                    ),
                )
                projected += 1
                stale_failures += 1
            continue
        execution_status = str(getattr(execution, "status", "") or "").lower()
        if execution_status not in _RPC_SUCCESS_STATUSES | _RPC_FAILURE_STATUSES:
            if (
                stale_failures < limit
                and _collection_pending_timed_out(collection, now)
            ):
                _mark_collection_failed(
                    collection,
                    execution,
                    (
                        "RPC execution did not reach a terminal state within "
                        f"30 minutes; current status is {execution_status or 'unknown'}."
                    ),
                )
                projected += 1
                stale_failures += 1
            continue

        if execution_status in _RPC_FAILURE_STATUSES:
            _mark_collection_failed(
                collection,
                execution,
                str(
                    getattr(execution, "error", "")
                    or getattr(execution, "last_error", "")
                    or f"RPC execution ended with status {execution_status}."
                ),
            )
            projected += 1
            continue

        result = _result_dict(getattr(execution, "result", None))
        reachable = bool(result.get("reachable"))
        if result.get("ok") is False:
            _mark_collection_failed(
                collection,
                execution,
                str(
                    result.get("error")
                    or result.get("detail")
                    or "RPC execution returned ok=false."
                ),
            )
            projected += 1
            continue

        completed_at = _execution_finished_at(execution) or _utcnow()
        if reachable:
            _project_service_rows(
                collection,
                result.get("services"),
                completed_at,
            )
            _mark_collection_succeeded(
                collection,
                execution,
                reachable=True,
                success_at=completed_at,
            )
        else:
            _mark_collection_succeeded(
                collection,
                execution,
                reachable=False,
                error_message=str(result.get("error") or ""),
            )
        projected += 1

    return projected
def rpc_dashboard_context() -> dict[str, Any]:
    """Best-effort dashboard context for the optional netbox-rpc companion card.

    Returns ``{}`` when netbox-rpc is not installed, so the Proxbox home page
    simply omits the card. When netbox-rpc is present, returns
    ``{"rpc_integration": {...}}`` describing whether the operator has opted in
    (``enabled``) and which backend is configured. Never raises and never issues
    a network call — live backend reachability is offered by the netbox-rpc
    landing page's own *Test connection* action, so the Proxbox dashboard render
    stays fast and fully decoupled.
    """
    if not is_netbox_rpc_installed():
        return {}

    info: dict[str, Any] = {
        "installed": True,
        "enabled": False,
        "backend_name": "",
        "backend_url": "",
        "home_url": NETBOX_RPC_HOME_URL,
        "settings_supported": False,
    }

    try:
        from netbox_rpc.models import RpcPluginSettings  # type: ignore[import]
    except ImportError:
        # netbox-rpc is installed but predates the opt-in settings model; still
        # show the card (config state unknown) with a link to the plugin.
        return {"rpc_integration": info}

    info["settings_supported"] = True
    try:
        settings = RpcPluginSettings.get_solo()
        info["enabled"] = bool(getattr(settings, "enabled", False))
        backend = getattr(settings, "backend", None)
        if backend is not None:
            info["backend_name"] = str(backend)
            info["backend_url"] = getattr(backend, "backend_url", "") or ""
    except Exception:  # noqa: BLE001 - a bad/missing settings row must not break home
        logger.debug("Unable to read netbox-rpc RpcPluginSettings for dashboard card.")

    return {"rpc_integration": info}
