"""API serializer for plugin-owned branch intent safety gates."""

from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers

from netbox_proxbox.models import ProxboxBranchIntent
from netbox_proxbox.services.branch_intent import resolve_branch_reference


class ProxboxBranchIntentSerializer(NetBoxModelSerializer):
    """Validate the soft reference while exposing explicit boolean gates."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxboxbranchintent-detail"
    )

    def validate(self, attrs):
        """Require a live branch and keep an existing reference immutable."""
        attrs = super().validate(attrs)
        branch_id = attrs.get(
            "branch_id",
            getattr(self.instance, "branch_id", None),
        )
        branch_schema_id = attrs.get(
            "branch_schema_id",
            getattr(self.instance, "branch_schema_id", None),
        )
        if self.instance is not None and (
            branch_id != getattr(self.instance, "branch_id", None)
            or branch_schema_id != getattr(self.instance, "branch_schema_id", None)
        ):
            raise serializers.ValidationError(
                "The branch reference for an existing Proxbox branch intent "
                "cannot be changed."
            )
        if resolve_branch_reference(branch_id, branch_schema_id) is None:
            raise serializers.ValidationError(
                "The referenced netbox-branching branch is unavailable."
            )
        return attrs

    class Meta:
        model = ProxboxBranchIntent
        fields = (
            "id",
            "url",
            "display",
            "branch_id",
            "branch_schema_id",
            "apply_to_proxmox",
            "apply_destroy_confirmed",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = (
            "id",
            "url",
            "display",
            "branch_id",
            "branch_schema_id",
        )
