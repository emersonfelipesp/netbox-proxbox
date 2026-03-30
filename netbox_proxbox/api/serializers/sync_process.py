"""API serializer for sync process tracking rows."""

from __future__ import annotations

from netbox.api.fields import ChoiceField
from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers

from netbox_proxbox.choices import SyncStatusChoices, SyncTypeChoices
from netbox_proxbox.models import SyncProcess


class SyncProcessSerializer(NetBoxModelSerializer):
    """Sync job metadata exposed on the plugin REST API."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:syncprocess-detail",
    )
    sync_type = ChoiceField(choices=SyncTypeChoices)
    status = ChoiceField(choices=SyncStatusChoices)
    runtime = serializers.FloatField(required=False, allow_null=True)
    started_at = serializers.DateTimeField(required=False, allow_null=True)
    completed_at = serializers.DateTimeField(required=False, allow_null=True)

    class Meta:
        model = SyncProcess
        fields = (
            "id",
            "url",
            "display",
            "name",
            "sync_type",
            "status",
            "started_at",
            "completed_at",
            "runtime",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "status")
