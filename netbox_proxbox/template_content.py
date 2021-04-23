"""Template contet temporarily disabled

from extras.plugins import PluginTemplateExtension
from .models import ProxmoxVM


class ProxmoxVMCustomFields(PluginTemplateExtension):
    model = 'virtualization.virtualmachine'

    def left_page(self):
        return self.render(
            'netbox_proxbox/virtualmachine_proxmox_fields.html'
        )

template_extensions = [ProxmoxVMCustomFields]
"""