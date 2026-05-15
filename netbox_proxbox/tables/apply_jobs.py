"""Table for Proxmox apply job dry-run records."""

from django_tables2 import tables
from django.utils.translation import gettext as _

from netbox.tables import NetBoxTable

from netbox_proxbox.models import ProxmoxApplyJob


class ProxmoxApplyJobTable(NetBoxTable):
    """django-tables2 layout for intent apply-job list views."""

    name = tables.Column(linkify=True)
    branch_name = tables.Column(verbose_name=_("Branch"))
    user = tables.Column(linkify=True)
    started_at = tables.Column(verbose_name=_("Started"))
    finished_at = tables.Column(verbose_name=_("Finished"))

    class Meta(NetBoxTable.Meta):
        model = ProxmoxApplyJob
        fields = (
            "pk",
            "id",
            "name",
            "branch_id",
            "branch_name",
            "user",
            "run_uuid",
            "state",
            "started_at",
            "finished_at",
            "actions",
        )
        default_columns = (
            "pk",
            "name",
            "branch_name",
            "user",
            "state",
            "started_at",
            "finished_at",
        )
