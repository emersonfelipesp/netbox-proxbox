"""Forms for Proxmox metrics integration metadata."""

from __future__ import annotations

from django import forms
from netbox.forms import NetBoxModelFilterSetForm, NetBoxModelForm
from utilities.forms.fields import CommentField, DynamicModelChoiceField

from netbox_proxbox.models import (
    ProxmoxCluster,
    ProxmoxEndpoint,
    ProxmoxMetricsInfluxDB,
)


class ProxmoxMetricsInfluxDBForm(NetBoxModelForm):
    """Create/edit form for Proxmox cluster InfluxDB metrics endpoints."""

    endpoint = DynamicModelChoiceField(
        queryset=ProxmoxEndpoint.objects.all(),
        required=True,
    )
    proxmox_cluster = DynamicModelChoiceField(
        queryset=ProxmoxCluster.objects.all(),
        required=True,
    )
    comments = CommentField()

    class Meta:
        model = ProxmoxMetricsInfluxDB
        fields = (
            "name",
            "endpoint",
            "proxmox_cluster",
            "influx_url",
            "org",
            "bucket",
            "measurement_prefix",
            "query_token_secret_ref",
            "writer_token_secret_ref",
            "verify_tls",
            "enabled",
            "tags",
            "comments",
        )


class ProxmoxMetricsInfluxDBFilterForm(NetBoxModelFilterSetForm):
    """Filter form for Proxmox InfluxDB metrics endpoint list views."""

    model = ProxmoxMetricsInfluxDB

    endpoint = DynamicModelChoiceField(
        queryset=ProxmoxEndpoint.objects.all(),
        required=False,
    )
    proxmox_cluster = DynamicModelChoiceField(
        queryset=ProxmoxCluster.objects.all(),
        required=False,
    )
    name = forms.CharField(required=False)
    enabled = forms.BooleanField(required=False)
