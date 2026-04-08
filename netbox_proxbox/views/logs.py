"""Backend logs page view for viewing proxbox-api log buffer."""

from pathlib import PurePosixPath

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from netbox_proxbox.models import FastAPIEndpoint, ProxboxPluginSettings
from netbox_proxbox.utils import get_fastapi_url
from netbox_proxbox.views.proxbox_access import (
    permission_change_proxbox_plugin_settings,
)
from utilities.views import (
    ConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    TokenConditionalLoginRequiredMixin,
)

DEFAULT_BACKEND_LOG_FILE_PATH = "/var/log/proxbox.log"


def _validate_backend_log_file_path(
    raw_value: str | None,
) -> tuple[str | None, str | None]:
    """Return normalized log file path or validation error message."""
    path = (raw_value or "").strip()
    if not path:
        return None, "Backend log file path is required."
    if not PurePosixPath(path).is_absolute():
        return (
            None,
            "Backend log file path must be absolute (for example /var/log/proxbox.log).",
        )
    if path.endswith("/"):
        return (
            None,
            "Backend log file path must include a filename, not only a directory.",
        )
    return path, None


class BackendLogsView(ConditionalLoginRequiredMixin, View):
    """Display backend logs from the proxbox-api log buffer."""

    template_name = "netbox_proxbox/logs.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        """Render the logs page with FastAPI URL for JavaScript."""
        endpoint = FastAPIEndpoint.objects.restrict(request.user, "view").first()
        fastapi_info = get_fastapi_url(endpoint) if endpoint is not None else {}
        settings_obj = ProxboxPluginSettings.get_solo()

        fastapi_url = fastapi_info.get("http_url", "")
        return render(
            request,
            self.template_name,
            {
                "fastapi_url": fastapi_url,
                "fastapi_websocket_url": fastapi_info.get("websocket_url", ""),
                "logs_api_url": f"{fastapi_url}/admin/logs" if fastapi_url else "",
                "backend_log_file_path": settings_obj.backend_log_file_path
                or DEFAULT_BACKEND_LOG_FILE_PATH,
                "save_log_path_api_url": reverse(
                    "plugins:netbox_proxbox:backend_logs_path_update"
                ),
            },
        )


class BackendLogPathUpdateView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """Persist backend log file destination for proxbox-api."""

    http_method_names = ["post"]

    def get_required_permission(self) -> str:
        """Require Proxbox plugin settings change permission."""
        return permission_change_proxbox_plugin_settings()

    def post(self, request: HttpRequest) -> JsonResponse:
        """Validate and persist a new backend log file path."""
        cleaned_path, error = _validate_backend_log_file_path(
            request.POST.get("backend_log_file_path")
        )
        if error is not None or cleaned_path is None:
            return JsonResponse({"ok": False, "error": error}, status=400)

        settings_obj = ProxboxPluginSettings.get_solo()
        settings_obj.backend_log_file_path = cleaned_path
        settings_obj.save(update_fields=["backend_log_file_path"])
        return JsonResponse(
            {
                "ok": True,
                "backend_log_file_path": cleaned_path,
                "message": "Saved. Changes apply after proxbox-api restart.",
            }
        )
