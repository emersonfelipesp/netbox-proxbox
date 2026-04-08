"""Add SSRF protection settings to ProxboxPluginSettings."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0022_populate_fastapi_tokens"),
    ]

    operations = [
        migrations.AddField(
            model_name="proxboxpluginsettings",
            name="ssrf_protection_enabled",
            field=models.BooleanField(
                default=True,
                help_text="When enabled, validates that Proxmox/NetBox/FastAPI endpoints do not point to reserved or internal IP addresses. Disable only in trusted environments.",
                verbose_name="Enable SSRF protection",
            ),
        ),
        migrations.AddField(
            model_name="proxboxpluginsettings",
            name="allow_private_ips",
            field=models.BooleanField(
                default=True,
                help_text="When enabled, allows endpoints with private IP addresses (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16). Recommended for on-premises deployments.",
                verbose_name="Allow private IP addresses",
            ),
        ),
        migrations.AddField(
            model_name="proxboxpluginsettings",
            name="additional_allowed_ip_ranges",
            field=models.TextField(
                blank=True,
                default="",
                help_text="One CIDR range per line (e.g., 10.30.0.0/16). IPs in these ranges are always allowed, regardless of other SSRF settings.",
                verbose_name="Additional allowed IP CIDR ranges",
            ),
        ),
        migrations.AddField(
            model_name="proxboxpluginsettings",
            name="explicitly_blocked_ip_ranges",
            field=models.TextField(
                blank=True,
                default="",
                help_text="One CIDR range per line. IPs in these ranges are always blocked, even if they match allowed ranges above.",
                verbose_name="Explicitly blocked IP CIDR ranges",
            ),
        ),
    ]
