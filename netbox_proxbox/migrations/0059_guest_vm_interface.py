"""Add guest OS VM interface inventory and sync strategy setting."""

import django.db.models.deletion
import netbox.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import (
    add_field_idempotent,
    create_model_idempotent,
)


VM_INTERFACE_SYNC_STRATEGY_CHOICES = [
    ("guest_os_model", "Guest OS model"),
    ("legacy_rename", "Legacy rename"),
]


def _backfill_existing_installs_to_legacy(apps, schema_editor):
    """Preserve pre-upgrade behavior on existing installs only.

    New installs get the model default ``guest_os_model`` (the new standard);
    an existing install that was already syncing under the old single-interface
    rename behavior must keep it so an upgrade never silently changes
    interface-sync behavior (operators opt into ``guest_os_model`` explicitly).

    The settings singleton alone cannot distinguish the two: dependency ``0058``
    calls ``get_or_create`` on it, so a from-scratch install is not rowless when
    this runs. An install that has ever synced interfaces must have at least one
    ``ProxmoxEndpoint`` configured, so endpoint existence is the reliable
    "existing install" signal. Only backfill when real Proxmox inventory exists.
    """
    ProxmoxEndpoint = apps.get_model("netbox_proxbox", "ProxmoxEndpoint")
    if not ProxmoxEndpoint.objects.exists():
        # Fresh install: keep the model default (guest_os_model, the new standard).
        return
    ProxboxPluginSettings = apps.get_model("netbox_proxbox", "ProxboxPluginSettings")
    ProxboxPluginSettings.objects.update(vm_interface_sync_strategy="legacy_rename")


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0058_encrypt_primary_endpoint_secrets"),
    ]

    operations = [
        create_model_idempotent(
            name="GuestVMInterface",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
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
                ("name", models.CharField(max_length=128)),
                (
                    "mac_address",
                    models.CharField(
                        blank=True,
                        help_text="Guest OS-reported MAC address for informational matching.",
                        max_length=32,
                    ),
                ),
                ("enabled", models.BooleanField(default=True)),
                ("mtu", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem",
                        to="extras.Tag",
                    ),
                ),
                (
                    "virtual_machine",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proxbox_guest_interfaces",
                        to="virtualization.virtualmachine",
                    ),
                ),
                (
                    "vm_interface",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="guest_interface",
                        to="virtualization.vminterface",
                    ),
                ),
            ],
            options={
                "ordering": ("virtual_machine", "name"),
                "verbose_name": "Guest VM interface",
                "verbose_name_plural": "Guest VM interfaces",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("virtual_machine", "name"),
                        name="unique_guest_vm_interface_vm_name",
                    ),
                ],
            },
            bases=(netbox.models.deletion.DeleteMixin, models.Model),
        ),
        create_model_idempotent(
            name="GuestVMInterfaceAddress",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
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
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem",
                        to="extras.Tag",
                    ),
                ),
                (
                    "guest_interface",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="addresses",
                        to="netbox_proxbox.guestvminterface",
                    ),
                ),
                (
                    "ip_address",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="proxbox_guest_interface_addresses",
                        to="ipam.ipaddress",
                    ),
                ),
            ],
            options={
                "verbose_name": "Guest VM interface address",
                "verbose_name_plural": "Guest VM interface addresses",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("guest_interface", "ip_address"),
                        name="unique_guest_vm_interface_address",
                    ),
                ],
            },
            bases=(netbox.models.deletion.DeleteMixin, models.Model),
        ),
        add_field_idempotent(
            model_name="proxboxpluginsettings",
            field_name="vm_interface_sync_strategy",
            field=models.CharField(
                choices=VM_INTERFACE_SYNC_STRATEGY_CHOICES,
                default="guest_os_model",
                help_text=(
                    "Controls how proxbox-api represents VM interfaces. The default keeps "
                    "Proxmox netX NICs as core VMInterface rows and writes guest OS names "
                    "to GuestVMInterface rows. Legacy rename keeps the older "
                    "single-interface rename behavior."
                ),
                max_length=32,
                verbose_name="VM interface sync strategy",
            ),
        ),
        migrations.RunPython(
            _backfill_existing_installs_to_legacy,
            migrations.RunPython.noop,
        ),
    ]
