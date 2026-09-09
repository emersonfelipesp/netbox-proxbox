"""Forms for plugin-owned Proxmox InfluxDB metrics."""

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
from netbox_proxbox.models.proxmox_metrics import masked_influx_url
from netbox_proxbox.models.plugin_settings import ProxboxPluginSettings
from netbox_proxbox.utils import encryption as enc_helpers
from netbox_proxbox.utils.metrics import (
    validate_metrics_interval,
    validate_metrics_time,
)


class _WriteOnlyTextarea(forms.Textarea):
    """Accept multiline input without ever redisplaying the token."""

    def format_value(self, value: object) -> None:
        return None


class ProxmoxMetricsInfluxDBForm(NetBoxModelForm):
    """Create/edit form without exposing stored token ciphertext or plaintext."""

    endpoint = DynamicModelChoiceField(
        queryset=ProxmoxEndpoint.objects.all(), required=True
    )
    proxmox_cluster = DynamicModelChoiceField(
        queryset=ProxmoxCluster.objects.all(), required=True
    )
    query_token = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        label=_("InfluxDB query token"),
        help_text=_(
            "Required on create or when enabling. Leave blank on edit to keep the stored token."
        ),
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
            "verify_tls",
            "enabled",
            "tags",
            "comments",
        )

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        instance = getattr(self, "instance", None)
        if instance and getattr(instance, "pk", None):
            display_url = masked_influx_url(instance.influx_url)
            if display_url == "********":
                self.initial["influx_url"] = ""
                self.fields["influx_url"].help_text = _(
                    "The stored URL is unsafe or invalid. Enter a replacement HTTPS URL."
                )
            else:
                self.initial["influx_url"] = display_url
            state = instance.credential_encryption_state
            if state == "Recovery required":
                warning = _(
                    " Recovery required: a stored token cannot be decrypted. "
                    "Enter a replacement token or use destructive recovery."
                )
                self.fields["query_token"].help_text += warning

    def _encryption_key(self) -> str:
        key = ProxboxPluginSettings.get_solo().encryption_key or ""
        if not key:
            raise forms.ValidationError(
                _("Configure the Proxbox encryption key before storing metrics tokens.")
            )
        return key

    def _apply_token_inputs(self) -> None:
        query_token = self.cleaned_data.get("query_token")
        if not query_token:
            return
        key = self._encryption_key()
        try:
            if query_token:
                self.instance.set_query_token(query_token, key=key)
        except enc_helpers.EncryptionError as exc:
            raise forms.ValidationError(str(exc)) from exc

    def _post_clean(self) -> None:
        if not self.errors:
            try:
                self._apply_token_inputs()
            except forms.ValidationError as exc:
                self.add_error(None, exc)
        super()._post_clean()


class ProxmoxMetricsInfluxDBFilterForm(NetBoxModelFilterSetForm):
    """Filter form for Proxmox InfluxDB metrics endpoint list views."""

    model = ProxmoxMetricsInfluxDB
    endpoint = DynamicModelChoiceField(
        queryset=ProxmoxEndpoint.objects.all(), required=False
    )
    proxmox_cluster = DynamicModelChoiceField(
        queryset=ProxmoxCluster.objects.all(), required=False
    )
    name = forms.CharField(required=False)
    enabled = forms.BooleanField(required=False)


class ProxmoxMetricsInfluxDBQueryForm(forms.Form):
    """Bounded metric query filters accepted by the NetBox data page."""

    time_start = forms.CharField(
        required=False,
        initial="-1h",
        help_text=_("Flux relative duration or RFC3339 start time."),
    )
    time_stop = forms.CharField(required=False, initial="now()")
    measurement = forms.CharField(required=True, max_length=128)
    field = forms.CharField(required=False, max_length=128)
    node = forms.CharField(required=False, max_length=128)
    vmid = forms.IntegerField(required=False, min_value=0)
    tag_key = forms.CharField(required=False, max_length=64)
    tag_value = forms.CharField(required=False, max_length=256)
    aggregation_every = forms.CharField(required=False, max_length=32)
    aggregation_function = forms.ChoiceField(
        required=False,
        choices=(
            ("count", "count"),
            ("first", "first"),
            ("last", "last"),
            ("max", "max"),
            ("mean", "mean"),
            ("min", "min"),
            ("sum", "sum"),
        ),
    )
    limit = forms.IntegerField(required=False, initial=500, min_value=1, max_value=5000)

    def clean_time_start(self) -> str:
        value = self.cleaned_data["time_start"] or "-1h"
        return validate_metrics_time(value)

    def clean_time_stop(self) -> str:
        value = self.cleaned_data["time_stop"] or "now()"
        return validate_metrics_time(value, allow_now=True)

    def clean_aggregation_every(self) -> str:
        value = self.cleaned_data["aggregation_every"]
        return validate_metrics_interval(value) if value else ""
