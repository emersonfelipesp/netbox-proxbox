"""NetBox forms for netbox-packer image factory views."""

from __future__ import annotations

from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from netbox.forms import NetBoxModelFilterSetForm, NetBoxModelForm
from tenancy.models import Tenant
from utilities.forms.fields import (
    CommentField,
    DynamicModelChoiceField,
    DynamicModelMultipleChoiceField,
    JSONField,
)
from utilities.forms.rendering import FieldSet
from virtualization.models import Cluster

from netbox_packer.choices import (
    PackerBuildStatusChoices,
    PackerBuilderTypeChoices,
    PackerOSFamilyChoices,
    PackerProvisionerRecipeChoices,
)
from netbox_packer.models import (
    PackerImageBuild,
    PackerImageDefinition,
    PackerPluginSettings,
)
from netbox_proxbox.models import ProxmoxEndpoint


class PackerImageDefinitionForm(NetBoxModelForm):
    """Create and edit reusable Packer image definitions."""

    proxmox_endpoint = DynamicModelChoiceField(
        queryset=ProxmoxEndpoint.objects.all(),
        required=True,
        label=_("Proxmox endpoint"),
    )
    target_cluster = DynamicModelChoiceField(
        queryset=Cluster.objects.all(),
        required=False,
        label=_("Target cluster"),
    )
    allowed_tenants = DynamicModelMultipleChoiceField(
        queryset=Tenant.objects.all(),
        required=False,
        label=_("Allowed tenants"),
        help_text=_("Leave empty to make this definition available to all tenants."),
    )
    default_variables = JSONField(
        required=False,
        label=_("Default variables"),
    )
    comments = CommentField()

    fieldsets = (
        FieldSet(
            "name",
            "slug",
            "description",
            "enabled",
            "tags",
            name=_("Image definition"),
        ),
        FieldSet(
            "builder_type",
            "proxmox_endpoint",
            "target_cluster",
            "target_node",
            "source_template_vmid",
            "default_storage",
            "default_bridge",
            name=_("Proxmox target"),
        ),
        FieldSet(
            "os_family",
            "os_release",
            "default_ciuser",
            "provisioner_recipe",
            "default_variables",
            name=_("Image defaults"),
        ),
        FieldSet(
            "iso_storage",
            "iso_url",
            "iso_checksum",
            name=_("ISO builder (proxmox-iso only)"),
        ),
        FieldSet("allowed_tenants", name=_("Tenant scope")),
    )

    class Meta:
        model = PackerImageDefinition
        fields = (
            "name",
            "slug",
            "description",
            "enabled",
            "builder_type",
            "proxmox_endpoint",
            "target_cluster",
            "target_node",
            "source_template_vmid",
            "default_storage",
            "default_bridge",
            "os_family",
            "os_release",
            "default_ciuser",
            "provisioner_recipe",
            "default_variables",
            "iso_storage",
            "iso_url",
            "iso_checksum",
            "allowed_tenants",
            "tags",
            "comments",
        )


class PackerImageBuildSubmitForm(forms.Form):
    """Action form for queueing a build in a later phase."""

    output_vmid = forms.IntegerField(
        min_value=1,
        required=True,
        label=_("Output VMID"),
    )
    output_name = forms.CharField(
        max_length=255,
        required=True,
        label=_("Output name"),
    )
    image_version = forms.CharField(
        max_length=64,
        required=True,
        label=_("Image version"),
    )
    dry_run = forms.BooleanField(
        required=False,
        label=_("Dry run"),
    )
    force = forms.BooleanField(
        required=False,
        label=_("Force"),
    )

    def __init__(
        self,
        *args: object,
        definition: PackerImageDefinition | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(*args, **kwargs)
        if definition is None:
            return

        defaults = definition.default_variables or {}
        today = timezone.localdate()
        self.fields["output_vmid"].initial = defaults.get("output_vmid")
        self.fields["output_name"].initial = defaults.get(
            "output_name",
            f"{definition.slug}-{today:%Y%m%d}",
        )
        self.fields["image_version"].initial = defaults.get(
            "image_version",
            today.isoformat(),
        )
        self.fields["dry_run"].initial = bool(defaults.get("dry_run", False))
        self.fields["force"].initial = bool(defaults.get("force", False))

    def clean_output_name(self) -> str:
        value = (self.cleaned_data.get("output_name") or "").strip()
        if not value:
            raise forms.ValidationError(_("Output name is required."))
        return value

    def clean_image_version(self) -> str:
        value = (self.cleaned_data.get("image_version") or "").strip()
        if not value:
            raise forms.ValidationError(_("Image version is required."))
        return value


class PackerPluginSettingsForm(NetBoxModelForm):
    """Edit the singleton image factory settings row."""

    fieldsets = (
        FieldSet(
            "image_factory_enabled",
            "image_factory_max_concurrent_builds",
            "image_factory_default_job_timeout",
            name=_("Execution"),
        ),
        FieldSet(
            "image_factory_allow_iso_builds",
            "image_factory_allow_custom_variables",
            "tags",
            name=_("Feature gates"),
        ),
    )

    class Meta:
        model = PackerPluginSettings
        fields = (
            "image_factory_enabled",
            "image_factory_max_concurrent_builds",
            "image_factory_default_job_timeout",
            "image_factory_allow_iso_builds",
            "image_factory_allow_custom_variables",
            "tags",
        )


class PackerImageDefinitionFilterForm(NetBoxModelFilterSetForm):
    """Filter controls for image definition list views."""

    model = PackerImageDefinition

    q = forms.CharField(required=False, label=_("Search"))
    enabled = forms.NullBooleanField(
        required=False,
        widget=forms.Select(
            choices=[("", "---------"), ("true", _("Yes")), ("false", _("No"))],
        ),
        label=_("Enabled"),
    )
    builder_type = forms.MultipleChoiceField(
        choices=PackerBuilderTypeChoices,
        required=False,
        label=_("Builder type"),
    )
    os_family = forms.MultipleChoiceField(
        choices=PackerOSFamilyChoices,
        required=False,
        label=_("OS family"),
    )
    provisioner_recipe = forms.MultipleChoiceField(
        choices=PackerProvisionerRecipeChoices,
        required=False,
        label=_("Provisioner recipe"),
    )
    proxmox_endpoint = DynamicModelMultipleChoiceField(
        queryset=ProxmoxEndpoint.objects.all(),
        required=False,
        label=_("Proxmox endpoint"),
    )
    target_cluster = DynamicModelMultipleChoiceField(
        queryset=Cluster.objects.all(),
        required=False,
        label=_("Target cluster"),
    )
    tenant = DynamicModelMultipleChoiceField(
        queryset=Tenant.objects.all(),
        required=False,
        label=_("Tenant"),
    )

    fieldsets = (
        FieldSet("q", "enabled", "builder_type", "os_family", name=_("Definition")),
        FieldSet(
            "proxmox_endpoint",
            "target_cluster",
            "tenant",
            "provisioner_recipe",
            name=_("Scope"),
        ),
    )


class PackerImageBuildFilterForm(NetBoxModelFilterSetForm):
    """Filter controls for image build list views."""

    model = PackerImageBuild

    q = forms.CharField(required=False, label=_("Search"))
    status = forms.MultipleChoiceField(
        choices=PackerBuildStatusChoices,
        required=False,
        label=_("Status"),
    )
    os_family = forms.MultipleChoiceField(
        choices=PackerOSFamilyChoices,
        required=False,
        label=_("OS family"),
    )
    proxmox_endpoint = DynamicModelMultipleChoiceField(
        queryset=ProxmoxEndpoint.objects.all(),
        required=False,
        label=_("Proxmox endpoint"),
    )
    tenant = DynamicModelMultipleChoiceField(
        queryset=Tenant.objects.all(),
        required=False,
        label=_("Tenant"),
    )

    fieldsets = (
        FieldSet("q", "status", "os_family", name=_("Build")),
        FieldSet("proxmox_endpoint", "tenant", name=_("Scope")),
    )
