from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import add_field_idempotent


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0081_encrypted_secret_reset_permission"),
    ]

    operations = [
        add_field_idempotent(
            "proxmoxendpoint",
            "allow_packer_template_builds",
            models.BooleanField(
                default=False,
                help_text=(
                    "Explicitly authorize netbox-packer to create Cloud-Init template "
                    "images on this endpoint. Default off and effective only while "
                    "'Allow Proxmox-side writes' is also enabled. This capability does "
                    "not authorize any other Proxmox mutation."
                ),
                verbose_name="Allow netbox-packer template builds",
            ),
        ),
        add_field_idempotent(
            "proxmoxendpoint",
            "packer_template_builds_backend_authorized",
            models.BooleanField(
                default=False,
                editable=False,
                help_text=(
                    "Internal record of the last netbox-packer template-build grant "
                    "successfully confirmed on proxbox-api. A true value blocks "
                    "endpoint deletion until a later save confirms backend revocation."
                ),
                verbose_name="Backend-authorized netbox-packer template builds",
            ),
        ),
    ]
