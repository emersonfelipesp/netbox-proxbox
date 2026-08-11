"""Lightweight serializers for non-model API views (resource lists, schedule sync, etc.)."""

from __future__ import annotations

from rest_framework import serializers

from netbox_proxbox.choices import ScheduleIntervalUnitChoices, SyncTypeChoices


class NestedObjectSerializer(serializers.Serializer):
    """Minimal nested representation for any FK with id/name/url."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    url = serializers.URLField()


class InterfaceItemSerializer(serializers.Serializer):
    """Single interface item in node/VM resource responses."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    enabled = serializers.BooleanField()
    ip_addresses = serializers.ListField(child=serializers.CharField())


class DeviceResourceSerializer(serializers.Serializer):
    """Proxbox-tagged Device row returned by the /api/plugins/proxbox/resources/nodes/ endpoint."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    url = serializers.URLField()
    device_type = serializers.CharField(allow_null=True)
    manufacturer = serializers.CharField(allow_null=True)
    role = NestedObjectSerializer(allow_null=True)
    site = NestedObjectSerializer(allow_null=True)
    tenant = NestedObjectSerializer(allow_null=True)
    cluster = NestedObjectSerializer(allow_null=True)
    interfaces = InterfaceItemSerializer(many=True)


class VirtualMachineResourceSerializer(serializers.Serializer):
    """Proxbox-tagged VirtualMachine row for the /resources/virtual-machines/ and /resources/lxc-containers/ endpoints."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    url = serializers.URLField()
    site = NestedObjectSerializer(allow_null=True)
    cluster = NestedObjectSerializer(allow_null=True)
    role = NestedObjectSerializer(allow_null=True)
    tenant = NestedObjectSerializer(allow_null=True)
    platform = NestedObjectSerializer(allow_null=True)
    interfaces = InterfaceItemSerializer(many=True)


class InterfaceResourceSerializer(serializers.Serializer):
    """Single interface in the /resources/interfaces/ response."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    enabled = serializers.BooleanField()
    parent_type = serializers.ChoiceField(choices=["device", "vm"])
    parent_name = serializers.CharField()
    ip_addresses = serializers.ListField(child=serializers.CharField())


class IPAddressResourceSerializer(serializers.Serializer):
    """Single IP address in the /resources/ip-addresses/ response."""

    id = serializers.IntegerField()
    address = serializers.CharField()
    assigned_object_type = serializers.CharField(allow_null=True)
    assigned_object_id = serializers.IntegerField(allow_null=True)
    assigned_object_name = serializers.CharField(allow_null=True)


class VirtualDiskResourceSerializer(serializers.Serializer):
    """Single virtual disk in the /resources/virtual-disks/ response."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    size = serializers.IntegerField(allow_null=True)
    virtual_machine = NestedObjectSerializer()


class ScheduledJobSerializer(serializers.Serializer):
    """Scheduled Proxbox sync job row returned by GET /api/plugins/proxbox/sync/schedule/."""

    id = serializers.IntegerField()
    pk = serializers.IntegerField()
    name = serializers.CharField(allow_null=True)
    sync_types = serializers.ListField(child=serializers.CharField())
    schedule = serializers.DateTimeField(allow_null=True)
    interval = serializers.IntegerField(allow_null=True)
    status = serializers.CharField()


class ScheduleSyncRequestSerializer(serializers.Serializer):
    """Input body for POST /api/plugins/proxbox/sync/schedule/."""

    sync_types = serializers.ListField(
        child=serializers.ChoiceField(choices=SyncTypeChoices),
        min_length=1,
        help_text=(
            "List of sync type slugs (e.g. ['all'] or "
            "['virtual-machines', 'storage']); 'all' must be selected by itself."
        ),
    )
    job_name = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="Optional label for the job.",
    )
    schedule_at = serializers.DateTimeField(
        required=False,
        allow_null=True,
        default=None,
        help_text="ISO 8601 datetime. Omit or null to run immediately.",
    )
    interval_value = serializers.IntegerField(
        required=False,
        allow_null=True,
        default=None,
        min_value=1,
        help_text="Recurrence interval value (integer). Requires interval_unit.",
    )
    interval_unit = serializers.ChoiceField(
        choices=ScheduleIntervalUnitChoices,
        required=False,
        allow_null=True,
        default=None,
        help_text="Unit for interval_value.",
    )
    proxmox_endpoint_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=list,
        help_text=(
            "PKs of enabled ProxmoxEndpoint objects to include. Omit for all; "
            "an explicit empty list or any unknown/disabled ID rejects the "
            "entire request."
        ),
    )
    netbox_endpoint_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=list,
        help_text=(
            "PKs of NetBoxEndpoint objects to include. Omit for all; an explicit "
            "empty list is rejected."
        ),
    )

    def validate(self, attrs: dict) -> dict:
        """Reject scope widening and incomplete recurrence before enqueue."""
        errors: dict[str, list[str]] = {}
        for field_name in ("proxmox_endpoint_ids", "netbox_endpoint_ids"):
            if field_name in self.initial_data and not attrs.get(field_name):
                errors[field_name] = [
                    "An explicit endpoint scope must contain at least one ID; "
                    "omit the field to select all endpoints."
                ]

        has_interval_value = attrs.get("interval_value") is not None
        has_interval_unit = attrs.get("interval_unit") is not None
        if has_interval_value != has_interval_unit:
            missing_field = "interval_unit" if has_interval_value else "interval_value"
            errors[missing_field] = [
                "interval_value and interval_unit must be provided together."
            ]
        if errors:
            raise serializers.ValidationError(errors)
        return attrs
