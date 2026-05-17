"""Add tenant-scoped cloud image templates for Cloud Portal provisioning.

Idempotent: the ``CreateModel`` is wrapped through ``create_model_idempotent``
so reporter-style installs whose legacy lineage already created this table do
not abort with ``DuplicateTable``.
"""

from __future__ import annotations

import django.db.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import create_model_idempotent


class Migration(migrations.Migration):

    dependencies = [
        ("extras", "0134_owner"),
        ("netbox_proxbox", "0043_pluginsettings_warn_plaintext"),
        ("tenancy", "0023_add_mptt_tree_indexes"),
        ("virtualization", "0052_gfk_indexes"),
    ]

    operations = [
        create_model_idempotent(
            name="CloudImageTemplate",
            fields=[
                (
                    "custom_field_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=utilities.json.CustomFieldJSONEncoder,
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        help_text="Human-readable cloud image template name.",
                        max_length=255,
                        verbose_name="Name",
                    ),
                ),
                (
                    "slug",
                    models.SlugField(
                        help_text="Unique slug used by API clients and automation.",
                        max_length=255,
                        unique=True,
                        verbose_name="Slug",
                    ),
                ),
                (
                    "description",
                    models.TextField(
                        blank=True,
                        help_text="Optional operator-facing description for this cloud image.",
                        verbose_name="Description",
                    ),
                ),
                (
                    "source_vmid",
                    models.PositiveIntegerField(
                        help_text="Proxmox VMID of the source cloud-image template.",
                        verbose_name="Source VMID",
                    ),
                ),
                (
                    "os_family",
                    models.CharField(
                        choices=[
                            ("ubuntu", "Ubuntu"),
                            ("debian", "Debian"),
                            ("rocky", "Rocky Linux"),
                            ("alpine", "Alpine Linux"),
                            ("generic", "Generic Linux"),
                        ],
                        default="generic",
                        help_text="Operating-system family represented by this image.",
                        max_length=32,
                        verbose_name="OS family",
                    ),
                ),
                (
                    "os_release",
                    models.CharField(
                        blank=True,
                        help_text="Optional OS release or codename, for example jammy.",
                        max_length=64,
                        verbose_name="OS release",
                    ),
                ),
                (
                    "default_ciuser",
                    models.CharField(
                        default="cloud-user",
                        help_text="Default ciuser value supplied when provisioning from this image.",
                        max_length=64,
                        verbose_name="Default cloud-init user",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="Inactive templates are hidden from tenant provisioning flows.",
                        verbose_name="Active",
                    ),
                ),
                (
                    "allowed_tenants",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Tenants allowed to use this image. Leave empty for all tenants.",
                        related_name="proxbox_cloud_image_templates",
                        to="tenancy.tenant",
                        verbose_name="Allowed tenants",
                    ),
                ),
                (
                    "cluster",
                    models.ForeignKey(
                        help_text="NetBox cluster that contains the Proxmox source template VMID.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proxbox_cloud_image_templates",
                        to="virtualization.cluster",
                        verbose_name="Cluster",
                    ),
                ),
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem",
                        to="extras.Tag",
                    ),
                ),
            ],
            options={
                "verbose_name": "Cloud image template",
                "verbose_name_plural": "Cloud image templates",
                "ordering": ("cluster", "name", "source_vmid"),
                "permissions": [
                    (
                        "provision_cloud_vm",
                        "Can provision a VM from a cloud image template",
                    ),
                ],
                "unique_together": {("cluster", "source_vmid")},
            },
        ),
    ]
