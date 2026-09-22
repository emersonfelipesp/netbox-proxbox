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
from django.views.decorators.debug import sensitive_variables

from netbox.models import NetBoxModel

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
    openbao_password_credential_uuid = models.UUIDField(
        null=True,
        blank=True,
        editable=False,
        verbose_name=_("OpenBao password credential UUID"),
        help_text=_("Opaque reference to the OpenBao SSH password credential."),
    )
    openbao_keypair_credential_uuid = models.UUIDField(
        null=True,
        blank=True,
        editable=False,
        verbose_name=_("OpenBao key-pair credential UUID"),
        help_text=_("Opaque reference to the OpenBao SSH key-pair credential."),
    )

    class Meta:
        ordering = ("node",)
        verbose_name = _("Node SSH credential")
        verbose_name_plural = _("Node SSH credentials")

    def __str__(self) -> str:
        return f"{self.username}@{self.node}"

    @property
    def has_password(self) -> bool:
        """Return whether a password ciphertext or OpenBao reference is stored."""
        from netbox_proxbox.integrations.openbao import node_uses_openbao_storage
        from netbox_proxbox.integrations.openbao_node_pending import pending_credential

        if node_uses_openbao_storage(self):
            return bool(
                self.openbao_password_credential_uuid
                or pending_credential(self, "openbao_password_credential_uuid")
            )
        return bool(self.password_enc)

    @property
    def has_private_key(self) -> bool:
        """Return whether a private-key ciphertext or OpenBao reference is stored."""
        from netbox_proxbox.integrations.openbao import node_uses_openbao_storage
        from netbox_proxbox.integrations.openbao_node_pending import pending_credential

        if node_uses_openbao_storage(self):
            return bool(
                self.openbao_keypair_credential_uuid
                or pending_credential(self, "openbao_keypair_credential_uuid")
            )
        return bool(self.private_key_enc)

    @property
    def credential_encryption_state(self) -> str:
        """Return a secret-free aggregate state for list and edit recovery UX."""

        from netbox_proxbox.services.encryption_recovery import ciphertext_state
        from netbox_proxbox.integrations.openbao import node_uses_openbao_storage

        if node_uses_openbao_storage(self):
            states = (
                "configured" if self.openbao_password_credential_uuid else "empty",
                "configured" if self.openbao_keypair_credential_uuid else "empty",
            )
        else:
            states = (
                ciphertext_state(self.password_enc),
                ciphertext_state(self.private_key_enc),
            )
        if "recovery_required" in states:
            return "Recovery required"
        if "configured" in states:
            return "Configured"
        return "Not configured"

    def get_absolute_url(self) -> str:
        """Plugin UI URL for this credential's detail view."""
        return reverse("plugins:netbox_proxbox:nodesshcredential", args=[self.pk])

    # ------------------------------------------------------------------ secrets

    @sensitive_variables()
    def set_password(
        self,
        plaintext: str,
        *,
        key: str,
        user: object | None = None,
        request: object | None = None,
    ) -> None:
        """Queue OpenBao material or encrypt with the supplied Fernet key."""
        from netbox_proxbox.integrations.openbao import store_node_ssh_password

        store_node_ssh_password(
            self,
            plaintext,
            key=key,
            user=user,
            request=request,
        )

    @sensitive_variables()
    def get_password(self, *, key: str) -> str:
        """Resolve the stored SSH password from the selected backend."""
        from netbox_proxbox.integrations.openbao import resolve_node_ssh_password

        return resolve_node_ssh_password(self, key=key)

    @sensitive_variables()
    def set_private_key(
        self,
        plaintext: str,
        *,
        key: str,
        user: object | None = None,
        request: object | None = None,
    ) -> None:
        """Queue OpenBao material or encrypt with the supplied Fernet key."""
        from netbox_proxbox.integrations.openbao import store_node_ssh_keypair

        store_node_ssh_keypair(
            self,
            plaintext,
            key=key,
            user=user,
            request=request,
        )

    @sensitive_variables()
    def get_private_key(self, *, key: str) -> str:
        """Resolve the stored SSH private key from the selected backend."""
        from netbox_proxbox.integrations.openbao import resolve_node_ssh_private_key

        return resolve_node_ssh_private_key(self, key=key)

    # ------------------------------------------------------------------ clean

    def clean(self) -> None:
        """Validate fingerprint + auth-method invariants before save."""
        super().clean()
        self.known_host_fingerprint = normalize_fingerprint(self.known_host_fingerprint)
        if self.port < 1 or self.port > 65535:
            raise ValidationError({"port": "Port must be between 1 and 65535."})
        if self.auth_method == AUTH_METHOD_KEY and not self.has_private_key:
            raise ValidationError(
                {
                    "auth_method": (
                        "auth_method=key requires a private key — store one with "
                        "set_private_key() before saving."
                    )
                }
            )
        if self.auth_method == AUTH_METHOD_PASSWORD and not self.has_password:
            raise ValidationError(
                {
                    "auth_method": (
                        "auth_method=password requires a password — store one "
                        "with set_password() before saving."
                    )
                }
            )
