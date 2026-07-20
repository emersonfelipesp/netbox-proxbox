"""API serializers for guest OS VM interface inventory."""

from __future__ import annotations

from django.db import IntegrityError, transaction
from ipam.api.serializers_.nested import NestedIPAddressSerializer
from netbox.api.serializers import NetBoxModelSerializer, WritableNestedSerializer
from rest_framework import serializers
from virtualization.api.serializers_.nested import (
    NestedVirtualMachineSerializer,
    NestedVMInterfaceSerializer,
)

from netbox_proxbox.models import GuestVMInterface, GuestVMInterfaceAddress


GUEST_VM_INTERFACE_VM_INTERFACE_UNIQUE_ERROR = (
    "This core VM interface is already mapped to another guest interface "
    "(one-to-one). A guest interface that shares a MAC with the Proxmox NIC "
    "(e.g. a VLAN sub-interface) must not claim the same core interface."
)
GUEST_VM_INTERFACE_ADDRESS_UNIQUE_ERROR = (
    "This IP address is already linked to this guest interface."
)


def _is_unique_violation(message: str) -> bool:
    """Match only a UNIQUE-constraint violation, never a foreign-key one.

    ``str(IntegrityError)`` carries the backend text: PostgreSQL emits
    ``duplicate key value violates unique constraint`` for uniqueness and
    ``violates foreign key constraint`` for a bad FK target. Requiring the
    unique-violation signature keeps a raced FK failure from being mistranslated
    into a duplicate 400 (it must re-raise instead).
    """
    return "unique constraint" in message or "duplicate key" in message


def _is_vm_interface_integrity_error(exc: IntegrityError) -> bool:
    message = str(exc).lower()
    return _is_unique_violation(message) and "vm_interface_id" in message


def _is_guest_interface_address_integrity_error(exc: IntegrityError) -> bool:
    message = str(exc).lower()
    if not _is_unique_violation(message):
        return False
    return "unique_guest_vm_interface_address" in message or (
        "guest_interface_id" in message and "ip_address_id" in message
    )


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

    def validate(self, data):
        """Reject a core VM interface already claimed by another guest interface.

        ``vm_interface`` is a ``OneToOneField``; NetBox's serializer runs
        ``full_clean(validate_unique=False)``, so the uniqueness collision is not
        caught at validation time and would otherwise surface as an unhandled DB
        ``IntegrityError`` (HTTP 500) on ``.save()``. This happens when the
        backend maps two guest interfaces that share a MAC (for example a VLAN
        sub-interface ``eth0.100`` and its parent ``eth0``) to the same core
        interface. Return a clean field-level 400 instead so a partial-failure
        stream is never turned into a 500 that could abort the sync run.
        """
        data = super().validate(data)
        vm_interface = data.get("vm_interface")
        if vm_interface is not None:
            claimed = GuestVMInterface.objects.filter(vm_interface=vm_interface)
            if self.instance is not None:
                claimed = claimed.exclude(pk=self.instance.pk)
            if claimed.exists():
                self._raise_duplicate_vm_interface()
        return data

    def create(self, validated_data):
        try:
            with transaction.atomic():
                return super().create(validated_data)
        except IntegrityError as exc:
            if _is_vm_interface_integrity_error(exc):
                self._raise_duplicate_vm_interface(exc)
            raise

    def update(self, instance, validated_data):
        try:
            with transaction.atomic():
                return super().update(instance, validated_data)
        except IntegrityError as exc:
            if _is_vm_interface_integrity_error(exc):
                self._raise_duplicate_vm_interface(exc)
            raise

    @staticmethod
    def _raise_duplicate_vm_interface(exc: IntegrityError | None = None) -> None:
        raise serializers.ValidationError(
            {"vm_interface": GUEST_VM_INTERFACE_VM_INTERFACE_UNIQUE_ERROR}
        ) from exc


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

    def validate(self, data):
        """Reject a duplicate ``(guest_interface, ip_address)`` link cleanly.

        The model has a ``UniqueConstraint`` on ``(guest_interface, ip_address)``,
        but NetBox's ``full_clean(validate_unique=False)`` skips it, so a
        duplicate would surface as an unhandled DB ``IntegrityError`` (HTTP 500)
        on ``.save()``. Return a 400 instead.
        """
        data = super().validate(data)
        guest_interface = data.get("guest_interface")
        ip_address = data.get("ip_address")
        if self.instance is not None:
            guest_interface = guest_interface or self.instance.guest_interface
            ip_address = ip_address or self.instance.ip_address
        if guest_interface is not None and ip_address is not None:
            existing = GuestVMInterfaceAddress.objects.filter(
                guest_interface=guest_interface, ip_address=ip_address
            )
            if self.instance is not None:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                self._raise_duplicate_address()
        return data

    def create(self, validated_data):
        try:
            with transaction.atomic():
                return super().create(validated_data)
        except IntegrityError as exc:
            if _is_guest_interface_address_integrity_error(exc):
                self._raise_duplicate_address(exc)
            raise

    def update(self, instance, validated_data):
        try:
            with transaction.atomic():
                return super().update(instance, validated_data)
        except IntegrityError as exc:
            if _is_guest_interface_address_integrity_error(exc):
                self._raise_duplicate_address(exc)
            raise

    @staticmethod
    def _raise_duplicate_address(exc: IntegrityError | None = None) -> None:
        raise serializers.ValidationError(
            {"ip_address": GUEST_VM_INTERFACE_ADDRESS_UNIQUE_ERROR}
        ) from exc
