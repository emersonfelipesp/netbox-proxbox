"""django-tables2 layout for Proxmox VM cloud-init records (issue #363)."""

from django.utils.translation import gettext as _
import django_tables2 as tables

from netbox.tables import NetBoxTable
from netbox.tables.columns import BooleanColumn

from netbox_proxbox.models import ProxmoxVMCloudInit


class ProxmoxVMCloudInitTable(NetBoxTable):
    """Table view of Proxmox VM cloud-init reflections."""

    virtual_machine = tables.Column(linkify=True)
    ciuser = tables.Column(verbose_name=_("Cloud-init User"))
    ipconfig0 = tables.Column(verbose_name=_("ipconfig0"))
    sshkeys_truncated = BooleanColumn(verbose_name=_("SSH Keys Truncated"))
    is_intent = BooleanColumn(verbose_name=_("Intent"))
    hostname = tables.Column(verbose_name=_("Hostname"))
    nms_credential_id = tables.Column(verbose_name=_("NMS Credential"))
    has_sshkeys = BooleanColumn(verbose_name=_("Intent SSH Keys"))
    last_synced = tables.DateTimeColumn(verbose_name=_("Last Synced"))

    class Meta(NetBoxTable.Meta):
        model = ProxmoxVMCloudInit
        fields = (
            "pk",
            "id",
            "virtual_machine",
            "ciuser",
            "ipconfig0",
            "sshkeys_truncated",
            "is_intent",
            "hostname",
            "nms_credential_id",
            "has_sshkeys",
            "last_synced",
        )

        default_columns = (
            "pk",
            "virtual_machine",
            "ciuser",
            "ipconfig0",
            "is_intent",
            "sshkeys_truncated",
            "last_synced",
        )
