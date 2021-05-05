# base serializer class
from rest_framework import serializers

# import nested serializers for Netbox objects that we link to in our model ProxmoxVM
from virtualization.api.nested_serializers import NestedClusterSerializer, NestedVirtualMachineSerializer

# model that will be built the serializer
from netbox_proxbox.models import ProxmoxVM

class ProxmoxVMSerializer(serializers.ModelSerializer):
    """Serializer for the ProxmoxVM model."""

    cluster = NestedClusterSerializer(
        # set relationship type to many-to-one
        many=False,
        # the field is allowed as the input in API calls
        read_only=False,
        # specifies whether field is required.
        # it must follow the corresponding property set for the model field
        required=False,
        help_text="ProxmoxVM Cluster"
    )

    virtual_machine = NestedVirtualMachineSerializer(
        many=False,
        read_only=False,
        required=True,
        help_text="ProxmoxVM Virtual Machine"
    )

    class Meta:
        model = ProxmoxVM
        fields = [
            "id",
            "cluster",
            "virtual_machine",
            "proxmox_vm_id",
            "status",
            "node",
            "vcpus",
            "memory",
            "disk",
            "type",
            "description",
        ]