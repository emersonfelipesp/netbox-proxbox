"""API serializer for ProxboxPluginSettings."""

from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers

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
            "singleton_key",
            "use_guest_agent_interface_name",
            "proxbox_fetch_max_concurrency",
            "ignore_ipv6_link_local_addresses",
            "backend_log_file_path",
            "ssrf_protection_enabled",
            "allow_private_ips",
            "additional_allowed_ip_ranges",
            "explicitly_blocked_ip_ranges",
            "created",
            "last_updated",
        ]
        read_only_fields = ["id", "url", "singleton_key", "created", "last_updated"]
