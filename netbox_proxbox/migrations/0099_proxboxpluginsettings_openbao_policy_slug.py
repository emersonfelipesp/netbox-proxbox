"""Add the exact OpenBao policy selector used by Proxbox credentials."""

from django.db import migrations, models

from ._idempotent_ops import add_field_idempotent


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0098_proxmoxendpoint_iana_timezone"),
    ]

    operations = [
        add_field_idempotent(
            "proxboxpluginsettings",
            "openbao_policy_slug",
            models.SlugField(
                default="proxbox",
                help_text=(
                    "Exact CredentialPolicy slug on the default OpenBao SecretEngine. "
                    "No other policy is selected when it is missing."
                ),
                max_length=100,
                verbose_name="OpenBao policy slug",
            ),
        ),
    ]
