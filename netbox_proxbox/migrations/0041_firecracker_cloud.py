from __future__ import annotations

import uuid

import django.core.validators
import django.db.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import create_model_idempotent


class Migration(migrations.Migration):
    dependencies = [
        ("extras", "0134_owner"),
        ("tenancy", "0023_add_mptt_tree_indexes"),
        ("virtualization", "0052_gfk_indexes"),
        ("netbox_proxbox", "0040_firewall_write_status"),
    ]

    operations = [
        create_model_idempotent(
            name="FirecrackerHostPool",
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
                ("name", models.CharField(max_length=255, verbose_name="Name")),
                (
                    "slug",
                    models.SlugField(
                        help_text="Stable identifier used by Cloud API clients.",
                        max_length=255,
                        unique=True,
                        verbose_name="Slug",
                    ),
                ),
                (
                    "description",
                    models.TextField(blank=True, verbose_name="Description"),
                ),
                (
                    "default_network_mode",
                    models.CharField(
                        choices=[("nat", "NAT"), ("bridge", "Bridge")],
                        default="nat",
                        max_length=16,
                        verbose_name="Default network mode",
                    ),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="Active")),
                (
                    "allowed_tenants",
                    models.ManyToManyField(
                        blank=True,
                        help_text=(
                            "Tenants allowed to provision here. Leave empty for all tenants."
                        ),
                        related_name="proxbox_firecracker_host_pools",
                        to="tenancy.tenant",
                        verbose_name="Allowed tenants",
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
                "verbose_name": "Firecracker host pool",
                "verbose_name_plural": "Firecracker host pools",
                "ordering": ("name",),
            },
        ),
        create_model_idempotent(
            name="FirecrackerImageTemplate",
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
                ("name", models.CharField(max_length=255, verbose_name="Name")),
                (
                    "slug",
                    models.SlugField(max_length=255, unique=True, verbose_name="Slug"),
                ),
                (
                    "description",
                    models.TextField(blank=True, verbose_name="Description"),
                ),
                (
                    "architecture",
                    models.CharField(
                        default="x86_64",
                        max_length=32,
                        verbose_name="Architecture",
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
                            ("proxmox-pbs", "Proxmox Backup Server"),
                            ("proxmox-pdm", "Proxmox Datacenter Manager"),
                            ("pfsense", "pfSense"),
                            ("opnsense", "OPNsense"),
                        ],
                        default="generic",
                        max_length=32,
                        verbose_name="OS family",
                    ),
                ),
                (
                    "os_release",
                    models.CharField(
                        blank=True,
                        max_length=64,
                        verbose_name="OS release",
                    ),
                ),
                (
                    "kernel_image_url",
                    models.CharField(
                        help_text=(
                            "HTTP(S) URL or host-agent-local path for the Firecracker kernel."
                        ),
                        max_length=1024,
                        verbose_name="Kernel image URL",
                    ),
                ),
                (
                    "kernel_image_sha256",
                    models.CharField(max_length=64, verbose_name="Kernel SHA256"),
                ),
                (
                    "rootfs_image_url",
                    models.CharField(
                        help_text=(
                            "HTTP(S) URL or host-agent-local path for the root filesystem."
                        ),
                        max_length=1024,
                        verbose_name="Rootfs image URL",
                    ),
                ),
                (
                    "rootfs_image_sha256",
                    models.CharField(max_length=64, verbose_name="Rootfs SHA256"),
                ),
                (
                    "default_kernel_args",
                    models.TextField(blank=True, verbose_name="Default kernel args"),
                ),
                (
                    "default_user",
                    models.CharField(
                        default="cloud-user",
                        max_length=64,
                        verbose_name="Default user",
                    ),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="Active")),
                (
                    "allowed_tenants",
                    models.ManyToManyField(
                        blank=True,
                        help_text=(
                            "Tenants allowed to use this image. Leave empty for all tenants."
                        ),
                        related_name="proxbox_firecracker_image_templates",
                        to="tenancy.tenant",
                        verbose_name="Allowed tenants",
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
                "verbose_name": "Firecracker image template",
                "verbose_name_plural": "Firecracker image templates",
                "ordering": ("name", "architecture"),
                "permissions": [
                    (
                        "provision_firecracker_microvm",
                        "Can provision a Firecracker micro-VM",
                    ),
                ],
            },
        ),
        create_model_idempotent(
            name="FirecrackerHost",
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
                ("name", models.CharField(max_length=255, verbose_name="Name")),
                (
                    "agent_base_url",
                    models.URLField(
                        help_text="Base URL for the Firecracker host-agent HTTP API.",
                        max_length=500,
                        verbose_name="Agent base URL",
                    ),
                ),
                (
                    "agent_token_enc",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Fernet-encrypted host-agent bearer token. Internal.",
                        verbose_name="Encrypted agent token",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("ready", "Ready"),
                            ("draining", "Draining"),
                            ("offline", "Offline"),
                            ("error", "Error"),
                        ],
                        default="offline",
                        max_length=32,
                        verbose_name="Status",
                    ),
                ),
                ("firecracker_version", models.CharField(blank=True, max_length=64)),
                (
                    "kvm_available",
                    models.BooleanField(default=False, verbose_name="KVM available"),
                ),
                (
                    "supports_nat",
                    models.BooleanField(default=True, verbose_name="Supports NAT"),
                ),
                (
                    "supports_bridge",
                    models.BooleanField(default=False, verbose_name="Supports bridge"),
                ),
                (
                    "capacity_vcpus",
                    models.PositiveIntegerField(
                        default=0,
                        validators=[django.core.validators.MinValueValidator(0)],
                        verbose_name="vCPU capacity",
                    ),
                ),
                (
                    "capacity_memory_mib",
                    models.PositiveIntegerField(
                        default=0,
                        validators=[django.core.validators.MinValueValidator(0)],
                        verbose_name="Memory capacity (MiB)",
                    ),
                ),
                (
                    "capacity_disk_mib",
                    models.PositiveIntegerField(
                        default=0,
                        validators=[django.core.validators.MinValueValidator(0)],
                        verbose_name="Disk capacity (MiB)",
                    ),
                ),
                (
                    "allocated_vcpus",
                    models.PositiveIntegerField(
                        default=0,
                        validators=[django.core.validators.MinValueValidator(0)],
                        verbose_name="Allocated vCPUs",
                    ),
                ),
                (
                    "allocated_memory_mib",
                    models.PositiveIntegerField(
                        default=0,
                        validators=[django.core.validators.MinValueValidator(0)],
                        verbose_name="Allocated memory (MiB)",
                    ),
                ),
                (
                    "allocated_disk_mib",
                    models.PositiveIntegerField(
                        default=0,
                        validators=[django.core.validators.MinValueValidator(0)],
                        verbose_name="Allocated disk (MiB)",
                    ),
                ),
                (
                    "last_seen",
                    models.DateTimeField(blank=True, null=True, verbose_name="Last seen"),
                ),
                (
                    "host_vm",
                    models.ForeignKey(
                        blank=True,
                        help_text="NetBox VM that runs the Firecracker host agent.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="firecracker_host_agent",
                        to="virtualization.virtualmachine",
                        verbose_name="Proxmox host VM",
                    ),
                ),
                (
                    "pool",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="hosts",
                        to="netbox_proxbox.firecrackerhostpool",
                        verbose_name="Host pool",
                    ),
                ),
                (
                    "proxmox_node",
                    models.ForeignKey(
                        blank=True,
                        help_text="Physical Proxmox node currently hosting the agent VM.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="firecracker_hosts",
                        to="netbox_proxbox.proxmoxnode",
                        verbose_name="Proxmox node",
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
                "verbose_name": "Firecracker host",
                "verbose_name_plural": "Firecracker hosts",
                "ordering": ("pool", "name"),
                "unique_together": {("pool", "name")},
            },
        ),
        create_model_idempotent(
            name="FirecrackerMicroVM",
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
                    "microvm_id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        unique=True,
                        verbose_name="Micro-VM ID",
                    ),
                ),
                ("name", models.CharField(max_length=255, verbose_name="Name")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("provisioning", "Provisioning"),
                            ("running", "Running"),
                            ("stopped", "Stopped"),
                            ("error", "Error"),
                            ("deleted", "Deleted"),
                        ],
                        default="provisioning",
                        max_length=32,
                        verbose_name="Status",
                    ),
                ),
                (
                    "network_mode",
                    models.CharField(
                        choices=[("nat", "NAT"), ("bridge", "Bridge")],
                        default="nat",
                        max_length=16,
                        verbose_name="Network mode",
                    ),
                ),
                (
                    "vcpus",
                    models.PositiveSmallIntegerField(default=1, verbose_name="vCPUs"),
                ),
                (
                    "memory_mib",
                    models.PositiveIntegerField(default=512, verbose_name="Memory (MiB)"),
                ),
                (
                    "disk_mib",
                    models.PositiveIntegerField(default=1024, verbose_name="Disk (MiB)"),
                ),
                (
                    "guest_ip",
                    models.GenericIPAddressField(
                        blank=True,
                        null=True,
                        verbose_name="Guest IP",
                    ),
                ),
                (
                    "mac_address",
                    models.CharField(
                        blank=True,
                        max_length=32,
                        verbose_name="MAC address",
                    ),
                ),
                (
                    "bridge_name",
                    models.CharField(blank=True, max_length=64, verbose_name="Bridge"),
                ),
                (
                    "tap_name",
                    models.CharField(blank=True, max_length=64, verbose_name="TAP"),
                ),
                ("ssh_authorized_keys", models.JSONField(blank=True, default=list)),
                ("agent_payload", models.JSONField(blank=True, default=dict)),
                ("last_agent_state", models.JSONField(blank=True, default=dict)),
                (
                    "started_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="Started at"),
                ),
                (
                    "stopped_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="Stopped at"),
                ),
                (
                    "host",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="microvms",
                        to="netbox_proxbox.firecrackerhost",
                        verbose_name="Firecracker host",
                    ),
                ),
                (
                    "image",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="microvms",
                        to="netbox_proxbox.firecrackerimagetemplate",
                        verbose_name="Image template",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="proxbox_firecracker_microvms",
                        to="tenancy.tenant",
                        verbose_name="Tenant",
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
                "verbose_name": "Firecracker micro-VM",
                "verbose_name_plural": "Firecracker micro-VMs",
                "ordering": ("tenant", "name"),
                "unique_together": {("host", "name")},
            },
        ),
    ]
