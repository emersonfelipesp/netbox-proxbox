"""Shared template context for the Proxbox plugin home page."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from urllib.parse import urlencode

from core.choices import JobStatusChoices
from core.models import Job
from django.http import HttpRequest
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
from netbox_proxbox.tables import (
    FastAPIEndpointTable,
    NetBoxEndpointTable,
    ProxmoxEndpointTable,
)
from netbox_proxbox.utils import get_fastapi_url
from netbox_proxbox.views.proxbox_access import permission_enqueue_proxbox_sync

__all__ = ("build_companion_endpoint_groups", "build_home_dashboard_context")

logger = logging.getLogger(__name__)

_COMPANION_PLUGIN_REQUIREMENT = "netbox_proxbox"
_COMPANION_ENDPOINT_FIELD_LABELS = (
    ("host", "Host"),
    ("domain", "Domain"),
    ("ip_address", "IP Address"),
    ("port", "Port"),
    ("status", "Status"),
    ("version", "Version"),
    ("verify_ssl", "Verify SSL"),
    ("enabled", "Enabled"),
    ("last_seen_at", "Last seen"),
)
_SENSITIVE_COMPANION_FIELDS = {
    "api_key",
    "fingerprint",
    "key",
    "password",
    "proxbox_api_key",
    "secret",
    "token",
    "token_id",
    "token_name",
    "token_secret",
    "token_value",
}


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


# Every Proxbox sync job name contains this literal ("Proxbox Sync" or
# "Proxbox Sync: Virtual machine <id>"), so the core job list filtered by the
# ``q`` search (which matches ``name__icontains``) shows all Proxbox sync jobs.
_PROXBOX_SYNC_JOB_NAME_QUERY = "Proxbox Sync"


def _get_latest_proxbox_sync_jobs(request: HttpRequest, limit: int = 5) -> list[Job]:
    """Return up to ``limit`` newest visible Proxbox sync jobs (newest first)."""
    jobs = Job.objects.restrict(request.user, "view").order_by("-created")
    latest: list[Job] = []
    for job in jobs.iterator():
        if is_proxbox_sync_job(job):
            latest.append(job)
            if len(latest) >= limit:
                break
    return latest


def _proxbox_sync_jobs_list_url() -> str:
    """Return the core job list URL filtered to Proxbox sync jobs."""
    return (
        f"{reverse('core:job_list')}?{urlencode({'q': _PROXBOX_SYNC_JOB_NAME_QUERY})}"
    )


def _model_field_names(model: type[object]) -> set[str]:
    try:
        return {field.name for field in model._meta.get_fields()}
    except Exception:
        return set()


def _is_companion_plugin(app_config: object) -> bool:
    plugin_name = getattr(app_config, "name", "")
    required_plugins = getattr(app_config, "required_plugins", None) or ()
    return (
        plugin_name != _COMPANION_PLUGIN_REQUIREMENT
        and _COMPANION_PLUGIN_REQUIREMENT in required_plugins
    )


def _iter_installed_companion_plugins() -> Iterable[object]:
    try:
        from django.apps import apps
        from netbox.registry import registry
    except Exception:
        return ()

    plugin_names = registry.get("plugins", {}).get("installed", ()) or ()
    companion_plugins = []
    for plugin_name in plugin_names:
        try:
            app_config = apps.get_app_config(plugin_name)
        except Exception:
            logger.debug(
                "Unable to resolve installed plugin app config for %s",
                plugin_name,
                exc_info=True,
            )
            continue
        if _is_companion_plugin(app_config):
            companion_plugins.append(app_config)
    return companion_plugins


def _is_endpoint_like_model(model: type[object]) -> bool:
    model_name = model.__name__.lower()
    if "settings" in model_name:
        return False

    field_names = _model_field_names(model)
    has_host_field = bool({"domain", "host", "ip_address"} & field_names)
    has_http_shape = has_host_field and "port" in field_names
    name_suggests_endpoint = model_name.endswith(("endpoint", "server"))
    return has_http_shape and name_suggests_endpoint


def _iter_visible_model_objects(model: type[object], user: object) -> Iterable[object]:
    manager = getattr(model, "objects", None)
    if manager is None:
        return ()

    try:
        queryset = manager.restrict(user, "view")
    except AttributeError:
        all_objects = getattr(manager, "all", None)
        queryset = all_objects() if callable(all_objects) else manager
    except Exception:
        logger.debug(
            "Unable to restrict companion endpoint queryset for %s",
            getattr(model, "__name__", model),
            exc_info=True,
        )
        return ()

    ordering = getattr(getattr(model, "_meta", None), "ordering", ()) or ("pk",)
    try:
        queryset = queryset.order_by(*ordering)
    except Exception:
        pass

    try:
        if not queryset.exists():
            return ()
    except Exception:
        pass

    try:
        return list(queryset)
    except Exception:
        logger.debug(
            "Unable to evaluate companion endpoint queryset for %s",
            getattr(model, "__name__", model),
            exc_info=True,
        )
        return ()


def _object_url(obj: object, request: HttpRequest, *, absolute_urls: bool) -> str:
    get_absolute_url = getattr(obj, "get_absolute_url", None)
    if not callable(get_absolute_url):
        return ""
    try:
        url = get_absolute_url()
    except Exception:
        return ""
    if not absolute_urls:
        return url
    try:
        return request.build_absolute_uri(url)
    except Exception:
        return url


def _field_display_value(obj: object, field_name: str) -> str:
    display_method = getattr(obj, f"get_{field_name}_display", None)
    if callable(display_method):
        try:
            value = display_method()
        except Exception:
            value = getattr(obj, field_name, None)
    else:
        value = getattr(obj, field_name, None)

    if value in (None, ""):
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return str(value)


def _companion_endpoint_status_service(obj: object) -> str:
    model_meta = getattr(obj.__class__, "_meta", None)
    app_label = getattr(model_meta, "app_label", "")
    model_name = getattr(model_meta, "model_name", "")
    class_name = obj.__class__.__name__
    if (
        app_label == "netbox_pbs"
        and model_name == "pbsserver"
        and class_name == "PBSServer"
    ):
        return "pbs"
    return ""


def _companion_endpoint_connection_status(obj: object) -> dict[str, object] | None:
    service = _companion_endpoint_status_service(obj)
    endpoint_id = getattr(obj, "pk", getattr(obj, "id", None))
    if not service or endpoint_id is None:
        return None
    return {
        "label": "Connection Status",
        "service": service,
        "badge_id": f"{service}-status-badge-{endpoint_id}",
        "message_id": f"{service}-connection-error-{endpoint_id}",
        "url": reverse(
            "plugins:netbox_proxbox:keepalive_status",
            args=[service, endpoint_id],
        ),
    }


def _serialize_companion_endpoint(
    obj: object, request: HttpRequest, *, absolute_urls: bool
) -> dict[str, object]:
    field_names = _model_field_names(obj.__class__)
    fields = []
    for field_name, label in _COMPANION_ENDPOINT_FIELD_LABELS:
        if field_name not in field_names or field_name in _SENSITIVE_COMPANION_FIELDS:
            continue
        value = _field_display_value(obj, field_name)
        if value:
            fields.append({"name": field_name, "label": label, "value": value})

    return {
        "id": getattr(obj, "pk", getattr(obj, "id", None)),
        "name": str(obj),
        "url": _object_url(obj, request, absolute_urls=absolute_urls),
        "fields": fields,
        "connection_status": _companion_endpoint_connection_status(obj),
    }


def build_companion_endpoint_groups(
    request: HttpRequest, *, absolute_urls: bool = False
) -> list[dict[str, object]]:
    """
    Return endpoint rows owned by installed Proxbox companion plugins.

    This mirrors NetBox's installed-plugins API source server-side so the home
    page can remain useful to non-superusers; the API itself is superuser-only.
    """
    groups = []
    user = getattr(request, "user", None)

    for app_config in _iter_installed_companion_plugins():
        try:
            models = app_config.get_models()
        except Exception:
            logger.debug(
                "Unable to enumerate models for companion plugin %s",
                getattr(app_config, "name", app_config),
                exc_info=True,
            )
            continue

        for model in models:
            if not _is_endpoint_like_model(model):
                continue
            objects = list(_iter_visible_model_objects(model, user))
            if not objects:
                continue

            model_meta = getattr(model, "_meta", None)
            groups.append(
                {
                    "plugin_name": str(
                        getattr(app_config, "verbose_name", "")
                        or getattr(app_config, "name", "")
                    ),
                    "plugin_package": getattr(app_config, "name", ""),
                    "plugin_version": getattr(app_config, "version", ""),
                    "plugin_base_url": getattr(
                        app_config, "base_url", getattr(app_config, "label", "")
                    ),
                    "model_name": getattr(model, "__name__", ""),
                    "model_label": str(
                        getattr(model_meta, "verbose_name", None)
                        or getattr(model, "__name__", "Endpoint")
                    ),
                    "model_label_plural": str(
                        getattr(model_meta, "verbose_name_plural", None)
                        or getattr(model, "__name__", "Endpoints")
                    ),
                    "endpoints": [
                        _serialize_companion_endpoint(
                            obj, request, absolute_urls=absolute_urls
                        )
                        for obj in objects
                    ],
                }
            )

    return groups


def _build_pdm_endpoint_context(request: HttpRequest) -> dict[str, object]:
    """
    Return PDM endpoint table and list URL when netbox-pdm is installed.

    ``PDMEndpoint`` is defined in ``netbox_proxbox`` (so it's always available),
    but the companion ``netbox-pdm`` plugin owns the table class and the UI
    routes for it. This helper gates display on whether that plugin is present.
    Returns an empty dict when ``netbox-pdm`` is not installed.
    """
    try:
        from netbox_pdm.tables import PDMEndpointTable as _PDMEndpointTable  # type: ignore[import]
    except ImportError:
        return {}

    try:
        from netbox_proxbox.models import PDMEndpoint as _PDMEndpoint
    except ImportError:
        return {}

    pdm_qs = _PDMEndpoint.objects.restrict(request.user, "view")
    pdm_table = _PDMEndpointTable(pdm_qs)
    pdm_table.configure(request)

    try:
        pdm_list_url = reverse("plugins:netbox_proxbox:pdmendpoint_list")
    except Exception:
        pdm_list_url = ""

    return {
        "pdm_endpoint_table": pdm_table,
        "pdm_endpoint_list": pdm_qs if pdm_qs.exists() else None,
        "pdm_list_url": pdm_list_url,
    }


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

    proxmox_endpoint_table = ProxmoxEndpointTable(proxmox_endpoint_obj)
    proxmox_endpoint_table.configure(request)

    netbox_endpoint_table = NetBoxEndpointTable(netbox_endpoint_obj)
    netbox_endpoint_table.configure(request)

    fastapi_endpoint_table = FastAPIEndpointTable(fastapi_endpoint_obj)
    fastapi_endpoint_table.configure(request)

    context: dict[str, object] = {
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
        "proxmox_endpoint_table": proxmox_endpoint_table,
        "netbox_endpoint_table": netbox_endpoint_table,
        "fastapi_endpoint_table": fastapi_endpoint_table,
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
        "companion_endpoint_groups": build_companion_endpoint_groups(request),
        "latest_sync_jobs": _get_latest_proxbox_sync_jobs(request),
        "sync_jobs_list_url": _proxbox_sync_jobs_list_url(),
    }
    context.update(_build_pdm_endpoint_context(request))
    return context
