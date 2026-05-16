"""NetBox forms for netbox-ceph.

v1 reflects Proxmox-managed Ceph state read-only, so the only editable form
is ``CephPluginSettingsForm`` for branch-aware sync behavior. All other forms
are filter-only.
"""

from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _
from netbox.forms import NetBoxModelFilterSetForm, NetBoxModelForm
from utilities.forms.fields import DynamicModelChoiceField

from netbox_ceph.models import (
    CephCluster,
    CephCrushRule,
    CephDaemon,
    CephFilesystem,
    CephFlag,
    CephHealthCheck,
    CephOSD,
    CephPluginSettings,
    CephPool,
)


class CephPluginSettingsForm(NetBoxModelForm):
    class Meta:
        model = CephPluginSettings
        fields = (
            "branching_enabled",
            "branch_name_prefix",
            "branch_on_conflict",
            "tags",
        )


class _EndpointFilterMixin:
    endpoint = DynamicModelChoiceField(
        queryset=None,  # lazy below
        required=False,
        label=_("Proxmox endpoint"),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from netbox_proxbox.models import ProxmoxEndpoint  # noqa: PLC0415

        self.fields["endpoint"].queryset = ProxmoxEndpoint.objects.all()


class CephClusterFilterForm(_EndpointFilterMixin, NetBoxModelFilterSetForm):
    model = CephCluster
    name = forms.CharField(required=False)
    fsid = forms.CharField(required=False)
    health = forms.CharField(required=False)


class CephDaemonFilterForm(_EndpointFilterMixin, NetBoxModelFilterSetForm):
    model = CephDaemon
    daemon_type = forms.CharField(required=False)
    name = forms.CharField(required=False)
    state = forms.CharField(required=False)


class CephOSDFilterForm(_EndpointFilterMixin, NetBoxModelFilterSetForm):
    model = CephOSD
    osd_id = forms.IntegerField(required=False)
    up = forms.NullBooleanField(required=False)
    in_cluster = forms.NullBooleanField(required=False)
    device_class = forms.CharField(required=False)


class CephPoolFilterForm(_EndpointFilterMixin, NetBoxModelFilterSetForm):
    model = CephPool
    name = forms.CharField(required=False)
    application = forms.CharField(required=False)


class CephFilesystemFilterForm(_EndpointFilterMixin, NetBoxModelFilterSetForm):
    model = CephFilesystem
    name = forms.CharField(required=False)


class CephCrushRuleFilterForm(_EndpointFilterMixin, NetBoxModelFilterSetForm):
    model = CephCrushRule
    name = forms.CharField(required=False)
    rule_type = forms.CharField(required=False)
    device_class = forms.CharField(required=False)


class CephFlagFilterForm(_EndpointFilterMixin, NetBoxModelFilterSetForm):
    model = CephFlag
    name = forms.CharField(required=False)
    enabled = forms.NullBooleanField(required=False)


class CephHealthCheckFilterForm(_EndpointFilterMixin, NetBoxModelFilterSetForm):
    model = CephHealthCheck
    name = forms.CharField(required=False)
    severity = forms.CharField(required=False)
    source = forms.CharField(required=False)
