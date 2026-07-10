"""API serializers for guest OS VM interface inventory."""

from __future__ import annotations

from ipam.api.serializers_.nested import NestedIPAddressSerializer
from netbox.api.serializers import NetBoxModelSerializer, WritableNestedSerializer
from rest_framework import serializers
from virtualization.api.serializers_.nested import (
    NestedVirtualMachineSerializer,
    NestedVMInterfaceSerializer,
)

from netbox_proxbox.models import GuestVMInterface, GuestVMInterfaceAddress


class NestedGuestVMInterfaceSerializer(WritableNestedSerializer):
    """Minimal nested representation for GuestVMInterface relations."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:guestvminterface-detail",
    )
    virtual_machine = NestedVirtualMachineSerializer(read_only=True)

    class Meta:
        model = GuestVMInterface
        fields = ("id", "url", "display", "virtual_machine", "name")
        brief_fields = ("id", "url", "display", "virtual_machine", "name")


class GuestVMInterfaceSerializer(NetBoxModelSerializer):
    """Full representation of a guest OS interface for a NetBox VM."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:guestvminterface-detail",
    )
    virtual_machine = NestedVirtualMachineSerializer()
    vm_interface = NestedVMInterfaceSerializer(required=False, allow_null=True)

    class Meta:
        model = GuestVMInterface
        fields = (
            "id",
            "url",
            "display",
            "virtual_machine",
            "vm_interface",
            "name",
            "mac_address",
            "enabled",
            "mtu",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = (
            "id",
            "url",
            "display",
            "virtual_machine",
            "vm_interface",
            "name",
        )


class GuestVMInterfaceAddressSerializer(NetBoxModelSerializer):
    """Join a guest OS interface to an existing core NetBox IPAddress row."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:guestvminterfaceaddress-detail",
    )
    guest_interface = NestedGuestVMInterfaceSerializer()
    ip_address = NestedIPAddressSerializer()

    class Meta:
        model = GuestVMInterfaceAddress
        fields = (
            "id",
            "url",
            "display",
            "guest_interface",
            "ip_address",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = (
            "id",
            "url",
            "display",
            "guest_interface",
            "ip_address",
        )
