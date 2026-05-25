"""NetBox CRUD views for Proxmox firewall models."""

from __future__ import annotations

from typing import ClassVar

from django.contrib import messages
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.views import View
from netbox.object_actions import (
    AddObject,
    BulkDelete,
    BulkEdit,
    BulkExport,
    BulkImport,
    BulkRename,
    ObjectAction,
)
from netbox.views.generic import (
    ObjectDeleteView,
    ObjectEditView,
    ObjectListView,
    ObjectView,
)
from utilities.views import (
    ContentTypePermissionRequiredMixin,
    TokenConditionalLoginRequiredMixin,
    register_model_view,
)

from netbox_proxbox import filtersets, forms, models, tables
from netbox_proxbox.intent.firewall_common import (
    FirewallPushError,
    push_firewall_object,
)
from netbox_proxbox.views.proxbox_access import permission_run_proxmox_action

_SG_QS = models.ProxmoxFirewallSecurityGroup.objects.select_related("endpoint")
_RULE_QS = models.ProxmoxFirewallRule.objects.select_related(
    "endpoint", "proxmox_node", "virtual_machine", "security_group"
)
_IPSET_QS = models.ProxmoxFirewallIPSet.objects.select_related(
    "endpoint", "virtual_machine"
)
_IPSET_ENTRY_QS = models.ProxmoxFirewallIPSetEntry.objects.select_related("ipset")
_ALIAS_QS = models.ProxmoxFirewallAlias.objects.select_related(
    "endpoint", "virtual_machine"
)
_OPTIONS_QS = models.ProxmoxFirewallOptions.objects.select_related(
    "endpoint", "proxmox_node", "virtual_machine"
)


class _FirewallPushView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """Shared detail action for pushing a firewall object to Proxmox."""

    model: ClassVar[type]
    queryset: ClassVar[object]
    http_method_names: ClassVar[list[str]] = ["post"]

    def get_required_permission(self) -> str:
        """Require the Proxmox write permission for every firewall push."""
        return permission_run_proxmox_action()

    def post(self, request: HttpRequest, pk: int | str) -> HttpResponseRedirect:
        """Forward the push to proxbox-api and redirect back to the object."""
        qs = self.queryset
        restrict = getattr(qs, "restrict", None)
        if callable(restrict):
            qs = restrict(request.user, "change")
        obj = get_object_or_404(qs, pk=pk)
        redirect_to = obj.get_absolute_url()
        actor = _actor_from_request(request)
        try:
            result = push_firewall_object(obj, actor=actor)
        except FirewallPushError as exc:
            messages.error(
                request,
                _("Firewall push failed: {reason}. {detail}").format(
                    reason=exc.reason,
                    detail=exc.detail,
                ),
            )
            return HttpResponseRedirect(redirect_to)

        if result.status == "skipped":
            messages.warning(
                request,
                _("Firewall push skipped: {reason}. {detail}").format(
                    reason=result.reason or "unsupported",
                    detail=result.detail or "",
                ),
            )
        else:
            messages.success(request, _("Firewall object pushed to Proxmox."))
        return HttpResponseRedirect(redirect_to)


class FirewallBulkPushAction(ObjectAction):
    """List-view action for pushing selected firewall rules."""

    name = "bulk_push"
    label = _("Push Selected")
    multi = True
    permissions_required = {"change"}
    template_name = "netbox_proxbox/buttons/firewall_bulk_push.html"


class ProxmoxFirewallRuleBulkPushView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """Push selected firewall rules and summarize per-record results."""

    http_method_names: ClassVar[list[str]] = ["post"]

    def get_required_permission(self) -> str:
        """Require the Proxmox write permission for bulk firewall push."""
        return permission_run_proxmox_action()

    def post(self, request: HttpRequest) -> HttpResponseRedirect:
        """Push selected firewall rules and redirect back to the list."""
        selected_ids = request.POST.getlist("pk") or request.POST.getlist("pk[]")
        redirect_to = request.POST.get("return_url") or request.META.get(
            "HTTP_REFERER",
            "/",
        )
        if not selected_ids:
            messages.error(request, _("Select at least one firewall rule to push."))
            return HttpResponseRedirect(redirect_to)

        actor = _actor_from_request(request)
        success_count = 0
        failures: list[str] = []
        queryset = _RULE_QS.restrict(request.user, "change")
        for rule in queryset.filter(pk__in=selected_ids):
            try:
                push_firewall_object(rule, actor=actor)
                success_count += 1
            except FirewallPushError as exc:
                failures.append(f"#{rule.pk}: {exc.reason}")

        if success_count:
            messages.success(
                request,
                _("Pushed {count} firewall rule(s) to Proxmox.").format(
                    count=success_count
                ),
            )
        if failures:
            messages.error(
                request,
                _("Firewall push failures: {failures}").format(
                    failures=", ".join(failures)
                ),
            )
        return HttpResponseRedirect(redirect_to)


def _actor_from_request(request: HttpRequest) -> str:
    user = getattr(request, "user", None)
    get_username = getattr(user, "get_username", None)
    if callable(get_username):
        return str(get_username())
    return str(getattr(user, "username", "") or getattr(user, "pk", "") or "netbox")


# ── ProxmoxFirewallSecurityGroup ─────────────────────────────────────────────


@register_model_view(models.ProxmoxFirewallSecurityGroup, "list", path="", detail=False)
class ProxmoxFirewallSecurityGroupListView(ObjectListView):
    queryset = _SG_QS
    table = tables.ProxmoxFirewallSecurityGroupTable
    filterset = filtersets.ProxmoxFirewallSecurityGroupFilterSet
    filterset_form = forms.ProxmoxFirewallSecurityGroupFilterForm
    actions = {}


@register_model_view(models.ProxmoxFirewallSecurityGroup)
class ProxmoxFirewallSecurityGroupView(ObjectView):
    queryset = _SG_QS


@register_model_view(models.ProxmoxFirewallSecurityGroup, "add", detail=False)
@register_model_view(models.ProxmoxFirewallSecurityGroup, "edit")
class ProxmoxFirewallSecurityGroupEditView(ObjectEditView):
    queryset = _SG_QS
    form = forms.ProxmoxFirewallSecurityGroupForm
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewallsecuritygroup_list"


@register_model_view(models.ProxmoxFirewallSecurityGroup, "delete")
class ProxmoxFirewallSecurityGroupDeleteView(ObjectDeleteView):
    queryset = _SG_QS
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewallsecuritygroup_list"


@register_model_view(
    models.ProxmoxFirewallSecurityGroup,
    "push_to_proxmox",
    path="push-to-proxmox",
)
class ProxmoxFirewallSecurityGroupPushView(_FirewallPushView):
    model = models.ProxmoxFirewallSecurityGroup
    queryset = _SG_QS


# ── ProxmoxFirewallRule ───────────────────────────────────────────────────────


@register_model_view(models.ProxmoxFirewallRule, "list", path="", detail=False)
class ProxmoxFirewallRuleListView(ObjectListView):
    queryset = _RULE_QS
    table = tables.ProxmoxFirewallRuleTable
    filterset = filtersets.ProxmoxFirewallRuleFilterSet
    filterset_form = forms.ProxmoxFirewallRuleFilterForm
    actions = (
        AddObject,
        BulkImport,
        BulkExport,
        FirewallBulkPushAction,
        BulkDelete,
    )


@register_model_view(models.ProxmoxFirewallRule)
class ProxmoxFirewallRuleView(ObjectView):
    queryset = _RULE_QS


@register_model_view(models.ProxmoxFirewallRule, "add", detail=False)
@register_model_view(models.ProxmoxFirewallRule, "edit")
class ProxmoxFirewallRuleEditView(ObjectEditView):
    queryset = _RULE_QS
    form = forms.ProxmoxFirewallRuleForm
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewallrule_list"


@register_model_view(models.ProxmoxFirewallRule, "delete")
class ProxmoxFirewallRuleDeleteView(ObjectDeleteView):
    queryset = _RULE_QS
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewallrule_list"


@register_model_view(
    models.ProxmoxFirewallRule,
    "push_to_proxmox",
    path="push-to-proxmox",
)
class ProxmoxFirewallRulePushView(_FirewallPushView):
    model = models.ProxmoxFirewallRule
    queryset = _RULE_QS


@register_model_view(
    models.ProxmoxFirewallRule,
    "bulk_push",
    path="push-selected",
    detail=False,
)
class ProxmoxFirewallRuleBulkPushActionView(ProxmoxFirewallRuleBulkPushView):
    """Registered route for selected firewall rule pushes."""


# ── ProxmoxFirewallIPSet ──────────────────────────────────────────────────────


@register_model_view(models.ProxmoxFirewallIPSet, "list", path="", detail=False)
class ProxmoxFirewallIPSetListView(ObjectListView):
    queryset = _IPSET_QS
    table = tables.ProxmoxFirewallIPSetTable
    filterset = filtersets.ProxmoxFirewallIPSetFilterSet
    filterset_form = forms.ProxmoxFirewallIPSetFilterForm
    actions = {}


@register_model_view(models.ProxmoxFirewallIPSet)
class ProxmoxFirewallIPSetView(ObjectView):
    queryset = _IPSET_QS


@register_model_view(models.ProxmoxFirewallIPSet, "add", detail=False)
@register_model_view(models.ProxmoxFirewallIPSet, "edit")
class ProxmoxFirewallIPSetEditView(ObjectEditView):
    queryset = _IPSET_QS
    form = forms.ProxmoxFirewallIPSetForm
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewallipset_list"


@register_model_view(models.ProxmoxFirewallIPSet, "delete")
class ProxmoxFirewallIPSetDeleteView(ObjectDeleteView):
    queryset = _IPSET_QS
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewallipset_list"


@register_model_view(
    models.ProxmoxFirewallIPSet,
    "push_to_proxmox",
    path="push-to-proxmox",
)
class ProxmoxFirewallIPSetPushView(_FirewallPushView):
    model = models.ProxmoxFirewallIPSet
    queryset = _IPSET_QS


# ── ProxmoxFirewallIPSetEntry ─────────────────────────────────────────────────


@register_model_view(models.ProxmoxFirewallIPSetEntry, "list", path="", detail=False)
class ProxmoxFirewallIPSetEntryListView(ObjectListView):
    queryset = _IPSET_ENTRY_QS
    table = tables.ProxmoxFirewallIPSetEntryTable
    filterset = filtersets.ProxmoxFirewallIPSetEntryFilterSet
    filterset_form = forms.ProxmoxFirewallIPSetEntryFilterForm
    actions = {}


@register_model_view(models.ProxmoxFirewallIPSetEntry)
class ProxmoxFirewallIPSetEntryView(ObjectView):
    queryset = _IPSET_ENTRY_QS


@register_model_view(models.ProxmoxFirewallIPSetEntry, "add", detail=False)
@register_model_view(models.ProxmoxFirewallIPSetEntry, "edit")
class ProxmoxFirewallIPSetEntryEditView(ObjectEditView):
    queryset = _IPSET_ENTRY_QS
    form = forms.ProxmoxFirewallIPSetEntryForm
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewallipsetentry_list"


@register_model_view(models.ProxmoxFirewallIPSetEntry, "delete")
class ProxmoxFirewallIPSetEntryDeleteView(ObjectDeleteView):
    queryset = _IPSET_ENTRY_QS
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewallipsetentry_list"


@register_model_view(
    models.ProxmoxFirewallIPSetEntry,
    "push_to_proxmox",
    path="push-to-proxmox",
)
class ProxmoxFirewallIPSetEntryPushView(_FirewallPushView):
    model = models.ProxmoxFirewallIPSetEntry
    queryset = _IPSET_ENTRY_QS


# ── ProxmoxFirewallAlias ──────────────────────────────────────────────────────


@register_model_view(models.ProxmoxFirewallAlias, "list", path="", detail=False)
class ProxmoxFirewallAliasListView(ObjectListView):
    queryset = _ALIAS_QS
    table = tables.ProxmoxFirewallAliasTable
    filterset = filtersets.ProxmoxFirewallAliasFilterSet
    filterset_form = forms.ProxmoxFirewallAliasFilterForm
    actions = {}


@register_model_view(models.ProxmoxFirewallAlias)
class ProxmoxFirewallAliasView(ObjectView):
    queryset = _ALIAS_QS


@register_model_view(models.ProxmoxFirewallAlias, "add", detail=False)
@register_model_view(models.ProxmoxFirewallAlias, "edit")
class ProxmoxFirewallAliasEditView(ObjectEditView):
    queryset = _ALIAS_QS
    form = forms.ProxmoxFirewallAliasForm
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewallalias_list"


@register_model_view(models.ProxmoxFirewallAlias, "delete")
class ProxmoxFirewallAliasDeleteView(ObjectDeleteView):
    queryset = _ALIAS_QS
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewallalias_list"


@register_model_view(
    models.ProxmoxFirewallAlias,
    "push_to_proxmox",
    path="push-to-proxmox",
)
class ProxmoxFirewallAliasPushView(_FirewallPushView):
    model = models.ProxmoxFirewallAlias
    queryset = _ALIAS_QS


# ── ProxmoxFirewallOptions ────────────────────────────────────────────────────


@register_model_view(models.ProxmoxFirewallOptions, "list", path="", detail=False)
class ProxmoxFirewallOptionsListView(ObjectListView):
    queryset = _OPTIONS_QS
    table = tables.ProxmoxFirewallOptionsTable
    filterset = filtersets.ProxmoxFirewallOptionsFilterSet
    filterset_form = forms.ProxmoxFirewallOptionsFilterForm
    actions = {}


@register_model_view(models.ProxmoxFirewallOptions)
class ProxmoxFirewallOptionsView(ObjectView):
    queryset = _OPTIONS_QS


@register_model_view(models.ProxmoxFirewallOptions, "add", detail=False)
@register_model_view(models.ProxmoxFirewallOptions, "edit")
class ProxmoxFirewallOptionsEditView(ObjectEditView):
    queryset = _OPTIONS_QS
    form = forms.ProxmoxFirewallOptionsForm
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewalloptions_list"


@register_model_view(models.ProxmoxFirewallOptions, "delete")
class ProxmoxFirewallOptionsDeleteView(ObjectDeleteView):
    queryset = _OPTIONS_QS
    default_return_url = "plugins:netbox_proxbox:proxmoxfirewalloptions_list"


@register_model_view(
    models.ProxmoxFirewallOptions,
    "push_to_proxmox",
    path="push-to-proxmox",
)
class ProxmoxFirewallOptionsPushView(_FirewallPushView):
    model = models.ProxmoxFirewallOptions
    queryset = _OPTIONS_QS
