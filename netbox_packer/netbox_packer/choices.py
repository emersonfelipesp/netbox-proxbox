"""Choice sets for netbox-packer image definitions and builds."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from utilities.choices import ChoiceSet


class PackerBuilderTypeChoices(ChoiceSet):
    """Packer builder types supported by the NetBox image factory."""

    key = "PackerImageDefinition.builder_type"

    PROXMOX_CLONE = "proxmox-clone"
    PROXMOX_ISO = "proxmox-iso"

    CHOICES = [
        (PROXMOX_CLONE, _("Proxmox clone"), "blue"),
        (PROXMOX_ISO, _("Proxmox ISO"), "purple"),
    ]


class PackerOSFamilyChoices(ChoiceSet):
    """Operating system families available for Packer image definitions."""

    key = "PackerImageDefinition.os_family"

    UBUNTU = "ubuntu"
    DEBIAN = "debian"
    ROCKY = "rocky"
    ALMALINUX = "almalinux"
    FREEBSD = "freebsd"

    CHOICES = [
        (UBUNTU, _("Ubuntu"), "orange"),
        (DEBIAN, _("Debian"), "red"),
        (ROCKY, _("Rocky Linux"), "green"),
        (ALMALINUX, _("AlmaLinux"), "blue"),
        (FREEBSD, _("FreeBSD"), "gray"),
    ]


class PackerProvisionerRecipeChoices(ChoiceSet):
    """Provisioner recipe allowlist mirrored from proxbox-api static templates."""

    key = "PackerImageDefinition.provisioner_recipe"

    UBUNTU_BASE = "ubuntu-base"
    DEBIAN_BASE = "debian-base"
    DOCKER_HOST = "docker-host"
    QEMU_AGENT = "qemu-agent"

    CHOICES = [
        (UBUNTU_BASE, _("Ubuntu base"), "orange"),
        (DEBIAN_BASE, _("Debian base"), "red"),
        (DOCKER_HOST, _("Docker host"), "blue"),
        (QEMU_AGENT, _("QEMU agent"), "green"),
    ]


class PackerBuildStatusChoices(ChoiceSet):
    """Lifecycle states for one Packer image build execution."""

    key = "PackerImageBuild.status"

    PENDING = "pending"
    RUNNING = "running"
    FAILED = "failed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

    CHOICES = [
        (PENDING, _("Pending"), "gray"),
        (RUNNING, _("Running"), "blue"),
        (FAILED, _("Failed"), "red"),
        (COMPLETED, _("Completed"), "green"),
        (CANCELLED, _("Cancelled"), "yellow"),
    ]
