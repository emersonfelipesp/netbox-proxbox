"""Forms for endpoint-owned application services."""

from django import forms
from django.contrib.postgres.forms import SimpleArrayField
from ipam.models import IPAddress
from netbox.forms import NetBoxModelFilterSetForm, NetBoxModelForm
from utilities.forms.fields import (
    DynamicModelChoiceField,
    DynamicModelMultipleChoiceField,
)

from netbox_proxbox.models import ProxmoxEndpoint, ProxmoxEndpointService


class ProxmoxEndpointServiceForm(NetBoxModelForm):
    endpoint = DynamicModelChoiceField(queryset=ProxmoxEndpoint.objects.all())
    ipaddresses = DynamicModelMultipleChoiceField(
        queryset=IPAddress.objects.all(), required=False
    )
    ports = SimpleArrayField(
        forms.IntegerField(min_value=1, max_value=65535), delimiter=","
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        try:
            from netbox.context import current_request

            actor = getattr(current_request.get(), "user", None)
        except (ImportError, LookupError):
            actor = None
        queryset = ProxmoxEndpoint.objects.none()
        if getattr(actor, "is_authenticated", False) and getattr(
            actor, "is_active", False
        ):
            queryset = ProxmoxEndpoint.objects.restrict(actor, "change")
        self.fields["endpoint"].queryset = queryset

    class Meta:
        model = ProxmoxEndpointService
        fields = (
            "endpoint",
            "name",
            "protocol",
            "ports",
            "ipaddresses",
            "description",
            "comments",
            "tags",
        )


class ProxmoxEndpointServiceFilterForm(NetBoxModelFilterSetForm):
    model = ProxmoxEndpointService
    endpoint_id = DynamicModelMultipleChoiceField(
        queryset=ProxmoxEndpoint.objects.all(),
        required=False,
        label="Proxmox endpoint",
    )
    name = forms.CharField(required=False)
    protocol = forms.MultipleChoiceField(
        choices=ProxmoxEndpointService._meta.get_field("protocol").choices,
        required=False,
    )
