"""Forms for plugin-owned branch intent safety gates."""

from django import forms
from netbox.forms import NetBoxModelFilterSetForm, NetBoxModelForm

from netbox_proxbox.models import ProxboxBranchIntent
from netbox_proxbox.services.branch_intent import resolve_branch_reference


class ProxboxBranchIntentForm(NetBoxModelForm):
    """Edit gates while keeping an existing soft branch reference immutable."""

    def clean(self):
        """Require a live exact branch reference and forbid reassignment."""
        super().clean()
        cleaned_data = self.cleaned_data
        branch_id = cleaned_data.get("branch_id")
        branch_schema_id = cleaned_data.get("branch_schema_id")
        if branch_id is None or not branch_schema_id:
            return cleaned_data

        if getattr(self.instance, "pk", None) is not None and (
            getattr(self.instance, "branch_id", None) != branch_id
            or getattr(self.instance, "branch_schema_id", None) != branch_schema_id
        ):
            raise forms.ValidationError(
                "The branch reference for an existing Proxbox branch intent "
                "cannot be changed."
            )
        if resolve_branch_reference(branch_id, branch_schema_id) is None:
            raise forms.ValidationError(
                "The referenced netbox-branching branch is unavailable."
            )
        return cleaned_data

    class Meta:
        model = ProxboxBranchIntent
        fields = (
            "branch_id",
            "branch_schema_id",
            "apply_to_proxmox",
            "apply_destroy_confirmed",
            "tags",
        )


class ProxboxBranchIntentFilterForm(NetBoxModelFilterSetForm):
    """Filter branch intent rows by their soft reference and gate values."""

    model = ProxboxBranchIntent

    branch_id = forms.IntegerField(required=False, min_value=1)
    branch_schema_id = forms.CharField(required=False)
    apply_to_proxmox = forms.NullBooleanField(required=False)
    apply_destroy_confirmed = forms.NullBooleanField(required=False)
