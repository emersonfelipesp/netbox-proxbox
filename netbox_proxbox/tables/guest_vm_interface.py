"""Tables for guest OS VM interface inventory."""

from django_tables2 import tables
from django.utils.translation import gettext as _

from netbox.tables import NetBoxTable
from netbox.tables.columns import BooleanColumn

from netbox_proxbox.models import GuestVMInterface, GuestVMInterfaceAddress


class GuestVMInterfaceTable(NetBoxTable):
    """django-tables2 layout for guest OS VM interfaces."""

    virtual_machine = tables.Column(linkify=True)
    vm_interface = tables.Column(linkify=True)
    name = tables.Column(linkify=True)
    enabled = BooleanColumn(verbose_name=_("Enabled"))

    class Meta(NetBoxTable.Meta):
        model = GuestVMInterface
        fields = (
            "pk",
            "id",
            "virtual_machine",
            "vm_interface",
            "name",
            "mac_address",
            "enabled",
            "mtu",
            "actions",
        )
        default_columns = (
            "pk",
            "virtual_machine",
            "vm_interface",
            "name",
            "mac_address",
            "enabled",
            "mtu",
        )


class GuestVMInterfaceAddressTable(NetBoxTable):
    """django-tables2 layout for guest interface address links."""

    guest_interface = tables.Column(linkify=True)
    ip_address = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = GuestVMInterfaceAddress
        fields = (
            "pk",
            "id",
            "guest_interface",
            "ip_address",
            "actions",
        )
        default_columns = (
            "pk",
            "guest_interface",
            "ip_address",
        )
