"""Define the NetBox table used to render VM backup records."""

# Django Imports
from django_tables2 import tables
from django.utils.translation import gettext as _

# NetBox Imports
from netbox.tables import NetBoxTable, ChoiceFieldColumn

# Proxbox Imports
from netbox_proxbox.models import VMBackup


class VMBackupTable(NetBoxTable):
    """django-tables2 layout for VM backup list views."""

    storage = tables.Column(linkify=True)
    virtual_machine = tables.Column(linkify=True)
    proxmox_storage = tables.Column(linkify=True)
    subtype = ChoiceFieldColumn(
        verbose_name=_("Subtype"),
    )
    format = ChoiceFieldColumn(
        verbose_name=_("Format"),
    )
    creation_time = tables.Column(
        verbose_name=_("Creation Time"),
    )
    size = tables.Column(
        verbose_name=_("Size in Bytes"),
    )
    used = tables.Column(
        verbose_name=_("Used in Bytes"),
    )
    encrypted = tables.Column(
        verbose_name=_("Encrypted"),
    )
    volume_id = tables.Column(
        verbose_name=_("Volume ID"),
    )
    vmid = tables.Column(
        verbose_name=_("VM ID"),
    )

    class Meta(NetBoxTable.Meta):
        model = VMBackup
        fields = (
            "pk",
            "id",
            "proxmox_storage",
            "vmid",
            "storage",
            "virtual_machine",
            "subtype",
            "format",
            "creation_time",
            "size",
            "used",
            "encrypted",
            "volume_id",
            "verification_state",
            "verification_upid",
            "notes",
        )

        default_columns = (
            "pk",
            "proxmox_storage",
            "storage",
            "id",
            "virtual_machine",
            "subtype",
            "format",
            "creation_time",
            "size",
            "volume_id",
            "encrypted",
        )
