"""Table for PDMRemote discovered remote rows."""

import django_tables2 as tables
from django.utils.translation import gettext_lazy as _

from netbox.tables import NetBoxTable
from netbox_proxbox.models.pdm_remote import PDMRemote


class PDMRemoteTable(NetBoxTable):
    """django-tables2 layout for the PDMRemote list and endpoint detail table."""

    name = tables.Column(linkify=True)
    type = tables.Column(verbose_name=_("Type"))
    hostname = tables.Column(verbose_name=_("Hostname"))
    version = tables.Column(verbose_name=_("Version"))
    linked_proxmox_endpoint = tables.Column(
        linkify=True,
        verbose_name=_("Linked PVE"),
    )
    linked_pbs_endpoint = tables.Column(
        linkify=True,
        verbose_name=_("Linked PBS"),
    )
    last_seen_at = tables.DateTimeColumn(verbose_name=_("Last Seen"))

    class Meta(NetBoxTable.Meta):
        model = PDMRemote
        fields = (
            "pk",
            "id",
            "name",
            "type",
            "hostname",
            "version",
            "linked_proxmox_endpoint",
            "linked_pbs_endpoint",
            "last_seen_at",
            "actions",
        )
        default_columns = (
            "name",
            "type",
            "hostname",
            "version",
            "linked_proxmox_endpoint",
            "linked_pbs_endpoint",
            "last_seen_at",
        )
