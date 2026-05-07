"""REST shim that mirrors the HA UI views over JSON.

`HAClusterView` (`netbox_proxbox/views/ha.py`) and `ProxmoxVMHATabView`
(`netbox_proxbox/views/vm_ha.py`) render Django HTML pages by calling
proxbox-api 0.0.11+ at `/proxmox/cluster/ha/summary` and
`/proxmox/cluster/ha/resources/by-vm/{vmid}`. The frontend (and any other
JSON consumer routed through the existing nms-backend
`/netbox/netbox-proxbox/plugin/{path}` proxy) needs the same data without
parsing HTML, so we expose the two upstream calls as plain DRF
`APIView`s under `/api/plugins/proxbox/ha/`.

Any 404 from upstream is rebadged as 503 with the same hint the HTML
pages already render: "upgrade proxbox-api to v0.0.11 or later".
"""

from __future__ import annotations

import requests
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from netbox_proxbox.services._endpoint_errors import translate_request_exception
from netbox_proxbox.services.backend_context import get_fastapi_request_context

_BACKEND_NOT_CONFIGURED = "No FastAPI backend endpoint is configured."
_BACKEND_TOO_OLD = (
    "Backend does not support HA endpoints — upgrade proxbox-api to v0.0.11 or later."
)
_HA_REQUEST_TIMEOUT = 15


def _proxy_get(url: str, *, headers: dict, verify: bool, timeout: int) -> Response:
    """Forward a GET to proxbox-api and translate errors into DRF responses."""
    try:
        response = requests.get(url, headers=headers, timeout=timeout, verify=verify)
    except requests.exceptions.RequestException as exc:
        return Response(
            {"detail": translate_request_exception(exc)},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    if response.status_code == 404:
        return Response(
            {"detail": _BACKEND_TOO_OLD},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    if not response.ok:
        return Response(
            {"detail": f"Upstream HA call failed: {response.status_code}"},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    try:
        payload = response.json()
    except ValueError as exc:
        return Response(
            {"detail": f"Invalid HA payload from backend: {exc}"},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    return Response(payload)


class HAClusterSummaryAPIView(APIView):
    """API mirror of `/plugins/proxbox/ha/`.

    Proxies `GET {proxbox-api}/proxmox/cluster/ha/summary`. Permissions
    follow `_ProxboxDashboardPermission` (defined in
    `netbox_proxbox.api.views`) so the API and HTML pages gate on the
    same rule.
    """

    @property
    def permission_classes(self) -> list:
        from netbox_proxbox.api.views import _ProxboxDashboardPermission

        return [_ProxboxDashboardPermission]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request) -> Response:
        """Return aggregated cluster HA status, groups, and resources."""
        ctx = get_fastapi_request_context()
        if ctx is None or not ctx.http_url:
            return Response(
                {"detail": _BACKEND_NOT_CONFIGURED},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return _proxy_get(
            f"{ctx.http_url}/proxmox/cluster/ha/summary",
            headers=ctx.headers or {},
            verify=ctx.verify_ssl,
            timeout=_HA_REQUEST_TIMEOUT,
        )


class HAVMResourceAPIView(APIView):
    """API mirror of the per-VM HA tab.

    Proxies `GET {proxbox-api}/proxmox/cluster/ha/resources/by-vm/{vmid}`.
    Returns `{}` (HTTP 200) when the upstream returns ``null`` so the
    frontend can render an empty state without special-casing JSON null.
    """

    @property
    def permission_classes(self) -> list:
        from netbox_proxbox.api.views import _ProxboxDashboardPermission

        return [_ProxboxDashboardPermission]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request, vmid: int) -> Response:
        """Return the HA resource record for ``vmid`` or an empty object."""
        ctx = get_fastapi_request_context()
        if ctx is None or not ctx.http_url:
            return Response(
                {"detail": _BACKEND_NOT_CONFIGURED},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        proxied = _proxy_get(
            f"{ctx.http_url}/proxmox/cluster/ha/resources/by-vm/{vmid}",
            headers=ctx.headers or {},
            verify=ctx.verify_ssl,
            timeout=10,
        )
        if proxied.status_code == status.HTTP_200_OK and proxied.data is None:
            return Response({})
        return proxied
