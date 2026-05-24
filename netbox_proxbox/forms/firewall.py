"""Create/edit and filter forms for Proxmox firewall models."""

from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError
from netbox.forms import NetBoxModelFilterSetForm, NetBoxModelForm
from utilities.forms.fields import DynamicModelChoiceField
from virtualization.models import VirtualMachine

from netbox_proxbox import models
from netbox_proxbox.choices import (
    FirewallLogLevelChoices,
    FirewallRuleTypeChoices,
    FirewallScopeChoices,
    FirewallSyncStatusChoices,
    FirewallZoneChoices,
)
from netbox_proxbox.intent.firewall_common import (
    mark_firewall_object_stale,
    validation_errors_for_options,
    validation_errors_for_rule,
    validation_errors_for_scoped_object,
)


def _choices_2tuple(choice_set):
    """Strip color from a NetBox ChoiceSet so Django's ChoiceField can iterate."""
    return [(value, label) for value, label, *_ in choice_set.CHOICES]


_FIREWALL_STATUS_CHOICES = [("", "---------")] + _choices_2tuple(
    FirewallSyncStatusChoices
)


class _FirewallEndpointMixin:
    endpoint = DynamicModelChoiceField(
        queryset=models.ProxmoxEndpoint.objects.all(),
        required=False,
    )


class _FirewallManualEditMixin:
    """Mark manually edited firewall objects stale until pushed or re-synced."""

    def save(self, commit=True):
        obj = super().save(commit=False)
        mark_firewall_object_stale(obj)
        if commit:
            obj.save()
            self.save_m2m()
            status_target = getattr(obj, "ipset", None)
            if status_target is not None and hasattr(status_target, "save"):
                status_target.save(update_fields=["status"])
        return obj


class ProxmoxFirewallSecurityGroupForm(
    _FirewallManualEditMixin, _FirewallEndpointMixin, NetBoxModelForm
):
    class Meta:
        model = models.ProxmoxFirewallSecurityGroup
        fields = ("endpoint", "name", "comment", "status", "raw_config", "tags")


class ProxmoxFirewallSecurityGroupFilterForm(
    _FirewallEndpointMixin, NetBoxModelFilterSetForm
):
    model = models.ProxmoxFirewallSecurityGroup
    status = forms.ChoiceField(choices=_FIREWALL_STATUS_CHOICES, required=False)


class ProxmoxFirewallRuleForm(
    _FirewallManualEditMixin, _FirewallEndpointMixin, NetBoxModelForm
):
    proxmox_node = DynamicModelChoiceField(
        queryset=models.ProxmoxNode.objects.all(),
        required=False,
    )
    virtual_machine = DynamicModelChoiceField(
        queryset=VirtualMachine.objects.all(),
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
            "virtual_machine",
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

    def clean(self):
        cleaned_data = super().clean()
        errors = validation_errors_for_rule(cleaned_data, instance=self.instance)
        if errors:
            raise ValidationError(errors)
        return cleaned_data


class ProxmoxFirewallRuleFilterForm(_FirewallEndpointMixin, NetBoxModelFilterSetForm):
    model = models.ProxmoxFirewallRule
    zone = forms.ChoiceField(
        choices=[("", "---------")] + _choices_2tuple(FirewallZoneChoices),
        required=False,
    )
    rule_type = forms.ChoiceField(
        choices=[("", "---------")] + _choices_2tuple(FirewallRuleTypeChoices),
        required=False,
    )
    status = forms.ChoiceField(choices=_FIREWALL_STATUS_CHOICES, required=False)


class ProxmoxFirewallIPSetForm(
    _FirewallManualEditMixin, _FirewallEndpointMixin, NetBoxModelForm
):
    virtual_machine = DynamicModelChoiceField(
        queryset=VirtualMachine.objects.all(),
        required=False,
    )

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

    def clean(self):
        cleaned_data = super().clean()
        errors = validation_errors_for_scoped_object(
            cleaned_data, instance=self.instance
        )
        if errors:
            raise ValidationError(errors)
        return cleaned_data


class ProxmoxFirewallIPSetFilterForm(_FirewallEndpointMixin, NetBoxModelFilterSetForm):
    model = models.ProxmoxFirewallIPSet
    scope = forms.ChoiceField(
        choices=[("", "---------")] + _choices_2tuple(FirewallScopeChoices),
        required=False,
    )
    status = forms.ChoiceField(choices=_FIREWALL_STATUS_CHOICES, required=False)


class ProxmoxFirewallIPSetEntryForm(_FirewallManualEditMixin, NetBoxModelForm):
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


class ProxmoxFirewallAliasForm(
    _FirewallManualEditMixin, _FirewallEndpointMixin, NetBoxModelForm
):
    virtual_machine = DynamicModelChoiceField(
        queryset=VirtualMachine.objects.all(),
        required=False,
    )

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

    def clean(self):
        cleaned_data = super().clean()
        errors = validation_errors_for_scoped_object(
            cleaned_data, instance=self.instance
        )
        if errors:
            raise ValidationError(errors)
        return cleaned_data


class ProxmoxFirewallAliasFilterForm(_FirewallEndpointMixin, NetBoxModelFilterSetForm):
    model = models.ProxmoxFirewallAlias
    scope = forms.ChoiceField(
        choices=[("", "---------")] + _choices_2tuple(FirewallScopeChoices),
        required=False,
    )
    status = forms.ChoiceField(choices=_FIREWALL_STATUS_CHOICES, required=False)


class ProxmoxFirewallOptionsForm(
    _FirewallManualEditMixin, _FirewallEndpointMixin, NetBoxModelForm
):
    proxmox_node = DynamicModelChoiceField(
        queryset=models.ProxmoxNode.objects.all(),
        required=False,
    )
    virtual_machine = DynamicModelChoiceField(
        queryset=VirtualMachine.objects.all(),
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
            "status",
            "raw_config",
            "tags",
        )
        widgets = {
            "virtual_machine": forms.Select,
        }

    def clean(self):
        cleaned_data = super().clean()
        errors = validation_errors_for_options(cleaned_data, instance=self.instance)
        if errors:
            raise ValidationError(errors)
        return cleaned_data


class ProxmoxFirewallOptionsFilterForm(
    _FirewallEndpointMixin, NetBoxModelFilterSetForm
):
    model = models.ProxmoxFirewallOptions
    zone = forms.ChoiceField(
        choices=[("", "---------")] + _choices_2tuple(FirewallZoneChoices),
        required=False,
    )
    status = forms.ChoiceField(choices=_FIREWALL_STATUS_CHOICES, required=False)
