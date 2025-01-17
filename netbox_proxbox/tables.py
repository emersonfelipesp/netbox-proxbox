import django_tables2 as tables
from netbox.tables import NetBoxTable, ChoiceFieldColumn
from netbox.tables.columns import BooleanColumn

from .models import (
    ProxmoxEndpoint,
    NetboxEndpoint,
    FastAPIEndpoint,
)

class ProxmoxEndpointTable(NetBoxTable):
    name = tables.Column(linkify=True)
    ip_address = tables.Column(linkify=True)
    mode = ChoiceFieldColumn()
    verify_ssl = BooleanColumn()
    
    class Meta(NetBoxTable.Meta):
        model = ProxmoxEndpoint
        fields = (
            'pk', 'id', 'name', 'ip_address', 'port',
            'mode', 'version', 'repoid', 'username', 'token_name',
            'verify_ssl', 'actions',
        )
        
        default_columns = (
            'pk',
            'name',
            'ip_address',
            'port',
            'mode',
            'version',
        )