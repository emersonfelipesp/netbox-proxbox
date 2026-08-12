"""Lightweight serializers for non-model API views (resource lists, schedule sync, etc.)."""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from rest_framework import serializers

from netbox_proxbox.api.mcp_bridge import (
    INTERVAL_VALUE_MAXIMUMS,
    MAX_EXACT_JSON_FLOAT_INTEGER,
    MAX_POSITIVE_SIGNED_64_BIT_INTEGER,
    MAX_PERSISTED_INTERVAL_MINUTES,
    SYNC_TYPE_VALUES,
)
from netbox_proxbox.choices import ScheduleIntervalUnitChoices, SyncTypeChoices

_RFC3339_DATE_TIME_RE = re.compile(
    r"^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])"
    r"[Tt](?:[01]\d|2[0-3]):[0-5]\d:(?:[0-5]\d|60)(?:\.\d+)?"
    r"(?:[Zz]|[+-](?:[01]\d|2[0-3]):[0-5]\d)$"
)


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


class _StrictJSONIntegerField(serializers.IntegerField):
    """Implement lossless JSON integer semantics without DRF coercion."""

    def to_internal_value(self, data: object) -> int:
        if isinstance(data, bool):
            self.fail("invalid")
        if isinstance(data, float):
            if (
                not math.isfinite(data)
                or not data.is_integer()
                or abs(data) > MAX_EXACT_JSON_FLOAT_INTEGER
            ):
                self.fail("invalid")
            data = int(data)
        elif isinstance(data, Decimal):
            if (
                not data.is_finite()
                or data != data.to_integral_value()
                or abs(data) > MAX_EXACT_JSON_FLOAT_INTEGER
            ):
                self.fail("invalid")
            data = int(data)
        elif not isinstance(data, int):
            self.fail("invalid")
        return super().to_internal_value(data)


class _StrictJSONStringField(serializers.CharField):
    """Reject numeric input instead of applying DRF's string coercion."""

    def to_internal_value(self, data: object) -> str:
        if not isinstance(data, str):
            self.fail("invalid")
        return super().to_internal_value(data)


class _StrictRFC3339DateTimeField(serializers.DateTimeField):
    """Match bridge-v1 RFC 3339 while preserving the legacy REST parser."""

    def to_internal_value(self, value: object) -> datetime:
        initial_data = getattr(self.parent, "initial_data", {})
        if "sync_stages" not in initial_data:
            return super().to_internal_value(value)
        if not isinstance(value, str) or _RFC3339_DATE_TIME_RE.fullmatch(value) is None:
            self.fail("invalid", format="RFC 3339 date-time")
        leap_second = re.search(r":60(?=(?:\.\d+)?(?:[Zz]|[+-]))", value) is not None
        normalized = value.replace("t", "T").replace("z", "Z")
        normalized = re.sub(r":60(?=(?:\.\d+)?(?:Z|[+-]))", ":59", normalized)
        parsed = super().to_internal_value(normalized)
        try:
            parsed = parsed.astimezone(UTC)
            if leap_second:
                parsed += timedelta(seconds=1)
        except OverflowError:
            self.fail("invalid", format="RFC 3339 date-time")
        if not leap_second:
            return parsed
        if not (
            parsed.day == 1
            and parsed.hour == 0
            and parsed.minute == 0
            and parsed.second == 0
        ):
            self.fail("invalid", format="RFC 3339 date-time")
        return parsed


class ScheduleSyncRecurrenceSerializer(serializers.Serializer):
    """Exactly one recurrence unit whose converted value fits NetBox Job.interval."""

    minutes = _StrictJSONIntegerField(
        required=False, min_value=1, max_value=INTERVAL_VALUE_MAXIMUMS["minutes"]
    )
    hours = _StrictJSONIntegerField(
        required=False, min_value=1, max_value=INTERVAL_VALUE_MAXIMUMS["hours"]
    )
    days = _StrictJSONIntegerField(
        required=False, min_value=1, max_value=INTERVAL_VALUE_MAXIMUMS["days"]
    )
    weeks = _StrictJSONIntegerField(
        required=False, min_value=1, max_value=INTERVAL_VALUE_MAXIMUMS["weeks"]
    )

    def to_internal_value(self, data: object) -> dict:
        """Reject nested unknowns before the exactly-one-member validation."""
        attrs = super().to_internal_value(data)
        if isinstance(data, dict):
            unknown_fields = sorted(set(data) - set(self.fields))
            if unknown_fields:
                raise serializers.ValidationError(
                    {field_name: ["Unknown field."] for field_name in unknown_fields}
                )
        return attrs

    def validate(self, attrs: dict) -> dict:
        errors: dict[str, list[str]] = {}
        if len(attrs) != 1:
            errors[serializers.api_settings.NON_FIELD_ERRORS_KEY] = [
                "Recurrence must contain exactly one unit/value member."
            ]
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class ScheduleSyncRequestSerializer(serializers.Serializer):
    """Input body for POST /api/plugins/proxbox/sync/schedule/."""

    sync_types = serializers.ListField(
        child=serializers.ChoiceField(choices=SyncTypeChoices),
        required=False,
        min_length=1,
        help_text=(
            "List of sync type slugs (e.g. ['all'] or "
            "['virtual-machines', 'storage']); 'all' must be selected by itself."
        ),
    )
    sync_stages = serializers.ListField(
        child=serializers.ChoiceField(choices=SYNC_TYPE_VALUES),
        required=False,
        min_length=1,
        help_text=(
            "Bridge-v1 concrete stage slugs. The 'all' sentinel is not accepted; "
            "send the complete canonical stage list for a full sync."
        ),
    )
    job_name = _StrictJSONStringField(
        required=False,
        allow_blank=True,
        default="",
        max_length=200,
        help_text="Optional label for the job.",
    )
    schedule_at = _StrictRFC3339DateTimeField(
        required=False,
        allow_null=True,
        default=None,
        help_text="ISO 8601 datetime. Omit or null to run immediately.",
    )
    interval_value = _StrictJSONIntegerField(
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
    recurrence = ScheduleSyncRecurrenceSerializer(
        required=False,
        help_text="Bridge-v1 recurrence with exactly one bounded unit/value member.",
    )
    proxmox_endpoint_ids = serializers.ListField(
        child=_StrictJSONIntegerField(
            min_value=1, max_value=MAX_POSITIVE_SIGNED_64_BIT_INTEGER
        ),
        required=False,
        default=list,
        min_length=1,
        help_text=(
            "PKs of enabled ProxmoxEndpoint objects to include. Omit for all; "
            "an explicit empty list or any unknown/disabled ID rejects the "
            "entire request. Integer JSON literals retain signed-64 identity; "
            "decimal forms are accepted only through 9007199254740991."
        ),
    )
    netbox_endpoint_ids = serializers.ListField(
        child=_StrictJSONIntegerField(
            min_value=1, max_value=MAX_POSITIVE_SIGNED_64_BIT_INTEGER
        ),
        required=False,
        default=list,
        min_length=1,
        help_text=(
            "PKs of NetBoxEndpoint objects to include. Omit for all; an explicit "
            "empty list is rejected. Integer JSON literals retain signed-64 "
            "identity; decimal forms are accepted only through 9007199254740991."
        ),
    )

    def validate(self, attrs: dict) -> dict:
        """Enforce the strict bridge-v1 input contract before enqueue."""
        errors: dict[str, list[str]] = {}
        unknown_fields = sorted(set(self.initial_data) - set(self.fields))
        for field_name in unknown_fields:
            errors[field_name] = ["Unknown field."]

        is_bridge_request = "sync_stages" in self.initial_data
        has_legacy_sync_types = "sync_types" in self.initial_data
        if is_bridge_request == has_legacy_sync_types:
            errors["sync_stages"] = [
                "Provide bridge sync_stages or legacy sync_types, but not both."
            ]

        bridge_forbidden_fields = {
            "interval_value",
            "interval_unit",
            "netbox_endpoint_ids",
            "sync_types",
        }
        if is_bridge_request:
            for field_name in sorted(bridge_forbidden_fields & set(self.initial_data)):
                errors[field_name] = ["Field is not part of bridge v1."]
        elif "recurrence" in self.initial_data:
            errors["recurrence"] = [
                "Use interval_value and interval_unit for the legacy REST contract."
            ]

        for field_name in ("proxmox_endpoint_ids", "netbox_endpoint_ids"):
            if field_name in self.initial_data and not attrs.get(field_name):
                errors[field_name] = [
                    "An explicit endpoint scope must contain at least one ID; "
                    "omit the field to select all endpoints."
                ]

        for field_name in (
            "sync_types",
            "sync_stages",
            "proxmox_endpoint_ids",
            "netbox_endpoint_ids",
        ):
            values = attrs.get(field_name) or []
            if len(values) != len(set(values)):
                errors[field_name] = ["Duplicate values are not allowed."]

        has_interval_value = attrs.get("interval_value") is not None
        has_interval_unit = attrs.get("interval_unit") is not None
        if has_interval_value != has_interval_unit:
            missing_field = "interval_unit" if has_interval_value else "interval_value"
            errors[missing_field] = [
                "interval_value and interval_unit must be provided together."
            ]
        if has_interval_value and has_interval_unit:
            interval = ScheduleIntervalUnitChoices.to_minutes(
                attrs["interval_value"], attrs["interval_unit"]
            )
            if interval > MAX_PERSISTED_INTERVAL_MINUTES:
                errors["interval_value"] = [
                    "Converted recurrence exceeds the persisted minute limit."
                ]
        if errors:
            raise serializers.ValidationError(errors)
        if is_bridge_request:
            sync_stages = attrs.pop("sync_stages")
            attrs["sync_types"] = (
                [SyncTypeChoices.ALL]
                if len(sync_stages) == len(SYNC_TYPE_VALUES)
                and set(sync_stages) == set(SYNC_TYPE_VALUES)
                else sync_stages
            )
        return attrs
