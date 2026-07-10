"""Guest OS interface inventory linked to core NetBox VM interfaces."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse

from netbox.models import NetBoxModel


class GuestVMInterface(NetBoxModel):
    """Guest-agent reported OS interface for a NetBox virtual machine."""

    virtual_machine = models.ForeignKey(
        to="virtualization.VirtualMachine",
        on_delete=models.CASCADE,
        related_name="proxbox_guest_interfaces",
    )
    vm_interface = models.OneToOneField(
        to="virtualization.VMInterface",
        on_delete=models.SET_NULL,
        related_name="guest_interface",
        null=True,
        blank=True,
        help_text=(
            "The Proxmox-side core VM interface (e.g. net0) this guest OS "
            "interface maps to one-to-one, matched by MAC address. Null for "
            "agent-only interfaces with no matching Proxmox NIC."
        ),
    )
    name = models.CharField(max_length=128)
    mac_address = models.CharField(
        max_length=32,
        blank=True,
        help_text="Guest OS-reported MAC address for informational matching.",
    )
    enabled = models.BooleanField(default=True)
    mtu = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ("virtual_machine", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("virtual_machine", "name"),
                name="unique_guest_vm_interface_vm_name",
            ),
        ]
        verbose_name = "Guest VM interface"
        verbose_name_plural = "Guest VM interfaces"

    def clean(self) -> None:
        """A mapped core VM interface must belong to this guest interface's VM."""
        super().clean()
        if (
            self.vm_interface_id
            and self.virtual_machine_id
            and self.vm_interface.virtual_machine_id != self.virtual_machine_id
        ):
            raise ValidationError(
                {
                    "vm_interface": (
                        "Mapped core VM interface must belong to the same "
                        "virtual machine as the guest interface."
                    )
                }
            )

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_proxbox:guestvminterface", args=[self.pk])


class GuestVMInterfaceAddress(NetBoxModel):
    """Shared core IP address observed on a guest OS interface."""

    guest_interface = models.ForeignKey(
        to="netbox_proxbox.GuestVMInterface",
        on_delete=models.CASCADE,
        related_name="addresses",
    )
    ip_address = models.ForeignKey(
        to="ipam.IPAddress",
        on_delete=models.PROTECT,
        related_name="proxbox_guest_interface_addresses",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("guest_interface", "ip_address"),
                name="unique_guest_vm_interface_address",
            ),
        ]
        verbose_name = "Guest VM interface address"
        verbose_name_plural = "Guest VM interface addresses"

    def clean(self) -> None:
        """Guarantee the linked IP is the same core object, not a foreign VM's.

        The guest OS interface and its one-to-one Proxmox core ``VMInterface``
        must point at the *same* ``ipam.IPAddress`` object. When the core IP is
        assigned to an interface, reject links whose IP is assigned to a
        different interface (for a mapped guest interface) or to a different
        virtual machine (for an agent-only guest interface). An unassigned IP is
        allowed because the backend assigns it to the core interface first.
        """
        super().clean()
        if not (self.ip_address_id and self.guest_interface_id):
            return

        # Local import avoids a model-load-time circular import.
        from virtualization.models import VMInterface

        assigned = self.ip_address.assigned_object
        # An unassigned IP is allowed: the backend assigns it to the core VM
        # interface before creating this link. But once the IP *is* assigned to
        # something, that something must be the mapped core VM interface (or, for
        # an agent-only guest, a VM interface on the same VM). Anything else — an
        # IP already owned by a dcim.Interface, an FHRP group, or a different
        # VM's interface — must be rejected so this row cannot PROTECT-lock a
        # foreign object or misrepresent the guest/IP relationship.
        if assigned is None:
            return

        guest = self.guest_interface
        if guest.vm_interface_id:
            if (
                not isinstance(assigned, VMInterface)
                or assigned.pk != guest.vm_interface_id
            ):
                raise ValidationError(
                    {
                        "ip_address": (
                            "IP address must be the same object assigned to the "
                            "mapped Proxmox core VM interface."
                        )
                    }
                )
        elif (
            not isinstance(assigned, VMInterface)
            or assigned.virtual_machine_id != guest.virtual_machine_id
        ):
            raise ValidationError(
                {
                    "ip_address": (
                        "IP address must be assigned to a VM interface on the "
                        "same virtual machine as the guest interface."
                    )
                }
            )

    def __str__(self) -> str:
        return f"{self.guest_interface} - {self.ip_address}"

    def get_absolute_url(self) -> str:
        return reverse(
            "plugins:netbox_proxbox:guestvminterfaceaddress",
            args=[self.pk],
        )
