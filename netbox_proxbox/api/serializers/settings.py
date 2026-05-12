"""API serializer for ProxboxPluginSettings."""

from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers

from netbox_proxbox.constants import OVERWRITE_FIELDS
from netbox_proxbox.models import ProxboxPluginSettings


class ProxboxPluginSettingsSerializer(NetBoxModelSerializer):
    """Serializer for ProxboxPluginSettings singleton.

    Provides full CRUD via API for settings that proxbox-api reads.
    """

    class Meta:
        model = ProxboxPluginSettings
        fields = [
            "id",
            "url",
            "display",
            "singleton_key",
            "use_guest_agent_interface_name",
            "proxbox_fetch_max_concurrency",
            "ignore_ipv6_link_local_addresses",
            "primary_ip_preference",
            "netbox_max_concurrent",
            "netbox_timeout",
            "netbox_write_concurrency",
            "proxmox_fetch_concurrency",
            "netbox_max_retries",
            "netbox_retry_delay",
            "netbox_get_cache_ttl",
            "netbox_get_cache_max_entries",
            "netbox_get_cache_max_bytes",
            "bulk_batch_size",
            "bulk_batch_delay_ms",
            "backup_batch_size",
            "backup_batch_delay_ms",
            "vm_sync_max_concurrency",
            "custom_fields_request_delay",
            "backend_log_file_path",
            "debug_cache",
            "expose_internal_errors",
            "ssrf_protection_enabled",
            "allow_private_ips",
            "additional_allowed_ip_ranges",
            "explicitly_blocked_ip_ranges",
            "encryption_key",
            "proxmox_timeout",
            "proxmox_max_retries",
            "proxmox_retry_backoff",
            "default_role_qemu",
            "default_role_lxc",
            "branching_enabled",
            "branch_name_prefix",
            "branch_on_conflict",
            "netbox_to_proxmox_enabled",
            "netbox_to_proxmox_typed_confirmation",
            "apply_destroy_confirmed",
            *OVERWRITE_FIELDS,
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        ]
        read_only_fields = [
            "id",
            "url",
            "display",
            "singleton_key",
            "created",
            "last_updated",
        ]
        extra_kwargs = {
            "encryption_key": {"write_only": True},
        }
