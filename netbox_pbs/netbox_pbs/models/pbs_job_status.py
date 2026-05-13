"""Reflected PBS scheduled-job status (verify, prune, GC, sync, tape)."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox.models import NetBoxModel

from netbox_pbs.choices import PBSJobRunStateChoices, PBSJobTypeChoices


class PBSJobStatus(NetBoxModel):
    """Last-known status of a PBS scheduled job."""

    endpoint = models.ForeignKey(
        to="netbox_pbs.PBSEndpoint",
        on_delete=models.CASCADE,
        related_name="jobs",
    )
    job_type = models.CharField(
        max_length=16,
        choices=PBSJobTypeChoices,
    )
    job_id = models.CharField(
        max_length=128,
        verbose_name=_("Job ID"),
    )
    datastore = models.ForeignKey(
        to="netbox_pbs.PBSDatastore",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="jobs",
    )
    enabled = models.BooleanField(
        default=True,
    )
    last_run_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Last run at"),
    )
    last_run_state = models.CharField(
        max_length=16,
        choices=PBSJobRunStateChoices,
        default=PBSJobRunStateChoices.RUN_STATE_UNKNOWN,
    )
    last_run_duration_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Last run duration (seconds)"),
    )
    next_run_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Next run at"),
    )

    class Meta:
        ordering = ("endpoint", "job_type", "job_id")
        verbose_name = _("PBS job status")
        verbose_name_plural = _("PBS job statuses")
        constraints = (
            models.UniqueConstraint(
                fields=("endpoint", "job_type", "job_id"),
                name="netbox_pbs_pbsjobstatus_identity",
            ),
        )

    def __str__(self) -> str:
        return f"{self.endpoint} / {self.job_type}:{self.job_id}"

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_pbs:pbsjobstatus", args=[self.pk])
