from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0028_fastapiendpoint_websocket_port_nullable"),
    ]

    operations = [
        migrations.AddField(
            model_name="proxboxpluginsettings",
            name="primary_ip_preference",
            field=models.CharField(
                choices=[("ipv4", "Prefer IPv4"), ("ipv6", "Prefer IPv6")],
                default="ipv4",
                help_text=(
                    "Preferred IP family when Proxbox selects the VM primary IP. "
                    "Choose IPv4 or IPv6."
                ),
                max_length=4,
                verbose_name="Primary IP preference",
            ),
        ),
    ]
