"""Singleton plugin settings for netbox-pbs.

Mirrors the shape used by ``netbox_proxbox.models.ProxboxPluginSettings`` so
the branching lifecycle helpers (``branch_lifecycle.py``, landing in PR C3)
can read the same field names.

PR C1 ships only the fields needed to boot the plugin:

- ``singleton_key`` — unique key for ``get_solo()``.
- ``branching_enabled`` / ``branch_name_prefix`` / ``branch_on_conflict`` —
  reserved for the netbox-branching integration in PR C3.

Additional fields (FastAPI endpoint pointer, encryption key, on-conflict
policy hooks) are added in later sub-PRs.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from netbox.models import NetBoxModel


BRANCH_ON_CONFLICT_CHOICES = (
    ("fail", _("Fail (leave branch open for review)")),
    ("acknowledge", _("Acknowledge and merge anyway")),
)


class PBSPluginSettings(NetBoxModel):
    """Singleton-style settings row used by the netbox-pbs plugin."""

    singleton_key = models.CharField(
        max_length=32,
        unique=True,
        default="default",
        editable=False,
    )
    branching_enabled = models.BooleanField(
        default=False,
        verbose_name=_("Branching-enabled sync (PBS → NetBox)"),
        help_text=_(
            "When enabled, every PBS sync job creates a fresh netbox-branching "
            "branch, runs the sync on that branch, and merges it back into "
            "main on success. Requires the netbox_branching plugin to be "
            "installed and listed last in PLUGINS."
        ),
    )
    branch_name_prefix = models.CharField(
        max_length=64,
        default="pbs-sync",
        verbose_name=_("Branch name prefix"),
        help_text=_(
            "Prefix used when auto-creating a NetBox branch per PBS sync job "
            "(e.g. pbs-sync-<job_id>-<timestamp>)."
        ),
    )
    branch_on_conflict = models.CharField(
        max_length=16,
        choices=BRANCH_ON_CONFLICT_CHOICES,
        default="fail",
        verbose_name=_("Branch merge conflict policy"),
        help_text=_(
            "What to do when the auto-created sync branch reports merge "
            "conflicts. 'fail' leaves the branch open for operator review and "
            "marks the job failed. 'acknowledge' retries the merge with "
            "acknowledge_conflicts=True."
        ),
    )

    class Meta:
        verbose_name = _("PBS plugin settings")
        verbose_name_plural = _("PBS plugin settings")

    def __str__(self) -> str:
        return "PBS plugin settings"

    def save(self, *args: object, **kwargs: object) -> None:
        """Force the singleton key so only one row ever exists."""
        self.singleton_key = "default"
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls) -> "PBSPluginSettings":
        """Return the single settings row, creating it on first access."""
        obj, _created = cls.objects.get_or_create(singleton_key="default")
        return obj
