"""Filter form for Proxmox VM template inventory."""

from django import forms
from netbox.forms import NetBoxModelFilterSetForm, NetBoxModelForm
from utilities.forms.fields import DynamicModelChoiceField

from netbox_proxbox.models import (
    ProxmoxCluster,
    ProxmoxEndpoint,
    ProxmoxNode,
    ProxmoxVMTemplate,
)


class ProxmoxVMTemplateForm(NetBoxModelForm):
    """NetBox-side form. Proxmox is the source of truth; all fields are disabled."""

    class Meta:
        model = ProxmoxVMTemplate
        fields = (
            "name",
            "vmid",
            "proxmox_endpoint",
            "cluster",
            "node",
            "source_vm",
            "cloned_vms",
            "node_name",
            "proxmox_type",
            "status",
            "vcpus",
            "memory",
            "disk",
            "os_type",
            "description",
            "cloud_init_enabled",
            "net_config",
            "disk_config",
            "raw_config",
            "last_synced",
            "tags",
        )

    def __init__(self, *args, **kwargs):
        """Disable every editable field so operators cannot drift the row in NetBox."""
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.disabled = True
            field.help_text = (
                (field.help_text or "")
                + " Read-only mirror of Proxmox; edit on the Proxmox side."
            ).strip()


class ProxmoxVMTemplateFilterForm(NetBoxModelFilterSetForm):
    """Filter form for Proxmox VM template list views."""

    model = ProxmoxVMTemplate

    proxmox_endpoint = DynamicModelChoiceField(
        queryset=ProxmoxEndpoint.objects.all(),
        required=False,
    )
    cluster = DynamicModelChoiceField(
        queryset=ProxmoxCluster.objects.all(),
        required=False,
    )
    node = DynamicModelChoiceField(
        queryset=ProxmoxNode.objects.all(),
        required=False,
    )
    name = forms.CharField(required=False)
    vmid = forms.IntegerField(required=False)
    node_name = forms.CharField(required=False)
    proxmox_type = forms.CharField(required=False)
    status = forms.CharField(required=False)
    cloud_init_enabled = forms.BooleanField(required=False)
