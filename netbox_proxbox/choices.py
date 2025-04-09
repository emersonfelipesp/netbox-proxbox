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


class ProxmoxBackupSubtypeChoices(ChoiceSet):
    key = 'VMBackup.subtype'
    
    BACKUP_SUBTYPE_UNDEFINED = 'undefined'
    BACKUP_SUBTYPE_LXC = 'lxc'
    BACKUP_SUBTYPE_QEMU = 'qemu'
    
    CHOICES = [
        (BACKUP_SUBTYPE_UNDEFINED, _('Undefined'), 'gray'),
        (BACKUP_SUBTYPE_LXC, _('LXC'), 'blue'),
        (BACKUP_SUBTYPE_QEMU, _('QEMU'), 'green'),
    ]


class ProxmoxBackupFormatChoices(ChoiceSet):
    key = 'VMBackup.format'
    
    BACKUP_FORMAT_UNDEFINED = 'undefined'
    BACKUP_FORMAT_PBS_VM = 'pbs-vm'
    BACKUP_FORMAT_PBS_CT = 'pbs-ct'
    BACKUP_FORMAT_ISO = 'iso'
    BACKUP_FORMAT_TZST = 'tzst'
    BACKUP_FORMAT_TGZ = 'tgz'
    BACKUP_FORMAT_QCOW2 = 'qcow2'
    BACKUP_FORMAT_RAW = 'raw'
    BACKUP_FORMAT_TAR = 'tar'
    BACKUP_FORMAT_TBZ = 'tbz'
    
    CHOICES = [
        (BACKUP_FORMAT_UNDEFINED, _('Undefined'), 'gray'),
        (BACKUP_FORMAT_PBS_VM, _('PBS VM'), 'blue'),
        (BACKUP_FORMAT_PBS_CT, _('PBS CT'), 'green'),
        (BACKUP_FORMAT_ISO, _('ISO'), 'yellow'),
        (BACKUP_FORMAT_TZST, _('TZST'), 'purple'),
        (BACKUP_FORMAT_TGZ, _('TGZ'), 'red'),
        (BACKUP_FORMAT_QCOW2, _('QCOW2'), 'orange'),
        (BACKUP_FORMAT_RAW, _('RAW'), 'pink'),
        (BACKUP_FORMAT_TAR, _('TAR'), 'brown'),
        (BACKUP_FORMAT_TBZ, _('TBZ'), 'gray'),
    ]
