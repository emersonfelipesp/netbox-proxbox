"""Retire the external handoff setting and add the console permission."""

from django.db import migrations
from django.utils.translation import gettext_lazy as _


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0094_automatic_credential_storage_default"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="proxboxpluginsettings",
            name="console_url",
        ),
        migrations.AlterModelOptions(
            name="proxmoxendpoint",
            options={
                "ordering": ("name", "pk"),
                "permissions": (
                    ("open_ssh_terminal", _("Can open Proxbox SSH terminal")),
                    (
                        "open_console_proxmoxendpoint",
                        _("Can open Proxbox VM consoles"),
                    ),
                ),
                "verbose_name": _("Proxmox endpoint"),
                "verbose_name_plural": _("Proxmox endpoints"),
            },
        ),
    ]
