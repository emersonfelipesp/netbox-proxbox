"""Create NodeSSHCredential table for hardware-discovery SSH credentials."""

from django.db import migrations, models
import django.db.models.deletion
import taggit.managers
import utilities.json


class Migration(migrations.Migration):
    dependencies = [
        ("extras", "0100_customfield_ui_attrs"),
        ("netbox_proxbox", "0047_pluginsettings_hardware_discovery"),
    ]

    operations = [
        migrations.CreateModel(
            name="NodeSSHCredential",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "custom_field_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=utilities.json.CustomFieldJSONEncoder,
                    ),
                ),
                (
                    "username",
                    models.CharField(
                        help_text=(
                            "Dedicated discovery user on the node (e.g. proxbox-discovery). "
                            "Should NOT be root — pair with a least-privilege sudoers entry."
                        ),
                        max_length=64,
                        verbose_name="SSH username",
                    ),
                ),
                (
                    "port",
                    models.PositiveIntegerField(
                        default=22,
                        help_text="TCP port for the SSH listener. Default 22.",
                        verbose_name="SSH port",
                    ),
                ),
                (
                    "auth_method",
                    models.CharField(
                        choices=[
                            ("key", "SSH private key (recommended)"),
                            ("password", "Password (fallback)"),
                        ],
                        default="key",
                        help_text=(
                            "Prefer key-based authentication. Password is a fallback for "
                            "legacy fleets — only key-based unlocks the locked-down sudoers "
                            "/ ForceCommand pattern."
                        ),
                        max_length=8,
                        verbose_name="Authentication method",
                    ),
                ),
                (
                    "known_host_fingerprint",
                    models.CharField(
                        help_text=(
                            "Canonical SHA256:<base64> form. Proxbox refuses to connect "
                            "unless the node's host key matches this exact value (no TOFU)."
                        ),
                        max_length=128,
                        verbose_name="Pinned host-key SHA-256 fingerprint",
                    ),
                ),
                (
                    "sudo_required",
                    models.BooleanField(
                        default=True,
                        help_text=(
                            "When enabled, the discovery driver prepends 'sudo -n' to each "
                            "discovery command. Disable only if the user already has direct "
                            "permissions for dmidecode/ip/ethtool."
                        ),
                        verbose_name="Run discovery commands under sudo -n",
                    ),
                ),
                (
                    "password_enc",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Fernet-encrypted password ciphertext. Internal.",
                        verbose_name="Encrypted password",
                    ),
                ),
                (
                    "private_key_enc",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Fernet-encrypted OpenSSH PEM ciphertext. Internal.",
                        verbose_name="Encrypted private key",
                    ),
                ),
                (
                    "node",
                    models.OneToOneField(
                        help_text="Node these credentials authorize SSH access to.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ssh_credential",
                        to="netbox_proxbox.proxmoxnode",
                        verbose_name="Proxmox node",
                    ),
                ),
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem",
                        to="extras.Tag",
                    ),
                ),
            ],
            options={
                "verbose_name": "Node SSH credential",
                "verbose_name_plural": "Node SSH credentials",
                "ordering": ("node",),
            },
        ),
    ]
