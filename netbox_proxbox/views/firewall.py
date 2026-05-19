"""NetBox CRUD views for Proxmox firewall models."""
from __future__ import annotations

from netbox.views.generic import (
    ObjectDeleteView,
    ObjectEditView,
    ObjectListView,
    ObjectView,
)
from utilities.views import register_model_view

from netbox_proxbox import filtersets, forms, models, tables

_SG_QS = models.ProxmoxFirewallSecurityGroup.objects.select_related("endpoint")
_RULE_QS = models.ProxmoxFirewallRule.objects.select_related(
    "endpoint", "proxmox_node", "virtual_machine", "security_group"
)
_IPSET_QS = models.ProxmoxFirewallIPSet.objects.select_related("endpoint", "virtual_machine")
_IPSET_ENTRY_QS = models.ProxmoxFirewallIPSetEntry.objects.select_related("ipset")
_ALIAS_QS = models.ProxmoxFirewallAlias.objects.select_related("endpoint", "virtual_machine")
_OPTIONS_QS = models.ProxmoxFirewallOptions.objects.select_related(
    "endpoint", "proxmox_node", "virtual_machine"
)


# ── ProxmoxFirewallSecurityGroup ─────────────────────────────────────────────

@register_model_view(models.ProxmoxFirewallSecurityGroup, "list", path="", detail=False)
class ProxmoxFirewallSecurityGroupListView(ObjectListView):
    queryset = _SG_QS
    table = tables.ProxmoxFirewallSecurityGroupTable
    filterset = filtersets.ProxmoxFirewallSecurityGroupFilterSet
    filterset_form = forms.ProxmoxFirewallSecurityGroupFilterForm


@register_model_view(models.ProxmoxFirewallSecurityGroup)
class ProxmoxFirewallSecurityGroupView(ObjectView):
    queryset = _SG_QS


@register_model_view(models.ProxmoxFirewallSecurityGroup, "edit")
class ProxmoxFirewallSecurityGroupEditView(ObjectEditView):
    queryset = _SG_QS
    form = forms.ProxmoxFirewallSecurityGroupForm
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewallsecuritygroup_list"


@register_model_view(models.ProxmoxFirewallSecurityGroup, "delete")
class ProxmoxFirewallSecurityGroupDeleteView(ObjectDeleteView):
    queryset = _SG_QS
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewallsecuritygroup_list"


# ── ProxmoxFirewallRule ───────────────────────────────────────────────────────

@register_model_view(models.ProxmoxFirewallRule, "list", path="", detail=False)
class ProxmoxFirewallRuleListView(ObjectListView):
    queryset = _RULE_QS
    table = tables.ProxmoxFirewallRuleTable
    filterset = filtersets.ProxmoxFirewallRuleFilterSet
    filterset_form = forms.ProxmoxFirewallRuleFilterForm


@register_model_view(models.ProxmoxFirewallRule)
class ProxmoxFirewallRuleView(ObjectView):
    queryset = _RULE_QS


@register_model_view(models.ProxmoxFirewallRule, "edit")
class ProxmoxFirewallRuleEditView(ObjectEditView):
    queryset = _RULE_QS
    form = forms.ProxmoxFirewallRuleForm
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewallrule_list"


@register_model_view(models.ProxmoxFirewallRule, "delete")
class ProxmoxFirewallRuleDeleteView(ObjectDeleteView):
    queryset = _RULE_QS
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewallrule_list"


# ── ProxmoxFirewallIPSet ──────────────────────────────────────────────────────

@register_model_view(models.ProxmoxFirewallIPSet, "list", path="", detail=False)
class ProxmoxFirewallIPSetListView(ObjectListView):
    queryset = _IPSET_QS
    table = tables.ProxmoxFirewallIPSetTable
    filterset = filtersets.ProxmoxFirewallIPSetFilterSet
    filterset_form = forms.ProxmoxFirewallIPSetFilterForm


@register_model_view(models.ProxmoxFirewallIPSet)
class ProxmoxFirewallIPSetView(ObjectView):
    queryset = _IPSET_QS


@register_model_view(models.ProxmoxFirewallIPSet, "edit")
class ProxmoxFirewallIPSetEditView(ObjectEditView):
    queryset = _IPSET_QS
    form = forms.ProxmoxFirewallIPSetForm
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewallipset_list"


@register_model_view(models.ProxmoxFirewallIPSet, "delete")
class ProxmoxFirewallIPSetDeleteView(ObjectDeleteView):
    queryset = _IPSET_QS
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewallipset_list"


# ── ProxmoxFirewallIPSetEntry ─────────────────────────────────────────────────

@register_model_view(models.ProxmoxFirewallIPSetEntry, "list", path="", detail=False)
class ProxmoxFirewallIPSetEntryListView(ObjectListView):
    queryset = _IPSET_ENTRY_QS
    table = tables.ProxmoxFirewallIPSetEntryTable
    filterset = filtersets.ProxmoxFirewallIPSetEntryFilterSet
    filterset_form = forms.ProxmoxFirewallIPSetEntryFilterForm


@register_model_view(models.ProxmoxFirewallIPSetEntry)
class ProxmoxFirewallIPSetEntryView(ObjectView):
    queryset = _IPSET_ENTRY_QS


@register_model_view(models.ProxmoxFirewallIPSetEntry, "edit")
class ProxmoxFirewallIPSetEntryEditView(ObjectEditView):
    queryset = _IPSET_ENTRY_QS
    form = forms.ProxmoxFirewallIPSetEntryForm
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewallipsetentry_list"


@register_model_view(models.ProxmoxFirewallIPSetEntry, "delete")
class ProxmoxFirewallIPSetEntryDeleteView(ObjectDeleteView):
    queryset = _IPSET_ENTRY_QS
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewallipsetentry_list"


# ── ProxmoxFirewallAlias ──────────────────────────────────────────────────────

@register_model_view(models.ProxmoxFirewallAlias, "list", path="", detail=False)
class ProxmoxFirewallAliasListView(ObjectListView):
    queryset = _ALIAS_QS
    table = tables.ProxmoxFirewallAliasTable
    filterset = filtersets.ProxmoxFirewallAliasFilterSet
    filterset_form = forms.ProxmoxFirewallAliasFilterForm


@register_model_view(models.ProxmoxFirewallAlias)
class ProxmoxFirewallAliasView(ObjectView):
    queryset = _ALIAS_QS


@register_model_view(models.ProxmoxFirewallAlias, "edit")
class ProxmoxFirewallAliasEditView(ObjectEditView):
    queryset = _ALIAS_QS
    form = forms.ProxmoxFirewallAliasForm
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewallalias_list"


@register_model_view(models.ProxmoxFirewallAlias, "delete")
class ProxmoxFirewallAliasDeleteView(ObjectDeleteView):
    queryset = _ALIAS_QS
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewallalias_list"


# ── ProxmoxFirewallOptions ────────────────────────────────────────────────────

@register_model_view(models.ProxmoxFirewallOptions, "list", path="", detail=False)
class ProxmoxFirewallOptionsListView(ObjectListView):
    queryset = _OPTIONS_QS
    table = tables.ProxmoxFirewallOptionsTable
    filterset = filtersets.ProxmoxFirewallOptionsFilterSet
    filterset_form = forms.ProxmoxFirewallOptionsFilterForm


@register_model_view(models.ProxmoxFirewallOptions)
class ProxmoxFirewallOptionsView(ObjectView):
    queryset = _OPTIONS_QS


@register_model_view(models.ProxmoxFirewallOptions, "edit")
class ProxmoxFirewallOptionsEditView(ObjectEditView):
    queryset = _OPTIONS_QS
    form = forms.ProxmoxFirewallOptionsForm
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewalloptions_list"


@register_model_view(models.ProxmoxFirewallOptions, "delete")
class ProxmoxFirewallOptionsDeleteView(ObjectDeleteView):
    queryset = _OPTIONS_QS
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewalloptions_list"
