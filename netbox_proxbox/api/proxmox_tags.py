"""REST endpoints for mutating live Proxmox config tags on inventoried VMs."""

from __future__ import annotations

import uuid
from typing import Any, Literal

import requests
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from virtualization.models import VirtualMachine

from netbox_proxbox.services._endpoint_errors import translate_request_exception
from netbox_proxbox.services.backend_context import get_fastapi_request_context
from netbox_proxbox.utils import resolve_vm_type
from netbox_proxbox.views.operational import (
    _current_node_name,
    resolve_vm_endpoint_context,
)
from netbox_proxbox.views.proxbox_access import permission_run_proxmox_action

_BACKEND_TIMEOUT_S = 30
VmKind = Literal["qemu", "lxc"]


def _actor_from_request(request: Request) -> str:
    user = getattr(request, "user", None)
    get_username = getattr(user, "get_username", None)
    if callable(get_username):
        return str(get_username())
    return str(getattr(user, "username", "") or getattr(user, "pk", "") or "netbox")


def _vm_for_tags_request(
    request: Request,
    *,
    pk: int | str,
    expected_kind: VmKind,
) -> VirtualMachine | Response:
    try:
        vm = (
            VirtualMachine.objects.restrict(request.user, "view")
            .select_related("cluster", "device")
            .get(pk=pk)
        )
    except VirtualMachine.DoesNotExist:
        return Response(
            {"detail": "Virtual machine not found."}, status=status.HTTP_404_NOT_FOUND
        )

    if resolve_vm_type(vm) != expected_kind:
        return Response(
            {
                "status": "error",
                "reason": "vm_type_mismatch",
                "detail": (
                    f"Instance {pk} is not a {expected_kind} container; "
                    f"use the matching proxmox-tags endpoint."
                ),
            },
            status=status.HTTP_404_NOT_FOUND,
        )
    return vm


def _resolve_tags_context(vm: VirtualMachine) -> tuple[int, int, str, str] | Response:
    resolved = resolve_vm_endpoint_context(vm)
    if resolved is None:
        return Response(
            {
                "status": "error",
                "reason": "vm_not_addressable",
                "detail": (
                    "VM is not linked to a Proxmox endpoint or is missing proxmox_vm_id metadata."
                ),
            },
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    endpoint_id, vmid, vm_type = resolved
    node = _current_node_name(vm).strip()
    if not node:
        return Response(
            {
                "status": "error",
                "reason": "node_unresolved",
                "detail": "Could not resolve the Proxmox node name for this VM.",
            },
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    return endpoint_id, vmid, vm_type, node


def _forward_tags_request(
    request: Request,
    *,
    vm: VirtualMachine,
    method: str,
    payload: dict[str, Any],
) -> Response:
    if not request.user.has_perm(permission_run_proxmox_action()):
        return Response(
            {
                "status": "error",
                "reason": "permission_denied",
                "detail": "Missing core.run_proxmox_action permission.",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    ctx_result = _resolve_tags_context(vm)
    if isinstance(ctx_result, Response):
        return ctx_result
    endpoint_id, vmid, vm_type, node = ctx_result

    ctx = get_fastapi_request_context()
    if ctx is None or not ctx.http_url:
        return Response(
            {"detail": "No FastAPI backend endpoint is configured."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    body = {"node": node, **payload}
    url = f"{ctx.http_url.rstrip('/')}/proxmox/{vm_type}/{vmid}/tags"
    headers = dict(ctx.headers or {})
    headers.setdefault("Content-Type", "application/json")
    headers["X-Proxbox-Actor"] = _actor_from_request(request)
    headers["Idempotency-Key"] = str(uuid.uuid4())

    try:
        response = requests.request(
            method,
            url,
            params={"endpoint_id": endpoint_id},
            json=body,
            headers=headers,
            timeout=_BACKEND_TIMEOUT_S,
            verify=ctx.verify_ssl,
            allow_redirects=False,
        )
    except requests.exceptions.RequestException as exc:
        return Response(
            {"detail": translate_request_exception(exc)},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    try:
        upstream = response.json()
    except ValueError:
        upstream = {"detail": response.text[:500] or f"HTTP {response.status_code}"}

    if not response.ok:
        detail = upstream if isinstance(upstream, dict) else {"detail": str(upstream)}
        return Response(detail, status=response.status_code)

    if not isinstance(upstream, dict):
        return Response(
            {"detail": "Invalid tag mutation payload from backend."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    return Response(
        {
            "ok": True,
            "vmid": upstream.get("vmid", vmid),
            "vm_type": upstream.get("vm_type", vm_type),
            "endpoint_id": upstream.get("endpoint_id", endpoint_id),
            "node": upstream.get("node", node),
            "tags_after": upstream.get("tags_after", []),
        },
        status=status.HTTP_200_OK,
    )


class _VirtualMachineProxmoxTagsBase(APIView):
    expected_kind: VmKind = "qemu"

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def put(self, request: Request, pk: int | str) -> Response:
        vm_or_response = _vm_for_tags_request(
            request, pk=pk, expected_kind=self.expected_kind
        )
        if isinstance(vm_or_response, Response):
            return vm_or_response
        tags = request.data.get("tags") if isinstance(request.data, dict) else None
        if not isinstance(tags, list):
            return Response(
                {
                    "status": "error",
                    "reason": "invalid_payload",
                    "detail": "Request body must include a tags list.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return _forward_tags_request(
            request,
            vm=vm_or_response,
            method="PUT",
            payload={"tags": tags},
        )

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def patch(self, request: Request, pk: int | str) -> Response:
        vm_or_response = _vm_for_tags_request(
            request, pk=pk, expected_kind=self.expected_kind
        )
        if isinstance(vm_or_response, Response):
            return vm_or_response
        data = request.data if isinstance(request.data, dict) else {}
        add = data.get("add")
        remove = data.get("remove")
        if add is None and remove is None:
            return Response(
                {
                    "status": "error",
                    "reason": "invalid_payload",
                    "detail": "Request body must include add and/or remove tag lists.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        payload: dict[str, Any] = {}
        if isinstance(add, list):
            payload["add"] = add
        if isinstance(remove, list):
            payload["remove"] = remove
        return _forward_tags_request(
            request,
            vm=vm_or_response,
            method="PATCH",
            payload=payload,
        )


class VirtualMachineProxmoxTagsAPIView(_VirtualMachineProxmoxTagsBase):
    """Replace or merge Proxmox config tags for a QEMU virtual machine."""

    expected_kind = "qemu"


class LXCContainerProxmoxTagsAPIView(_VirtualMachineProxmoxTagsBase):
    """Replace or merge Proxmox config tags for an LXC container."""

    expected_kind = "lxc"
