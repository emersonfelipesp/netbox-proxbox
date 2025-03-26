from django.utils.translation import gettext_lazy as _
from utilities.choices import ChoiceSet

class ProxmoxModeChoices(ChoiceSet):
    key = 'ProxmoxEndpoint.mode'
    
    PROXMOX_MODE_UNDEFINED = 'undefined'
    PROXMOX_MODE_STANDALONE = 'standalone'
    PROXMOX_MODE_CLUSTER = 'cluster'
    
    CHOICES = [
        (PROXMOX_MODE_UNDEFINED, _('Undefined'), 'gray'),
        (PROXMOX_MODE_STANDALONE, _('Standalone'), 'blue'),
        (PROXMOX_MODE_CLUSTER, _('Cluster'), 'green'),
    ]
    
class SyncTypeChoices(ChoiceSet):
    key = 'SyncProcess.sync_type'
    
    VIRTUAL_MACHINES = 'virtual-machines'
    DEVICES = 'devices'
    ALL = 'all'
    
    CHOICES = [
        (VIRTUAL_MACHINES, _('Virtual Machines'), 'blue'),
        (DEVICES, _('Devices'), 'green'),
        (ALL, _('All'), 'red'),
    ]

class SyncStatusChoices(ChoiceSet):
    key = 'SyncProcess.status'
    
    NOT_STARTED = 'not-started'
    SYNCING = 'syncing'
    COMPLETED = 'completed'
    
    CHOICES = [
        (NOT_STARTED, _('Not Started'), 'gray'),
        (SYNCING, _('Syncing'), 'blue'),
        (COMPLETED, _('Completed'), 'green'),
    ]
