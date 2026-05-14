"""Read-only Ceph inventory models.

All operational objects are reflected from Proxmox-managed Ceph state in v1.
They intentionally do not carry ``allow_writes`` fields or desired-state
configuration. v2 tracks NetBox-to-Ceph writes separately.
"""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel
from utilities.json import CustomFieldJSONEncoder

from netbox_ceph.choices import (
    CephDaemonStateChoices,
    CephDaemonTypeChoices,
    CephHealthChoices,
)


BRANCH_ON_CONFLICT_CHOICES = (
    ("fail", _("Fail (leave branch open for review)")),
    ("acknowledge", _("Acknowledge and merge anyway")),
)


class CephPluginSettings(NetBoxModel):
    """Singleton-style settings row for netbox-ceph sync behavior."""

    singleton_key = models.CharField(
        max_length=32,
        unique=True,
        default="default",
        editable=False,
    )
    branching_enabled = models.BooleanField(
        default=False,
        verbose_name=_("Branching-enabled sync (Ceph -> NetBox)"),
        help_text=_(
            "When enabled, every Ceph sync job creates a fresh netbox-branching "
            "branch, runs the sync on that branch, and merges it back into main "
            "on success."
        ),
    )
    branch_name_prefix = models.CharField(
        max_length=64,
        default="ceph-sync",
        verbose_name=_("Branch name prefix"),
    )
    branch_on_conflict = models.CharField(
        max_length=16,
        choices=BRANCH_ON_CONFLICT_CHOICES,
        default="fail",
        verbose_name=_("Branch merge conflict policy"),
    )

    class Meta:
        verbose_name = _("Ceph plugin settings")
        verbose_name_plural = _("Ceph plugin settings")

    def __str__(self) -> str:
        return "Ceph plugin settings"

    def save(self, *args: object, **kwargs: object) -> None:
        self.singleton_key = "default"
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls) -> "CephPluginSettings":
        obj, _created = cls.objects.get_or_create(singleton_key="default")
        return obj


class CephCluster(NetBoxModel):
    """Ceph cluster state discovered from a Proxmox endpoint."""

    endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.CASCADE,
        related_name="ceph_clusters",
        verbose_name=_("Proxmox endpoint"),
    )
    proxmox_cluster = models.ForeignKey(
        to="netbox_proxbox.ProxmoxCluster",
        on_delete=models.SET_NULL,
        related_name="ceph_clusters",
        null=True,
        blank=True,
        verbose_name=_("Proxmox cluster"),
    )
    name = models.CharField(max_length=255, verbose_name=_("Cluster name"))
    fsid = models.CharField(max_length=64, blank=True, verbose_name=_("FSID"))
    health = models.CharField(
        max_length=32,
        choices=CephHealthChoices,
        default=CephHealthChoices.HEALTH_UNKNOWN,
    )
    quorum_names = models.JSONField(
        blank=True,
        default=list,
        encoder=CustomFieldJSONEncoder,
        verbose_name=_("Quorum members"),
    )
    status = models.JSONField(blank=True, default=dict, encoder=CustomFieldJSONEncoder)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("endpoint", "name")
        verbose_name = _("Ceph cluster")
        verbose_name_plural = _("Ceph clusters")
        constraints = [
            models.UniqueConstraint(
                fields=("endpoint", "name"),
                name="netbox_ceph_cluster_identity",
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.endpoint})"

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_ceph:cephcluster", args=[self.pk])


class CephDaemon(NetBoxModel):
    """MON/MGR/MDS daemon record reflected from Ceph."""

    endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.CASCADE,
        related_name="ceph_daemons",
    )
    cluster = models.ForeignKey(
        to="netbox_ceph.CephCluster",
        on_delete=models.CASCADE,
        related_name="daemons",
        null=True,
        blank=True,
    )
    proxmox_node = models.ForeignKey(
        to="netbox_proxbox.ProxmoxNode",
        on_delete=models.SET_NULL,
        related_name="ceph_daemons",
        null=True,
        blank=True,
    )
    daemon_type = models.CharField(
        max_length=16,
        choices=CephDaemonTypeChoices,
        default=CephDaemonTypeChoices.TYPE_UNKNOWN,
    )
    name = models.CharField(max_length=255)
    daemon_id = models.CharField(max_length=255, blank=True)
    host = models.CharField(max_length=255, blank=True)
    state = models.CharField(
        max_length=32,
        choices=CephDaemonStateChoices,
        default=CephDaemonStateChoices.STATE_UNKNOWN,
    )
    status = models.CharField(max_length=255, blank=True)
    version = models.CharField(max_length=128, blank=True)
    metadata = models.JSONField(blank=True, default=dict, encoder=CustomFieldJSONEncoder)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("endpoint", "daemon_type", "name")
        verbose_name = _("Ceph daemon")
        verbose_name_plural = _("Ceph daemons")
        constraints = [
            models.UniqueConstraint(
                fields=("endpoint", "daemon_type", "name"),
                name="netbox_ceph_daemon_identity",
            )
        ]

    def __str__(self) -> str:
        return f"{self.daemon_type}.{self.name}"

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_ceph:cephdaemon", args=[self.pk])


class CephOSD(NetBoxModel):
    """Ceph OSD capacity and status."""

    endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.CASCADE,
        related_name="ceph_osds",
    )
    cluster = models.ForeignKey(
        to="netbox_ceph.CephCluster",
        on_delete=models.CASCADE,
        related_name="osds",
        null=True,
        blank=True,
    )
    proxmox_node = models.ForeignKey(
        to="netbox_proxbox.ProxmoxNode",
        on_delete=models.SET_NULL,
        related_name="ceph_osds",
        null=True,
        blank=True,
    )
    osd_id = models.PositiveIntegerField(verbose_name=_("OSD ID"))
    name = models.CharField(max_length=255, blank=True)
    host = models.CharField(max_length=255, blank=True)
    up = models.BooleanField(default=False)
    in_cluster = models.BooleanField(default=False, verbose_name=_("In cluster"))
    status = models.CharField(max_length=255, blank=True)
    device_class = models.CharField(max_length=64, blank=True)
    weight = models.FloatField(null=True, blank=True)
    reweight = models.FloatField(null=True, blank=True)
    used_bytes = models.BigIntegerField(null=True, blank=True)
    available_bytes = models.BigIntegerField(null=True, blank=True)
    total_bytes = models.BigIntegerField(null=True, blank=True)
    pgs = models.PositiveIntegerField(null=True, blank=True)
    metadata = models.JSONField(blank=True, default=dict, encoder=CustomFieldJSONEncoder)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("endpoint", "osd_id")
        verbose_name = _("Ceph OSD")
        verbose_name_plural = _("Ceph OSDs")
        constraints = [
            models.UniqueConstraint(
                fields=("endpoint", "osd_id"),
                name="netbox_ceph_osd_identity",
            )
        ]

    def __str__(self) -> str:
        return f"osd.{self.osd_id}"

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_ceph:cephosd", args=[self.pk])


class CephPool(NetBoxModel):
    """Ceph pool state."""

    endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.CASCADE,
        related_name="ceph_pools",
    )
    cluster = models.ForeignKey(
        to="netbox_ceph.CephCluster",
        on_delete=models.CASCADE,
        related_name="pools",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=255)
    pool_id = models.PositiveIntegerField(null=True, blank=True)
    size = models.PositiveSmallIntegerField(null=True, blank=True)
    min_size = models.PositiveSmallIntegerField(null=True, blank=True)
    pg_num = models.PositiveIntegerField(null=True, blank=True)
    pg_autoscale_mode = models.CharField(max_length=32, blank=True)
    crush_rule = models.CharField(max_length=255, blank=True)
    application = models.CharField(max_length=64, blank=True)
    used_bytes = models.BigIntegerField(null=True, blank=True)
    max_available_bytes = models.BigIntegerField(null=True, blank=True)
    percent_used = models.FloatField(null=True, blank=True)
    status = models.JSONField(blank=True, default=dict, encoder=CustomFieldJSONEncoder)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("endpoint", "name")
        verbose_name = _("Ceph pool")
        verbose_name_plural = _("Ceph pools")
        constraints = [
            models.UniqueConstraint(
                fields=("endpoint", "name"),
                name="netbox_ceph_pool_identity",
            )
        ]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_ceph:cephpool", args=[self.pk])


class CephFilesystem(NetBoxModel):
    """CephFS state."""

    endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.CASCADE,
        related_name="ceph_filesystems",
    )
    cluster = models.ForeignKey(
        to="netbox_ceph.CephCluster",
        on_delete=models.CASCADE,
        related_name="filesystems",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=255)
    metadata_pool = models.ForeignKey(
        to="netbox_ceph.CephPool",
        on_delete=models.SET_NULL,
        related_name="metadata_filesystems",
        null=True,
        blank=True,
    )
    data_pools = models.JSONField(blank=True, default=list, encoder=CustomFieldJSONEncoder)
    standby_count_wanted = models.PositiveIntegerField(null=True, blank=True)
    status = models.JSONField(blank=True, default=dict, encoder=CustomFieldJSONEncoder)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("endpoint", "name")
        verbose_name = _("Ceph filesystem")
        verbose_name_plural = _("Ceph filesystems")
        constraints = [
            models.UniqueConstraint(
                fields=("endpoint", "name"),
                name="netbox_ceph_filesystem_identity",
            )
        ]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_ceph:cephfilesystem", args=[self.pk])


class CephCrushRule(NetBoxModel):
    """CRUSH rule reflected from Ceph."""

    endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.CASCADE,
        related_name="ceph_crush_rules",
    )
    cluster = models.ForeignKey(
        to="netbox_ceph.CephCluster",
        on_delete=models.CASCADE,
        related_name="crush_rules",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=255)
    rule_id = models.IntegerField(null=True, blank=True)
    rule_type = models.CharField(max_length=64, blank=True)
    device_class = models.CharField(max_length=64, blank=True)
    steps = models.JSONField(blank=True, default=list, encoder=CustomFieldJSONEncoder)
    raw = models.JSONField(blank=True, default=dict, encoder=CustomFieldJSONEncoder)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("endpoint", "name")
        verbose_name = _("Ceph CRUSH rule")
        verbose_name_plural = _("Ceph CRUSH rules")
        constraints = [
            models.UniqueConstraint(
                fields=("endpoint", "name"),
                name="netbox_ceph_crush_rule_identity",
            )
        ]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_ceph:cephcrushrule", args=[self.pk])


class CephFlag(NetBoxModel):
    """Cluster-level Ceph flag state."""

    endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.CASCADE,
        related_name="ceph_flags",
    )
    cluster = models.ForeignKey(
        to="netbox_ceph.CephCluster",
        on_delete=models.CASCADE,
        related_name="flags",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=64)
    enabled = models.BooleanField(null=True, blank=True)
    value = models.CharField(max_length=255, blank=True)
    raw = models.JSONField(blank=True, default=dict, encoder=CustomFieldJSONEncoder)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("endpoint", "name")
        verbose_name = _("Ceph flag")
        verbose_name_plural = _("Ceph flags")
        constraints = [
            models.UniqueConstraint(
                fields=("endpoint", "name"),
                name="netbox_ceph_flag_identity",
            )
        ]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_ceph:cephflag", args=[self.pk])


class CephHealthCheck(NetBoxModel):
    """Health check entry parsed from Ceph status payloads."""

    endpoint = models.ForeignKey(
        to="netbox_proxbox.ProxmoxEndpoint",
        on_delete=models.CASCADE,
        related_name="ceph_health_checks",
    )
    cluster = models.ForeignKey(
        to="netbox_ceph.CephCluster",
        on_delete=models.CASCADE,
        related_name="health_checks",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=255)
    severity = models.CharField(
        max_length=32,
        choices=CephHealthChoices,
        default=CephHealthChoices.HEALTH_UNKNOWN,
    )
    summary = models.CharField(max_length=512, blank=True)
    detail = models.JSONField(blank=True, default=list, encoder=CustomFieldJSONEncoder)
    source = models.CharField(max_length=64, blank=True)
    first_seen_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("endpoint", "severity", "name")
        verbose_name = _("Ceph health check")
        verbose_name_plural = _("Ceph health checks")
        constraints = [
            models.UniqueConstraint(
                fields=("endpoint", "name"),
                name="netbox_ceph_health_check_identity",
            )
        ]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_ceph:cephhealthcheck", args=[self.pk])
