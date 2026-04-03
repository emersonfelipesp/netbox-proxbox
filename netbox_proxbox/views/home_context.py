"""Shared template context for the Proxbox plugin home page."""

from __future__ import annotations

from urllib.parse import urlencode

from core.choices import JobStatusChoices
from core.models import Job
from django.urls import reverse

from netbox_proxbox import ProxboxConfig
from netbox_proxbox.choices import NetBoxTokenVersionChoices
from netbox_proxbox.jobs import is_proxbox_sync_job
from netbox_proxbox.forms.schedule_sync import ScheduleSyncForm
from netbox_proxbox.models import FastAPIEndpoint, NetBoxEndpoint, ProxmoxEndpoint
from netbox_proxbox.schedule_hints import (
    has_recurring_proxbox_sync_all,
    quick_schedule_home_form_kwargs,
)
from netbox_proxbox.utils import get_fastapi_url
from netbox_proxbox.views.proxbox_access import permission_enqueue_proxbox_sync

__all__ = ("build_home_dashboard_context",)


def _build_add_url(view_name: str, params: dict[str, object]) -> str:
    """Return an endpoint add URL with query-string defaults."""
    query_params = {
        key: value for key, value in params.items() if value not in (None, "")
    }
    url = reverse(view_name)
    if not query_params:
        return url
    return f"{url}?{urlencode(query_params)}"


def _get_latest_active_proxbox_job(request):
    """Return the newest visible Proxbox sync job that is still running or queued."""
    jobs = (
        Job.objects.restrict(request.user, "view")
        .filter(status__in=JobStatusChoices.ENQUEUED_STATE_CHOICES)
        .order_by("-created")
    )
    for job in jobs:
        if is_proxbox_sync_job(job):
            return job
    return None


def build_home_dashboard_context(
    request, quick_schedule_form: ScheduleSyncForm | None = None
):
    """
    Build the context dict for ``home.html`` (endpoint lists, URLs, quick schedule card).
    """
    default_config = getattr(ProxboxConfig, "default_settings", {})
    fastapi_example_url = "https://example.fastapi.com"
    fastapi_example_websocket_url = "wss://example.fastapi.com/ws"

    proxmox_endpoint_obj = ProxmoxEndpoint.objects.restrict(request.user, "view")
    netbox_endpoint_obj = NetBoxEndpoint.objects.restrict(request.user, "view")
    fastapi_endpoint_obj = FastAPIEndpoint.objects.restrict(request.user, "view")

    netbox_quick_add_url = _build_add_url(
        "plugins:netbox_proxbox:netboxendpoint_add",
        {
            "domain": "localhost",
            "ip_address": "127.0.0.1/32",
            "token_version": NetBoxTokenVersionChoices.V1,
        },
    )
    fastapi_quick_add_url = _build_add_url(
        "plugins:netbox_proxbox:fastapiendpoint_add",
        {
            "domain": "localhost",
            "ip_address": "127.0.0.1/32",
        },
    )

    fastapi_info = {}
    if fastapi_endpoint_obj.exists():
        fastapi_info = get_fastapi_url(fastapi_endpoint_obj.first()) or {}
        if not isinstance(fastapi_info, dict):
            fastapi_info = {}

    show_quick_full_sync_banner = not has_recurring_proxbox_sync_all(request.user)
    can_quick_schedule_sync = show_quick_full_sync_banner and request.user.has_perm(
        permission_enqueue_proxbox_sync()
    )
    if can_quick_schedule_sync:
        if quick_schedule_form is None:
            quick_schedule_form = ScheduleSyncForm(**quick_schedule_home_form_kwargs())
    else:
        quick_schedule_form = None

    active_proxbox_job = _get_latest_active_proxbox_job(request)

    return {
        "default_config": default_config,
        "proxmox_endpoint_list": proxmox_endpoint_obj
        if proxmox_endpoint_obj.exists()
        else None,
        "netbox_endpoint_list": netbox_endpoint_obj
        if netbox_endpoint_obj.exists()
        else None,
        "fastapi_endpoint_list": fastapi_endpoint_obj
        if fastapi_endpoint_obj.exists()
        else None,
        "netbox_quick_add_url": netbox_quick_add_url,
        "fastapi_quick_add_url": fastapi_quick_add_url,
        "fastapi_url": fastapi_info.get("http_url", fastapi_example_url),
        "fastapi_websocket_url": fastapi_info.get(
            "websocket_url", fastapi_example_websocket_url
        ),
        "show_quick_full_sync_banner": show_quick_full_sync_banner,
        "can_quick_schedule_sync": can_quick_schedule_sync,
        "quick_schedule_form": quick_schedule_form,
        "active_proxbox_job": active_proxbox_job,
    }
