"""Serializers for cloud image build actions on ProxmoxEndpoint."""

from __future__ import annotations

from rest_framework import serializers


class PVETemplateBuildRequestSerializer(serializers.Serializer):
    """Mirror of proxbox-api's CloudImageTemplateBuildRequest.

    The plugin proxies this body straight through to proxbox-api, so the field
    set is kept in lock-step with
    ``proxbox_api.schemas.cloud_provision.CloudImageTemplateBuildRequest``.
    ``endpoint_id`` is injected on the server side from the URL path
    parameter and must not be supplied by the caller.
    """

    product_type = serializers.ChoiceField(
        choices=("pve", "pbs", "pdm", "pfsense", "opnsense"),
        default="pve",
    )
    product_version = serializers.CharField(
        required=False, allow_null=True, allow_blank=True
    )
    provider = serializers.ChoiceField(
        choices=("debian_cloud_image", "release_image", "source_tree"),
        required=False,
        allow_null=True,
    )
    vmid = serializers.IntegerField(min_value=100)
    name = serializers.CharField(max_length=128, default="cloud-image-template")
    target_node = serializers.CharField(
        max_length=256, required=False, allow_blank=True
    )
    storage = serializers.CharField(max_length=64, default="local-lvm")
    snippets_dir = serializers.CharField(max_length=255, default="/var/lib/vz/snippets")
    debian_image_url = serializers.URLField(
        required=False,
        allow_blank=True,
        default=(
            "https://cloud.debian.org/images/cloud/bookworm/latest/"
            "debian-12-genericcloud-amd64.qcow2"
        ),
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
    image_url = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    checksum_url = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
    sha256 = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    source_tree_path = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
    source_build_command = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
    source_artifact_path = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
    disk_size_gb = serializers.IntegerField(
        min_value=1, required=False, allow_null=True
    )
    execute = serializers.BooleanField(default=False)
    ssh_host = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    ssh_user = serializers.CharField(max_length=64, default="root")
    ssh_port = serializers.IntegerField(min_value=1, max_value=65535, default=22)
    ssh_identity_file = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
    ssh_authorized_keys = serializers.ListField(
        child=serializers.CharField(),
        default=list,
    )
    verify_image_certificates = serializers.BooleanField(default=True)
    create_vm = serializers.BooleanField(default=True)


class PVETemplateBuildResponseSerializer(serializers.Serializer):
    """OpenAPI-shape mirror of proxbox-api's CloudImageTemplateBuildResponse.

    Legacy PVE-only response fields remain optional for clients still calling
    the compatibility action, but the generic pipeline fields below are the
    canonical response shape.
    """

    endpoint_id = serializers.IntegerField(required=False, allow_null=True)
    target_node = serializers.CharField(
        required=False, allow_null=True, allow_blank=True
    )
    vmid = serializers.IntegerField(required=False)
    name = serializers.CharField(required=False)
    status = serializers.CharField()
    image_volid = serializers.CharField(required=False, allow_blank=True)
    snippet_user_data_path = serializers.CharField(required=False, allow_blank=True)
    snippet_network_config_path = serializers.CharField(
        required=False, allow_blank=True
    )
    snippet_meta_data_path = serializers.CharField(required=False, allow_blank=True)
    user_data = serializers.CharField(required=False, allow_blank=True)
    network_config = serializers.CharField(required=False, allow_blank=True)
    meta_data = serializers.CharField(required=False, allow_blank=True)
    qm_cicustom = serializers.CharField(required=False, allow_blank=True)
    operator_instructions = serializers.CharField()
    download_upid = serializers.CharField(required=False, allow_null=True)
    create_upid = serializers.CharField(required=False, allow_null=True)
    pipeline_name = serializers.CharField(
        required=False, default="Cloud Image Build Pipeline"
    )
    product_type = serializers.CharField(required=False)
    product_version = serializers.CharField(required=False)
    provider = serializers.CharField(required=False)
    template_vmid = serializers.IntegerField(required=False)
    image_url = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    source_tree_path = serializers.CharField(
        required=False, allow_null=True, allow_blank=True
    )
    source_artifact_path = serializers.CharField(
        required=False, allow_null=True, allow_blank=True
    )
    generated_userdata = serializers.CharField(
        required=False, allow_null=True, allow_blank=True
    )
    first_boot_script = serializers.CharField(
        required=False, allow_null=True, allow_blank=True
    )
    build_script = serializers.CharField(required=False, allow_blank=True)
    commands = serializers.ListField(child=serializers.CharField(), required=False)
    execution_enabled = serializers.BooleanField(required=False)
    returncode = serializers.IntegerField(required=False, allow_null=True)
    stdout = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    stderr = serializers.CharField(required=False, allow_null=True, allow_blank=True)
