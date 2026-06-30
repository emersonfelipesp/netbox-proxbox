"""Per-node SSH credential storage for hardware discovery.

The hardware-discovery flow opens an SSH session to a Proxmox node (or any
Debian-style host) using `proxmox_sdk.ssh.RemoteSSHClient`. To do so it needs
a username, a pinned host-key fingerprint, and either a private key or
password. This model stores those values for each `ProxmoxNode`, encrypting
the two secrets at rest with `ProxboxPluginSettings.encryption_key`.

Notes:
* `password_enc` and `private_key_enc` hold Fernet-encrypted ciphertext —
  they are never stored in cleartext on disk.
* `set_password()` / `set_private_key()` write the ciphertext; the matching
  `get_*()` accessors decrypt on read.
* When `ProxboxPluginSettings.encryption_key` is empty the helpers raise
  `EncryptionKeyMissing` — the hardware-discovery REST endpoint and orchestrator
  must treat that as a hard refusal rather than silently dropping the credential.
"""

from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from netbox.models import NetBoxModel

from netbox_proxbox.utils import encryption as enc_helpers


AUTH_METHOD_KEY = "key"
AUTH_METHOD_PASSWORD = "password"

AUTH_METHOD_CHOICES = (
    (AUTH_METHOD_KEY, _("SSH private key (recommended)")),
    (AUTH_METHOD_PASSWORD, _("Password (fallback)")),
)

SSH_CRED_SOURCE_DEDICATED = "dedicated"
SSH_CRED_SOURCE_REUSE = "reuse_endpoint"

SSH_CRED_SOURCE_CHOICES = (
    (SSH_CRED_SOURCE_DEDICATED, _("Dedicated SSH credential")),
    (SSH_CRED_SOURCE_REUSE, _("Reuse endpoint username/password")),
)

_FINGERPRINT_RE = re.compile(r"^SHA256:[A-Za-z0-9+/]{43}=?$")


def normalize_fingerprint(value: str) -> str:
    """Normalize a host-key fingerprint string into ``SHA256:<base64>`` form.

    Accepts the canonical ``SHA256:<base64>`` form, a lowercase ``sha256:``
    prefix, padded or unpadded base64. Raises ``ValidationError`` for anything
    that does not look like a SHA-256 fingerprint — and explicitly rejects the
    legacy weak ``MD5:`` prefix.
    """
    if not value:
        raise ValidationError("Host-key fingerprint cannot be empty.")
    text = value.strip()
    if text.lower().startswith("md5:"):
        raise ValidationError(
            "MD5 host-key fingerprints are not accepted — use the SHA-256 form."
        )
    if text.lower().startswith("sha256:"):
        body = text.split(":", 1)[1].rstrip("=")
        canonical = f"SHA256:{body}"
    else:
        canonical = f"SHA256:{text.rstrip('=')}"
    if not _FINGERPRINT_RE.match(canonical) and not _FINGERPRINT_RE.match(
        canonical + "="
    ):
        raise ValidationError(
            "Host-key fingerprint must be SHA256:<base64> (43 base64 characters)."
        )
    return canonical


class NodeSSHCredential(NetBoxModel):
    """Encrypted SSH credentials for a single ProxmoxNode.

    The relationship is one-to-one: each node can have at most one stored
    credential row. The discovery orchestrator looks up by node id and refuses
    to proceed if no row exists.
    """

    node = models.OneToOneField(
        to="netbox_proxbox.ProxmoxNode",
        on_delete=models.CASCADE,
        related_name="ssh_credential",
        verbose_name=_("Proxmox node"),
        help_text=_("Node these credentials authorize SSH access to."),
    )
    username = models.CharField(
        max_length=64,
        verbose_name=_("SSH username"),
        help_text=_(
            "Dedicated discovery user on the node (e.g. proxbox-discovery). "
            "Should NOT be root — pair with a least-privilege sudoers entry."
        ),
    )
    port = models.PositiveIntegerField(
        default=22,
        verbose_name=_("SSH port"),
        help_text=_("TCP port for the SSH listener. Default 22."),
    )
    auth_method = models.CharField(
        max_length=8,
        choices=AUTH_METHOD_CHOICES,
        default=AUTH_METHOD_KEY,
        verbose_name=_("Authentication method"),
        help_text=_(
            "Prefer key-based authentication. Password is a fallback for legacy "
            "fleets — only key-based unlocks the locked-down sudoers / "
            "ForceCommand pattern."
        ),
    )
    known_host_fingerprint = models.CharField(
        max_length=128,
        verbose_name=_("Pinned host-key SHA-256 fingerprint"),
        help_text=_(
            "Canonical SHA256:<base64> form. Proxbox refuses to connect unless "
            "the node's host key matches this exact value (no TOFU)."
        ),
    )
    sudo_required = models.BooleanField(
        default=True,
        verbose_name=_("Run discovery commands under sudo -n"),
        help_text=_(
            "When enabled, the discovery driver prepends 'sudo -n' to each "
            "discovery command. Disable only if the user already has direct "
            "permissions for dmidecode/ip/ethtool."
        ),
    )
    password_enc = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Encrypted password"),
        help_text=_("Fernet-encrypted password ciphertext. Internal."),
    )
    private_key_enc = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Encrypted private key"),
        help_text=_("Fernet-encrypted OpenSSH PEM ciphertext. Internal."),
    )

    class Meta:
        ordering = ("node",)
        verbose_name = _("Node SSH credential")
        verbose_name_plural = _("Node SSH credentials")

    def __str__(self) -> str:
        return f"{self.username}@{self.node}"

    @property
    def has_password(self) -> bool:
        """Return whether a password ciphertext is stored."""
        return bool(self.password_enc)

    @property
    def has_private_key(self) -> bool:
        """Return whether a private-key ciphertext is stored."""
        return bool(self.private_key_enc)

    def get_absolute_url(self) -> str:
        """Plugin UI URL for this credential's detail view."""
        return reverse("plugins:netbox_proxbox:nodesshcredential", args=[self.pk])

    # ------------------------------------------------------------------ secrets

    def set_password(self, plaintext: str, *, key: str) -> None:
        """Encrypt and store the SSH password with the supplied Fernet key."""
        self.password_enc = enc_helpers.encrypt(plaintext, key=key)

    def get_password(self, *, key: str) -> str:
        """Decrypt and return the stored SSH password."""
        return enc_helpers.decrypt(self.password_enc, key=key)

    def set_private_key(self, plaintext: str, *, key: str) -> None:
        """Encrypt and store the SSH private key PEM with the supplied key."""
        self.private_key_enc = enc_helpers.encrypt(plaintext, key=key)

    def get_private_key(self, *, key: str) -> str:
        """Decrypt and return the stored SSH private key PEM."""
        return enc_helpers.decrypt(self.private_key_enc, key=key)

    # ------------------------------------------------------------------ clean

    def clean(self) -> None:
        """Validate fingerprint + auth-method invariants before save."""
        super().clean()
        self.known_host_fingerprint = normalize_fingerprint(self.known_host_fingerprint)
        if self.port < 1 or self.port > 65535:
            raise ValidationError({"port": "Port must be between 1 and 65535."})
        if self.auth_method == AUTH_METHOD_KEY and not self.private_key_enc:
            raise ValidationError(
                {
                    "auth_method": (
                        "auth_method=key requires a private key — store one with "
                        "set_private_key() before saving."
                    )
                }
            )
        if self.auth_method == AUTH_METHOD_PASSWORD and not self.password_enc:
            raise ValidationError(
                {
                    "auth_method": (
                        "auth_method=password requires a password — store one "
                        "with set_password() before saving."
                    )
                }
            )
