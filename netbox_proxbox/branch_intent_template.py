"""Conditional branch-detail template extension for intent safety gates."""

from __future__ import annotations

from django.urls import reverse
from django.utils.safestring import mark_safe
from netbox.plugins import PluginTemplateExtension
from utilities.permissions import get_permission_for_model

from netbox_proxbox.services.branch_intent import resolve_branch_intent_flags
from netbox_proxbox.services.branch_lifecycle import is_branching_available


class ProxboxBranchIntentTemplateExtension(PluginTemplateExtension):
    """Render branch intent gates without importing the optional model."""

    models = ("netbox_branching.branch",)

    def right_page(self) -> str:
        """Render the gate card when permissions and branch identity are valid."""
        from netbox_proxbox.models import ProxboxBranchIntent

        branch = self.context.get("object")
        request = self.context.get("request")
        user = getattr(request, "user", None)
        has_perm = getattr(user, "has_perm", None)
        branch_id = getattr(branch, "pk", None)
        branch_schema_id = getattr(branch, "schema_id", None)
        if (
            not callable(has_perm)
            or branch_id is None
            or not branch_schema_id
            or not is_branching_available()
        ):
            return ""

        intent = None
        if has_perm(get_permission_for_model(ProxboxBranchIntent, "view")):
            manager = ProxboxBranchIntent.objects
            restrict = getattr(manager, "restrict", None)
            if not callable(restrict):
                return ""
            try:
                intent = (
                    restrict(user, "view")
                    .filter(
                        branch_id=branch_id,
                        branch_schema_id=str(branch_schema_id),
                    )
                    .first()
                )
            except Exception:
                return ""

        edit_url = None
        add_url = None
        if intent is not None and has_perm(
            get_permission_for_model(ProxboxBranchIntent, "change")
        ):
            edit_url = reverse(
                "plugins:netbox_proxbox:proxboxbranchintent_edit",
                args=[intent.pk],
            )
        elif intent is None and has_perm(
            get_permission_for_model(ProxboxBranchIntent, "add")
        ):
            add_url = (
                reverse("plugins:netbox_proxbox:proxboxbranchintent_add")
                + f"?branch_id={branch_id}&branch_schema_id={branch_schema_id}"
            )
        if intent is None and add_url is None:
            return ""

        rendered = self.render(
            "netbox_proxbox/inc/branch_intent_card.html",
            {
                "intent": intent,
                "intent_flags": resolve_branch_intent_flags(branch),
                "edit_url": edit_url,
                "add_url": add_url,
            },
        )
        return mark_safe(rendered)  # nosec - autoescaped plugin template


def branch_intent_template_extensions() -> list[type[PluginTemplateExtension]]:
    """Register the extension only while netbox-branching is enabled."""
    if not is_branching_available():
        return []
    return [ProxboxBranchIntentTemplateExtension]
