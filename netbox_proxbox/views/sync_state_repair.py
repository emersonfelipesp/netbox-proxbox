"""Operator repair action for Proxbox sync-state/bootstrap recovery."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass

from core.choices import JobStatusChoices
from core.models import Job
from django.contrib import messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.views import View
from utilities.views import (
    ConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
)

from netbox_proxbox.choices import SyncTypeChoices
from netbox_proxbox.jobs import (
    PROXBOX_SYNC_QUEUE_NAME,
    ProxboxSyncJob,
    is_proxbox_sync_job,
    proxbox_sync_params_from_job,
)
from netbox_proxbox.models import FastAPIEndpoint, ProxmoxEndpoint
from netbox_proxbox.views.proxbox_access import (
    permission_enqueue_proxbox_sync,
    permission_view_fastapi_endpoint,
)
from netbox_proxbox.views.sync_helpers import build_job_name

__all__ = (
    "BootstrapStatusView",
    "RepairSyncStateView",
    "BackendPayloadResult",
    "SyncStateRepairOutcome",
    "build_bootstrap_status_payload",
    "build_bootstrap_status_context",
    "build_sync_state_repair_outcome",
)

_REPAIR_NEXT_ROUTES = {
    "home": "plugins:netbox_proxbox:home",
    "settings": "plugins:netbox_proxbox:settings",
}
logger = logging.getLogger(__name__)
_BACKEND_FAILURE_STATUSES = {
    "error",
    "errored",
    "failed",
    "failure",
    "unhealthy",
    "unreachable",
}
_BACKEND_FAILURE_DETAIL_MARKERS = (
    "denied",
    "error",
    "exception",
    "fail",
    "invalid",
    "timeout",
    "unable",
    "unreachable",
)


@dataclass(frozen=True)
class BackendPayloadResult:
    """Interpreted result from the proxy envelope and backend JSON body."""

    ok: bool
    detail: str
    body: object
    requested_urls: list[object]


@dataclass(frozen=True)
class SyncStateRepairOutcome:
    """User-facing result of a repair/rebuild request."""

    status: str
    message: str
    job: object | None = None
    backend_status: int | None = None

    @property
    def ok(self) -> bool:
        """Return true when the repair completed and queued the sync job."""
        return self.status == "success"


def _all_enabled_proxmox_endpoint_ids() -> list[int]:
    """Return enabled Proxmox endpoint primary keys for a broad rebuild sync."""
    return list(
        ProxmoxEndpoint.objects.filter(enabled=True).values_list("pk", flat=True)
    )


def _stringify_backend_detail(value: object) -> str:
    if isinstance(value, (dict, list, tuple)):
        try:
            return json.dumps(value, sort_keys=True, default=str)
        except TypeError:
            return str(value)
    return str(value)


def _inner_backend_body(payload: dict[str, object]) -> object:
    if payload.get("ok") is True and "response" in payload:
        return payload.get("response") or {}
    return payload


def _detail_from_mapping(mapping: dict[str, object]) -> str:
    for key in ("detail", "error", "message", "errors", "warning", "warnings"):
        value = mapping.get(key)
        if value not in (None, "", [], {}):
            return _stringify_backend_detail(value)
    return ""


def _backend_payload_detail(payload: dict[str, object]) -> str:
    body = _inner_backend_body(payload)
    if isinstance(body, dict):
        detail = _detail_from_mapping(body)
        if detail:
            return detail
    detail = _detail_from_mapping(payload)
    if detail:
        return detail
    return "ProxBox backend returned an unexpected response."


def _is_false_marker(value: object) -> bool:
    if value is False:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"0", "false", "failed", "failure", "no"}
    return False


def _is_true_marker(value: object) -> bool:
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"1", "ok", "success", "true", "yes"}
    return False


def _detail_indicates_failure(detail: object) -> bool:
    detail_text = str(detail).strip().lower()
    if not detail_text:
        return False
    return any(marker in detail_text for marker in _BACKEND_FAILURE_DETAIL_MARKERS)


def backend_payload_result(
    payload: dict[str, object], http_status: int
) -> BackendPayloadResult:
    """Classify proxy transport success and the proxbox-api JSON body together."""
    body = _inner_backend_body(payload)
    requested_urls = list(payload.get("requested_urls") or [])
    transport_ok = 200 <= http_status < 300 and payload.get("ok") is not False

    if not transport_ok:
        return BackendPayloadResult(
            ok=False,
            detail=_backend_payload_detail(payload),
            body=body,
            requested_urls=requested_urls,
        )

    detail = _backend_payload_detail(payload)
    if isinstance(body, dict):
        status_value = str(body.get("status") or body.get("state") or "").lower()
        explicit_success = _is_true_marker(body.get("ok")) or _is_true_marker(
            body.get("success")
        )
        explicit_failure = _is_false_marker(body.get("ok")) or _is_false_marker(
            body.get("success")
        )
        error_value = body.get("error") or body.get("errors")
        detail_value = body.get("detail")
        failed = (
            explicit_failure
            or bool(error_value)
            or status_value in _BACKEND_FAILURE_STATUSES
            or (
                not explicit_success
                and detail_value not in (None, "")
                and _detail_indicates_failure(detail_value)
            )
        )
        if failed:
            return BackendPayloadResult(
                ok=False,
                detail=detail,
                body=body,
                requested_urls=requested_urls,
            )

        warning_detail = _detail_from_mapping(
            {key: body[key] for key in ("warning", "warnings", "detail") if key in body}
        )
        if warning_detail:
            detail = warning_detail
        else:
            detail = ""
    else:
        detail = ""

    return BackendPayloadResult(
        ok=True,
        detail=detail,
        body=body,
        requested_urls=requested_urls,
    )


def _visible_fastapi_endpoint(request: HttpRequest) -> object | None:
    return (
        FastAPIEndpoint.objects.restrict(request.user, "view")
        .filter(enabled=True)
        .first()
    )


def _reconcile_backend_custom_fields(
    endpoint_id: int | None = None,
) -> tuple[dict[str, object], int]:
    """Lazy import wrapper so status helpers do not create startup import cycles."""
    try:
        from netbox_proxbox.services.backend_proxy import (
            reconcile_backend_custom_fields,
        )

        return reconcile_backend_custom_fields(endpoint_id=endpoint_id)
    except Exception as exc:  # noqa: BLE001 - repair action must surface, not 500
        logger.warning("Unable to reconcile Proxbox custom fields: %s", exc)
        return {"ok": False, "detail": str(exc)}, 503


def _reconcile_backend_custom_fields_for_request(
    request: HttpRequest,
) -> tuple[dict[str, object], int]:
    endpoint = _visible_fastapi_endpoint(request)
    if endpoint is None:
        return {
            "ok": False,
            "detail": "No viewable enabled FastAPI endpoint is configured.",
        }, 404
    return _reconcile_backend_custom_fields(endpoint_id=getattr(endpoint, "pk", None))


def _get_backend_bootstrap_status(
    endpoint_id: int | None = None,
) -> tuple[dict[str, object], int]:
    """Lazy import wrapper around the proxbox-api bootstrap-status helper."""
    try:
        from netbox_proxbox.services.backend_proxy import get_backend_bootstrap_status

        return get_backend_bootstrap_status(endpoint_id=endpoint_id)
    except Exception as exc:  # noqa: BLE001 - status card must not break pages
        logger.warning("Unable to read Proxbox bootstrap status: %s", exc)
        return {"ok": False, "detail": str(exc)}, 503


def _get_backend_bootstrap_status_for_request(
    request: HttpRequest,
) -> tuple[dict[str, object], int]:
    endpoint = _visible_fastapi_endpoint(request)
    if endpoint is None:
        return {
            "ok": False,
            "detail": "No viewable enabled FastAPI endpoint is configured.",
        }, 404
    return _get_backend_bootstrap_status(endpoint_id=getattr(endpoint, "pk", None))


def _normalize_endpoint_ids(endpoint_ids: list[int] | None) -> list[int]:
    return (
        endpoint_ids
        if endpoint_ids is not None
        else _all_enabled_proxmox_endpoint_ids()
    )


def _active_repair_sync_job(user: object, endpoint_ids: list[int]) -> object | None:
    """Return an active full Proxbox sync job for the same endpoint scope, if any."""
    try:
        jobs = (
            Job.objects.restrict(user, "view")
            .filter(status__in=JobStatusChoices.ENQUEUED_STATE_CHOICES)
            .order_by("-created")
        )
    except Exception:  # noqa: BLE001 - debounce is best-effort around NetBox versions
        logger.debug("Unable to inspect active Proxbox sync jobs.", exc_info=True)
        return None

    target_endpoint_ids = {str(value) for value in endpoint_ids if str(value)}
    for job in jobs:
        if not is_proxbox_sync_job(job):
            continue
        try:
            params = proxbox_sync_params_from_job(job)
        except Exception:  # noqa: BLE001 - ignore malformed legacy job metadata
            continue
        sync_types = list(params.get("sync_types") or [])
        if sync_types != [SyncTypeChoices.ALL]:
            continue
        job_endpoint_ids = {
            str(value) for value in list(params.get("proxmox_endpoint_ids") or [])
        }
        if not job_endpoint_ids or job_endpoint_ids == target_endpoint_ids:
            return job
    return None


def build_sync_state_repair_outcome(
    *,
    user: object,
    can_enqueue: bool,
    reconcile_backend: Callable[[], tuple[dict[str, object], int]] | None = None,
    enqueue_sync: Callable[..., object] | None = None,
    endpoint_ids: list[int] | None = None,
    active_job_check: Callable[[object, list[int]], object | None] | None = None,
) -> SyncStateRepairOutcome:
    """Reconcile backend custom fields, then enqueue a normal full sync job."""
    if not can_enqueue:
        return SyncStateRepairOutcome(
            status="permission_denied",
            message="You do not have permission to enqueue Proxbox sync jobs.",
        )

    target_endpoint_ids = _normalize_endpoint_ids(endpoint_ids)
    active_job = (active_job_check or _active_repair_sync_job)(
        user, target_endpoint_ids
    )
    if active_job is not None:
        return SyncStateRepairOutcome(
            status="already_running",
            message=(
                "A Proxbox full sync is already pending or running for this "
                "repair scope. No duplicate repair sync was queued."
            ),
            job=active_job,
        )

    reconcile = reconcile_backend or _reconcile_backend_custom_fields
    try:
        payload, backend_status = reconcile()
    except Exception as exc:  # noqa: BLE001 - dependency injection tests/backend stubs
        return SyncStateRepairOutcome(
            status="backend_error",
            message=(
                f"Proxbox custom-field reconcile failed: {exc} No sync was queued."
            ),
            backend_status=503,
        )
    backend_result = backend_payload_result(payload, backend_status)
    if not backend_result.ok:
        return SyncStateRepairOutcome(
            status="backend_error",
            message=(
                "Proxbox custom-field reconcile failed: "
                f"{backend_result.detail} No sync was queued."
            ),
            backend_status=backend_status,
        )

    enqueue = enqueue_sync or ProxboxSyncJob.enqueue
    try:
        job = enqueue(
            instance=None,
            user=user,
            queue_name=PROXBOX_SYNC_QUEUE_NAME,
            name=build_job_name(_("Repair / Rebuild sync-state")),
            sync_types=[SyncTypeChoices.ALL],
            proxmox_endpoint_ids=target_endpoint_ids,
        )
    except Exception as exc:  # noqa: BLE001 - surface enqueue failures, never 500
        return SyncStateRepairOutcome(
            status="enqueue_error",
            message=(
                "Custom fields were reconciled, but the Proxbox rebuild sync job "
                f"could not be queued: {exc}"
            ),
            backend_status=backend_status,
        )

    return SyncStateRepairOutcome(
        status="success",
        message=(
            "Proxbox custom fields were reconciled and a rebuild sync job has "
            "been queued."
        ),
        job=job,
        backend_status=backend_status,
    )


def _bootstrap_status_json(payload: dict[str, object]) -> str:
    response = _inner_backend_body(payload)
    return json.dumps(response or {}, indent=2, sort_keys=True, default=str)


def build_bootstrap_status_payload(
    request: HttpRequest,
    *,
    fetch_status: Callable[[], tuple[dict[str, object], int]] | None = None,
) -> tuple[dict[str, object], int]:
    """Fetch bootstrap status for the AJAX card without raising page errors."""
    user = getattr(request, "user", None)
    can_view_status = bool(user and user.has_perm(permission_view_fastapi_endpoint()))
    if not can_view_status:
        return {
            "can_view": False,
            "ok": False,
            "detail": "Viewing bootstrap status requires FastAPI endpoint view permission.",
            "http_status": None,
            "requested_urls": [],
            "payload": {},
        }, 403

    getter = fetch_status or (
        lambda: _get_backend_bootstrap_status_for_request(request)
    )
    try:
        payload, http_status = getter()
    except Exception as exc:  # noqa: BLE001 - AJAX status must never return 500
        logger.warning("Unable to read Proxbox bootstrap status: %s", exc)
        payload, http_status = {"ok": False, "detail": str(exc)}, 503

    backend_result = backend_payload_result(payload, http_status)
    return {
        "can_view": True,
        "ok": backend_result.ok,
        "detail": backend_result.detail,
        "http_status": http_status,
        "requested_urls": backend_result.requested_urls,
        "payload": backend_result.body if backend_result.body is not None else {},
    }, 200


def build_bootstrap_status_context(
    request: HttpRequest,
    *,
    surface: str,
    fetch_status: Callable[[], tuple[dict[str, object], int]] | None = None,
) -> dict[str, object]:
    """Build shared template context for bootstrap status and repair controls."""
    user = getattr(request, "user", None)
    can_view_status = bool(user and user.has_perm(permission_view_fastapi_endpoint()))
    can_repair_sync_state = bool(
        user and user.has_perm(permission_enqueue_proxbox_sync())
    )

    status_context: dict[str, object] = {
        "can_view": can_view_status,
        "ok": False,
        "detail": "",
        "http_status": None,
        "requested_urls": [],
        "deferred": can_view_status,
    }
    status_json = ""

    if can_view_status and fetch_status is not None:
        payload, http_status = fetch_status()
        backend_result = backend_payload_result(payload, http_status)
        status_context = {
            "can_view": True,
            "ok": backend_result.ok,
            "detail": backend_result.detail,
            "http_status": http_status,
            "requested_urls": backend_result.requested_urls,
            "deferred": False,
        }
        status_json = _bootstrap_status_json(payload)

    return {
        "bootstrap_status": status_context,
        "bootstrap_status_json": status_json,
        "can_repair_sync_state": can_repair_sync_state,
        "proxbox_repair_next": surface
        if surface in _REPAIR_NEXT_ROUTES
        else "settings",
    }


def _redirect_name_from_request(request: HttpRequest) -> str:
    target = request.POST.get("next", "settings")
    return _REPAIR_NEXT_ROUTES.get(target, _REPAIR_NEXT_ROUTES["settings"])


class RepairSyncStateView(
    ContentTypePermissionRequiredMixin,
    View,
):
    """POST action that reconciles Proxbox custom fields and queues a full sync."""

    http_method_names = ["post", "head", "options"]

    def get_required_permission(self) -> str:
        """Require the same permission used by normal sync enqueue actions."""
        return permission_enqueue_proxbox_sync()

    def post(
        self, request: HttpRequest, *args: object, **kwargs: object
    ) -> HttpResponse:
        """Handle the repair/rebuild request and redirect back to the source page."""
        outcome = build_sync_state_repair_outcome(
            user=request.user,
            can_enqueue=request.user.has_perm(self.get_required_permission()),
            reconcile_backend=lambda: _reconcile_backend_custom_fields_for_request(
                request
            ),
        )

        if outcome.ok and outcome.job is not None:
            messages.success(
                request,
                format_html(
                    '{} <a href="{}">{}</a>',
                    outcome.message,
                    outcome.job.get_absolute_url(),
                    _("View job"),
                ),
            )
        elif outcome.status == "already_running" and outcome.job is not None:
            get_absolute_url = getattr(outcome.job, "get_absolute_url", None)
            if callable(get_absolute_url):
                messages.warning(
                    request,
                    format_html(
                        '{} <a href="{}">{}</a>',
                        outcome.message,
                        get_absolute_url(),
                        _("View job"),
                    ),
                )
            else:
                messages.warning(request, outcome.message)
        elif outcome.status == "permission_denied":
            messages.error(request, outcome.message)
        else:
            messages.error(request, outcome.message)

        return redirect(_redirect_name_from_request(request))


class BootstrapStatusView(ConditionalLoginRequiredMixin, View):
    """AJAX bootstrap-status endpoint for the repair card."""

    http_method_names = ["get", "head", "options"]

    def get(
        self, request: HttpRequest, *args: object, **kwargs: object
    ) -> JsonResponse:
        """Return request-scoped bootstrap status; backend failures stay in JSON."""
        payload, status = build_bootstrap_status_payload(request)
        return JsonResponse(payload, status=status)
