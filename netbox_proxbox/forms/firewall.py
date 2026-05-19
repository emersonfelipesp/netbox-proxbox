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


class ProxmoxFirewallSecurityGroupForm(NetBoxModelForm):
    endpoint = DynamicModelChoiceField(
        queryset=models.ProxmoxEndpoint.objects.all(),
        required=False,
    )

    class Meta:
        model = models.ProxmoxFirewallSecurityGroup
        fields = ("endpoint", "name", "comment", "status", "raw_config", "tags")


class ProxmoxFirewallSecurityGroupFilterForm(NetBoxModelFilterSetForm):
    model = models.ProxmoxFirewallSecurityGroup
    endpoint = DynamicModelChoiceField(
        queryset=models.ProxmoxEndpoint.objects.all(),
        required=False,
    )
    status = forms.ChoiceField(
        choices=[("", "---------")] + list(FirewallSyncStatusChoices.CHOICES),
        required=False,
    )


class ProxmoxFirewallRuleForm(NetBoxModelForm):
    endpoint = DynamicModelChoiceField(
        queryset=models.ProxmoxEndpoint.objects.all(),
        required=False,
    )
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


class ProxmoxFirewallRuleFilterForm(NetBoxModelFilterSetForm):
    model = models.ProxmoxFirewallRule
    endpoint = DynamicModelChoiceField(
        queryset=models.ProxmoxEndpoint.objects.all(),
        required=False,
    )
    zone = forms.ChoiceField(
        choices=[("", "---------")] + list(FirewallZoneChoices.CHOICES),
        required=False,
    )
    rule_type = forms.ChoiceField(
        choices=[("", "---------")] + list(FirewallRuleTypeChoices.CHOICES),
        required=False,
    )
    status = forms.ChoiceField(
        choices=[("", "---------")] + list(FirewallSyncStatusChoices.CHOICES),
        required=False,
    )


class ProxmoxFirewallIPSetForm(NetBoxModelForm):
    endpoint = DynamicModelChoiceField(
        queryset=models.ProxmoxEndpoint.objects.all(),
        required=False,
    )

    class Meta:
        model = models.ProxmoxFirewallIPSet
        fields = ("endpoint", "scope", "virtual_machine", "name", "comment", "status", "raw_config", "tags")
        widgets = {
            "virtual_machine": forms.Select,
        }


class ProxmoxFirewallIPSetFilterForm(NetBoxModelFilterSetForm):
    model = models.ProxmoxFirewallIPSet
    endpoint = DynamicModelChoiceField(
        queryset=models.ProxmoxEndpoint.objects.all(),
        required=False,
    )
    scope = forms.ChoiceField(
        choices=[("", "---------")] + list(FirewallScopeChoices.CHOICES),
        required=False,
    )
    status = forms.ChoiceField(
        choices=[("", "---------")] + list(FirewallSyncStatusChoices.CHOICES),
        required=False,
    )


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


class ProxmoxFirewallAliasForm(NetBoxModelForm):
    endpoint = DynamicModelChoiceField(
        queryset=models.ProxmoxEndpoint.objects.all(),
        required=False,
    )

    class Meta:
        model = models.ProxmoxFirewallAlias
        fields = ("endpoint", "scope", "virtual_machine", "name", "cidr", "comment", "status", "tags")
        widgets = {
            "virtual_machine": forms.Select,
        }


class ProxmoxFirewallAliasFilterForm(NetBoxModelFilterSetForm):
    model = models.ProxmoxFirewallAlias
    endpoint = DynamicModelChoiceField(
        queryset=models.ProxmoxEndpoint.objects.all(),
        required=False,
    )
    scope = forms.ChoiceField(
        choices=[("", "---------")] + list(FirewallScopeChoices.CHOICES),
        required=False,
    )
    status = forms.ChoiceField(
        choices=[("", "---------")] + list(FirewallSyncStatusChoices.CHOICES),
        required=False,
    )


class ProxmoxFirewallOptionsForm(NetBoxModelForm):
    endpoint = DynamicModelChoiceField(
        queryset=models.ProxmoxEndpoint.objects.all(),
        required=False,
    )
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


class ProxmoxFirewallOptionsFilterForm(NetBoxModelFilterSetForm):
    model = models.ProxmoxFirewallOptions
    endpoint = DynamicModelChoiceField(
        queryset=models.ProxmoxEndpoint.objects.all(),
        required=False,
    )
    zone = forms.ChoiceField(
        choices=[("", "---------")] + list(FirewallZoneChoices.CHOICES),
        required=False,
    )
