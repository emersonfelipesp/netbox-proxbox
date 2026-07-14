"""API serializer for the ProxmoxVMCloudInit model (issue #363)."""

from __future__ import annotations

from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers
from virtualization.api.serializers_.nested import NestedVirtualMachineSerializer

from netbox_proxbox.models import ProxmoxVMCloudInit


class ProxmoxVMCloudInitSerializer(NetBoxModelSerializer):
    """Full representation of a Proxmox VM cloud-init row stored in NetBox.

    proxbox-api writes the reflection fields (``ciuser``/``sshkeys``/
    ``ipconfig0``/``sshkeys_truncated``) from ``qm config``; the NMS stack
    writes the create-time *intent* fields (``hostname``/``search_domain``/
    ``dns_servers``/``bridge``/``vlan_tag``/``gateway``/``ip_cidr``/
    ``ssh_pwauth``/``enable_agent``/``is_intent``/``nms_credential_id`` and the
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
    has_sshkeys = serializers.BooleanField(read_only=True)

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
            "nms_credential_id",
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

    def validate(self, data: dict) -> dict:
        # ``sshkeys_intent`` is a write-only serializer field with no model
        # counterpart; encrypt it into ``sshkeys_enc`` before the parent
        # instantiates/saves the model. Empty/absent keeps the existing value.
        sshkeys_intent = data.pop("sshkeys_intent", None)
        if sshkeys_intent:
            from netbox_proxbox.models.primary_secrets import encrypt_primary_secret

            data["sshkeys_enc"] = encrypt_primary_secret(sshkeys_intent)
        return super().validate(data)
