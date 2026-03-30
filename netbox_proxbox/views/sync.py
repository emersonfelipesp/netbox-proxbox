"""Trigger sync operations on the external ProxBox backend over HTTP."""

from __future__ import annotations

import logging
from typing import Any

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.http import StreamingHttpResponse
from django.shortcuts import redirect
from django.views import View

from netbox_proxbox.services import backend_proxy
from netbox_proxbox.views.proxbox_access import permission_change_fastapi_endpoint
from utilities.views import (
    ContentTypePermissionRequiredMixin,
    TokenConditionalLoginRequiredMixin,
)

logger = logging.getLogger(__name__)


def wants_json_response(request: HttpRequest | None) -> bool:
    """Return True if the client expects JSON (XHR or Accept: application/json)."""
    if request is None:
        return True

    requested_with = ""
    headers = getattr(request, "headers", {}) or {}
    if isinstance(headers, dict):
        requested_with = headers.get("X-Requested-With", "")
        accept = headers.get("Accept", "")
    else:
        requested_with = getattr(headers, "get", lambda *args, **kwargs: "")(
            "X-Requested-With", ""
        )
        accept = getattr(headers, "get", lambda *args, **kwargs: "")("Accept", "")

    return requested_with == "XMLHttpRequest" or "application/json" in accept


def sync_response(
    request: HttpRequest | None,
    *,
    path: str,
    action_label: str,
    query_params: dict[str, Any] | None = None,
) -> HttpResponse:
    """Run sync against the backend and return JSON or redirect with messages."""
    if path == "full-update":
        merged_qp = {**(query_params or {})}
        if request is not None and getattr(request, "GET", None):
            merged_qp.update(dict(request.GET.items()))
        payload, status = backend_proxy.sync_full_update_resource(
            query_params=merged_qp if merged_qp else None
        )
    else:
        payload, status = backend_proxy.sync_resource(path, query_params=query_params)
    if wants_json_response(request):
        return JsonResponse(payload, status=status)

    detail = payload.get("detail")
    if status < 400:
        messages.success(
            request, detail or f"{action_label} sync queued successfully."
        )
    else:
        messages.error(request, detail or f"{action_label} sync failed.")
    return redirect("plugins:netbox_proxbox:home")


def sync_stream_response(
    request: HttpRequest,
    *,
    path: str,
    query_params: dict[str, Any] | None = None,
) -> StreamingHttpResponse:
    """Proxy an SSE stream from the backend for the given sync path."""
    try:
        context = backend_proxy.get_fastapi_request_context()
        if context is None:
            stream_iter = backend_proxy.sse_error_frames(
                "No FastAPI endpoint configured."
            )
        else:
            stream_path = f"{path.rstrip('/')}/stream"
            stream_iter = backend_proxy.iter_backend_sse_lines(
                context,
                stream_path,
                query_params=query_params,
            )

        response = StreamingHttpResponse(
            stream_iter,
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
    except Exception as exc:  # pragma: no cover
        logger.exception("Failed to build stream response for %s", path)
        response = StreamingHttpResponse(
            backend_proxy.sse_error_frames(
                str(exc), final_message="Stream response bootstrap failed."
            ),
            content_type="text/event-stream",
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response


class _ProxboxSyncActionView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """POST/GET sync trigger; requires change on FastAPIEndpoint (backend integration)."""

    http_method_names = ["get", "post", "head", "options"]
    sync_path: str = ""
    action_label: str = ""
    sync_query_params: dict[str, Any] | None = None

    def get_required_permission(self) -> str:
        """Require ``change`` on ``FastAPIEndpoint`` (backend integration)."""
        return permission_change_fastapi_endpoint()

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """Trigger a backend sync GET and return JSON or redirect with flash messages."""
        return sync_response(
            request,
            path=self.sync_path,
            action_label=self.action_label,
            query_params=self.sync_query_params,
        )

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """Same behavior as GET (form posts from the plugin home)."""
        return self.get(request, *args, **kwargs)


class SyncDevicesView(_ProxboxSyncActionView):
    """POST/GET hook: sync Proxmox nodes into NetBox devices."""

    sync_path = "dcim/devices/create"
    action_label = "Devices"


class SyncVirtualMachinesView(_ProxboxSyncActionView):
    """POST/GET hook: sync Proxmox VMs into NetBox virtualization."""

    sync_path = "virtualization/virtual-machines/create"
    action_label = "Virtual machines"


class SyncFullUpdateView(_ProxboxSyncActionView):
    """POST/GET hook: run the full multi-stage ProxBox update."""

    sync_path = "full-update"
    action_label = "Full update"


class SyncVmBackupsView(_ProxboxSyncActionView):
    """POST/GET hook: sync VM backups from Proxmox."""

    sync_path = "virtualization/virtual-machines/backups/all/create"
    action_label = "VM backups"
    sync_query_params = {"delete_nonexistent_backup": True}


class SyncVirtualDisksView(_ProxboxSyncActionView):
    """POST/GET hook: sync virtual disk records for VMs."""

    sync_path = "virtualization/virtual-machines/virtual-disks/create"
    action_label = "Virtual disks"


class SyncVmSnapshotsView(_ProxboxSyncActionView):
    """POST/GET hook: sync VM snapshots from Proxmox."""

    sync_path = "virtualization/virtual-machines/snapshots/all/create"
    action_label = "VM snapshots"


class _ProxboxSyncStreamView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """SSE proxy; same permission as sync triggers."""

    http_method_names = ["get", "head", "options"]
    stream_path: str = ""
    stream_query_params: dict[str, Any] | None = None

    def get_required_permission(self) -> str:
        """Require ``change`` on ``FastAPIEndpoint`` (same as non-streaming sync)."""
        return permission_change_fastapi_endpoint()

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        """Proxy Server-Sent Events from proxbox-api for this sync path."""
        return sync_stream_response(
            request,
            path=self.stream_path,
            query_params=self.stream_query_params,
        )


class SyncDevicesStreamView(_ProxboxSyncStreamView):
    """SSE stream for device sync progress."""

    stream_path = "dcim/devices/create"


class SyncVirtualMachinesStreamView(_ProxboxSyncStreamView):
    """SSE stream for virtual machine sync progress."""

    stream_path = "virtualization/virtual-machines/create"


class SyncVmBackupsStreamView(_ProxboxSyncStreamView):
    """SSE stream for VM backup sync progress."""

    stream_path = "virtualization/virtual-machines/backups/all/create"
    stream_query_params = {"delete_nonexistent_backup": True}


class SyncVirtualDisksStreamView(_ProxboxSyncStreamView):
    """SSE stream for virtual disk sync progress."""

    stream_path = "virtualization/virtual-machines/virtual-disks/create"


class SyncVmSnapshotsStreamView(_ProxboxSyncStreamView):
    """SSE stream for VM snapshot sync progress."""

    stream_path = "virtualization/virtual-machines/snapshots/all/create"


class SyncFullUpdateStreamView(_ProxboxSyncStreamView):
    """SSE stream for full-update orchestration."""

    stream_path = "full-update"


sync_devices = SyncDevicesView.as_view()
sync_virtual_machines = SyncVirtualMachinesView.as_view()
sync_full_update = SyncFullUpdateView.as_view()
sync_vm_backups = SyncVmBackupsView.as_view()
sync_vm_snapshots = SyncVmSnapshotsView.as_view()
sync_virtual_disks = SyncVirtualDisksView.as_view()
sync_devices_stream = SyncDevicesStreamView.as_view()
sync_virtual_machines_stream = SyncVirtualMachinesStreamView.as_view()
sync_vm_backups_stream = SyncVmBackupsStreamView.as_view()
sync_vm_snapshots_stream = SyncVmSnapshotsStreamView.as_view()
sync_virtual_disks_stream = SyncVirtualDisksStreamView.as_view()
sync_full_update_stream = SyncFullUpdateStreamView.as_view()
