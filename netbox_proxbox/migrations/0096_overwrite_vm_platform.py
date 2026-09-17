"""Add the default-off VM platform overwrite gate and endpoint override."""

from django.db import migrations, models
from django.utils.translation import gettext_lazy as _

from netbox_proxbox.migrations._idempotent_ops import add_field_idempotent


class Migration(migrations.Migration):
    dependencies = [("netbox_proxbox", "0095_standalone_vm_console")]

    operations = [
        add_field_idempotent(
            "proxboxpluginsettings",
            "overwrite_vm_platform",
            models.BooleanField(
                default=False,
                help_text=_(
                    "When enabled, sync reconciles the platform on existing NetBox "
                    "virtual machines from the Proxmox guest operating system. "
                    "Disabled by default to preserve operator-managed platform assignments."
                ),
                verbose_name=_("Overwrite VM platform"),
            ),
        ),
        add_field_idempotent(
            "proxmoxendpoint",
            "overwrite_vm_platform",
            models.BooleanField(
                blank=True,
                help_text=_(
                    "Per-endpoint override for the global Proxbox setting. "
                    "Leave blank to inherit."
                ),
                null=True,
                verbose_name=_("Overwrite VM platform"),
            ),
        ),
    ]
