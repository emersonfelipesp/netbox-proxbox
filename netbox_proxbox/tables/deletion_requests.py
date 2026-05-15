"""Table for Proxmox deletion request authorization records."""

from __future__ import annotations

import django_tables2 as tables
from django.utils.translation import gettext as _

from netbox.tables import NetBoxTable

from netbox_proxbox.models import DeletionRequest

__all__ = ("DeletionRequestTable",)


class DeletionRequestTable(NetBoxTable):
    """django-tables2 layout for safe-delete approval records."""

    name = tables.Column(linkify=True)
    branch_name = tables.Column(verbose_name=_("Branch"))
    requested_by = tables.Column(linkify=True, verbose_name=_("Requested by"))
    authorizer = tables.Column(linkify=True)
    requested_at = tables.Column(verbose_name=_("Requested"))
    approved_at = tables.Column(verbose_name=_("Approved"))

    class Meta(NetBoxTable.Meta):
        model = DeletionRequest
        fields = (
            "pk",
            "id",
            "name",
            "branch_id",
            "branch_name",
            "requested_by",
            "authorizer",
            "state",
            "vmid",
            "node",
            "kind",
            "requested_at",
            "approved_at",
            "executed_at",
            "actions",
        )
        default_columns = (
            "pk",
            "name",
            "requested_by",
            "authorizer",
            "state",
            "vmid",
            "node",
            "kind",
            "requested_at",
        )
