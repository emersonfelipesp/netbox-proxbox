"""Tables for endpoint application services and their SSH credentials."""

import django_tables2 as tables
from django.utils.translation import gettext_lazy as _
from netbox.tables import ChoiceFieldColumn, NetBoxTable
from netbox.tables.columns import ActionsColumn, BooleanColumn

from netbox_proxbox.models import ProxmoxEndpointService, ServiceSSHCredential


class ProxmoxEndpointServiceTable(NetBoxTable):
    endpoint = tables.Column(linkify=True)
    name = tables.Column(linkify=True)
    protocol = ChoiceFieldColumn()

    class Meta(NetBoxTable.Meta):
        model = ProxmoxEndpointService
        fields = (
            "pk",
            "id",
            "name",
            "endpoint",
            "protocol",
            "ports",
            "description",
            "actions",
        )
        default_columns = ("pk", "name", "endpoint", "protocol", "ports")


class ServiceSSHCredentialTable(NetBoxTable):
    service = tables.Column(linkify=True)
    auth_method = ChoiceFieldColumn()
    has_password = BooleanColumn(verbose_name=_("Password stored"))
    has_private_key = BooleanColumn(verbose_name=_("Private key stored"))
    # Credentials are edited through the endpoint SSH form, so the row offers
    # delete only. Annotated so it is not mistaken for a view action tuple.
    actions: ActionsColumn = ActionsColumn(actions=("delete",))

    class Meta(NetBoxTable.Meta):
        model = ServiceSSHCredential
        fields = (
            "pk",
            "id",
            "service",
            "username",
            "auth_method",
            "storage_backend",
            "has_password",
            "has_private_key",
            "actions",
        )
        default_columns = (
            "pk",
            "service",
            "username",
            "auth_method",
            "storage_backend",
            "has_password",
            "has_private_key",
        )
