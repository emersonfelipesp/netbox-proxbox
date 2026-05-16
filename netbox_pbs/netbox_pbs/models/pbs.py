"""PBS inventory models reflected through proxbox-api."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel

from netbox_pbs.choices import (
    PBSBackupTypeChoices,
    PBSGCStatusChoices,
    PBSJobRunStateChoices,
    PBSJobTypeChoices,
    PBSServerStatusChoices,
)

PBS_BRANCH_ON_CONFLICT_CHOICES = (
    ("abort", _("Abort and leave branch open for review")),
    ("overwrite", _("Overwrite by merging despite conflicts")),
)


class PBSPluginSettings(NetBoxModel):
    """Singleton-style settings row for netbox-pbs sync behavior."""

    singleton_key = models.CharField(
        max_length=32,
        unique=True,
        default="default",
        editable=False,
    )
    proxbox_api_url = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("proxbox-api URL"),
        help_text=_(
            "Base URL used when netbox-proxbox FastAPIEndpoint resolution is not available."
        ),
    )
    proxbox_api_key = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("proxbox-api API key"),
        help_text=_("Optional bearer token used with the standalone proxbox-api URL."),
    )
    branching_enabled = models.BooleanField(
        default=False,
        verbose_name=_("Branching-enabled sync (PBS -> NetBox)"),
        help_text=_(
            "When enabled, PBS sync jobs create a netbox-branching branch, run sync "
            "against that branch, and merge the branch back into main on success."
        ),
    )
    branch_name_prefix = models.CharField(
        max_length=64,
        default="pbs-sync",
        verbose_name=_("Branch name prefix"),
    )
    branch_on_conflict = models.CharField(
        max_length=16,
        choices=PBS_BRANCH_ON_CONFLICT_CHOICES,
        default="abort",
        verbose_name=_("Branch merge conflict policy"),
    )

    class Meta:
        verbose_name = _("PBS plugin settings")
        verbose_name_plural = _("PBS plugin settings")

    def __str__(self) -> str:
        return "PBS plugin settings"

    def save(self, *args: object, **kwargs: object) -> None:
        self.singleton_key = "default"
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls) -> "PBSPluginSettings":
        obj, _created = cls.objects.get_or_create(singleton_key="default")
        return obj


class PBSServer(NetBoxModel):
    """Proxmox Backup Server endpoint known to proxbox-api."""

    name = models.CharField(max_length=255, unique=True, verbose_name=_("Name"))
    host = models.CharField(max_length=255, verbose_name=_("Host"))
    port = models.IntegerField(default=8007, verbose_name=_("Port"))
    token_id = models.CharField(max_length=255, verbose_name=_("Token ID"))
    fingerprint = models.CharField(
        max_length=255, blank=True, verbose_name=_("Fingerprint")
    )
    verify_ssl = models.BooleanField(default=True, verbose_name=_("Verify SSL"))
    status = models.CharField(
        max_length=32,
        choices=PBSServerStatusChoices,
        blank=True,
        verbose_name=_("Status"),
    )
    version = models.CharField(max_length=128, blank=True, verbose_name=_("Version"))
    last_seen_at = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Last seen")
    )

    class Meta:
        ordering = ("name",)
        verbose_name = _("PBS server")
        verbose_name_plural = _("PBS servers")

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_pbs:pbsserver", args=[self.pk])


class PBSDatastore(NetBoxModel):
    """PBS datastore capacity and garbage-collection state."""

    server = models.ForeignKey(
        to="netbox_pbs.PBSServer",
        on_delete=models.CASCADE,
        related_name="datastores",
        verbose_name=_("PBS server"),
    )
    name = models.CharField(max_length=255, verbose_name=_("Name"))
    path = models.CharField(max_length=1024, verbose_name=_("Path"))
    used_bytes = models.BigIntegerField(
        null=True, blank=True, verbose_name=_("Used bytes")
    )
    total_bytes = models.BigIntegerField(
        null=True, blank=True, verbose_name=_("Total bytes")
    )
    avail_bytes = models.BigIntegerField(
        null=True, blank=True, verbose_name=_("Available bytes")
    )
    gc_status = models.CharField(
        max_length=32,
        choices=PBSGCStatusChoices,
        blank=True,
        verbose_name=_("GC status"),
    )
    comment = models.CharField(max_length=1024, blank=True, verbose_name=_("Comment"))
    last_seen_at = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Last seen")
    )

    class Meta:
        ordering = ("server", "name")
        verbose_name = _("PBS datastore")
        verbose_name_plural = _("PBS datastores")
        constraints = [
            models.UniqueConstraint(
                fields=("server", "name"),
                name="netbox_pbs_datastore_identity",
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.server})"

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_pbs:pbsdatastore", args=[self.pk])


class PBSSnapshot(NetBoxModel):
    """PBS backup snapshot reflected from a datastore."""

    server = models.ForeignKey(
        to="netbox_pbs.PBSServer",
        on_delete=models.CASCADE,
        related_name="snapshots",
        verbose_name=_("PBS server"),
    )
    datastore_name = models.CharField(max_length=255, verbose_name=_("Datastore"))
    backup_type = models.CharField(
        max_length=16,
        choices=PBSBackupTypeChoices,
        verbose_name=_("Backup type"),
    )
    backup_id = models.CharField(max_length=255, verbose_name=_("Backup ID"))
    backup_time = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Backup time")
    )
    size_bytes = models.BigIntegerField(
        null=True, blank=True, verbose_name=_("Size bytes")
    )
    owner = models.CharField(max_length=255, blank=True, verbose_name=_("Owner"))
    protected = models.BooleanField(default=False, verbose_name=_("Protected"))
    comment = models.CharField(max_length=1024, blank=True, verbose_name=_("Comment"))
    verification_state = models.CharField(
        max_length=32,
        blank=True,
        verbose_name=_("Verification state"),
    )
    last_seen_at = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Last seen")
    )

    class Meta:
        ordering = (
            "server",
            "datastore_name",
            "backup_type",
            "backup_id",
            "-backup_time",
        )
        verbose_name = _("PBS snapshot")
        verbose_name_plural = _("PBS snapshots")
        constraints = [
            models.UniqueConstraint(
                fields=(
                    "server",
                    "datastore_name",
                    "backup_type",
                    "backup_id",
                    "backup_time",
                ),
                name="netbox_pbs_snapshot_identity",
            )
        ]

    def __str__(self) -> str:
        return f"{self.datastore_name}/{self.backup_type}/{self.backup_id}"

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_pbs:pbssnapshot", args=[self.pk])


class PBSJob(NetBoxModel):
    """PBS scheduled job state."""

    server = models.ForeignKey(
        to="netbox_pbs.PBSServer",
        on_delete=models.CASCADE,
        related_name="jobs",
        verbose_name=_("PBS server"),
    )
    job_type = models.CharField(
        max_length=16,
        choices=PBSJobTypeChoices,
        verbose_name=_("Job type"),
    )
    job_id = models.CharField(max_length=255, verbose_name=_("Job ID"))
    store = models.CharField(max_length=255, blank=True, verbose_name=_("Store"))
    schedule = models.CharField(max_length=255, blank=True, verbose_name=_("Schedule"))
    comment = models.CharField(max_length=1024, blank=True, verbose_name=_("Comment"))
    disable = models.BooleanField(default=False, verbose_name=_("Disabled"))
    last_run_state = models.CharField(
        max_length=32,
        choices=PBSJobRunStateChoices,
        blank=True,
        verbose_name=_("Last run state"),
    )
    last_run_endtime = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Last run end time"),
    )
    next_run = models.DateTimeField(null=True, blank=True, verbose_name=_("Next run"))
    last_seen_at = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Last seen")
    )

    class Meta:
        ordering = ("server", "job_type", "job_id")
        verbose_name = _("PBS job")
        verbose_name_plural = _("PBS jobs")
        constraints = [
            models.UniqueConstraint(
                fields=("server", "job_type", "job_id"),
                name="netbox_pbs_job_identity",
            )
        ]

    def __str__(self) -> str:
        return f"{self.job_type}:{self.job_id}"

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_pbs:pbsjob", args=[self.pk])
