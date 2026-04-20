from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0029_proxboxpluginsettings_primary_ip_preference"),
    ]

    operations = [
        migrations.AlterField(
            model_name="vmtaskhistory",
            name="status",
            field=models.TextField(
                help_text="Task outcome or current state.",
            ),
        ),
        migrations.AlterField(
            model_name="vmtaskhistory",
            name="exitstatus",
            field=models.TextField(
                blank=True,
                null=True,
                help_text="Raw Proxmox task exit status.",
            ),
        ),
    ]
