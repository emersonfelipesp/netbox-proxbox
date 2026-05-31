"""Filter form for Proxmox VM template inventory."""

from django import forms
from netbox.forms import NetBoxModelFilterSetForm
from utilities.forms.fields import DynamicModelChoiceField

from netbox_proxbox.models import (
    ProxmoxCluster,
    ProxmoxEndpoint,
    ProxmoxNode,
    ProxmoxVMTemplate,
)


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
