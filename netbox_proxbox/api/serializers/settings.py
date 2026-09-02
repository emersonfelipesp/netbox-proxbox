"""API serializer for ProxboxPluginSettings."""

from django.core.exceptions import ValidationError
from django.views.decorators.debug import sensitive_variables
from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers

from netbox_proxbox.constants import OVERWRITE_FIELDS, SYNC_MODE_FIELDS
from netbox_proxbox.models import ProxboxPluginSettings
from netbox_proxbox.models.plugin_settings import (
    CEPH_POLL_INTERVAL_TIMEOUT_ERROR,
    validate_console_url,
)


class ProxboxPluginSettingsSerializer(NetBoxModelSerializer):
    """Serializer for ProxboxPluginSettings singleton.

    Provides full CRUD via API for settings that proxbox-api reads.
    """

    # Declare this explicitly instead of relying on NetBox's model-field builder.
    # NetBox 4.5/4.6 can otherwise omit a blank partial update from validated_data,
    # bypassing the field-level ordinary-mutation error until model save time.
    encryption_key = serializers.CharField(
        allow_blank=True,
        max_length=255,
        required=False,
        write_only=True,
    )

    @sensitive_variables()
    def run_validation(self, data: object = serializers.empty) -> object:
        """Validate settings without exposing write-only input in parent frames."""

        return super().run_validation(data)

    @sensitive_variables()
    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        """Validate timing relationships for full and partial API updates."""

        validated = super().validate(attrs)
        timeout = validated.get(
            "ceph_task_timeout",
            getattr(
                self.instance,
                "ceph_task_timeout",
                ProxboxPluginSettings._meta.get_field(
                    "ceph_task_timeout"
                ).get_default(),
            ),
        )
        poll_interval = validated.get(
            "ceph_task_poll_interval",
            getattr(
                self.instance,
                "ceph_task_poll_interval",
                ProxboxPluginSettings._meta.get_field(
                    "ceph_task_poll_interval"
                ).get_default(),
            ),
        )
        if poll_interval > timeout:
            raise serializers.ValidationError(
                {"ceph_task_poll_interval": CEPH_POLL_INTERVAL_TIMEOUT_ERROR}
            )
        console_url = (
            str(
                validated.get("console_url", getattr(self.instance, "console_url", ""))
                or ""
            )
            .strip()
            .rstrip("/")
        )
        try:
            validate_console_url(console_url)
        except ValidationError as exc:
            raise serializers.ValidationError({"console_url": str(exc)}) from exc
        if "encryption_key" in validated and self.instance is not None:
            from netbox_proxbox.services.encryption_recovery import (
                EncryptionRecoveryError,
                assert_ordinary_key_mutation_allowed,
            )

            try:
                assert_ordinary_key_mutation_allowed(
                    str(getattr(self.instance, "encryption_key", "") or ""),
                    str(validated.get("encryption_key") or ""),
                )
            except EncryptionRecoveryError as exc:
                raise serializers.ValidationError(
                    {"encryption_key": str(exc)}
                ) from None
        return validated

    @sensitive_variables()
    def create(self, validated_data: dict[str, object]) -> ProxboxPluginSettings:
        """Create settings without exposing write-only values in error reports."""

        return super().create(validated_data)

    @sensitive_variables()
    def update(
        self,
        instance: ProxboxPluginSettings,
        validated_data: dict[str, object],
    ) -> ProxboxPluginSettings:
        """Update settings without exposing write-only values in error reports."""

        return super().update(instance, validated_data)

    @sensitive_variables()
    def save(self, **kwargs: object) -> ProxboxPluginSettings:
        """Persist settings without exposing merged validated data in reports."""

        return super().save(**kwargs)

    class Meta:
        model = ProxboxPluginSettings
        fields = [
            "id",
            "url",
            "display",
            "singleton_key",
            "console_url",
            "use_guest_agent_interface_name",
            "vm_interface_sync_strategy",
            "proxbox_fetch_max_concurrency",
            "ignore_ipv6_link_local_addresses",
            "ensure_netbox_objects",
            "delete_orphans",
            *SYNC_MODE_FIELDS,
            "parse_description_metadata",
            "embed_description_metadata",
            "enable_tenant_name_regex",
            "tenant_name_regex_rules",
            "enable_tenant_tag_assignment",
            "enable_tenant_from_cluster",
            "cloud_network_lock_enabled",
            "cloud_customer_prefix_id",
            "cloud_customer_bridge",
            "cloud_customer_vlan_tag",
            "cloud_customer_gateway",
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
            "interface_batch_size",
            "interface_batch_delay_ms",
            "reconciliation_engine",
            "reconciliation_compare_strict",
            "custom_fields_request_delay",
            "backend_log_file_path",
            "debug_cache",
            "expose_internal_errors",
            "netbox_openapi_persist",
            "ssrf_protection_enabled",
            "allow_private_ips",
            "additional_allowed_ip_ranges",
            "explicitly_blocked_ip_ranges",
            "encryption_key",
            "credential_storage_backend",
            "openbao_service_username",
            "proxmox_timeout",
            "proxmox_max_retries",
            "proxmox_retry_backoff",
            "ceph_task_timeout",
            "ceph_task_poll_interval",
            "ceph_run_lease_seconds",
            "default_role_qemu",
            "default_role_lxc",
            "branching_enabled",
            "branch_name_prefix",
            "branch_on_conflict",
            "netbox_to_proxmox_enabled",
            "netbox_to_proxmox_typed_confirmation",
            "intent_warn_plaintext_password",
            "apply_destroy_confirmed",
            "intent_apply_authorization_self_approve_allowed",
            "intent_deletion_request_ttl_days",
            "hardware_discovery_enabled",
            "hardware_discovery_sync_nic_macs",
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
