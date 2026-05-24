"""Add endpoint-level SSH terminal fallback credentials."""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0041_firecracker_cloud"),
    ]

    operations = [
        migrations.AddField(
            model_name="proxmoxendpoint",
            name="ssh_auth_method",
            field=models.CharField(
                choices=[
                    ("key", "SSH private key (recommended)"),
                    ("password", "Password (fallback)"),
                ],
                default="key",
                help_text="Prefer key-based authentication. Password is a fallback.",
                max_length=8,
                verbose_name="SSH authentication method",
            ),
        ),
        migrations.AddField(
            model_name="proxmoxendpoint",
            name="ssh_known_host_fingerprint",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Canonical SHA256:<base64> form. Proxbox refuses terminal access "
                    "unless the host key matches this exact value."
                ),
                max_length=128,
                verbose_name="Pinned SSH host-key SHA-256 fingerprint",
            ),
        ),
        migrations.AddField(
            model_name="proxmoxendpoint",
            name="ssh_password_enc",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Fernet-encrypted fallback SSH password ciphertext. Internal.",
                verbose_name="Encrypted SSH password",
            ),
        ),
        migrations.AddField(
            model_name="proxmoxendpoint",
            name="ssh_port",
            field=models.PositiveIntegerField(
                default=22,
                help_text="Fallback SSH listener port for this endpoint.",
                validators=[MinValueValidator(1), MaxValueValidator(65535)],
                verbose_name="SSH port",
            ),
        ),
        migrations.AddField(
            model_name="proxmoxendpoint",
            name="ssh_private_key_enc",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Fernet-encrypted fallback SSH private key ciphertext. Internal.",
                verbose_name="Encrypted SSH private key",
            ),
        ),
        migrations.AddField(
            model_name="proxmoxendpoint",
            name="ssh_username",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Fallback SSH username for the endpoint itself when no per-node "
                    "NodeSSHCredential is selected."
                ),
                max_length=64,
                verbose_name="SSH username",
            ),
        ),
        migrations.AlterModelOptions(
            name="proxmoxendpoint",
            options={
                "ordering": ("name", "pk"),
                "permissions": (
                    ("open_ssh_terminal", "Can open Proxbox SSH terminal"),
                ),
                "verbose_name": "Proxmox endpoint",
                "verbose_name_plural": "Proxmox endpoints",
            },
        ),
    ]
