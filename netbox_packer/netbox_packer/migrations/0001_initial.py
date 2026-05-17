"""Initial schema for netbox-packer image factory models."""

from __future__ import annotations

import django.db.models.deletion
import taggit.managers
import utilities.json
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("extras", "0002_squashed_0059"),
        ("netbox_proxbox", "0001_initial"),
        ("netbox_proxbox", "0044_cloud_image_template"),
        ("tenancy", "0001_squashed_0012"),
        ("virtualization", "0001_squashed_0022"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PackerImageDefinition",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "custom_field_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=utilities.json.CustomFieldJSONEncoder,
                    ),
                ),
                ("name", models.CharField(max_length=255, unique=True)),
                ("slug", models.SlugField(max_length=255)),
                ("description", models.TextField(blank=True)),
                ("enabled", models.BooleanField(default=True)),
                (
                    "builder_type",
                    models.CharField(default="proxmox-clone", max_length=32),
                ),
                ("target_node", models.CharField(max_length=255)),
                ("source_template_vmid", models.PositiveIntegerField()),
                ("default_storage", models.CharField(max_length=255)),
                ("default_bridge", models.CharField(default="vmbr0", max_length=64)),
                ("os_family", models.CharField(max_length=32)),
                ("os_release", models.CharField(max_length=64)),
                ("default_ciuser", models.CharField(default="ubuntu", max_length=64)),
                ("provisioner_recipe", models.CharField(max_length=32)),
                (
                    "default_variables",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=utilities.json.CustomFieldJSONEncoder,
                    ),
                ),
                (
                    "allowed_tenants",
                    models.ManyToManyField(
                        blank=True,
                        related_name="packer_image_definitions",
                        to="tenancy.tenant",
                    ),
                ),
                (
                    "proxmox_endpoint",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="packer_image_definitions",
                        to="netbox_proxbox.proxmoxendpoint",
                    ),
                ),
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem", to="extras.Tag"
                    ),
                ),
                (
                    "target_cluster",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="packer_image_definitions",
                        to="virtualization.cluster",
                    ),
                ),
            ],
            options={
                "verbose_name": "Packer image definition",
                "verbose_name_plural": "Packer image definitions",
                "ordering": ("name",),
            },
        ),
        migrations.CreateModel(
            name="PackerImageBuild",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "custom_field_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=utilities.json.CustomFieldJSONEncoder,
                    ),
                ),
                ("status", models.CharField(default="pending", max_length=32)),
                ("backend_build_id", models.CharField(blank=True, max_length=255)),
                ("target_node", models.CharField(max_length=255)),
                ("output_vmid", models.PositiveIntegerField()),
                ("output_name", models.CharField(max_length=255)),
                ("image_version", models.CharField(max_length=64)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("netbox_job_id", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "backend_response",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=utilities.json.CustomFieldJSONEncoder,
                    ),
                ),
                ("error", models.TextField(blank=True)),
                (
                    "cloud_image_template",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="packer_image_builds",
                        to="netbox_proxbox.cloudimagetemplate",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="packer_image_builds",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "proxmox_endpoint",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="packer_image_builds",
                        to="netbox_proxbox.proxmoxendpoint",
                    ),
                ),
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem", to="extras.Tag"
                    ),
                ),
                (
                    "definition",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="builds",
                        to="netbox_packer.packerimagedefinition",
                    ),
                ),
            ],
            options={
                "verbose_name": "Packer image build",
                "verbose_name_plural": "Packer image builds",
                "ordering": ("-started_at", "-created"),
            },
        ),
        migrations.CreateModel(
            name="PackerPluginSettings",
            fields=[
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "custom_field_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=utilities.json.CustomFieldJSONEncoder,
                    ),
                ),
                (
                    "singleton_key",
                    models.CharField(
                        default="default",
                        editable=False,
                        max_length=32,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("image_factory_enabled", models.BooleanField(default=False)),
                (
                    "image_factory_max_concurrent_builds",
                    models.PositiveIntegerField(default=1),
                ),
                (
                    "image_factory_default_job_timeout",
                    models.PositiveIntegerField(default=14400),
                ),
                ("image_factory_allow_iso_builds", models.BooleanField(default=False)),
                (
                    "image_factory_allow_custom_variables",
                    models.BooleanField(default=False),
                ),
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem", to="extras.Tag"
                    ),
                ),
            ],
            options={
                "verbose_name": "Packer plugin settings",
                "verbose_name_plural": "Packer plugin settings",
            },
        ),
        migrations.AddConstraint(
            model_name="packerimagedefinition",
            constraint=models.UniqueConstraint(
                fields=("slug",), name="netbox_packer_definition_identity"
            ),
        ),
        migrations.AddIndex(
            model_name="packerimagebuild",
            index=models.Index(
                fields=["status", "started_at"],
                name="netbox_packer_build_status_started",
            ),
        ),
    ]
