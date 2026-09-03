"""Forms for operator-owned virtual-machine intent."""

from django import forms
from netbox.forms import NetBoxModelFilterSetForm, NetBoxModelForm
from utilities.forms.fields import DynamicModelChoiceField
from virtualization.models import VirtualMachine

from netbox_proxbox.models import ProxmoxVMIntent


class ProxmoxVMIntentForm(NetBoxModelForm):
    """Edit only operator-controlled intent values; apply stamps stay excluded."""

    virtual_machine = DynamicModelChoiceField(
        queryset=VirtualMachine.objects.all(),
        required=True,
        label="Virtual machine",
    )

    def clean_virtual_machine(self):
        """Keep an existing intent attached to its original virtual machine."""
        virtual_machine = self.cleaned_data["virtual_machine"]
        if getattr(self.instance, "pk", None) is not None and getattr(
            self.instance, "virtual_machine_id", None
        ) != getattr(virtual_machine, "pk", None):
            raise forms.ValidationError(
                "The virtual machine for an existing Proxmox VM intent cannot be changed."
            )
        return virtual_machine

    class Meta:
        model = ProxmoxVMIntent
        fields = (
            "virtual_machine",
            "target_node",
            "target_storage",
            "iso",
            "template_vmid",
            "swap",
            "rootfs",
            "ostemplate",
            "cloud_init_user",
            "cloud_init_ssh_keys",
            "cloud_init_user_data",
            "cloud_init_network",
            "tags",
        )
        widgets = {
            "cloud_init_ssh_keys": forms.Textarea(attrs={"rows": 4}),
            "cloud_init_user_data": forms.Textarea(attrs={"rows": 8}),
            "cloud_init_network": forms.Textarea(attrs={"rows": 6}),
        }


class ProxmoxVMIntentFilterForm(NetBoxModelFilterSetForm):
    model = ProxmoxVMIntent

    virtual_machine = forms.ModelMultipleChoiceField(
        queryset=VirtualMachine.objects.all(), required=False
    )
    target_node = forms.CharField(required=False)
    target_storage = forms.CharField(required=False)
