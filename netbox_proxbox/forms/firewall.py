"""Create/edit and filter forms for Proxmox firewall models."""

from __future__ import annotations

from django import forms
from netbox.forms import NetBoxModelFilterSetForm, NetBoxModelForm
from utilities.forms.fields import DynamicModelChoiceField

from netbox_proxbox import models
from netbox_proxbox.choices import (
    FirewallLogLevelChoices,
    FirewallRuleTypeChoices,
    FirewallScopeChoices,
    FirewallSyncStatusChoices,
    FirewallZoneChoices,
)

_FIREWALL_STATUS_CHOICES = [("", "---------")] + list(FirewallSyncStatusChoices.CHOICES)


class _FirewallEndpointMixin:
    endpoint = DynamicModelChoiceField(
        queryset=models.ProxmoxEndpoint.objects.all(),
        required=False,
    )


class ProxmoxFirewallSecurityGroupForm(_FirewallEndpointMixin, NetBoxModelForm):
    class Meta:
        model = models.ProxmoxFirewallSecurityGroup
        fields = ("endpoint", "name", "comment", "status", "raw_config", "tags")


class ProxmoxFirewallSecurityGroupFilterForm(
    _FirewallEndpointMixin, NetBoxModelFilterSetForm
):
    model = models.ProxmoxFirewallSecurityGroup
    status = forms.ChoiceField(choices=_FIREWALL_STATUS_CHOICES, required=False)


class ProxmoxFirewallRuleForm(_FirewallEndpointMixin, NetBoxModelForm):
    proxmox_node = DynamicModelChoiceField(
        queryset=models.ProxmoxNode.objects.all(),
        required=False,
    )
    security_group = DynamicModelChoiceField(
        queryset=models.ProxmoxFirewallSecurityGroup.objects.all(),
        required=False,
    )

    class Meta:
        model = models.ProxmoxFirewallRule
        fields = (
            "endpoint",
            "zone",
            "proxmox_node",
            "security_group",
            "pos",
            "rule_type",
            "action",
            "enable",
            "macro",
            "iface",
            "source",
            "dest",
            "proto",
            "dport",
            "sport",
            "log",
            "icmp_type",
            "comment",
            "digest",
            "status",
            "raw_config",
            "tags",
        )


class ProxmoxFirewallRuleFilterForm(_FirewallEndpointMixin, NetBoxModelFilterSetForm):
    model = models.ProxmoxFirewallRule
    zone = forms.ChoiceField(
        choices=[("", "---------")] + list(FirewallZoneChoices.CHOICES),
        required=False,
    )
    rule_type = forms.ChoiceField(
        choices=[("", "---------")] + list(FirewallRuleTypeChoices.CHOICES),
        required=False,
    )
    status = forms.ChoiceField(choices=_FIREWALL_STATUS_CHOICES, required=False)


class ProxmoxFirewallIPSetForm(_FirewallEndpointMixin, NetBoxModelForm):
    class Meta:
        model = models.ProxmoxFirewallIPSet
        fields = (
            "endpoint",
            "scope",
            "virtual_machine",
            "name",
            "comment",
            "status",
            "raw_config",
            "tags",
        )
        widgets = {
            "virtual_machine": forms.Select,
        }


class ProxmoxFirewallIPSetFilterForm(_FirewallEndpointMixin, NetBoxModelFilterSetForm):
    model = models.ProxmoxFirewallIPSet
    scope = forms.ChoiceField(
        choices=[("", "---------")] + list(FirewallScopeChoices.CHOICES),
        required=False,
    )
    status = forms.ChoiceField(choices=_FIREWALL_STATUS_CHOICES, required=False)


class ProxmoxFirewallIPSetEntryForm(NetBoxModelForm):
    ipset = DynamicModelChoiceField(
        queryset=models.ProxmoxFirewallIPSet.objects.all(),
    )

    class Meta:
        model = models.ProxmoxFirewallIPSetEntry
        fields = ("ipset", "cidr", "comment", "nomatch", "raw_config", "tags")


class ProxmoxFirewallIPSetEntryFilterForm(NetBoxModelFilterSetForm):
    model = models.ProxmoxFirewallIPSetEntry
    ipset = DynamicModelChoiceField(
        queryset=models.ProxmoxFirewallIPSet.objects.all(),
        required=False,
    )


class ProxmoxFirewallAliasForm(_FirewallEndpointMixin, NetBoxModelForm):
    class Meta:
        model = models.ProxmoxFirewallAlias
        fields = (
            "endpoint",
            "scope",
            "virtual_machine",
            "name",
            "cidr",
            "comment",
            "status",
            "tags",
        )
        widgets = {
            "virtual_machine": forms.Select,
        }


class ProxmoxFirewallAliasFilterForm(_FirewallEndpointMixin, NetBoxModelFilterSetForm):
    model = models.ProxmoxFirewallAlias
    scope = forms.ChoiceField(
        choices=[("", "---------")] + list(FirewallScopeChoices.CHOICES),
        required=False,
    )
    status = forms.ChoiceField(choices=_FIREWALL_STATUS_CHOICES, required=False)


class ProxmoxFirewallOptionsForm(_FirewallEndpointMixin, NetBoxModelForm):
    proxmox_node = DynamicModelChoiceField(
        queryset=models.ProxmoxNode.objects.all(),
        required=False,
    )

    class Meta:
        model = models.ProxmoxFirewallOptions
        fields = (
            "endpoint",
            "zone",
            "proxmox_node",
            "virtual_machine",
            "enable",
            "policy_in",
            "policy_out",
            "options",
            "raw_config",
            "tags",
        )
        widgets = {
            "virtual_machine": forms.Select,
        }


class ProxmoxFirewallOptionsFilterForm(
    _FirewallEndpointMixin, NetBoxModelFilterSetForm
):
    model = models.ProxmoxFirewallOptions
    zone = forms.ChoiceField(
        choices=[("", "---------")] + list(FirewallZoneChoices.CHOICES),
        required=False,
    )
