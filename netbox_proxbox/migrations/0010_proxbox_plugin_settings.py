"""Add persisted plugin settings for ProxBox runtime toggles."""

import taggit.managers
import utilities.json
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("extras", "0134_owner"),
        ("netbox_proxbox", "0009_squashed_post_v006b2_to_v008"),
        ("users", "0015_owner"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProxboxPluginSettings",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
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
                    "singleton_key",
                    models.CharField(
                        default="default",
                        editable=False,
                        max_length=32,
                        unique=True,
                    ),
                ),
                (
                    "use_guest_agent_interface_name",
                    models.BooleanField(
                        default=True,
                        help_text=(
                            "When enabled, VM interface names use QEMU guest-agent names when "
                            "available (for example ens18) instead of generic Proxmox labels "
                            "(for example net0/nic0)."
                        ),
                        verbose_name="Use guest agent interface name",
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
                "verbose_name": "Proxbox plugin settings",
                "verbose_name_plural": "Proxbox plugin settings",
            },
        ),
    ]
