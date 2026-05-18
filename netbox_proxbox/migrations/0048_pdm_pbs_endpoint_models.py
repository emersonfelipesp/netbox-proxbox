"""Add PBSEndpoint, PDMEndpoint, and PDMRemote models for PDM support.

These models land the netbox-proxbox-side ForeignKey wiring called for in
issue #449 (PDM support). Operator-declared federation lives on
`PDMEndpoint.proxmox_endpoints` / `pbs_endpoints` M2M fields; the
read-side `PDMRemote` table reflects what PDM itself reports about each
remote and links back to the matching `ProxmoxEndpoint` or `PBSEndpoint`
row when discovery is able to resolve it.
"""

from __future__ import annotations

import django.db.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dcim", "0227_alter_interface_speed_bigint"),
        ("extras", "0134_owner"),
        ("ipam", "0076_natural_ordering"),
        ("netbox_proxbox", "0038_v0_0_16_release"),
        ("tenancy", "0023_add_mptt_tree_indexes"),
    ]

    operations = [
        migrations.CreateModel(
            name="PBSEndpoint",
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
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        blank=True, default="PBS Endpoint", max_length=255, null=True
                    ),
                ),
                (
                    "domain",
                    models.CharField(blank=True, max_length=255, null=True),
                ),
                ("port", models.PositiveIntegerField(default=8007)),
                ("token_id", models.CharField(max_length=255)),
                ("token_secret", models.CharField(max_length=255)),
                (
                    "fingerprint",
                    models.CharField(blank=True, max_length=255, null=True),
                ),
                ("verify_ssl", models.BooleanField(default=True)),
                ("allow_writes", models.BooleanField(default=False)),
                ("timeout", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "ip_address",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="ipam.ipaddress",
                    ),
                ),
                (
                    "site",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="dcim.site",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="tenancy.tenant",
                    ),
                ),
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem", to="extras.Tag"
                    ),
                ),
            ],
            options={
                "verbose_name": "PBS endpoint",
                "verbose_name_plural": "PBS endpoints",
                "ordering": ("name", "pk"),
            },
        ),
        migrations.AddConstraint(
            model_name="pbsendpoint",
            constraint=models.UniqueConstraint(
                fields=("name", "ip_address", "domain"),
                name="netbox_proxbox_pbsendpoint_identity",
            ),
        ),
        migrations.CreateModel(
            name="PDMEndpoint",
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
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        blank=True, default="PDM Endpoint", max_length=255, null=True
                    ),
                ),
                (
                    "domain",
                    models.CharField(blank=True, max_length=255, null=True),
                ),
                ("port", models.PositiveIntegerField(default=8443)),
                ("token_id", models.CharField(max_length=255)),
                ("token_secret", models.CharField(max_length=255)),
                (
                    "fingerprint",
                    models.CharField(blank=True, max_length=255, null=True),
                ),
                ("verify_ssl", models.BooleanField(default=True)),
                ("allow_writes", models.BooleanField(default=False)),
                ("timeout", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "ip_address",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="ipam.ipaddress",
                    ),
                ),
                (
                    "site",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="dcim.site",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="tenancy.tenant",
                    ),
                ),
                (
                    "proxmox_endpoints",
                    models.ManyToManyField(
                        blank=True,
                        related_name="pdm_endpoints",
                        to="netbox_proxbox.proxmoxendpoint",
                    ),
                ),
                (
                    "pbs_endpoints",
                    models.ManyToManyField(
                        blank=True,
                        related_name="pdm_endpoints",
                        to="netbox_proxbox.pbsendpoint",
                    ),
                ),
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem", to="extras.Tag"
                    ),
                ),
            ],
            options={
                "verbose_name": "PDM endpoint",
                "verbose_name_plural": "PDM endpoints",
                "ordering": ("name", "pk"),
            },
        ),
        migrations.AddConstraint(
            model_name="pdmendpoint",
            constraint=models.UniqueConstraint(
                fields=("name", "ip_address", "domain"),
                name="netbox_proxbox_pdmendpoint_identity",
            ),
        ),
        migrations.CreateModel(
            name="PDMRemote",
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
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                (
                    "type",
                    models.CharField(
                        choices=[("pve", "PVE"), ("pbs", "PBS")], max_length=8
                    ),
                ),
                ("hostname", models.CharField(blank=True, max_length=255)),
                ("fingerprint", models.CharField(blank=True, max_length=255)),
                ("version", models.CharField(blank=True, max_length=64)),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                (
                    "pdm_endpoint",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="remotes",
                        to="netbox_proxbox.pdmendpoint",
                    ),
                ),
                (
                    "linked_proxmox_endpoint",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="pdm_remotes",
                        to="netbox_proxbox.proxmoxendpoint",
                    ),
                ),
                (
                    "linked_pbs_endpoint",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="pdm_remotes",
                        to="netbox_proxbox.pbsendpoint",
                    ),
                ),
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem", to="extras.Tag"
                    ),
                ),
            ],
            options={
                "verbose_name": "PDM remote",
                "verbose_name_plural": "PDM remotes",
                "ordering": ("pdm_endpoint", "name"),
            },
        ),
        migrations.AddConstraint(
            model_name="pdmremote",
            constraint=models.UniqueConstraint(
                fields=("pdm_endpoint", "name"),
                name="netbox_proxbox_pdmremote_unique_endpoint_name",
            ),
        ),
    ]
