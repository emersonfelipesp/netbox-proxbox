from django import forms

from utilities.forms import BootstrapMixin

from .models import ProxmoxVM

from virtualization.models import VirtualMachine, Cluster

# 'forms.ModelForm' is a Django helper class  that allows building forms from models
# 'BootstrapMixin' comes from Netbox and adds CSS classes
class ProxmoxVMForm(BootstrapMixin, forms.ModelForm):
    """Form for creating a new BgpPeering object."""

    class Meta:
        model = ProxmoxVM
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
 
class ProxmoxVMFilterForm(BootstrapMixin, forms.ModelForm):
    """Form for filtering ProxmoxVM instances."""

    q = forms.CharField(required=False, label="Search")

    # Link it to Cluster object
    cluster = forms.ModelChoiceField(
        # drop-down with all Cluster objects available
        queryset=Cluster.objects.all(), 

        # field is optional
        required=False,

        # when given item is selected, return 'name' attribute to be returned
        to_field_name="name"
    )

    node = forms.IntegerField(
        required=False,
        label="Node (Server)"
    )

    virtual_machine = forms.ModelChoiceField(
        queryset=VirtualMachine.objects.all(),
        to_field_name="name",
        required=False,

        # label = defines how field will appear in GUI
        label="Proxmox VM/CT"
    )

    proxmox_vm_id = forms.IntegerField(
        required=False,
        label="Proxmox VM/CT ID"
    )

    class Meta:
        # model that will be used in the form
        model = ProxmoxVM

        # fields that will be auto-generated,
        # in this case all form fields are specified manually
        fields = []