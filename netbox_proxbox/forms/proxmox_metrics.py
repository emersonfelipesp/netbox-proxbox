"""Forms for Proxmox metrics integration metadata."""

from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _
from netbox.forms import NetBoxModelFilterSetForm, NetBoxModelForm
from utilities.forms.fields import CommentField, DynamicModelChoiceField

from netbox_proxbox.models import (
    ProxmoxCluster,
    ProxmoxEndpoint,
    ProxmoxMetricsInfluxDB,
)
from netbox_proxbox.models.proxmox_metrics import (
    MASKED_INFLUX_URL,
    masked_influx_url,
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

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        stored_url = getattr(self.instance, "influx_url", "")
        if getattr(self.instance, "pk", None) and (
            masked_influx_url(stored_url) == MASKED_INFLUX_URL
        ):
            # ModelForm's per-instance value lives in ``self.initial`` rather
            # than on the field. Clear both so a bypass-written credential is
            # never reflected into the edit page.
            self.initial["influx_url"] = ""
            self.fields["influx_url"].initial = ""
            self.fields["influx_url"].help_text = _(
                "A non-conforming stored URL was hidden. Enter a credential-free "
                "HTTP(S) base URL to replace it, or delete this mapping to clear it."
            )

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
