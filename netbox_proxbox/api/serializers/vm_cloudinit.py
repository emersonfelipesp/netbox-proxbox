"""API serializer for the ProxmoxVMCloudInit model (issue #363)."""

from __future__ import annotations

from django.db import transaction
from django.views.decorators.debug import sensitive_variables
from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers
from virtualization.api.serializers_.nested import NestedVirtualMachineSerializer

from netbox_proxbox.models import ProxmoxVMCloudInit


class ProxmoxVMCloudInitSerializer(NetBoxModelSerializer):
    """Full representation of a Proxmox VM cloud-init row stored in NetBox.

    proxbox-api writes the reflection fields (``ciuser``/``sshkeys``/
    ``ipconfig0``/``sshkeys_truncated``) from ``qm config``; API clients
    write the create-time *intent* fields (``hostname``/``search_domain``/
    ``dns_servers``/``bridge``/``vlan_tag``/``gateway``/``ip_cidr``/
    ``ssh_pwauth``/``enable_agent``/``is_intent``/``credential_reference_id`` and the
    encrypted SSH key bundle).

    ``sshkeys`` is delivered already decoded (newlines as ``\\n``); proxbox-api
    runs ``urllib.parse.unquote`` upstream and stays a live reflection mirror.
    Create-time SSH public keys are written through the separate write-only
    ``sshkeys_intent`` field, which encrypts them at rest into ``sshkeys_enc``;
    the raw intent bundle is never returned — only the ``has_sshkeys`` flag.
    """

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxmoxvmcloudinit-detail",
    )
    virtual_machine = NestedVirtualMachineSerializer()
    # Write-only: encrypted into sshkeys_enc on write; never serialized out.
    sshkeys_intent = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )
    password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        style={"input_type": "password"},
    )
    private_key = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        style={"input_type": "password"},
    )
    has_sshkeys = serializers.BooleanField(read_only=True)
    password_configured = serializers.BooleanField(read_only=True)
    private_key_configured = serializers.BooleanField(read_only=True)
    credential_assignment_ready = serializers.SerializerMethodField()
    credential_assignment_detail = serializers.SerializerMethodField()
    credential_assignment_lookup = serializers.SerializerMethodField()

    class Meta:
        model = ProxmoxVMCloudInit
        fields = (
            "id",
            "url",
            "display",
            "virtual_machine",
            "ciuser",
            "sshkeys",
            "ipconfig0",
            "sshkeys_truncated",
            # create-time cloud-init intent
            "is_intent",
            "hostname",
            "search_domain",
            "dns_servers",
            "bridge",
            "vlan_tag",
            "gateway",
            "ip_cidr",
            "ssh_pwauth",
            "enable_agent",
            "credential_reference_id",
            "password",
            "private_key",
            "password_configured",
            "private_key_configured",
            "credential_assignment_ready",
            "credential_assignment_detail",
            "credential_assignment_lookup",
            "sshkeys_intent",
            "has_sshkeys",
            "last_synced",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = (
            "id",
            "url",
            "display",
            "virtual_machine",
            "ciuser",
        )

    def _request_context(self) -> tuple[object, object]:
        request = self.context.get("request")
        return getattr(request, "user", None), request

    def _assignment_state(self, obj: ProxmoxVMCloudInit) -> tuple[bool, str]:
        from netbox_proxbox.integrations.openbao_cloudinit import (
            cloudinit_assignment_readiness,
        )

        return cloudinit_assignment_readiness(obj)

    def get_credential_assignment_ready(self, obj: ProxmoxVMCloudInit) -> bool:
        return self._assignment_state(obj)[0]

    def get_credential_assignment_detail(self, obj: ProxmoxVMCloudInit) -> str:
        return self._assignment_state(obj)[1]

    def get_credential_assignment_lookup(
        self, obj: ProxmoxVMCloudInit
    ) -> dict[str, str] | None:
        from netbox_proxbox.integrations.openbao_cloudinit import (
            cloudinit_assignment_lookup,
        )

        return cloudinit_assignment_lookup(obj)

    @sensitive_variables()
    def validate(self, attrs: dict) -> dict:
        """Keep external legacy references and provider material disjoint."""
        material = {
            name: attrs.pop(name)
            for name in ("password", "private_key")
            if name in attrs
        }
        attrs = super().validate(attrs)
        from netbox_proxbox.integrations.openbao_cloudinit import (
            cloudinit_uses_openbao_storage,
        )

        uses_openbao = cloudinit_uses_openbao_storage()
        if not uses_openbao and material:
            raise serializers.ValidationError(
                "Password and private-key inputs require OpenBao storage."
            )
        if uses_openbao and "credential_reference_id" in attrs:
            raise serializers.ValidationError(
                {
                    "credential_reference_id": (
                        "The external credential reference is writable only in "
                        "explicit legacy storage mode."
                    )
                }
            )
        attrs.update(material)
        return attrs

    @sensitive_variables()
    def _queue_material(
        self, instance: ProxmoxVMCloudInit, material: dict[str, object]
    ) -> None:
        actor, request = self._request_context()
        if "password" in material:
            instance.set_password(material["password"], user=actor, request=request)
        if "private_key" in material:
            instance.set_private_key(
                material["private_key"], user=actor, request=request
            )

    @sensitive_variables()
    def create(self, validated_data: dict) -> ProxmoxVMCloudInit:
        """Create a row and persist intent keys through the guarded model setter."""
        sshkeys_intent = validated_data.pop("sshkeys_intent", None)
        material = {
            name: validated_data.pop(name)
            for name in ("password", "private_key")
            if name in validated_data
        }
        with transaction.atomic():
            instance = super().create(validated_data)
            if material:
                self._queue_material(instance, material)
                instance.save()
            if sshkeys_intent:
                instance.set_sshkeys(str(sshkeys_intent))
                instance.save(update_fields=("sshkeys_enc",))
        return instance

    @sensitive_variables()
    def update(
        self,
        instance: ProxmoxVMCloudInit,
        validated_data: dict,
    ) -> ProxmoxVMCloudInit:
        """Update a row and persist intent keys through the guarded model setter."""
        sshkeys_intent = validated_data.pop("sshkeys_intent", None)
        material = {
            name: validated_data.pop(name)
            for name in ("password", "private_key")
            if name in validated_data
        }
        if material:
            self._queue_material(instance, material)
        with transaction.atomic():
            instance = super().update(instance, validated_data)
            if sshkeys_intent:
                instance.set_sshkeys(str(sshkeys_intent))
                instance.save(update_fields=("sshkeys_enc",))
        return instance
