"""Add VM reconciliation engine runtime setting."""

from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import add_field_idempotent


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0042_proxmoxendpoint_ssh_terminal"),
    ]

    operations = [
        add_field_idempotent(
            model_name="proxboxpluginsettings",
            field_name="reconciliation_engine",
            field=models.CharField(
                choices=[
                    ("python", "Python (default)"),
                    ("compare", "Compare Python and Rust"),
                    ("rust", "Rust + PyO3"),
                ],
                default="python",
                help_text=(
                    "Engine used by proxbox-api to build VM operation queues. Python is the "
                    "default implementation; compare runs Python and Rust then returns Python "
                    "output; rust requires the optional proxbox-reconcile-rs PyO3 package."
                ),
                max_length=16,
                verbose_name="VM reconciliation engine",
            ),
        ),
    ]
