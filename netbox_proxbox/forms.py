from django import forms

from utilities.forms import BootstrapMixin

from .models import VmResources

from virtualization.models import VirtualMachine, Cluster

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
 
class VmResourcesFilterForm(BootstrapMixin, forms.ModelForm):
    """Form for filtering VmResources instances."""

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

    virtual_machine = forms.ModelChoiceField(
        queryset=VirtualMachine.objects.all(),
        to_field_name="name",
        required=False,
    )

    node = forms.IntegerField(
        required=False,
    )

    proxmox_vm_id = forms.IntegerField(
        required=False,
    )

    class Meta:
        # model that will be used in the form
        model = VmResources

        # fields that will be auto-generated,
        # in this case all form fields are specified manually
        fields = []