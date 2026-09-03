"""API serializer for operator-owned virtual-machine intent."""

from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers

from netbox_proxbox.api.serializers.sync_state import NestedVirtualMachineSerializer
from netbox_proxbox.models import ProxmoxVMIntent


class ProxmoxVMIntentSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxmoxvmintent-detail"
    )
    virtual_machine = NestedVirtualMachineSerializer()

    def validate_virtual_machine(self, value):
        """Keep an existing intent attached to its original virtual machine."""
        if self.instance is not None and getattr(
            self.instance, "virtual_machine_id", None
        ) != getattr(value, "pk", None):
            raise serializers.ValidationError(
                "The virtual machine for an existing Proxmox VM intent cannot be changed."
            )
        return value

    class Meta:
        model = ProxmoxVMIntent
        fields = (
            "id",
            "url",
            "display",
            "virtual_machine",
            "target_node",
            "target_storage",
            "iso",
            "template_vmid",
            "swap",
            "rootfs",
            "ostemplate",
            "cloud_init_user",
            "cloud_init_ssh_keys",
            "cloud_init_user_data",
            "cloud_init_network",
            "intent_state",
            "last_apply_run_id",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "virtual_machine")
        read_only_fields = ("intent_state", "last_apply_run_id")
