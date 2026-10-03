"""Secret-free review and protected approval of endpoint connection targets."""

from collections.abc import Mapping

from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from netbox_proxbox.sensitive_data import require_sensitive_data_access
from netbox_proxbox.services.connection_authority import (
    ConnectionAuthorityError,
    approve_connection_target,
    approved_connection_allows_secrets,
    connection_target_data,
    connection_target_fingerprint,
)


class ConnectionAuthorityViewSetMixin:
    """Expose approval independently of ordinary endpoint create/update fields."""

    @action(detail=True, methods=["get", "put"], url_path="connection-authority")
    def connection_authority(self, request: Request, pk: str | None = None) -> Response:
        """Review a target, then approve its exact fingerprint with an authorized actor."""
        if request.method == "PUT":
            require_sensitive_data_access(request.user)
        endpoint = self.get_object()
        try:
            if request.method == "PUT":
                if not isinstance(request.data, Mapping):
                    raise ValidationError("A target fingerprint object is required.")
                approve_connection_target(
                    endpoint,
                    user=request.user,
                    fingerprint=request.data.get("target_fingerprint"),
                )
            return Response(
                {
                    "target": connection_target_data(endpoint),
                    "target_fingerprint": connection_target_fingerprint(endpoint),
                    "approved": approved_connection_allows_secrets(endpoint),
                }
            )
        except (ValidationError, ConnectionAuthorityError):
            return Response(
                {
                    "detail": "The connection target is invalid or changed since review. Read and review the current target before approval."
                },
                status=status.HTTP_409_CONFLICT,
            )
