"""Define NetBox forms for tenant-scoped cloud image templates."""

from django import forms
from django.utils.translation import gettext as _
from netbox.forms import NetBoxModelFilterSetForm, NetBoxModelForm
from tenancy.models import Tenant
from utilities.forms.fields import (
    CommentField,
    DynamicModelChoiceField,
    DynamicModelMultipleChoiceField,
)
from virtualization.models import Cluster

from netbox_proxbox.choices import CloudImageOSFamilyChoices
from netbox_proxbox.models import CloudImageTemplate


class CloudImageTemplateForm(NetBoxModelForm):
    """Form for creating and editing CloudImageTemplate catalog entries."""

    cluster = DynamicModelChoiceField(
        queryset=Cluster.objects.all(),
        required=True,
        label=_("Cluster"),
        help_text=_("Cluster that contains the Proxmox source template VMID."),
    )
    allowed_tenants = DynamicModelMultipleChoiceField(
        queryset=Tenant.objects.all(),
        required=False,
        label=_("Allowed tenants"),
        help_text=_("Leave empty to make this template available to all tenants."),
    )
    comments = CommentField()

    class Meta:
        model = CloudImageTemplate
        fields = (
            "name",
            "slug",
            "description",
            "cluster",
            "source_vmid",
            "os_family",
            "os_release",
            "default_ciuser",
            "allowed_tenants",
            "is_active",
            "tags",
            "comments",
        )

    def clean_default_ciuser(self) -> str:
        """Keep ciuser values compatible with Proxmox cloud-init user fields."""
        value = (self.cleaned_data.get("default_ciuser") or "").strip()
        if not value:
            raise forms.ValidationError(_("Default cloud-init user is required."))
        if any(char.isspace() for char in value):
            raise forms.ValidationError(_("Cloud-init user cannot contain whitespace."))
        return value


class CloudImageTemplateFilterForm(NetBoxModelFilterSetForm):
    """Filter controls for CloudImageTemplate list views."""

    model = CloudImageTemplate

    cluster = DynamicModelMultipleChoiceField(
        queryset=Cluster.objects.all(),
        required=False,
        label=_("Cluster"),
    )
    os_family = forms.MultipleChoiceField(
        choices=CloudImageOSFamilyChoices,
        required=False,
        label=_("OS family"),
    )
    allowed_tenants = DynamicModelMultipleChoiceField(
        queryset=Tenant.objects.all(),
        required=False,
        label=_("Allowed tenants"),
    )
    is_active = forms.NullBooleanField(
        required=False,
        widget=forms.Select(
            choices=[("", "---------"), ("true", _("Yes")), ("false", _("No"))],
        ),
        label=_("Active"),
    )
