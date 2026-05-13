"""Shared template context for the Proxbox plugin home page."""

from __future__ import annotations

from importlib import util as importlib_util
from urllib.parse import urlencode

from core.choices import JobStatusChoices
from core.models import Job
from django.http import HttpRequest
from django.urls import NoReverseMatch, reverse

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

__all__ = ("build_home_dashboard_context", "pbs_integration_available")


def pbs_integration_available() -> bool:
    """Return ``True`` when the sibling ``netbox_pbs`` plugin is importable and
    its REST surface is mounted.

    Two gates: package importability (``find_spec``) plus REST URL resolution
    (``pbsendpoint-list``). Both must hold; otherwise the home page must not
    surface PBS markup.
    """
    if importlib_util.find_spec("netbox_pbs") is None:
        return False
    try:
        reverse("plugins:netbox_pbs-api:pbsendpoint-list")
    except NoReverseMatch:
        return False
    return True


def _build_add_url(view_name: str, params: dict[str, object]) -> str:
    """Return an endpoint add URL with query-string defaults."""
    query_params = {
        key: value for key, value in params.items() if value not in (None, "")
    }
    url = reverse(view_name)
    if not query_params:
        return url
    return f"{url}?{urlencode(query_params)}"


def _get_latest_active_proxbox_job(request: HttpRequest) -> Job | None:
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
    request: HttpRequest, quick_schedule_form: ScheduleSyncForm | None = None
) -> dict[str, object]:
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

    pbs_installed = pbs_integration_available()
    pbs_endpoint_list = None
    pbs_endpoint_add_url: str | None = None
    pbs_endpoint_bulk_import_url: str | None = None
    if pbs_installed:
        try:
            from netbox_pbs.models import PBSEndpoint  # noqa: PLC0415 — gated import

            pbs_qs = PBSEndpoint.objects.restrict(request.user, "view")
            pbs_endpoint_list = pbs_qs if pbs_qs.exists() else None
            pbs_endpoint_add_url = reverse("plugins:netbox_pbs:pbsendpoint_add")
            pbs_endpoint_bulk_import_url = reverse(
                "plugins:netbox_pbs:pbsendpoint_bulk_import"
            )
        except (ImportError, NoReverseMatch):
            pbs_installed = False
            pbs_endpoint_list = None
            pbs_endpoint_add_url = None
            pbs_endpoint_bulk_import_url = None

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
        "pbs_installed": pbs_installed,
        "pbs_endpoint_list": pbs_endpoint_list,
        "pbs_endpoint_add_url": pbs_endpoint_add_url,
        "pbs_endpoint_bulk_import_url": pbs_endpoint_bulk_import_url,
    }
