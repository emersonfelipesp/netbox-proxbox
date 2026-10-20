"""REST serializers for endpoint services and secret-free SSH metadata."""

from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers

from netbox_proxbox.models import ProxmoxEndpointService, ServiceSSHCredential


class ProxmoxEndpointServiceSerializer(NetBoxModelSerializer):
    """Full CRUD serializer for endpoint-owned application services."""

    class Meta:
        model = ProxmoxEndpointService
        fields = (
            "id",
            "url",
            "display",
            "endpoint",
            "name",
            "protocol",
            "ports",
            "ipaddresses",
            "description",
            "comments",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "protocol", "ports")

    def validate(self, data):
        """Pin the owning endpoint and require change access to it."""
        endpoint = data.get("endpoint")
        if self.instance is not None and endpoint is not None:
            if endpoint.pk != self.instance.endpoint_id:
                raise serializers.ValidationError(
                    {
                        "endpoint": "The owning endpoint of an application service cannot be changed."
                    }
                )
        if endpoint is None and self.instance is not None:
            # Partial updates omit the endpoint; authorize the stored owner.
            endpoint = self.instance.endpoint
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if endpoint is not None and user is not None:
            from netbox_proxbox.models import ProxmoxEndpoint

            allowed = ProxmoxEndpoint.objects.restrict(user, "change").filter(
                pk=endpoint.pk
            )
            if not allowed.exists():
                raise serializers.ValidationError(
                    {
                        "endpoint": "You do not have permission to change this Proxmox endpoint."
                    }
                )
        return super().validate(data)


class ServiceSSHCredentialSerializer(NetBoxModelSerializer):
    """Read-only metadata; ciphertext, UUIDs, and material are never serialized."""

    has_password = serializers.BooleanField(read_only=True)
    has_private_key = serializers.BooleanField(read_only=True)

    class Meta:
        model = ServiceSSHCredential
        fields = (
            "id",
            "url",
            "display",
            "service",
            "username",
            "auth_method",
            "storage_backend",
            "description",
            "has_password",
            "has_private_key",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        read_only_fields = fields
