from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0097_add_cloudinit_credential_reference"),
    ]

    operations = [
        migrations.AddField(
            model_name="proxmoxendpoint",
            name="iana_timezone",
            field=models.CharField(
                blank=True,
                default="",
                editable=False,
                help_text="Proxmox endpoint time zone discovered during synchronization.",
                max_length=64,
                verbose_name="IANA time zone",
            ),
        ),
    ]
