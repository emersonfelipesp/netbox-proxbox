"""Superuser-only grant administration and secret-free caller readiness."""

from netbox.api.serializers import NetBoxModelSerializer
from netbox.api.viewsets import NetBoxModelViewSet
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from netbox_proxbox.models import ProxboxSensitiveDataAccess
from netbox_proxbox.sensitive_data import (
    can_access_sensitive_data,
    is_active_superuser,
)


class ActiveSuperuserPermission(BasePermission):
    """Model, group, staff, and token permissions never authorize grant changes."""

    def has_permission(self, request: Request, view: object) -> bool:
        return is_active_superuser(request.user)


class SensitiveDataAccessSerializer(NetBoxModelSerializer):
    """Serialize grants without exposing any credential material."""

    class Meta:
        model = ProxboxSensitiveDataAccess
        fields = ("id", "user", "can_access_sensitive_data", "created", "last_updated")
        read_only_fields = ("id", "created", "last_updated")


class SensitiveDataAccessViewSet(NetBoxModelViewSet):
    """Grant CRUD is exclusive to active superusers, including bulk requests."""

    queryset = ProxboxSensitiveDataAccess.objects.all()
    serializer_class = SensitiveDataAccessSerializer
    permission_classes = (
        ActiveSuperuserPermission,
        *NetBoxModelViewSet.permission_classes,
    )


class SensitiveDataReadinessView(APIView):
    """Report only the caller's current sensitive-access decision, never secrets."""

    permission_classes = (IsAuthenticated,)

    def get(self, request: Request) -> Response:
        response = Response(
            {
                "schema_version": 1,
                "can_access_sensitive_data": can_access_sensitive_data(request.user),
            }
        )
        response["Cache-Control"] = "no-store"
        return response
