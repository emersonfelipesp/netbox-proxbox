"""Create the singleton ``PBSPluginSettings`` table.

PR C1 of issue #325. Subsequent migrations add the PBS domain models
(``PBSEndpoint``, ``PBSNode``, ``PBSDatastore``, ``PBSBackupGroup``,
``PBSSnapshot``, ``PBSJobStatus``).
"""

import taggit.managers
import utilities.json
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("extras", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PBSPluginSettings",
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
                    "branching_enabled",
                    models.BooleanField(
                        default=False,
                        verbose_name="Branching-enabled sync (PBS → NetBox)",
                        help_text=(
                            "When enabled, every PBS sync job creates a fresh "
                            "netbox-branching branch, runs the sync on that "
                            "branch, and merges it back into main on success. "
                            "Requires the netbox_branching plugin to be "
                            "installed and listed last in PLUGINS."
                        ),
                    ),
                ),
                (
                    "branch_name_prefix",
                    models.CharField(
                        default="pbs-sync",
                        max_length=64,
                        verbose_name="Branch name prefix",
                        help_text=(
                            "Prefix used when auto-creating a NetBox branch "
                            "per PBS sync job (e.g. "
                            "pbs-sync-<job_id>-<timestamp>)."
                        ),
                    ),
                ),
                (
                    "branch_on_conflict",
                    models.CharField(
                        choices=[
                            ("fail", "Fail (leave branch open for review)"),
                            ("acknowledge", "Acknowledge and merge anyway"),
                        ],
                        default="fail",
                        max_length=16,
                        verbose_name="Branch merge conflict policy",
                        help_text=(
                            "What to do when the auto-created sync branch "
                            "reports merge conflicts. 'fail' leaves the branch "
                            "open for operator review and marks the job "
                            "failed. 'acknowledge' retries the merge with "
                            "acknowledge_conflicts=True."
                        ),
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
                "verbose_name": "PBS plugin settings",
                "verbose_name_plural": "PBS plugin settings",
            },
        ),
    ]
