"""Build dashboard card payloads from Proxmox and backend API responses."""

from __future__ import annotations

import logging
from collections.abc import Sequence

import requests
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views import View

from netbox_proxbox.models import FastAPIEndpoint, ProxmoxEndpoint
from netbox_proxbox.utils import (
    get_backend_auth_headers,
    get_fastapi_url,
    get_ip_address_host,
)
from netbox_proxbox.views.backend_sync import (
    resolve_backend_endpoint_id,
    sync_proxmox_endpoint_to_backend,
)
from netbox_proxbox.views.error_utils import (
    extract_proxmox_backend_error_detail,
    parse_requests_response_json,
)
from utilities.permissions import get_permission_for_model
from utilities.views import (
    ContentTypePermissionRequiredMixin,
    TokenConditionalLoginRequiredMixin,
)


logger = logging.getLogger(__name__)


def _merge_cluster_payloads(
    version_payload: object, cluster_payload: object
) -> dict[str, object]:
    """Combine proxbox-api version and cluster session responses for the home card."""
    version_data: dict[str, object] = {}
    cluster_data: dict[str, object] = {}

    if isinstance(version_payload, Sequence) and version_payload:
        for _, value in version_payload[0].items():
            version_data = value
            break

    if isinstance(cluster_payload, Sequence) and cluster_payload:
        cluster_data = cluster_payload[0]

    if isinstance(cluster_data, dict) and isinstance(version_data, dict):
        return cluster_data | version_data
    return {}


class ProxboxProxmoxCardView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """JSON card for one Proxmox endpoint; requires view on ProxmoxEndpoint (and object-level via restrict)."""

    http_method_names = ["get", "head", "options"]

    def get_required_permission(self) -> str:
        """Require model-level view permission on ``ProxmoxEndpoint``."""
        return get_permission_for_model(ProxmoxEndpoint, "view")

    def get(
        self,
        request: HttpRequest,
        pk: int,
        *args: object,
        **kwargs: object,
    ) -> JsonResponse:
        """Fetch version/cluster JSON from proxbox-api after syncing the endpoint row."""
        proxmox_object = get_object_or_404(
            ProxmoxEndpoint.objects.restrict(request.user, "view"),
            pk=pk,
        )
        if not bool(getattr(proxmox_object, "enabled", True)):
            return JsonResponse(
                {
                    "cluster_data": {},
                    "object": {
                        "pk": getattr(
                            proxmox_object,
                            "pk",
                            getattr(proxmox_object, "id", None),
                        ),
                        "name": proxmox_object.name,
                        "domain": proxmox_object.domain,
                        "ip_address": str(proxmox_object.ip_address)
                        if proxmox_object.ip_address
                        else None,
                    },
                    "detail": "Proxmox endpoint is disabled; skipping status check.",
                }
            )

        fastapi_object = (
            FastAPIEndpoint.objects.restrict(request.user, "view")
            .filter(enabled=True)
            .first()
        )
        if fastapi_object is None:
            return JsonResponse(
                {
                    "cluster_data": {},
                    "object": {"name": proxmox_object.name, "pk": proxmox_object.pk},
                }
            )

        fastapi_info = get_fastapi_url(fastapi_object) or {}
        if not isinstance(fastapi_info, dict):
            fastapi_info = {}
        fastapi_url = fastapi_info.get("http_url")
        if not fastapi_url:
            return JsonResponse(
                {
                    "cluster_data": {},
                    "detail": "No FastAPI backend URL is configured.",
                    "object": {"name": proxmox_object.name, "pk": proxmox_object.pk},
                }
            )

        backend_headers = get_backend_auth_headers(fastapi_object)
        backend_verify_ssl = bool(fastapi_info.get("verify_ssl", True))

        domain = (proxmox_object.domain or "").strip()
        ip_address = get_ip_address_host(proxmox_object.ip_address)
        proxmox_host = domain or ip_address

        version_endpoint = f"{fastapi_url}/proxmox/version"
        cluster_endpoint = f"{fastapi_url}/proxmox/sessions"

        version_data = []
        cluster_data = []
        detail = None
        http_status = None

        sync_ok, sync_detail, sync_http_status = sync_proxmox_endpoint_to_backend(
            proxmox_object,
            base_url=fastapi_url,
            auth_headers=backend_headers,
            backend_verify_ssl=backend_verify_ssl,
            timeout=5,
        )
        if not sync_ok:
            payload = {
                "cluster_data": {},
                "object": {
                    "pk": getattr(
                        proxmox_object, "pk", getattr(proxmox_object, "id", None)
                    ),
                    "name": proxmox_object.name,
                    "domain": proxmox_object.domain,
                    "ip_address": str(proxmox_object.ip_address)
                    if proxmox_object.ip_address
                    else None,
                },
                "detail": sync_detail,
            }
            if sync_http_status is not None:
                payload["http_status"] = sync_http_status
            return JsonResponse(payload)

        backend_endpoint_id, resolve_error = resolve_backend_endpoint_id(
            proxmox_object,
            base_url=fastapi_url,
            auth_headers=backend_headers,
            backend_verify_ssl=backend_verify_ssl,
            timeout=5,
        )
        if backend_endpoint_id is None:
            return JsonResponse(
                {
                    "cluster_data": {},
                    "object": {
                        "pk": getattr(
                            proxmox_object,
                            "pk",
                            getattr(proxmox_object, "id", None),
                        ),
                        "name": proxmox_object.name,
                        "domain": proxmox_object.domain,
                        "ip_address": str(proxmox_object.ip_address)
                        if proxmox_object.ip_address
                        else None,
                    },
                    "detail": resolve_error
                    or "Failed to resolve Proxmox endpoint on ProxBox backend.",
                }
            )

        query_params = {
            "source": "database",
            "proxmox_endpoint_ids": str(backend_endpoint_id),
        }

        try:
            version_response = requests.get(
                version_endpoint,
                params=query_params,
                headers=backend_headers,
                verify=backend_verify_ssl,
                timeout=5,
            )
            cluster_response = requests.get(
                cluster_endpoint,
                params=query_params,
                headers=backend_headers,
                verify=backend_verify_ssl,
                timeout=5,
            )
            version_response.raise_for_status()
            cluster_response.raise_for_status()
            version_parsed, ver_err = parse_requests_response_json(
                version_response, log_label="proxmox/version"
            )
            cluster_parsed, cl_err = parse_requests_response_json(
                cluster_response, log_label="proxmox/sessions"
            )
            if ver_err or cl_err:
                detail = ver_err or cl_err
                http_status = 502
                logger.error(
                    "Unable to hydrate Proxmox card for endpoint %s: %s", pk, detail
                )
            else:
                version_data = version_parsed if version_parsed is not None else []
                cluster_data = cluster_parsed if cluster_parsed is not None else []
        except requests.exceptions.RequestException as exc:
            failed_endpoint = version_endpoint
            response = getattr(exc, "response", None)
            if response is not None:
                response_url = getattr(response, "url", "") or ""
                if "/proxmox/sessions" in response_url:
                    failed_endpoint = cluster_endpoint
                elif "/proxmox/version" in response_url:
                    failed_endpoint = version_endpoint
            elif "/proxmox/sessions" in str(exc):
                failed_endpoint = cluster_endpoint
            detail, http_status = extract_proxmox_backend_error_detail(
                exc,
                proxmox_host=proxmox_host,
                proxmox_port=proxmox_object.port,
                backend_url=failed_endpoint,
            )
            # The redacted detail, not the raw exception — a transport error can
            # echo request content, and this handler runs on every dashboard
            # card refresh.
            logger.error(
                "Unable to hydrate Proxmox card for endpoint %s: %s", pk, detail
            )

        payload: dict[str, object] = {
            "cluster_data": _merge_cluster_payloads(version_data, cluster_data),
            "object": {
                "pk": getattr(
                    proxmox_object, "pk", getattr(proxmox_object, "id", None)
                ),
                "name": proxmox_object.name,
                "domain": proxmox_object.domain,
                "ip_address": str(proxmox_object.ip_address)
                if proxmox_object.ip_address
                else None,
            },
        }
        if detail:
            payload["detail"] = detail
        if http_status is not None:
            payload["http_status"] = http_status

        return JsonResponse(payload)


get_proxmox_card = ProxboxProxmoxCardView.as_view()
