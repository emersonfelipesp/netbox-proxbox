from __future__ import annotations

import django.db.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import (
    add_field_idempotent,
    create_model_idempotent,
)


SYNC_MODE_CHOICES = [
    ("always", "Always"),
    ("bootstrap_only", "Bootstrap only"),
    ("disabled", "Disabled"),
]

SYNC_STATUS_CHOICES = [
    ("active", "Active"),
    ("stale", "Stale"),
]


def _netbox_model_fields():
    return [
        (
            "id",
            models.BigAutoField(auto_created=True, primary_key=True, serialize=False),
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
        (
            "tags",
            taggit.managers.TaggableManager(
                through="extras.TaggedItem",
                to="extras.Tag",
            ),
        ),
    ]


def _endpoint_field(related_name: str):
    return models.ForeignKey(
        blank=True,
        null=True,
        on_delete=django.db.models.deletion.CASCADE,
        related_name=related_name,
        to="netbox_proxbox.proxmoxendpoint",
        verbose_name="Proxmox endpoint",
    )


def _status_field():
    return models.CharField(
        choices=SYNC_STATUS_CHOICES,
        default="active",
        max_length=20,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("extras", "0134_owner"),
        ("ipam", "0086_gfk_indexes"),
        ("netbox_proxbox", "0054_proxmoxendpoint_ssh_credential_source"),
        ("vpn", "0011_add_comments_to_organizationalmodel"),
    ]

    operations = [
        add_field_idempotent(
            model_name="proxboxpluginsettings",
            field_name="sync_mode_sdn",
            field=models.CharField(
                choices=SYNC_MODE_CHOICES,
                default="disabled",
                max_length=16,
            ),
        ),
        add_field_idempotent(
            model_name="proxmoxendpoint",
            field_name="sync_mode_sdn",
            field=models.CharField(
                blank=True,
                choices=SYNC_MODE_CHOICES,
                max_length=16,
                null=True,
            ),
        ),
        create_model_idempotent(
            name="ProxmoxSdnController",
            fields=[
                *_netbox_model_fields(),
                ("endpoint", _endpoint_field("sdn_controllers")),
                ("cluster_name", models.CharField(max_length=255)),
                ("controller_name", models.CharField(max_length=255)),
                ("controller_type", models.CharField(blank=True, max_length=32)),
                ("asn", models.IntegerField(blank=True, null=True)),
                ("peers", models.JSONField(blank=True, default=list)),
                ("nodes", models.JSONField(blank=True, default=list)),
                ("loopback", models.CharField(blank=True, max_length=255)),
                ("state", models.CharField(blank=True, max_length=32)),
                ("status", _status_field()),
                ("raw_config", models.JSONField(blank=True, default=dict)),
            ],
            options={
                "verbose_name": "SDN Controller",
                "verbose_name_plural": "SDN Controllers",
                "ordering": ("endpoint", "cluster_name", "controller_name"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=["endpoint", "cluster_name", "controller_name"],
                        name="nbpx_sdncontroller_unique_endpoint_cluster_name",
                    )
                ],
            },
        ),
        create_model_idempotent(
            name="ProxmoxSdnZone",
            fields=[
                *_netbox_model_fields(),
                ("endpoint", _endpoint_field("sdn_zones")),
                ("cluster_name", models.CharField(max_length=255)),
                ("zone_name", models.CharField(max_length=255)),
                ("zone_type", models.CharField(blank=True, max_length=32)),
                ("controller", models.CharField(blank=True, max_length=255)),
                ("vrf_vxlan", models.IntegerField(blank=True, null=True)),
                ("tag", models.IntegerField(blank=True, null=True)),
                ("mtu", models.IntegerField(blank=True, null=True)),
                ("dns", models.CharField(blank=True, max_length=255)),
                ("ipam", models.CharField(blank=True, max_length=255)),
                ("rt_import", models.JSONField(blank=True, default=list)),
                ("state", models.CharField(blank=True, max_length=32)),
                ("status", _status_field()),
                ("raw_config", models.JSONField(blank=True, default=dict)),
            ],
            options={
                "verbose_name": "SDN Zone",
                "verbose_name_plural": "SDN Zones",
                "ordering": ("endpoint", "cluster_name", "zone_name"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=["endpoint", "cluster_name", "zone_name"],
                        name="nbpx_sdnzone_unique_endpoint_cluster_name",
                    )
                ],
            },
        ),
        create_model_idempotent(
            name="ProxmoxSdnVNet",
            fields=[
                *_netbox_model_fields(),
                ("endpoint", _endpoint_field("sdn_vnets")),
                ("cluster_name", models.CharField(max_length=255)),
                ("zone_name", models.CharField(blank=True, max_length=255)),
                ("vnet_name", models.CharField(max_length=255)),
                ("vnet_type", models.CharField(blank=True, max_length=32)),
                ("tag", models.IntegerField(blank=True, null=True)),
                ("alias", models.CharField(blank=True, max_length=255)),
                ("vlanaware", models.BooleanField(default=False)),
                ("state", models.CharField(blank=True, max_length=32)),
                (
                    "l2vpn",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="vpn.l2vpn",
                        verbose_name="NetBox L2VPN",
                    ),
                ),
                ("status", _status_field()),
                ("raw_config", models.JSONField(blank=True, default=dict)),
            ],
            options={
                "verbose_name": "SDN VNet",
                "verbose_name_plural": "SDN VNets",
                "ordering": ("endpoint", "cluster_name", "zone_name", "vnet_name"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=["endpoint", "cluster_name", "vnet_name"],
                        name="nbpx_sdnvnet_unique_endpoint_cluster_name",
                    )
                ],
            },
        ),
        create_model_idempotent(
            name="ProxmoxSdnSubnet",
            fields=[
                *_netbox_model_fields(),
                ("endpoint", _endpoint_field("sdn_subnets")),
                ("cluster_name", models.CharField(max_length=255)),
                ("zone_name", models.CharField(blank=True, max_length=255)),
                ("vnet_name", models.CharField(max_length=255)),
                ("subnet", models.CharField(max_length=128)),
                ("subnet_type", models.CharField(blank=True, max_length=32)),
                ("gateway", models.CharField(blank=True, max_length=128)),
                ("snat", models.BooleanField(default=False)),
                (
                    "prefix",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="ipam.prefix",
                        verbose_name="NetBox prefix",
                    ),
                ),
                ("skip_reason", models.TextField(blank=True)),
                ("status", _status_field()),
                ("raw_config", models.JSONField(blank=True, default=dict)),
            ],
            options={
                "verbose_name": "SDN Subnet",
                "verbose_name_plural": "SDN Subnets",
                "ordering": ("endpoint", "cluster_name", "vnet_name", "subnet"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=["endpoint", "cluster_name", "vnet_name", "subnet"],
                        name="nbpx_sdnsubnet_unique_endpoint_cluster_vnet_subnet",
                    )
                ],
            },
        ),
        create_model_idempotent(
            name="ProxmoxSdnBinding",
            fields=[
                *_netbox_model_fields(),
                ("endpoint", _endpoint_field("sdn_bindings")),
                ("cluster_name", models.CharField(max_length=255)),
                ("source_type", models.CharField(max_length=64)),
                ("source_name", models.CharField(max_length=512)),
                ("node", models.CharField(blank=True, max_length=255)),
                ("zone_name", models.CharField(blank=True, max_length=255)),
                ("vnet_name", models.CharField(blank=True, max_length=255)),
                ("target_type", models.CharField(blank=True, max_length=64)),
                ("target_id", models.PositiveBigIntegerField(blank=True, null=True)),
                ("status", models.CharField(default="active", max_length=64)),
                ("conflict_reason", models.TextField(blank=True)),
                ("raw_config", models.JSONField(blank=True, default=dict)),
            ],
            options={
                "verbose_name": "SDN Binding",
                "verbose_name_plural": "SDN Bindings",
                "ordering": ("endpoint", "cluster_name", "source_type", "source_name"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=[
                            "endpoint",
                            "cluster_name",
                            "source_type",
                            "source_name",
                        ],
                        name="nbpx_sdnbinding_unique_endpoint_cluster_source",
                    )
                ],
            },
        ),
    ]
