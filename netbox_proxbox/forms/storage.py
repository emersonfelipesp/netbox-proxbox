"""Forms for Proxmox storage records and list filtering."""

from django import forms

from netbox.forms import NetBoxModelFilterSetForm, NetBoxModelForm
from utilities.forms.fields import CommentField, DynamicModelChoiceField
from virtualization.models import Cluster

from netbox_proxbox.models import ProxmoxStorage


class ProxmoxStorageForm(NetBoxModelForm):
    """Create/edit form for synced Proxmox storage rows."""

    cluster = DynamicModelChoiceField(
        queryset=Cluster.objects.all(),
        required=True,
    )
    comments = CommentField()

    class Meta:
        model = ProxmoxStorage
        fields = (
            "cluster",
            "name",
            "storage_type",
            "content",
            "path",
            "nodes",
            "shared",
            "enabled",
            "tags",
            "comments",
        )


class ProxmoxStorageFilterForm(NetBoxModelFilterSetForm):
    """Filter form for Proxmox storage list views."""

    model = ProxmoxStorage

    cluster = DynamicModelChoiceField(
        queryset=Cluster.objects.all(),
        required=False,
    )
    name = forms.CharField(required=False)
    storage_type = forms.CharField(required=False)
    shared = forms.BooleanField(required=False)
    enabled = forms.BooleanField(required=False)
