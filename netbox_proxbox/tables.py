import django_tables2 as tables
from netbox.tables import NetBoxTable, ChoiceFieldColumn
from netbox.tables.columns import BooleanColumn

from .models import (
    ProxmoxEndpoint,
    NetBoxEndpoint,
    FastAPIEndpoint,
    SyncProcess,
)


class SyncProcessTable(NetBoxTable):
    name = tables.Column(linkify=True)
    sync_type = ChoiceFieldColumn()
    status = ChoiceFieldColumn()
    started_at = tables.Column()
    completed_at = tables.Column()
    last_updated = tables.Column()
    
    class Meta(NetBoxTable.Meta):
        model = SyncProcess
        fields = (
            'pk', 'id', 'name', 'sync_type', 'status', 'started_at', 'completed_at', 'last_updated',
            'actions',
        )
    
        default_columns = (
            'pk', 'name', 'sync_type', 'status', 'started_at', 'completed_at', 'last_updated'
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
            'pk', 'name', 'ip_address', 'port', 'mode',
            'version', 'verify_ssl'
        )


class NetBoxEndpointTable(NetBoxTable):
    name = tables.Column(linkify=True)
    ip_address = tables.Column(linkify=True)
    verify_ssl = BooleanColumn()
    
    class Meta(NetBoxTable.Meta):
        model = NetBoxEndpoint
        fields = (
            'pk', 'id', 'name', 'ip_address', 'port',
            'verify_ssl', 'actions',
        )
        
        default_columns = (
            'pk', 'name', 'ip_address', 'port', 'verify_ssl'
        )


class FastAPIEndpointTable(NetBoxTable):
    name = tables.Column(linkify=True)
    ip_address = tables.Column(linkify=True)
    verify_ssl = BooleanColumn()
    
    class Meta(NetBoxTable.Meta):
        model = FastAPIEndpoint
        fields = (
            'pk', 'id', 'name', 'domain', 'ip_address', 'port',
            'verify_ssl', 'actions',
        )
        
        default_columns = (
            'pk', 'name', 'domain', 'ip_address', 'port', 'verify_ssl',
        )