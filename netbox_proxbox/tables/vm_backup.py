# Django Imports
from django_tables2 import tables
from django.utils.translation import gettext as _

# NetBox Imports
from netbox.tables import NetBoxTable, ChoiceFieldColumn
from netbox.tables.columns import BooleanColumn

# Proxbox Imports
from netbox_proxbox.models import VMBackup


class VMBackupTable(NetBoxTable):
    virtual_machine = tables.Column(linkify=True)
    subtype = ChoiceFieldColumn(
        verbose_name=_('Subtype'),
    )
    format = ChoiceFieldColumn(
        verbose_name=_('Format'),
    )
    creation_time = tables.Column(
        verbose_name=_('Creation Time'),
    )
    size = tables.Column(
        verbose_name=_('Size in Bytes'),
    )
    used = tables.Column(
        verbose_name=_('Used in Bytes'),
    )
    encrypted = BooleanColumn(
        verbose_name=_('Encrypted'),
    )
    volume_id = tables.Column(
        verbose_name=_('Volume ID'),
    )
    vmid = tables.Column(
        verbose_name=_('VM ID'),
    )
    

    class Meta(NetBoxTable.Meta):
        model = VMBackup
        fields = (
            'pk', 'id', 'virtual_machine', 'subtype',
            'format', 'creation_time', 'size', 'used',
            'encrypted', 'volume_id', 'vmid',
            'verification_state', 'verification_upid',
            'notes', 'actions',
        )
        
        default_columns = (
            'pk', 'virtual_machine', 'subtype', 'format',
            'creation_time', 'size', 'encrypted', 'volume_id',
            'vmid', 'verification_state', 'notes'
        )


