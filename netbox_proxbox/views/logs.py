"""Backend logs page view for viewing proxbox-api log buffer."""

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views import View

from netbox_proxbox.models import FastAPIEndpoint
from netbox_proxbox.utils import get_fastapi_url
from utilities.views import ConditionalLoginRequiredMixin


class BackendLogsView(ConditionalLoginRequiredMixin, View):
    """Display backend logs from the proxbox-api log buffer."""

    template_name = "netbox_proxbox/logs.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        """Render the logs page with FastAPI URL for JavaScript."""
        fastapi_endpoint = FastAPIEndpoint.objects.restrict(
            request.user, "view"
        ).first()

        fastapi_info = {}
        if fastapi_endpoint:
            fastapi_info = get_fastapi_url(fastapi_endpoint) or {}

        fastapi_url = fastapi_info.get("http_url", "")
        return render(
            request,
            self.template_name,
            {
                "fastapi_url": fastapi_url,
                "fastapi_websocket_url": fastapi_info.get("websocket_url", ""),
                "logs_api_url": f"{fastapi_url}/admin/logs" if fastapi_url else "",
            },
        )
