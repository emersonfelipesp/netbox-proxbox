"""Serializer for the Build PVE Template REST action on ProxmoxEndpoint."""

from __future__ import annotations

from rest_framework import serializers


class PVETemplateBuildRequestSerializer(serializers.Serializer):
    """Mirror of proxbox-api's PVETemplateBuildRequest.

    The plugin proxies this body straight through to ``POST
    /cloud/templates/pve`` on proxbox-api, so the field set is kept in
    lock-step with ``proxbox_api.schemas.cloud_provision.PVETemplateBuildRequest``.
    ``endpoint_id`` is injected on the server side from the URL path
    parameter and must not be supplied by the caller.
    """

    vmid = serializers.IntegerField(min_value=100)
    name = serializers.CharField(max_length=128, default="debian12-pve-tmpl")
    target_node = serializers.CharField(max_length=256)
    debian_image_url = serializers.URLField(
        default=(
            "https://cloud.debian.org/images/cloud/bookworm/latest/"
            "debian-12-genericcloud-amd64.qcow2"
        )
    )
    image_filename = serializers.CharField(required=False, allow_blank=True, default="")
    image_storage = serializers.CharField(max_length=64, default="local")
    vm_storage = serializers.CharField(max_length=64, default="local-lvm")
    snippets_storage = serializers.CharField(max_length=64, default="local")
    bridge = serializers.CharField(max_length=64, default="vmbr0")
    memory_mb = serializers.IntegerField(min_value=512, default=4096)
    cores = serializers.IntegerField(min_value=1, default=4)
    nic_name = serializers.CharField(max_length=32, default="ens18")
    hostname = serializers.CharField(max_length=128, default="pve-node-01")
    domain = serializers.CharField(max_length=128, default="nmulti.local")
    node_cidr = serializers.CharField(max_length=64, default="10.0.30.50/24")
    gateway = serializers.CharField(max_length=64, default="10.0.30.1")
    nameservers = serializers.ListField(
        child=serializers.CharField(),
        default=["1.1.1.1", "8.8.8.8"],
    )
    pve_version_pin = serializers.CharField(max_length=32, default="9.1.11")
    debian_release = serializers.CharField(max_length=32, default="bookworm")
    ssh_authorized_keys = serializers.ListField(
        child=serializers.CharField(),
        default=list,
    )
    verify_image_certificates = serializers.BooleanField(default=True)
    create_vm = serializers.BooleanField(default=True)


class PVETemplateBuildResponseSerializer(serializers.Serializer):
    """OpenAPI-shape mirror of proxbox-api's PVETemplateBuildResponse."""

    endpoint_id = serializers.IntegerField()
    target_node = serializers.CharField()
    vmid = serializers.IntegerField()
    name = serializers.CharField()
    status = serializers.CharField()
    image_volid = serializers.CharField()
    snippet_user_data_path = serializers.CharField()
    snippet_network_config_path = serializers.CharField()
    snippet_meta_data_path = serializers.CharField()
    user_data = serializers.CharField()
    network_config = serializers.CharField()
    meta_data = serializers.CharField()
    qm_cicustom = serializers.CharField()
    operator_instructions = serializers.CharField()
    download_upid = serializers.CharField(required=False, allow_null=True)
    create_upid = serializers.CharField(required=False, allow_null=True)
