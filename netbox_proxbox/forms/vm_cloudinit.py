"""Define NetBox forms for the read-only Proxmox VM cloud-init record (issue #363)."""

from django import forms

from netbox.forms import (
    NetBoxModelFilterSetForm,
    NetBoxModelForm,
)
from utilities.forms.fields import DynamicModelChoiceField
from virtualization.models import VirtualMachine

from netbox_proxbox.models import ProxmoxVMCloudInit


class ProxmoxVMCloudInitForm(NetBoxModelForm):
    """NetBox-side form. Proxmox is the source of truth; all fields are disabled."""

    class Meta:
        model = ProxmoxVMCloudInit
        fields = (
            "virtual_machine",
            "ciuser",
            "sshkeys",
            "ipconfig0",
            "sshkeys_truncated",
            # create-time intent (displayed read-only; written by the NMS stack)
            "is_intent",
            "hostname",
            "search_domain",
            "dns_servers",
            "bridge",
            "vlan_tag",
            "gateway",
            "ip_cidr",
            "ssh_pwauth",
            "enable_agent",
            "nms_credential_id",
            "tags",
        )

    virtual_machine = DynamicModelChoiceField(
        queryset=VirtualMachine.objects.all(),
        required=True,
        help_text="Select a Virtual Machine.",
        label="Virtual Machine",
    )

    def __init__(self, *args, **kwargs):
        """Disable every editable field so operators cannot drift the row in NetBox."""
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.disabled = True
            field.help_text = (
                (field.help_text or "")
                + " Read-only mirror of Proxmox; edit on the Proxmox side."
            ).strip()


class ProxmoxVMCloudInitFilterForm(NetBoxModelFilterSetForm):
    """Filter controls for the cloud-init list view."""

    model = ProxmoxVMCloudInit

    virtual_machine = forms.ModelMultipleChoiceField(
        queryset=VirtualMachine.objects.all(),
        required=False,
    )

    ciuser = forms.CharField(
        required=False,
        label="Cloud-init user",
    )

    ipconfig0 = forms.CharField(
        required=False,
        label="ipconfig0",
    )

    sshkeys_truncated = forms.NullBooleanField(
        required=False,
        widget=forms.Select(
            choices=[("", "---------"), ("true", "Yes"), ("false", "No")],
        ),
        label="sshkeys truncated",
    )
