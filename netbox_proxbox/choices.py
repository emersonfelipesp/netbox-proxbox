from django.utils.translation import gettext_lazy as _
from utilities.choices import ChoiceSet
from django.db import models

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
    
class SyncType(models.TextChoices):
    VIRTUAL_MACHINES = 'virtual-machines', _('Virtual Machines')
    DEVICES = 'devices', _('Devices')
    ALL = 'all', _('All')

class SyncStatus(models.TextChoices):
    NOT_STARTED = 'not-started', _('Not Started')
    SYNCING = 'syncing', _('Syncing')
    COMPLETED = 'completed', _('Completed')