"""Adopt guest_os_model as the universal VM interface sync default.

Migration 0059 introduced the ``guest_os_model`` strategy but backfilled
existing installs to ``legacy_rename`` for backward compatibility. This
data-only migration supersedes that backfill by moving rows still set to
``legacy_rename`` back to ``guest_os_model`` for all installs. The
``legacy_rename`` choice remains selectable for operators who intentionally
want the deprecated rename behavior.
"""

from django.db import migrations


def forward(apps, schema_editor):
    ProxboxPluginSettings = apps.get_model(
        "netbox_proxbox",
        "ProxboxPluginSettings",
    )
    ProxboxPluginSettings.objects.filter(
        vm_interface_sync_strategy="legacy_rename",
    ).update(vm_interface_sync_strategy="guest_os_model")


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0059_guest_vm_interface"),
    ]

    operations = [
        migrations.RunPython(
            forward,
            migrations.RunPython.noop,
        ),
    ]
