from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import add_field_idempotent


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0073_netboxendpoint_pushed_credential_fingerprint"),
    ]

    operations = [
        add_field_idempotent(
            "proxmoxendpoint",
            "pushed_credential_fingerprint",
            models.CharField(
                blank=True,
                default="",
                editable=False,
                help_text=(
                    "Non-reversible fingerprint of the credentials last "
                    "successfully pushed to the ProxBox backend. Maintained "
                    "automatically by the push itself; used to detect "
                    "credentials rotated since that push."
                ),
                max_length=64,
                verbose_name="Pushed credential fingerprint",
            ),
        ),
    ]
