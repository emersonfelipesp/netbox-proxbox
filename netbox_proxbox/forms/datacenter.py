"""Create/edit and filter forms for Proxmox datacenter models."""

from __future__ import annotations

from django import forms
from netbox.forms import NetBoxModelFilterSetForm, NetBoxModelForm
from utilities.forms.fields import DynamicModelChoiceField

from netbox_proxbox import models
from netbox_proxbox.choices import FirewallSyncStatusChoices


def _choices_2tuple(choice_set):
    return [(value, label) for value, label, *_ in choice_set.CHOICES]


_STATUS_CHOICES = [("", "---------")] + _choices_2tuple(FirewallSyncStatusChoices)


class _DatacenterEndpointMixin:
    endpoint = DynamicModelChoiceField(
        queryset=models.ProxmoxEndpoint.objects.all(),
        required=False,
    )


class ProxmoxDatacenterCpuModelForm(_DatacenterEndpointMixin, NetBoxModelForm):
    class Meta:
        model = models.ProxmoxDatacenterCpuModel
        fields = (
            "endpoint",
            "cluster_name",
            "cputype",
            "base_cputype",
            "flags",
            "vendor_id",
            "level",
            "description",
            "status",
            "raw_config",
            "tags",
        )


class ProxmoxDatacenterCpuModelFilterForm(
    _DatacenterEndpointMixin, NetBoxModelFilterSetForm
):
    model = models.ProxmoxDatacenterCpuModel
    status = forms.ChoiceField(choices=_STATUS_CHOICES, required=False)
