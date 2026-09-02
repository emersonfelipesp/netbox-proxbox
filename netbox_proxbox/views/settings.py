"""Plugin settings page for feature toggles."""

import json

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables

from netbox_proxbox.constants import (
    OVERWRITE_FIELD_GROUPS,
    OVERWRITE_FIELDS,
    SYNC_MODE_FIELD_GROUPS,
    SYNC_MODE_FIELDS,
)
from netbox_proxbox.forms.settings import ProxboxPluginSettingsForm
from netbox_proxbox.integrations.bgp import netbox_bgp_status
from netbox_proxbox.models import ProxboxPluginSettings
from netbox_proxbox.views.proxbox_access import (
    permission_change_proxbox_plugin_settings,
)
from utilities.views import (
    ContentTypePermissionRequiredMixin,
    TokenConditionalLoginRequiredMixin,
)


def _settings_template_context(
    request: HttpRequest,
    form: ProxboxPluginSettingsForm,
    *,
    encryption_statuses: tuple[object, ...] = (),
) -> dict[str, object]:
    """Build shared template context for settings GET and invalid POST renders."""
    try:
        from netbox_proxbox.forms.settings import (
            EncryptedSecretResetForm,
            EncryptionKeyRotationForm,
        )

        rotation_form: object | None = EncryptionKeyRotationForm()
        reset_form: object | None = EncryptedSecretResetForm()
    except ImportError:  # Compatibility for the isolated mocked-view harness.
        rotation_form = None
        reset_form = None
    return {
        "form": form,
        "netbox_bgp_status": netbox_bgp_status(),
        "overwrite_field_groups": OVERWRITE_FIELD_GROUPS,
        "sync_mode_field_groups": SYNC_MODE_FIELD_GROUPS,
        "encryption_family_statuses": encryption_statuses,
        "encryption_payloads_exist": any(
            bool(getattr(status, "rows_with_ciphertext", 0))
            for status in encryption_statuses
        ),
        "encryption_recovery_required": any(
            bool(getattr(status, "recovery_required", False))
            for status in encryption_statuses
        ),
        "encryption_rotation_form": rotation_form,
        "encrypted_secret_reset_form": reset_form,
        "can_reset_encrypted_secrets": request.user.has_perm(
            "netbox_proxbox.reset_encrypted_secrets"
        ),
    }


@sensitive_variables()
def _encrypted_family_statuses(
    settings_obj: ProxboxPluginSettings,
) -> tuple[object, ...]:
    """Load secret-free registry state, tolerating only unavailable test scaffolding."""

    try:
        from netbox_proxbox.services.encryption_recovery import (
            encrypted_family_statuses,
        )
    except ImportError:
        return ()
    return encrypted_family_statuses(key=str(settings_obj.encryption_key or ""))


@method_decorator(sensitive_post_parameters("encryption_key"), name="dispatch")
class SettingsView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """Render and persist plugin-level operational settings."""

    template_name = "netbox_proxbox/settings.html"

    def get_required_permission(self) -> str:
        """Return required permission."""
        return permission_change_proxbox_plugin_settings()

    def get(self, request: HttpRequest) -> HttpResponse:
        """Handle get."""
        settings_obj = ProxboxPluginSettings.get_solo()
        encryption_statuses = _encrypted_family_statuses(settings_obj)
        initial = {
            "use_guest_agent_interface_name": settings_obj.use_guest_agent_interface_name,
            "console_url": getattr(settings_obj, "console_url", ""),
            "vm_interface_sync_strategy": getattr(
                settings_obj,
                "vm_interface_sync_strategy",
                "guest_os_model",
            ),
            "proxbox_fetch_max_concurrency": settings_obj.proxbox_fetch_max_concurrency,
            "ignore_ipv6_link_local_addresses": settings_obj.ignore_ipv6_link_local_addresses,
            "ensure_netbox_objects": settings_obj.ensure_netbox_objects,
            "delete_orphans": settings_obj.delete_orphans,
            "primary_ip_preference": settings_obj.primary_ip_preference,
            "netbox_max_concurrent": settings_obj.netbox_max_concurrent,
            "netbox_timeout": settings_obj.netbox_timeout,
            "netbox_write_concurrency": settings_obj.netbox_write_concurrency,
            "proxmox_fetch_concurrency": settings_obj.proxmox_fetch_concurrency,
            "netbox_max_retries": settings_obj.netbox_max_retries,
            "netbox_retry_delay": settings_obj.netbox_retry_delay,
            "netbox_get_cache_ttl": settings_obj.netbox_get_cache_ttl,
            "netbox_get_cache_max_entries": settings_obj.netbox_get_cache_max_entries,
            "netbox_get_cache_max_bytes": settings_obj.netbox_get_cache_max_bytes,
            "bulk_batch_size": settings_obj.bulk_batch_size,
            "bulk_batch_delay_ms": settings_obj.bulk_batch_delay_ms,
            "backup_batch_size": settings_obj.backup_batch_size,
            "backup_batch_delay_ms": settings_obj.backup_batch_delay_ms,
            "interface_batch_size": settings_obj.interface_batch_size,
            "interface_batch_delay_ms": settings_obj.interface_batch_delay_ms,
            "vm_sync_max_concurrency": settings_obj.vm_sync_max_concurrency,
            "reconciliation_engine": settings_obj.reconciliation_engine,
            "reconciliation_compare_strict": (
                settings_obj.reconciliation_compare_strict
            ),
            "custom_fields_request_delay": settings_obj.custom_fields_request_delay,
            "backend_log_file_path": settings_obj.backend_log_file_path,
            "debug_cache": settings_obj.debug_cache,
            "expose_internal_errors": settings_obj.expose_internal_errors,
            "netbox_openapi_persist": getattr(
                settings_obj, "netbox_openapi_persist", True
            ),
            "parse_description_metadata": settings_obj.parse_description_metadata,
            "embed_description_metadata": settings_obj.embed_description_metadata,
            "ssrf_protection_enabled": settings_obj.ssrf_protection_enabled,
            "allow_private_ips": settings_obj.allow_private_ips,
            "additional_allowed_ip_ranges": settings_obj.additional_allowed_ip_ranges,
            "explicitly_blocked_ip_ranges": settings_obj.explicitly_blocked_ip_ranges,
            "encryption_enabled": bool(settings_obj.encryption_key),
            "credential_storage_backend": getattr(
                settings_obj,
                "credential_storage_backend",
                "openbao",
            ),
            "openbao_service_username": getattr(
                settings_obj,
                "openbao_service_username",
                "",
            ),
            "proxmox_timeout": settings_obj.proxmox_timeout,
            "proxmox_max_retries": settings_obj.proxmox_max_retries,
            "proxmox_retry_backoff": settings_obj.proxmox_retry_backoff,
            "ceph_task_timeout": settings_obj.ceph_task_timeout,
            "ceph_task_poll_interval": settings_obj.ceph_task_poll_interval,
            "ceph_run_lease_seconds": settings_obj.ceph_run_lease_seconds,
            "default_role_qemu": settings_obj.default_role_qemu_id,
            "default_role_lxc": settings_obj.default_role_lxc_id,
            "enable_tenant_name_regex": settings_obj.enable_tenant_name_regex,
            "tenant_name_regex_rules": json.dumps(
                settings_obj.tenant_name_regex_rules or [],
                indent=2,
            ),
            "enable_tenant_tag_assignment": getattr(
                settings_obj,
                "enable_tenant_tag_assignment",
                False,
            ),
            "enable_tenant_from_cluster": getattr(
                settings_obj,
                "enable_tenant_from_cluster",
                False,
            ),
            "cloud_network_lock_enabled": getattr(
                settings_obj,
                "cloud_network_lock_enabled",
                False,
            ),
            "cloud_customer_prefix_id": getattr(
                settings_obj,
                "cloud_customer_prefix_id",
                None,
            ),
            "cloud_customer_bridge": getattr(
                settings_obj,
                "cloud_customer_bridge",
                "vmbr1",
            ),
            "cloud_customer_vlan_tag": getattr(
                settings_obj,
                "cloud_customer_vlan_tag",
                None,
            ),
            "cloud_customer_gateway": getattr(
                settings_obj,
                "cloud_customer_gateway",
                "",
            ),
            "branching_enabled": settings_obj.branching_enabled,
            "branch_name_prefix": settings_obj.branch_name_prefix,
            "branch_on_conflict": settings_obj.branch_on_conflict,
            "netbox_to_proxmox_enabled": settings_obj.netbox_to_proxmox_enabled,
            "netbox_to_proxmox_typed_confirmation": (
                settings_obj.netbox_to_proxmox_typed_confirmation
            ),
            "intent_warn_plaintext_password": getattr(
                settings_obj,
                "intent_warn_plaintext_password",
                True,
            ),
            "apply_destroy_confirmed": settings_obj.apply_destroy_confirmed,
            "intent_apply_authorization_self_approve_allowed": getattr(
                settings_obj,
                "intent_apply_authorization_self_approve_allowed",
                False,
            ),
            "intent_deletion_request_ttl_days": getattr(
                settings_obj,
                "intent_deletion_request_ttl_days",
                7,
            ),
            "hardware_discovery_enabled": settings_obj.hardware_discovery_enabled,
            "hardware_discovery_sync_nic_macs": getattr(
                settings_obj,
                "hardware_discovery_sync_nic_macs",
                False,
            ),
        }
        for name in SYNC_MODE_FIELDS:
            initial[name] = getattr(settings_obj, name, "always")
        for name in OVERWRITE_FIELDS:
            initial[name] = getattr(settings_obj, name)
        form = ProxboxPluginSettingsForm(
            initial=initial,
            encryption_key_configured=bool(settings_obj.encryption_key),
            encryption_key_locked=any(
                bool(getattr(status, "rows_with_ciphertext", 0))
                for status in encryption_statuses
            ),
        )
        return render(
            request,
            self.template_name,
            _settings_template_context(
                request, form, encryption_statuses=encryption_statuses
            ),
        )

    @sensitive_variables()
    def post(self, request: HttpRequest) -> HttpResponse:
        """Handle post."""
        settings_obj = ProxboxPluginSettings.get_solo()
        encryption_statuses = _encrypted_family_statuses(settings_obj)
        form = ProxboxPluginSettingsForm(
            request.POST,
            encryption_key_configured=bool(settings_obj.encryption_key),
            encryption_key_locked=any(
                bool(getattr(status, "rows_with_ciphertext", 0))
                for status in encryption_statuses
            ),
        )
        if form.is_valid():
            settings_obj.use_guest_agent_interface_name = form.cleaned_data[
                "use_guest_agent_interface_name"
            ]
            settings_obj.console_url = form.cleaned_data.get("console_url", "").strip()
            settings_obj.vm_interface_sync_strategy = form.cleaned_data.get(
                "vm_interface_sync_strategy",
                "guest_os_model",
            )
            settings_obj.proxbox_fetch_max_concurrency = form.cleaned_data[
                "proxbox_fetch_max_concurrency"
            ]
            settings_obj.ignore_ipv6_link_local_addresses = form.cleaned_data[
                "ignore_ipv6_link_local_addresses"
            ]
            settings_obj.ensure_netbox_objects = form.cleaned_data.get(
                "ensure_netbox_objects", True
            )
            settings_obj.delete_orphans = form.cleaned_data.get("delete_orphans", False)
            settings_obj.primary_ip_preference = form.cleaned_data[
                "primary_ip_preference"
            ]
            settings_obj.backend_log_file_path = form.cleaned_data[
                "backend_log_file_path"
            ]
            settings_obj.ssrf_protection_enabled = form.cleaned_data.get(
                "ssrf_protection_enabled", False
            )
            settings_obj.allow_private_ips = form.cleaned_data.get(
                "allow_private_ips", False
            )
            settings_obj.additional_allowed_ip_ranges = form.cleaned_data.get(
                "additional_allowed_ip_ranges", ""
            )
            settings_obj.explicitly_blocked_ip_ranges = form.cleaned_data.get(
                "explicitly_blocked_ip_ranges", ""
            )
            settings_obj.netbox_max_concurrent = form.cleaned_data[
                "netbox_max_concurrent"
            ]
            settings_obj.netbox_timeout = form.cleaned_data["netbox_timeout"]
            settings_obj.netbox_write_concurrency = form.cleaned_data[
                "netbox_write_concurrency"
            ]
            settings_obj.proxmox_fetch_concurrency = form.cleaned_data[
                "proxmox_fetch_concurrency"
            ]
            settings_obj.netbox_max_retries = form.cleaned_data["netbox_max_retries"]
            settings_obj.netbox_retry_delay = form.cleaned_data["netbox_retry_delay"]
            settings_obj.netbox_get_cache_ttl = form.cleaned_data[
                "netbox_get_cache_ttl"
            ]
            settings_obj.netbox_get_cache_max_entries = form.cleaned_data[
                "netbox_get_cache_max_entries"
            ]
            settings_obj.netbox_get_cache_max_bytes = form.cleaned_data[
                "netbox_get_cache_max_bytes"
            ]
            settings_obj.bulk_batch_size = form.cleaned_data["bulk_batch_size"]
            settings_obj.bulk_batch_delay_ms = form.cleaned_data["bulk_batch_delay_ms"]
            settings_obj.backup_batch_size = form.cleaned_data["backup_batch_size"]
            settings_obj.backup_batch_delay_ms = form.cleaned_data[
                "backup_batch_delay_ms"
            ]
            settings_obj.interface_batch_size = form.cleaned_data[
                "interface_batch_size"
            ]
            settings_obj.interface_batch_delay_ms = form.cleaned_data[
                "interface_batch_delay_ms"
            ]
            settings_obj.vm_sync_max_concurrency = form.cleaned_data[
                "vm_sync_max_concurrency"
            ]
            settings_obj.reconciliation_engine = form.cleaned_data[
                "reconciliation_engine"
            ]
            settings_obj.reconciliation_compare_strict = form.cleaned_data.get(
                "reconciliation_compare_strict",
                False,
            )
            settings_obj.custom_fields_request_delay = form.cleaned_data.get(
                "custom_fields_request_delay", 0
            )
            settings_obj.debug_cache = form.cleaned_data.get("debug_cache", False)
            settings_obj.expose_internal_errors = form.cleaned_data.get(
                "expose_internal_errors", False
            )
            settings_obj.netbox_openapi_persist = form.cleaned_data.get(
                "netbox_openapi_persist", True
            )
            settings_obj.parse_description_metadata = form.cleaned_data.get(
                "parse_description_metadata", False
            )
            settings_obj.embed_description_metadata = form.cleaned_data.get(
                "embed_description_metadata", False
            )
            settings_obj.proxmox_timeout = form.cleaned_data["proxmox_timeout"]
            settings_obj.proxmox_max_retries = form.cleaned_data["proxmox_max_retries"]
            settings_obj.proxmox_retry_backoff = form.cleaned_data[
                "proxmox_retry_backoff"
            ]
            settings_obj.ceph_task_timeout = form.cleaned_data["ceph_task_timeout"]
            settings_obj.ceph_task_poll_interval = form.cleaned_data[
                "ceph_task_poll_interval"
            ]
            settings_obj.ceph_run_lease_seconds = form.cleaned_data[
                "ceph_run_lease_seconds"
            ]
            settings_obj.default_role_qemu = form.cleaned_data.get("default_role_qemu")
            settings_obj.default_role_lxc = form.cleaned_data.get("default_role_lxc")
            settings_obj.enable_tenant_name_regex = form.cleaned_data.get(
                "enable_tenant_name_regex", False
            )
            settings_obj.tenant_name_regex_rules = form.cleaned_data.get(
                "tenant_name_regex_rules", []
            )
            settings_obj.enable_tenant_tag_assignment = form.cleaned_data.get(
                "enable_tenant_tag_assignment", False
            )
            settings_obj.enable_tenant_from_cluster = form.cleaned_data.get(
                "enable_tenant_from_cluster", False
            )
            settings_obj.cloud_network_lock_enabled = form.cleaned_data.get(
                "cloud_network_lock_enabled", False
            )
            settings_obj.cloud_customer_prefix_id = form.cleaned_data.get(
                "cloud_customer_prefix_id"
            )
            settings_obj.cloud_customer_bridge = form.cleaned_data.get(
                "cloud_customer_bridge", "vmbr1"
            )
            settings_obj.cloud_customer_vlan_tag = form.cleaned_data.get(
                "cloud_customer_vlan_tag"
            )
            settings_obj.cloud_customer_gateway = form.cleaned_data.get(
                "cloud_customer_gateway", ""
            )
            settings_obj.branching_enabled = form.cleaned_data.get(
                "branching_enabled", False
            )
            settings_obj.branch_name_prefix = form.cleaned_data.get(
                "branch_name_prefix", "proxbox-sync"
            )
            settings_obj.branch_on_conflict = form.cleaned_data.get(
                "branch_on_conflict", "fail"
            )
            settings_obj.netbox_to_proxmox_enabled = form.cleaned_data.get(
                "netbox_to_proxmox_enabled", False
            )
            settings_obj.netbox_to_proxmox_typed_confirmation = form.cleaned_data.get(
                "netbox_to_proxmox_typed_confirmation", ""
            )
            settings_obj.intent_warn_plaintext_password = form.cleaned_data.get(
                "intent_warn_plaintext_password",
                True,
            )
            settings_obj.apply_destroy_confirmed = form.cleaned_data.get(
                "apply_destroy_confirmed", False
            )
            settings_obj.intent_apply_authorization_self_approve_allowed = (
                form.cleaned_data.get(
                    "intent_apply_authorization_self_approve_allowed",
                    False,
                )
            )
            settings_obj.intent_deletion_request_ttl_days = form.cleaned_data.get(
                "intent_deletion_request_ttl_days",
                7,
            )
            settings_obj.hardware_discovery_enabled = form.cleaned_data.get(
                "hardware_discovery_enabled", False
            )
            settings_obj.hardware_discovery_sync_nic_macs = form.cleaned_data.get(
                "hardware_discovery_sync_nic_macs", False
            )
            for _sync_mode_field in SYNC_MODE_FIELDS:
                setattr(
                    settings_obj,
                    _sync_mode_field,
                    form.cleaned_data.get(_sync_mode_field, "always"),
                )
            for _overwrite_field in OVERWRITE_FIELDS:
                setattr(
                    settings_obj,
                    _overwrite_field,
                    form.cleaned_data.get(_overwrite_field, True),
                )
            encryption_enabled = form.cleaned_data.get("encryption_enabled", False)
            if encryption_enabled:
                new_key = form.cleaned_data.get("encryption_key", "").strip()
                if new_key:
                    settings_obj.encryption_key = new_key
                # If checked but key field is blank, preserve existing key
            else:
                settings_obj.encryption_key = ""
            settings_obj.credential_storage_backend = form.cleaned_data.get(
                "credential_storage_backend",
                "openbao",
            )
            settings_obj.openbao_service_username = (
                form.cleaned_data.get("openbao_service_username", "") or ""
            ).strip()
            settings_obj.save(
                update_fields=[
                    "use_guest_agent_interface_name",
                    "console_url",
                    "vm_interface_sync_strategy",
                    "proxbox_fetch_max_concurrency",
                    "ignore_ipv6_link_local_addresses",
                    "ensure_netbox_objects",
                    "delete_orphans",
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
                    "interface_batch_size",
                    "interface_batch_delay_ms",
                    "vm_sync_max_concurrency",
                    "reconciliation_engine",
                    "reconciliation_compare_strict",
                    "custom_fields_request_delay",
                    "backend_log_file_path",
                    "debug_cache",
                    "expose_internal_errors",
                    "netbox_openapi_persist",
                    "parse_description_metadata",
                    "embed_description_metadata",
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
                    "enable_tenant_name_regex",
                    "tenant_name_regex_rules",
                    "enable_tenant_tag_assignment",
                    "enable_tenant_from_cluster",
                    "cloud_network_lock_enabled",
                    "cloud_customer_prefix_id",
                    "cloud_customer_bridge",
                    "cloud_customer_vlan_tag",
                    "cloud_customer_gateway",
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
                    *SYNC_MODE_FIELDS,
                    *OVERWRITE_FIELDS,
                ]
            )
            messages.success(request, "Proxbox plugin settings updated.")
            return redirect("plugins:netbox_proxbox:settings")
        return render(
            request,
            self.template_name,
            _settings_template_context(
                request, form, encryption_statuses=encryption_statuses
            ),
        )


@method_decorator(
    sensitive_post_parameters("old_key", "new_key", "confirm_new_key"),
    name="dispatch",
)
class EncryptionKeyRotateView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """Rotate all plugin ciphertext only after complete old-key verification."""

    http_method_names = ("post",)

    def get_required_permission(self) -> str:
        """Require ordinary settings change permission for non-destructive rotation."""

        return permission_change_proxbox_plugin_settings()

    def post(self, request: HttpRequest) -> HttpResponse:
        """Run the atomic registry-wide rotation and return to settings."""

        from netbox_proxbox.forms.settings import EncryptionKeyRotationForm
        from netbox_proxbox.services.encryption_recovery import (
            EncryptionRecoveryError,
            record_encryption_recovery_event,
            rotate_encryption_key,
        )

        form = EncryptionKeyRotationForm(request.POST)
        if not form.is_valid():
            record_encryption_recovery_event(
                settings_obj=ProxboxPluginSettings.get_solo(),
                actor=request.user,
                request_id=request.id,
                operation="rotate",
                outcome="rejected",
                family_keys=("all_registered",),
            )
            messages.error(request, "Encryption key rotation was not submitted.")
            return redirect("plugins:netbox_proxbox:settings")
        try:
            result = rotate_encryption_key(
                old_key=str(form.cleaned_data["old_key"]),
                new_key=str(form.cleaned_data["new_key"]),
                audit_actor=request.user,
                audit_request_id=request.id,
            )
        except EncryptionRecoveryError as exc:
            record_encryption_recovery_event(
                settings_obj=ProxboxPluginSettings.get_solo(),
                actor=request.user,
                request_id=request.id,
                operation="rotate",
                outcome="failed",
                family_keys=("all_registered",),
            )
            messages.error(request, str(exc))
            return redirect("plugins:netbox_proxbox:settings")
        except Exception:  # noqa: BLE001 - audit then preserve unexpected traceback
            record_encryption_recovery_event(
                settings_obj=ProxboxPluginSettings.get_solo(),
                actor=request.user,
                request_id=request.id,
                operation="rotate",
                outcome="failed",
                family_keys=("all_registered",),
            )
            raise
        messages.success(
            request,
            "Plugin encryption key rotated atomically across "
            f"{result.ciphertext_values_rotated} encrypted value(s).",
        )
        return redirect("plugins:netbox_proxbox:settings")


class EncryptedSecretResetView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """Destructively clear selected ciphertext under a separate permission."""

    http_method_names = ("post",)

    def get_required_permission(self) -> str:
        """Require the dedicated destructive-recovery permission."""

        from netbox_proxbox.views.proxbox_access import (
            permission_reset_encrypted_secrets,
        )

        return permission_reset_encrypted_secrets()

    def post(self, request: HttpRequest) -> HttpResponse:
        """Validate explicit confirmation then clear through non-signaling updates."""

        from netbox_proxbox.forms.settings import EncryptedSecretResetForm
        from netbox_proxbox.services.encryption_recovery import (
            EncryptionRecoveryError,
            record_encryption_recovery_event,
            reset_encrypted_families,
        )

        form = EncryptedSecretResetForm(request.POST)
        if not form.is_valid():
            record_encryption_recovery_event(
                settings_obj=ProxboxPluginSettings.get_solo(),
                actor=request.user,
                request_id=request.id,
                operation="reset",
                outcome="rejected",
                family_keys=(),
            )
            messages.error(
                request,
                "Encrypted-secret reset was rejected; review the selection and "
                "exact confirmation phrase.",
            )
            return redirect("plugins:netbox_proxbox:settings")
        try:
            result = reset_encrypted_families(
                family_keys=list(form.cleaned_data["families"]),
                confirmation=str(form.cleaned_data["confirmation"]),
                audit_actor=request.user,
                audit_request_id=request.id,
            )
        except EncryptionRecoveryError as exc:
            record_encryption_recovery_event(
                settings_obj=ProxboxPluginSettings.get_solo(),
                actor=request.user,
                request_id=request.id,
                operation="reset",
                outcome="failed",
                family_keys=tuple(form.cleaned_data["families"]),
            )
            messages.error(request, str(exc))
            return redirect("plugins:netbox_proxbox:settings")
        except Exception:  # noqa: BLE001 - audit then preserve unexpected traceback
            record_encryption_recovery_event(
                settings_obj=ProxboxPluginSettings.get_solo(),
                actor=request.user,
                request_id=request.id,
                operation="reset",
                outcome="failed",
                family_keys=tuple(form.cleaned_data["families"]),
            )
            raise
        messages.warning(
            request,
            "Destructive recovery cleared selected encrypted data from "
            f"{result.rows_matched} row(s). Re-enter credentials before sync.",
        )
        return redirect("plugins:netbox_proxbox:settings")
