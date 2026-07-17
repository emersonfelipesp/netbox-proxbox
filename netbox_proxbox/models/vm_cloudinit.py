"""Define the read-only Proxmox cloud-init model stored alongside NetBox virtual machines."""

from __future__ import annotations

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox.models import NetBoxModel


class ProxmoxVMCloudInit(NetBoxModel):
    """Proxmox cloud-init row mirroring ``ciuser`` / ``sshkeys`` / ``ipconfig0``.

    Populated by proxbox-api from ``qm config <vmid>`` on each sync. Read-only
    on the NetBox side; Proxmox stays the source of truth. ``sshkeys`` is
    stored decoded (newlines as ``\\n``); proxbox-api runs
    ``urllib.parse.unquote`` before writing.
    """

    virtual_machine = models.OneToOneField(
        to="virtualization.VirtualMachine",
        on_delete=models.CASCADE,
        related_name="proxmox_cloudinit",
        help_text=_("NetBox VM this cloud-init record reflects."),
    )

    ciuser = models.CharField(
        max_length=64,
        blank=True,
        help_text=_("Proxmox cloud-init user (``ciuser``)."),
    )

    sshkeys = models.TextField(
        blank=True,
        help_text=_(
            "Decoded cloud-init SSH key bundle (one key per line). "
            "Proxmox-side is URL-encoded; proxbox-api runs urllib.parse.unquote "
            "before writing this row."
        ),
    )

    ipconfig0 = models.CharField(
        max_length=255,
        blank=True,
        help_text=_(
            "Cloud-init first-NIC IP configuration string from Proxmox "
            "(e.g. ``ip=dhcp`` or ``ip=10.0.0.5/24,gw=10.0.0.1``)."
        ),
    )

    sshkeys_truncated = models.BooleanField(
        default=False,
        help_text=_(
            "True when proxbox-api truncated the ``sshkeys`` payload because "
            "the decoded blob exceeded 10 KB."
        ),
    )

    # -- Create-time cloud-init intent -------------------------------------
    # The fields below capture the cloud-init request the NMS stack sent at
    # VM-create time. They are NOT part of proxbox-api's reflection
    # ``CLOUDINIT_PATCHABLE_FIELDS`` set, so a later ``qm config`` reflection
    # sync never overwrites them. ``is_intent`` marks rows that carry this
    # create-time intent (vs a pure post-hoc reflection row).

    is_intent = models.BooleanField(
        default=False,
        help_text=_(
            "True when this row carries the create-time cloud-init intent "
            "written by the NMS stack (not a pure Proxmox reflection)."
        ),
    )

    hostname = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("cloud-init hostname requested at create time."),
    )

    search_domain = models.CharField(
        max_length=255,
        blank=True,
        help_text=_("cloud-init DNS search domain requested at create time."),
    )

    dns_servers = models.CharField(
        max_length=255,
        blank=True,
        help_text=_(
            "cloud-init DNS nameservers requested at create time (comma-separated)."
        ),
    )

    bridge = models.CharField(
        max_length=64,
        blank=True,
        help_text=_("Proxmox bridge the primary NIC was attached to."),
    )

    vlan_tag = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text=_("VLAN tag applied to the primary NIC, if any."),
    )

    gateway = models.CharField(
        max_length=64,
        blank=True,
        help_text=_("cloud-init primary-NIC gateway requested at create time."),
    )

    ip_cidr = models.CharField(
        max_length=64,
        blank=True,
        help_text=_(
            "cloud-init primary-NIC address in CIDR form (or ``dhcp``) "
            "requested at create time."
        ),
    )

    ssh_pwauth = models.BooleanField(
        null=True,
        blank=True,
        help_text=_(
            "cloud-init ``ssh_pwauth`` (password login) requested at create "
            "time. Null when unspecified."
        ),
    )

    enable_agent = models.BooleanField(
        null=True,
        blank=True,
        help_text=_(
            "Whether the QEMU guest agent was requested at create time. "
            "Null when unspecified."
        ),
    )

    nms_credential_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text=_(
            "Soft reference to the netbox-nms CloudVMCredential PK holding the "
            "encrypted cloud-init password / SSH private key for this VM. "
            "Integer id only — netbox-proxbox never imports netbox-nms."
        ),
    )

    sshkeys_enc = models.TextField(
        blank=True,
        help_text=_(
            "Fernet-encrypted cloud-init SSH public-key bundle captured at "
            "create time. Written via the ``sshkeys_intent`` API field; never "
            "returned in the clear. The plaintext ``sshkeys`` column remains a "
            "live Proxmox reflection mirror."
        ),
    )

    last_synced = models.DateTimeField(
        auto_now=True,
        help_text=_("Time of the last cloud-init reconciliation pass."),
    )

    class Meta:
        verbose_name = _("Proxmox VM cloud-init")
        verbose_name_plural = _("Proxmox VM cloud-init records")
        ordering = ("virtual_machine",)

    def __str__(self) -> str:
        """Return the parent VM name for list displays."""
        return f"{self.virtual_machine} cloud-init"

    def get_absolute_url(self) -> str:
        """Plugin UI URL for this cloud-init record's detail page."""
        return reverse("plugins:netbox_proxbox:proxmoxvmcloudinit", args=[self.pk])

    @property
    def has_sshkeys(self) -> bool:
        """True when an encrypted create-time SSH key bundle is stored."""
        return bool(self.sshkeys_enc)

    def set_sshkeys(self, plaintext: str | None) -> None:
        """Encrypt and store the create-time SSH public-key bundle."""
        from netbox_proxbox.models.primary_secrets import encrypt_primary_secret

        self.sshkeys_enc = encrypt_primary_secret(plaintext)

    def get_sshkeys(self) -> str:
        """Decrypt the stored create-time SSH public-key bundle."""
        from netbox_proxbox.models.primary_secrets import decrypt_primary_secret

        return decrypt_primary_secret(self.sshkeys_enc) if self.sshkeys_enc else ""
