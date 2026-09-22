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

from uuid import uuid4

from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers
from django.views.decorators.debug import sensitive_variables

from netbox_proxbox.models import NodeSSHCredential, ProxboxPluginSettings
from netbox_proxbox.models.ssh_credential import normalize_fingerprint


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

    def _resolve_storage_key(self, instance: NodeSSHCredential) -> str:
        from netbox_proxbox.integrations.openbao import node_uses_openbao_storage

        if node_uses_openbao_storage(instance):
            return ""
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

    def _request_context(self) -> tuple[object | None, object | None]:
        request = self.context.get("request")
        return request, getattr(request, "user", None)

    def _attach_api_actor(self, instance: NodeSSHCredential) -> None:
        _request, user = self._request_context()
        if user is not None:
            instance._openbao_actor_user = user

    @staticmethod
    def _validation_markers(password: object, private_key: object) -> dict:
        markers = {}
        if password:
            markers.update(
                password_enc="validation-only",
                openbao_password_credential_uuid=uuid4(),
            )
        if private_key:
            markers.update(
                private_key_enc="validation-only",
                openbao_keypair_credential_uuid=uuid4(),
            )
        return markers

    @sensitive_variables()
    def validate(self, attrs: dict) -> dict:
        """Keep write-only plaintext outside NetBox's model constructor."""
        password = attrs.pop("password", None)
        private_key = attrs.pop("private_key", None)
        markers = self._validation_markers(password, private_key)
        if self.instance is None:
            attrs.update(markers)
            validated = super().validate(attrs)
            for name in markers:
                validated.pop(name, None)
        else:
            previous = {name: getattr(self.instance, name) for name in markers}
            for name, value in markers.items():
                setattr(self.instance, name, value)
            try:
                validated = super().validate(attrs)
            finally:
                for name, value in previous.items():
                    setattr(self.instance, name, value)
        if password is not None:
            validated["password"] = password
        if private_key is not None:
            validated["private_key"] = private_key
        return validated

    @sensitive_variables()
    def _apply_secrets(self, instance: NodeSSHCredential, validated_data: dict) -> None:
        password = validated_data.pop("password", None)
        private_key = validated_data.pop("private_key", None)
        if not password and not private_key:
            return
        key = self._resolve_storage_key(instance)
        request, user = self._request_context()

        if password:
            instance.set_password(password, key=key, user=user, request=request)
        if private_key:
            instance.set_private_key(private_key, key=key, user=user, request=request)

    @sensitive_variables()
    def create(self, validated_data: dict) -> NodeSSHCredential:
        password = validated_data.pop("password", None)
        private_key = validated_data.pop("private_key", None)
        instance = NodeSSHCredential(**validated_data)
        self._attach_api_actor(instance)
        secret_data = {"password": password, "private_key": private_key}
        self._apply_secrets(instance, secret_data)
        instance.full_clean()
        instance.save()
        return instance

    @sensitive_variables()
    def update(
        self, instance: NodeSSHCredential, validated_data: dict
    ) -> NodeSSHCredential:
        password = validated_data.pop("password", None)
        private_key = validated_data.pop("private_key", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        self._attach_api_actor(instance)
        self._apply_secrets(
            instance,
            {"password": password, "private_key": private_key},
        )
        instance.full_clean()
        instance.save()
        return instance
