"""Migration 0041: PVE 9.2 SDN and datacenter models.

Adds 3 SDN models and 1 datacenter CPU model, plus the node location field:
  - ProxmoxSdnFabric
  - ProxmoxSdnRouteMap
  - ProxmoxSdnPrefixList
  - ProxmoxDatacenterCpuModel
  - ProxmoxNode.location (CharField)

Every CreateModel/AddField is wrapped with the idempotent helpers so
this migration is safe against clean installs and partial-legacy environments.
"""
from __future__ import annotations

import django.db.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import (
    add_field_idempotent,
    create_model_idempotent,
)


class Migration(migrations.Migration):

    dependencies = [
        ("extras", "0134_owner"),
        ("netbox_proxbox", "0040_endpoint_enabled"),
        ("virtualization", "0052_gfk_indexes"),
    ]

    operations = [
        # ── ProxmoxSdnFabric ─────────────────────────────────────────────────
        create_model_idempotent(
            name="ProxmoxSdnFabric",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                (
                    "endpoint",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sdn_fabrics",
                        to="netbox_proxbox.proxmoxendpoint",
                        verbose_name="Proxmox endpoint",
                    ),
                ),
                ("cluster_name", models.CharField(help_text="Proxmox cluster name.", max_length=255)),
                ("fabric_name", models.CharField(help_text="SDN fabric identifier.", max_length=255)),
                (
                    "fabric_type",
                    models.CharField(
                        choices=[
                            ("wireguard", "WireGuard"),
                            ("bgp", "BGP"),
                            ("vxlan", "VXLAN"),
                            ("ospf", "OSPF"),
                        ],
                        help_text="SDN fabric type.",
                        max_length=32,
                    ),
                ),
                ("asn", models.IntegerField(blank=True, help_text="BGP ASN.", null=True)),
                ("advertise_subnets", models.BooleanField(default=False)),
                ("disable_arp_nd_suppression", models.BooleanField(default=False)),
                ("vrf_vxlan", models.IntegerField(blank=True, help_text="VRF VXLAN ID.", null=True)),
                ("peers", models.JSONField(blank=True, default=list)),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Active"), ("stale", "Stale")],
                        default="active",
                        max_length=20,
                    ),
                ),
                ("raw_config", models.JSONField(blank=True, default=dict)),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
            ],
            options={
                "verbose_name": "SDN Fabric",
                "verbose_name_plural": "SDN Fabrics",
                "ordering": ("endpoint", "cluster_name", "fabric_name"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=["endpoint", "cluster_name", "fabric_name"],
                        name="netbox_proxbox_sdnfabric_unique_endpoint_cluster_fabric",
                    )
                ],
            },
        ),
        # ── ProxmoxSdnRouteMap ───────────────────────────────────────────────
        create_model_idempotent(
            name="ProxmoxSdnRouteMap",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                (
                    "endpoint",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sdn_route_maps",
                        to="netbox_proxbox.proxmoxendpoint",
                        verbose_name="Proxmox endpoint",
                    ),
                ),
                ("cluster_name", models.CharField(help_text="Proxmox cluster name.", max_length=255)),
                ("name", models.CharField(help_text="Route-map name.", max_length=255)),
                ("action", models.CharField(blank=True, help_text="permit or deny.", max_length=16)),
                ("match_peer", models.CharField(blank=True, max_length=255)),
                ("match_ip", models.CharField(blank=True, max_length=255)),
                ("set_community", models.CharField(blank=True, max_length=255)),
                ("order", models.IntegerField(default=0)),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Active"), ("stale", "Stale")],
                        default="active",
                        max_length=20,
                    ),
                ),
                ("raw_config", models.JSONField(blank=True, default=dict)),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
            ],
            options={
                "verbose_name": "SDN Route Map",
                "verbose_name_plural": "SDN Route Maps",
                "ordering": ("endpoint", "cluster_name", "name", "order"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=["endpoint", "cluster_name", "name", "order"],
                        name="netbox_proxbox_sdnroutemap_unique_endpoint_cluster_name_order",
                    )
                ],
            },
        ),
        # ── ProxmoxSdnPrefixList ─────────────────────────────────────────────
        create_model_idempotent(
            name="ProxmoxSdnPrefixList",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                (
                    "endpoint",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sdn_prefix_lists",
                        to="netbox_proxbox.proxmoxendpoint",
                        verbose_name="Proxmox endpoint",
                    ),
                ),
                ("cluster_name", models.CharField(help_text="Proxmox cluster name.", max_length=255)),
                ("name", models.CharField(help_text="Prefix-list name.", max_length=255)),
                ("cidr", models.CharField(blank=True, help_text="CIDR prefix.", max_length=64)),
                ("action", models.CharField(blank=True, help_text="permit or deny.", max_length=16)),
                ("le", models.IntegerField(blank=True, help_text="Less-or-equal prefix length.", null=True)),
                ("ge", models.IntegerField(blank=True, help_text="Greater-or-equal prefix length.", null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Active"), ("stale", "Stale")],
                        default="active",
                        max_length=20,
                    ),
                ),
                ("raw_config", models.JSONField(blank=True, default=dict)),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
            ],
            options={
                "verbose_name": "SDN Prefix List",
                "verbose_name_plural": "SDN Prefix Lists",
                "ordering": ("endpoint", "cluster_name", "name"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=["endpoint", "cluster_name", "name"],
                        name="netbox_proxbox_sdnprefixlist_unique_endpoint_cluster_name",
                    )
                ],
            },
        ),
        # ── ProxmoxDatacenterCpuModel ────────────────────────────────────────
        create_model_idempotent(
            name="ProxmoxDatacenterCpuModel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                (
                    "endpoint",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="datacenter_cpu_models",
                        to="netbox_proxbox.proxmoxendpoint",
                        verbose_name="Proxmox endpoint",
                    ),
                ),
                ("cluster_name", models.CharField(help_text="Proxmox cluster name.", max_length=255)),
                ("cputype", models.CharField(help_text="Custom CPU type identifier.", max_length=255)),
                ("base_cputype", models.CharField(blank=True, help_text="Base CPU type.", max_length=255)),
                ("flags", models.CharField(blank=True, help_text="CPU feature flags.", max_length=512)),
                ("vendor_id", models.CharField(blank=True, help_text="CPUID vendor ID string.", max_length=255)),
                ("level", models.IntegerField(blank=True, help_text="CPUID level.", null=True)),
                ("description", models.TextField(blank=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Active"), ("stale", "Stale")],
                        default="active",
                        max_length=20,
                    ),
                ),
                ("raw_config", models.JSONField(blank=True, default=dict)),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
            ],
            options={
                "verbose_name": "Datacenter CPU Model",
                "verbose_name_plural": "Datacenter CPU Models",
                "ordering": ("endpoint", "cluster_name", "cputype"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=["endpoint", "cluster_name", "cputype"],
                        name="netbox_proxbox_datacentercpumodel_unique_endpoint_cluster_cputype",
                    )
                ],
            },
        ),
        # ── ProxmoxNode.location ─────────────────────────────────────────────
        add_field_idempotent(
            "proxmoxnode",
            "location",
            models.CharField(
                blank=True,
                default="",
                help_text="Geographic or physical location of the node (PVE 9.2+).",
                max_length=255,
                verbose_name="Location",
            ),
            preserve_default=False,
        ),
    ]
