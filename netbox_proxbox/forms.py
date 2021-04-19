from django import forms

from utilities.forms import BootstrapMixin

from .models import VmResources

# 'forms.ModelForm' is a Django helper class  that allows building forms from models
# 'BootstrapMixin' comes from Netbox and adds CSS classes
class VmResourcesForm(BootstrapMixin, forms.ModelForm):
    """Form for creating a new BgpPeering object."""

    class Meta:
        model = VmResources
        fields = [
            "cluster",
            "node",
            "virtual_machine",
            "status",
            "proxmox_vm_id",
            "vcpus",
            "memory",
            "disk",
        ]