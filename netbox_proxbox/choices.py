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