"""API serializer for NodeSSHCredential.

CRUD-shape serializer that lets operators store credentials through the REST
API or the NetBox UI. Secrets are write-only and never reflected back in any
response — `password_enc` / `private_key_enc` ciphertext is not exposed
either. Callers that need the *decrypted* secrets go through the dedicated
NetBox API-token-protected shim at
``/api/plugins/proxbox/ssh-credentials/by-node/<node_id>/credentials/``
(see ``netbox_proxbox/api/ssh_credentials.py``).

`password` and `private_key` on this serializer are write-only inputs; the
serializer encrypts them with ``ProxboxPluginSettings.encryption_key`` on
save and refuses to save when the encryption key is missing.
"""

from __future__ import annotations

from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers

from netbox_proxbox.models import NodeSSHCredential, ProxboxPluginSettings
from netbox_proxbox.models.ssh_credential import normalize_fingerprint
from netbox_proxbox.utils import encryption as enc_helpers


class NodeSSHCredentialSerializer(NetBoxModelSerializer):
    """CRUD serializer with write-only secret inputs."""

    password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        trim_whitespace=False,
        style={"input_type": "password"},
    )
    private_key = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        trim_whitespace=False,
    )

    class Meta:
        model = NodeSSHCredential
        fields = [
            "id",
            "url",
            "display",
            "node",
            "username",
            "port",
            "auth_method",
            "known_host_fingerprint",
            "sudo_required",
            "password",
            "private_key",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        ]
        read_only_fields = ["id", "url", "display", "created", "last_updated"]

    def validate_known_host_fingerprint(self, value: str) -> str:
        """Reuse the model-level fingerprint normaliser."""
        return normalize_fingerprint(value)

    def _resolve_encryption_key(self) -> str:
        settings_obj = ProxboxPluginSettings.get_solo()
        key = settings_obj.encryption_key or ""
        if not key:
            raise serializers.ValidationError(
                {
                    "detail": (
                        "ProxboxPluginSettings.encryption_key is empty — "
                        "refusing to store SSH secrets."
                    )
                }
            )
        return key

    def _apply_secrets(self, instance: NodeSSHCredential, validated_data: dict) -> None:
        password = validated_data.pop("password", None)
        private_key = validated_data.pop("private_key", None)
        if not password and not private_key:
            return
        key = self._resolve_encryption_key()
        if password:
            instance.password_enc = enc_helpers.encrypt(password, key=key)
        if private_key:
            instance.private_key_enc = enc_helpers.encrypt(private_key, key=key)

    def create(self, validated_data: dict) -> NodeSSHCredential:
        password = validated_data.pop("password", None)
        private_key = validated_data.pop("private_key", None)
        instance = NodeSSHCredential(**validated_data)
        if password or private_key:
            key = self._resolve_encryption_key()
            if password:
                instance.password_enc = enc_helpers.encrypt(password, key=key)
            if private_key:
                instance.private_key_enc = enc_helpers.encrypt(private_key, key=key)
        instance.full_clean()
        instance.save()
        return instance

    def update(
        self, instance: NodeSSHCredential, validated_data: dict
    ) -> NodeSSHCredential:
        self._apply_secrets(instance, validated_data)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.full_clean()
        instance.save()
        return instance
