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


# ── ProxmoxFirewallSecurityGroup ─────────────────────────────────────────────

@register_model_view(models.ProxmoxFirewallSecurityGroup, "list", path="", detail=False)
class ProxmoxFirewallSecurityGroupListView(ObjectListView):
    queryset = models.ProxmoxFirewallSecurityGroup.objects.select_related("endpoint")
    table = tables.ProxmoxFirewallSecurityGroupTable
    filterset = filtersets.ProxmoxFirewallSecurityGroupFilterSet
    filterset_form = forms.ProxmoxFirewallSecurityGroupFilterForm


@register_model_view(models.ProxmoxFirewallSecurityGroup)
class ProxmoxFirewallSecurityGroupView(ObjectView):
    queryset = models.ProxmoxFirewallSecurityGroup.objects.select_related("endpoint")


@register_model_view(models.ProxmoxFirewallSecurityGroup, "edit")
class ProxmoxFirewallSecurityGroupEditView(ObjectEditView):
    queryset = models.ProxmoxFirewallSecurityGroup.objects.select_related("endpoint")
    form = forms.ProxmoxFirewallSecurityGroupForm
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewallsecuritygroup_list"


@register_model_view(models.ProxmoxFirewallSecurityGroup, "delete")
class ProxmoxFirewallSecurityGroupDeleteView(ObjectDeleteView):
    queryset = models.ProxmoxFirewallSecurityGroup.objects.all()
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewallsecuritygroup_list"


# ── ProxmoxFirewallRule ───────────────────────────────────────────────────────

@register_model_view(models.ProxmoxFirewallRule, "list", path="", detail=False)
class ProxmoxFirewallRuleListView(ObjectListView):
    queryset = models.ProxmoxFirewallRule.objects.select_related(
        "endpoint", "proxmox_node", "virtual_machine", "security_group"
    )
    table = tables.ProxmoxFirewallRuleTable
    filterset = filtersets.ProxmoxFirewallRuleFilterSet
    filterset_form = forms.ProxmoxFirewallRuleFilterForm


@register_model_view(models.ProxmoxFirewallRule)
class ProxmoxFirewallRuleView(ObjectView):
    queryset = models.ProxmoxFirewallRule.objects.select_related(
        "endpoint", "proxmox_node", "virtual_machine", "security_group"
    )


@register_model_view(models.ProxmoxFirewallRule, "edit")
class ProxmoxFirewallRuleEditView(ObjectEditView):
    queryset = models.ProxmoxFirewallRule.objects.select_related(
        "endpoint", "proxmox_node", "virtual_machine", "security_group"
    )
    form = forms.ProxmoxFirewallRuleForm
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewallrule_list"


@register_model_view(models.ProxmoxFirewallRule, "delete")
class ProxmoxFirewallRuleDeleteView(ObjectDeleteView):
    queryset = models.ProxmoxFirewallRule.objects.all()
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewallrule_list"


# ── ProxmoxFirewallIPSet ──────────────────────────────────────────────────────

@register_model_view(models.ProxmoxFirewallIPSet, "list", path="", detail=False)
class ProxmoxFirewallIPSetListView(ObjectListView):
    queryset = models.ProxmoxFirewallIPSet.objects.select_related("endpoint", "virtual_machine")
    table = tables.ProxmoxFirewallIPSetTable
    filterset = filtersets.ProxmoxFirewallIPSetFilterSet
    filterset_form = forms.ProxmoxFirewallIPSetFilterForm


@register_model_view(models.ProxmoxFirewallIPSet)
class ProxmoxFirewallIPSetView(ObjectView):
    queryset = models.ProxmoxFirewallIPSet.objects.select_related("endpoint", "virtual_machine")


@register_model_view(models.ProxmoxFirewallIPSet, "edit")
class ProxmoxFirewallIPSetEditView(ObjectEditView):
    queryset = models.ProxmoxFirewallIPSet.objects.select_related("endpoint", "virtual_machine")
    form = forms.ProxmoxFirewallIPSetForm
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewallipset_list"


@register_model_view(models.ProxmoxFirewallIPSet, "delete")
class ProxmoxFirewallIPSetDeleteView(ObjectDeleteView):
    queryset = models.ProxmoxFirewallIPSet.objects.all()
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewallipset_list"


# ── ProxmoxFirewallIPSetEntry ─────────────────────────────────────────────────

@register_model_view(models.ProxmoxFirewallIPSetEntry, "list", path="", detail=False)
class ProxmoxFirewallIPSetEntryListView(ObjectListView):
    queryset = models.ProxmoxFirewallIPSetEntry.objects.select_related("ipset")
    table = tables.ProxmoxFirewallIPSetEntryTable
    filterset = filtersets.ProxmoxFirewallIPSetEntryFilterSet
    filterset_form = forms.ProxmoxFirewallIPSetEntryFilterForm


@register_model_view(models.ProxmoxFirewallIPSetEntry)
class ProxmoxFirewallIPSetEntryView(ObjectView):
    queryset = models.ProxmoxFirewallIPSetEntry.objects.select_related("ipset")


@register_model_view(models.ProxmoxFirewallIPSetEntry, "edit")
class ProxmoxFirewallIPSetEntryEditView(ObjectEditView):
    queryset = models.ProxmoxFirewallIPSetEntry.objects.select_related("ipset")
    form = forms.ProxmoxFirewallIPSetEntryForm
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewallipsetentry_list"


@register_model_view(models.ProxmoxFirewallIPSetEntry, "delete")
class ProxmoxFirewallIPSetEntryDeleteView(ObjectDeleteView):
    queryset = models.ProxmoxFirewallIPSetEntry.objects.all()
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewallipsetentry_list"


# ── ProxmoxFirewallAlias ──────────────────────────────────────────────────────

@register_model_view(models.ProxmoxFirewallAlias, "list", path="", detail=False)
class ProxmoxFirewallAliasListView(ObjectListView):
    queryset = models.ProxmoxFirewallAlias.objects.select_related("endpoint", "virtual_machine")
    table = tables.ProxmoxFirewallAliasTable
    filterset = filtersets.ProxmoxFirewallAliasFilterSet
    filterset_form = forms.ProxmoxFirewallAliasFilterForm


@register_model_view(models.ProxmoxFirewallAlias)
class ProxmoxFirewallAliasView(ObjectView):
    queryset = models.ProxmoxFirewallAlias.objects.select_related("endpoint", "virtual_machine")


@register_model_view(models.ProxmoxFirewallAlias, "edit")
class ProxmoxFirewallAliasEditView(ObjectEditView):
    queryset = models.ProxmoxFirewallAlias.objects.select_related("endpoint", "virtual_machine")
    form = forms.ProxmoxFirewallAliasForm
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewallalias_list"


@register_model_view(models.ProxmoxFirewallAlias, "delete")
class ProxmoxFirewallAliasDeleteView(ObjectDeleteView):
    queryset = models.ProxmoxFirewallAlias.objects.all()
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewallalias_list"


# ── ProxmoxFirewallOptions ────────────────────────────────────────────────────

@register_model_view(models.ProxmoxFirewallOptions, "list", path="", detail=False)
class ProxmoxFirewallOptionsListView(ObjectListView):
    queryset = models.ProxmoxFirewallOptions.objects.select_related(
        "endpoint", "proxmox_node", "virtual_machine"
    )
    table = tables.ProxmoxFirewallOptionsTable
    filterset = filtersets.ProxmoxFirewallOptionsFilterSet
    filterset_form = forms.ProxmoxFirewallOptionsFilterForm


@register_model_view(models.ProxmoxFirewallOptions)
class ProxmoxFirewallOptionsView(ObjectView):
    queryset = models.ProxmoxFirewallOptions.objects.select_related(
        "endpoint", "proxmox_node", "virtual_machine"
    )


@register_model_view(models.ProxmoxFirewallOptions, "edit")
class ProxmoxFirewallOptionsEditView(ObjectEditView):
    queryset = models.ProxmoxFirewallOptions.objects.select_related(
        "endpoint", "proxmox_node", "virtual_machine"
    )
    form = forms.ProxmoxFirewallOptionsForm
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewalloptions_list"


@register_model_view(models.ProxmoxFirewallOptions, "delete")
class ProxmoxFirewallOptionsDeleteView(ObjectDeleteView):
    queryset = models.ProxmoxFirewallOptions.objects.all()
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewalloptions_list"
