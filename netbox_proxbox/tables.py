import django_tables2 as tables
from django.utils.translation import gettext as _

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
    sync_type = ChoiceFieldColumn(
        verbose_name=_('Sync Type'),
    )
    status = ChoiceFieldColumn(
        verbose_name=_('Status'),
    )
    started_at = tables.Column(
        verbose_name=_('Started At'),
    )
    completed_at = tables.Column(
        verbose_name=_('Completed At'),
    )
    last_updated = tables.Column(
        verbose_name=_('Last Updated'),
    )
    runtime = tables.Column(
        verbose_name=_('Runtime'),
    )
    
    class Meta(NetBoxTable.Meta):
        model = SyncProcess
        fields = (
            'pk', 'id', 'name', 'sync_type', 'status', 'started_at', 'completed_at', 'last_updated',
            'runtime', 'actions',
        )
    
        default_columns = (
            'pk', 'name', 'sync_type', 'status', 'started_at', 'completed_at', 'runtime'
        )
        
        order_by = ('-id',)

class ProxmoxEndpointTable(NetBoxTable):
    name = tables.Column(linkify=True)
    ip_address = tables.Column(linkify=True)
    mode = ChoiceFieldColumn()
    verify_ssl = BooleanColumn()
    
    class Meta(NetBoxTable.Meta):
        model = ProxmoxEndpoint
        fields = (
            'pk', 'id', 'name', 'domain', 'ip_address', 'port',
            'mode', 'version', 'repoid', 'username', 'token_name',
            'verify_ssl', 'actions',
        )
        
        default_columns = (
            'pk', 'name', 'domain', 'ip_address', 'port', 'mode',
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
            'verify_ssl', 'token', 'actions',
        )
        
        default_columns = (
            'pk', 'name', 'ip_address', 'port', 'verify_ssl', 'token'
        )


class FastAPIEndpointTable(NetBoxTable):
    name = tables.Column(linkify=True)
    ip_address = tables.Column(linkify=True)
    verify_ssl = BooleanColumn()
    
    class Meta(NetBoxTable.Meta):
        model = FastAPIEndpoint
        fields = (
            'pk', 'id', 'name', 'domain', 'ip_address', 'port',
            'verify_ssl', 'use_websocket', 'websocket_domain', 'websocket_port', 'server_side_websocket', 'token', 'actions',
        )
        
        default_columns = (
            'pk', 'name', 'domain', 'ip_address', 'port', 'verify_ssl', 'use_websocket', 'websocket_domain'
        )