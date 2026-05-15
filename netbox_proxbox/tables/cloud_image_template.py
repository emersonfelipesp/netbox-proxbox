"""Define the NetBox table used to render cloud image templates."""

import django_tables2 as tables
from django.utils.translation import gettext as _
from netbox.tables import ChoiceFieldColumn, NetBoxTable
from netbox.tables.columns import BooleanColumn

from netbox_proxbox.models import CloudImageTemplate


class CloudImageTemplateTable(NetBoxTable):
    """django-tables2 layout for CloudImageTemplate list views."""

    name = tables.Column(linkify=True, verbose_name=_("Name"))
    cluster = tables.Column(linkify=True, verbose_name=_("Cluster"))
    os_family = ChoiceFieldColumn(verbose_name=_("OS family"))
    is_active = BooleanColumn(verbose_name=_("Active"))
    tenant_scope_label = tables.Column(
        orderable=False,
        verbose_name=_("Tenant scope"),
    )

    class Meta(NetBoxTable.Meta):
        model = CloudImageTemplate
        fields = (
            "pk",
            "id",
            "name",
            "slug",
            "cluster",
            "source_vmid",
            "os_family",
            "os_release",
            "default_ciuser",
            "tenant_scope_label",
            "is_active",
        )
        default_columns = (
            "pk",
            "name",
            "cluster",
            "source_vmid",
            "os_family",
            "os_release",
            "tenant_scope_label",
            "is_active",
        )
