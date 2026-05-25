"""Firecracker inventory models for ProxBox Cloud provisioning."""

from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel

from netbox_proxbox.choices import (
    CloudImageOSFamilyChoices,
    FirecrackerHostStatusChoices,
    FirecrackerMicroVMStatusChoices,
    FirecrackerNetworkModeChoices,
)
from netbox_proxbox.utils import encryption as enc_helpers


class FirecrackerHostPool(NetBoxModel):
    """Capacity pool containing Proxmox VMs that run Firecracker host agents."""

    name = models.CharField(max_length=255, verbose_name=_("Name"))
    slug = models.SlugField(
        max_length=255,
        unique=True,
        verbose_name=_("Slug"),
        help_text=_("Stable identifier used by Cloud API clients."),
    )
    description = models.TextField(blank=True, verbose_name=_("Description"))
    default_network_mode = models.CharField(
        max_length=16,
        choices=FirecrackerNetworkModeChoices,
        default=FirecrackerNetworkModeChoices.NAT,
        verbose_name=_("Default network mode"),
    )
    allowed_tenants = models.ManyToManyField(
        to="tenancy.Tenant",
        blank=True,
        related_name="proxbox_firecracker_host_pools",
        verbose_name=_("Allowed tenants"),
        help_text=_("Tenants allowed to provision here. Leave empty for all tenants."),
    )
    is_active = models.BooleanField(default=True, verbose_name=_("Active"))

    class Meta:
        ordering = ("name",)
        verbose_name = _("Firecracker host pool")
        verbose_name_plural = _("Firecracker host pools")

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_proxbox:firecrackerhostpool", args=[self.pk])

    @property
    def tenant_scope_label(self) -> str:
        if not getattr(self, "pk", None):
            return "All tenants"
        tenants = list(self.allowed_tenants.all()[:4])
        if not tenants:
            return "All tenants"
        names = ", ".join(str(tenant) for tenant in tenants)
        total = self.allowed_tenants.count()
        return f"{names} (+{total - 4} more)" if total > 4 else names


class FirecrackerHost(NetBoxModel):
    """One host-agent VM capable of running Firecracker micro-VMs."""

    pool = models.ForeignKey(
        to="netbox_proxbox.FirecrackerHostPool",
        on_delete=models.CASCADE,
        related_name="hosts",
        verbose_name=_("Host pool"),
    )
    name = models.CharField(max_length=255, verbose_name=_("Name"))
    host_vm = models.ForeignKey(
        to="virtualization.VirtualMachine",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="firecracker_host_agent",
        verbose_name=_("Proxmox host VM"),
        help_text=_("NetBox VM that runs the Firecracker host agent."),
    )
    proxmox_node = models.ForeignKey(
        to="netbox_proxbox.ProxmoxNode",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="firecracker_hosts",
        verbose_name=_("Proxmox node"),
        help_text=_("Physical Proxmox node currently hosting the agent VM."),
    )
    agent_base_url = models.URLField(
        max_length=500,
        verbose_name=_("Agent base URL"),
        help_text=_("Base URL for the Firecracker host-agent HTTP API."),
    )
    agent_token_enc = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Encrypted agent token"),
        help_text=_("Fernet-encrypted host-agent bearer token. Internal."),
    )
    status = models.CharField(
        max_length=32,
        choices=FirecrackerHostStatusChoices,
        default=FirecrackerHostStatusChoices.OFFLINE,
        verbose_name=_("Status"),
    )
    firecracker_version = models.CharField(max_length=64, blank=True)
    kvm_available = models.BooleanField(default=False, verbose_name=_("KVM available"))
    supports_nat = models.BooleanField(default=True, verbose_name=_("Supports NAT"))
    supports_bridge = models.BooleanField(
        default=False,
        verbose_name=_("Supports bridge"),
    )
    capacity_vcpus = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name=_("vCPU capacity"),
    )
    capacity_memory_mib = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name=_("Memory capacity (MiB)"),
    )
    capacity_disk_mib = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name=_("Disk capacity (MiB)"),
    )
    allocated_vcpus = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name=_("Allocated vCPUs"),
    )
    allocated_memory_mib = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name=_("Allocated memory (MiB)"),
    )
    allocated_disk_mib = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name=_("Allocated disk (MiB)"),
    )
    last_seen = models.DateTimeField(blank=True, null=True, verbose_name=_("Last seen"))

    class Meta:
        ordering = ("pool", "name")
        unique_together = ("pool", "name")
        verbose_name = _("Firecracker host")
        verbose_name_plural = _("Firecracker hosts")

    def __str__(self) -> str:
        return f"{self.name} ({self.pool})"

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_proxbox:firecrackerhost", args=[self.pk])

    @property
    def token_configured(self) -> bool:
        return bool(self.agent_token_enc)

    @property
    def available_vcpus(self) -> int:
        return max(self.capacity_vcpus - self.allocated_vcpus, 0)

    @property
    def available_memory_mib(self) -> int:
        return max(self.capacity_memory_mib - self.allocated_memory_mib, 0)

    @property
    def available_disk_mib(self) -> int:
        return max(self.capacity_disk_mib - self.allocated_disk_mib, 0)

    def set_agent_token(self, plaintext: str, *, key: str) -> None:
        self.agent_token_enc = enc_helpers.encrypt(plaintext, key=key)

    def get_agent_token(self, *, key: str) -> str:
        return enc_helpers.decrypt(self.agent_token_enc, key=key)


class FirecrackerImageTemplate(NetBoxModel):
    """Tenant-visible Firecracker kernel/rootfs image bundle."""

    name = models.CharField(max_length=255, verbose_name=_("Name"))
    slug = models.SlugField(max_length=255, unique=True, verbose_name=_("Slug"))
    description = models.TextField(blank=True, verbose_name=_("Description"))
    architecture = models.CharField(
        max_length=32,
        default="x86_64",
        verbose_name=_("Architecture"),
    )
    os_family = models.CharField(
        max_length=32,
        choices=CloudImageOSFamilyChoices,
        default=CloudImageOSFamilyChoices.GENERIC,
        verbose_name=_("OS family"),
    )
    os_release = models.CharField(
        max_length=64, blank=True, verbose_name=_("OS release")
    )
    kernel_image_url = models.CharField(
        max_length=1024,
        verbose_name=_("Kernel image URL"),
        help_text=_("HTTP(S) URL or host-agent-local path for the Firecracker kernel."),
    )
    kernel_image_sha256 = models.CharField(
        max_length=64,
        verbose_name=_("Kernel SHA256"),
    )
    rootfs_image_url = models.CharField(
        max_length=1024,
        verbose_name=_("Rootfs image URL"),
        help_text=_("HTTP(S) URL or host-agent-local path for the root filesystem."),
    )
    rootfs_image_sha256 = models.CharField(
        max_length=64,
        verbose_name=_("Rootfs SHA256"),
    )
    default_kernel_args = models.TextField(
        blank=True,
        verbose_name=_("Default kernel args"),
    )
    default_user = models.CharField(
        max_length=64,
        default="cloud-user",
        verbose_name=_("Default user"),
    )
    allowed_tenants = models.ManyToManyField(
        to="tenancy.Tenant",
        blank=True,
        related_name="proxbox_firecracker_image_templates",
        verbose_name=_("Allowed tenants"),
        help_text=_("Tenants allowed to use this image. Leave empty for all tenants."),
    )
    is_active = models.BooleanField(default=True, verbose_name=_("Active"))

    class Meta:
        ordering = ("name", "architecture")
        verbose_name = _("Firecracker image template")
        verbose_name_plural = _("Firecracker image templates")
        permissions = [
            (
                "provision_firecracker_microvm",
                _("Can provision a Firecracker micro-VM"),
            ),
        ]

    def __str__(self) -> str:
        release = f" {self.os_release}" if self.os_release else ""
        return f"{self.name} ({self.os_family}{release}, {self.architecture})"

    def get_absolute_url(self) -> str:
        return reverse(
            "plugins:netbox_proxbox:firecrackerimagetemplate", args=[self.pk]
        )

    @property
    def tenant_scope_label(self) -> str:
        if not getattr(self, "pk", None):
            return "All tenants"
        tenants = list(self.allowed_tenants.all()[:4])
        if not tenants:
            return "All tenants"
        names = ", ".join(str(tenant) for tenant in tenants)
        total = self.allowed_tenants.count()
        return f"{names} (+{total - 4} more)" if total > 4 else names

    def clean(self) -> None:
        super().clean()
        for field_name in ("kernel_image_sha256", "rootfs_image_sha256"):
            value = getattr(self, field_name, "")
            if len(value) != 64 or any(
                char not in "0123456789abcdefABCDEF" for char in value
            ):
                raise ValidationError(
                    {field_name: _("Expected a 64-character SHA256 hex digest.")}
                )


class FirecrackerMicroVM(NetBoxModel):
    """A Firecracker micro-VM provisioned through ProxBox Cloud."""

    microvm_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name=_("Micro-VM ID"),
    )
    name = models.CharField(max_length=255, verbose_name=_("Name"))
    tenant = models.ForeignKey(
        to="tenancy.Tenant",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="proxbox_firecracker_microvms",
        verbose_name=_("Tenant"),
    )
    host = models.ForeignKey(
        to="netbox_proxbox.FirecrackerHost",
        on_delete=models.PROTECT,
        related_name="microvms",
        verbose_name=_("Firecracker host"),
    )
    image = models.ForeignKey(
        to="netbox_proxbox.FirecrackerImageTemplate",
        on_delete=models.PROTECT,
        related_name="microvms",
        verbose_name=_("Image template"),
    )
    status = models.CharField(
        max_length=32,
        choices=FirecrackerMicroVMStatusChoices,
        default=FirecrackerMicroVMStatusChoices.PROVISIONING,
        verbose_name=_("Status"),
    )
    network_mode = models.CharField(
        max_length=16,
        choices=FirecrackerNetworkModeChoices,
        default=FirecrackerNetworkModeChoices.NAT,
        verbose_name=_("Network mode"),
    )
    vcpus = models.PositiveSmallIntegerField(default=1, verbose_name=_("vCPUs"))
    memory_mib = models.PositiveIntegerField(
        default=512, verbose_name=_("Memory (MiB)")
    )
    disk_mib = models.PositiveIntegerField(default=1024, verbose_name=_("Disk (MiB)"))
    guest_ip = models.GenericIPAddressField(
        blank=True,
        null=True,
        verbose_name=_("Guest IP"),
    )
    mac_address = models.CharField(
        max_length=32, blank=True, verbose_name=_("MAC address")
    )
    bridge_name = models.CharField(max_length=64, blank=True, verbose_name=_("Bridge"))
    tap_name = models.CharField(max_length=64, blank=True, verbose_name=_("TAP"))
    ssh_authorized_keys = models.JSONField(default=list, blank=True)
    agent_payload = models.JSONField(default=dict, blank=True)
    last_agent_state = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(
        blank=True, null=True, verbose_name=_("Started at")
    )
    stopped_at = models.DateTimeField(
        blank=True, null=True, verbose_name=_("Stopped at")
    )

    class Meta:
        ordering = ("tenant", "name")
        unique_together = ("host", "name")
        verbose_name = _("Firecracker micro-VM")
        verbose_name_plural = _("Firecracker micro-VMs")

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("plugins:netbox_proxbox:firecrackermicrovm", args=[self.pk])

    @property
    def instance_ref(self) -> str:
        return f"firecracker:{self.pk}"

    def mark_seen_running(self) -> None:
        self.status = FirecrackerMicroVMStatusChoices.RUNNING
        self.started_at = self.started_at or timezone.now()
