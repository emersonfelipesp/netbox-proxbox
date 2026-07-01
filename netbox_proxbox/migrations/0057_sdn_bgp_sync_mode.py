from django.db import migrations, models

import utilities.choices


SYNC_MODE_CHOICES = utilities.choices.ChoiceSet(
    [
        ("always", "Always", "green"),
        ("bootstrap_only", "Bootstrap only", "blue"),
        ("disabled", "Disabled", "red"),
    ]
)


class Migration(migrations.Migration):

    dependencies = [
        ("netbox_proxbox", "0056_proxmoxendpoint_access_methods"),
    ]

    operations = [
        migrations.AddField(
            model_name="proxboxpluginsettings",
            name="sync_mode_sdn_bgp",
            field=models.CharField(
                choices=SYNC_MODE_CHOICES,
                default="disabled",
                help_text=(
                    "Controls optional netbox-bgp projection for Proxmox SDN BGP "
                    "peer groups, sessions, routing policies, and prefix lists."
                ),
                max_length=16,
                verbose_name="SDN BGP projection sync mode",
            ),
        ),
        migrations.AddField(
            model_name="proxmoxendpoint",
            name="sync_mode_sdn_bgp",
            field=models.CharField(
                blank=True,
                choices=SYNC_MODE_CHOICES,
                help_text=(
                    "Per-endpoint override for optional netbox-bgp SDN projection. "
                    "Leave blank to inherit."
                ),
                max_length=16,
                null=True,
                verbose_name="SDN BGP projection sync mode",
            ),
        ),
    ]
