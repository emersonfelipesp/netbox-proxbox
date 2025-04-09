# Django Imports
from django.db import models
from django.utils.translation import gettext_lazy as _

# NetBox Imports
from netbox.models import NetBoxModel

# NetBox ProxBox Imports
from netbox_proxbox.choices import ProxmoxBackupSubtypeChoices, ProxmoxBackupFormatChoices

class VMBackup(NetBoxModel):
    virtual_machine = models.ForeignKey(
        to='virtualization.VirtualMachine',
        on_delete=models.CASCADE,
        related_name='backups',
    )
   
    subtype = models.CharField(
        max_length=255,
        choices=ProxmoxBackupSubtypeChoices,
        default=ProxmoxBackupSubtypeChoices.BACKUP_SUBTYPE_UNDEFINED,
    )
    
    format = models.CharField(
        max_length=255,
        choices=ProxmoxBackupFormatChoices,
        default=ProxmoxBackupFormatChoices.BACKUP_FORMAT_UNDEFINED,
    )
    
    creation_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_('Creation time of the backup.'),
    )
    
    size = models.BigIntegerField(
        null=True,
        blank=True,
        help_text=_('Size in bytes of the backup.'),
    )
    
    notes = models.TextField(
        null=True,
        blank=True,
        help_text=_('Notes of the backup.'),
    )
    
    volume_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text=_('Volume Identifier of the backup.'),
    )
    
    vmid = models.IntegerField(
        null=True,
        blank=True,
        help_text=_('VM ID of the backup.'),
    )
    
    used = models.BigIntegerField(
        null=True,
        blank=True,
        help_text=_('Used space of the backup.'),
    )
    
    encrypted = models.BooleanField(
        default=False,
        help_text=_('Encrypted status of the backup.'),
    )
    
    verification_state = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text=_('Verification state of the backup.'),
    )
    
    verification_upid = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text=_('Verification UPID of the backup.'),
    )
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    