"""API serializers for Proxmox, NetBox, and FastAPI endpoint plugin models."""

from __future__ import annotations

import copy
import logging

from django.utils.translation import gettext as _

from netbox.api.fields import ChoiceField
from netbox.api.serializers import NetBoxModelSerializer, WritableNestedSerializer
from dcim.api.serializers_.sites import SiteSerializer
from ipam.api.serializers_.nested import NestedIPAddressSerializer
from tenancy.api.serializers_.tenants import TenantSerializer
from rest_framework import serializers
from users.models import Token

from netbox_proxbox.choices import (
    CredentialStorageBackendChoices,
    NetBoxTokenVersionChoices,
    ProxmoxAccessMethodChoices,
    ProxmoxEndpointEnvironmentChoices,
    ProxmoxModeChoices,
)
from netbox_proxbox.constants import OVERWRITE_FIELDS, SYNC_MODE_FIELDS
from netbox_proxbox.models import FastAPIEndpoint, NetBoxEndpoint, ProxmoxEndpoint
from netbox_proxbox.models.proxmox_endpoint import (
    SERVICE_MONITORING_INELIGIBLE_MESSAGE,
)
from netbox_proxbox.models.ssh_credential import (
    AUTH_METHOD_KEY,
    SSH_CRED_SOURCE_REUSE,
)


logger = logging.getLogger(__name__)


SERVICE_MONITORING_ELIGIBILITY_FIELDS = (
    "allow_writes",
    "access_methods",
    "ssh_credential_source",
    "domain",
    "ip_address",
    "username",
    "password",
    "ssh_username",
    "ssh_auth_method",
    "ssh_known_host_fingerprint",
    "rpc_enabled",
    "service_monitoring_enabled",
)


def _group_openbao_credential_rows(rows) -> dict[str, tuple[str, set[int]]]:
    """Group one joined metadata result by credential UUID."""
    grouped: dict[str, tuple[str, set[int]]] = {}
    for credential_uuid, credential_type, policy_group_id in rows:
        key = str(credential_uuid)
        _, policy_groups = grouped.setdefault(key, (credential_type, set()))
        if policy_group_id is not None:
            policy_groups.add(policy_group_id)
    return grouped


def _policy_authorized_credential_types(grouped, user) -> dict[str, str]:
    """Apply the companion policy's empty-group and membership semantics."""
    if getattr(user, "is_superuser", False):
        return {key: value[0] for key, value in grouped.items()}
    referenced_group_ids = {
        group_id for _, groups in grouped.values() for group_id in groups
    }
    permitted_group_ids = set(
        user.groups.filter(pk__in=referenced_group_ids).values_list("pk", flat=True)
    )
    return {
        key: credential_type
        for key, (credential_type, policy_groups) in grouped.items()
        if not policy_groups or policy_groups & permitted_group_ids
    }


class NestedTokenSerializer(WritableNestedSerializer):
    """Minimal token shape for nested NetBox endpoint writes."""

    display = serializers.SerializerMethodField()

    def get_display(self, instance: Token) -> str:
        """Use an identifier, never a core token's secret-dependent representation."""
        return f"Token {instance.pk}"

    class Meta:
        model = Token
        fields = ["id", "url", "display"]
        brief_fields = ("id", "url", "display")


class ProxmoxEndpointSerializer(NetBoxModelSerializer):
    """Proxmox endpoint including secrets as write-only fields."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:endpoints:proxmoxendpoint-detail",
    )
    password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        allow_null=True,
        style={"input_type": "password"},
    )
    token_value = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        style={"input_type": "password"},
    )
    ip_address = NestedIPAddressSerializer(required=False, allow_null=True)
    domain = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    mode = ChoiceField(choices=ProxmoxModeChoices)
    environment = ChoiceField(
        choices=ProxmoxEndpointEnvironmentChoices,
        required=False,
        allow_null=True,
        allow_blank=True,
    )
    site = SiteSerializer(nested=True, required=False, allow_null=True)
    tenant = TenantSerializer(nested=True, required=False, allow_null=True)
    allowed_tenants = TenantSerializer(nested=True, many=True, required=False)
    has_ssh_password = serializers.SerializerMethodField(read_only=True)
    has_ssh_private_key = serializers.SerializerMethodField(read_only=True)
    has_ssh_terminal_credentials = serializers.SerializerMethodField(read_only=True)
    service_monitoring_eligible = serializers.SerializerMethodField(read_only=True)
    service_monitoring_last_success_at = serializers.DateTimeField(read_only=True)
    service_monitoring_last_status = serializers.CharField(read_only=True)
    service_monitoring_last_error = serializers.CharField(read_only=True)
    packer_template_builds_backend_authorized = serializers.BooleanField(read_only=True)
    effective_rpc_enabled = serializers.SerializerMethodField(read_only=True)

    def _effective_storage_backend(self, obj: ProxmoxEndpoint) -> str:
        """Resolve an endpoint override before the request-local global default."""
        override = str(getattr(obj, "credential_storage_backend", "") or "")
        if override:
            return override

        backend = getattr(self, "_global_credential_storage_backend", None)
        if backend is None:
            from netbox_proxbox.integrations.openbao import (
                effective_credential_storage_backend,
            )

            backend = effective_credential_storage_backend()
            self._global_credential_storage_backend = backend
        return backend

    def _ssh_readiness(self, obj: ProxmoxEndpoint) -> tuple[bool, bool, bool]:
        """Return password, key, and terminal readiness without reading material."""
        states = getattr(self, "_ssh_readiness_states", None)
        if states is None:
            states = {}
            self._ssh_readiness_states = states
        key = getattr(obj, "pk", None) or id(obj)
        if key in states:
            return states[key]

        uses_openbao = (
            self._effective_storage_backend(obj)
            == CredentialStorageBackendChoices.OPENBAO
        )
        endpoint_password, ssh_password, ssh_private_key = self._ssh_secret_presence(
            obj, uses_openbao=uses_openbao
        )
        terminal_ready = self._ssh_terminal_ready(
            obj,
            endpoint_password=endpoint_password,
            ssh_password=ssh_password,
            ssh_private_key=ssh_private_key,
        )
        states[key] = (ssh_password, ssh_private_key, terminal_ready)
        return states[key]

    def _openbao_credential_metadata(self, current: ProxmoxEndpoint) -> dict[str, str]:
        """Return request-authorized credential types for this response."""
        if hasattr(self, "_openbao_credential_types"):
            return self._openbao_credential_types

        references = self._openbao_references(current)
        credential_types: dict[str, str] = {}
        self._openbao_credential_types = credential_types
        if not references:
            return credential_types

        context = getattr(
            self, "context", getattr(self, "kwargs", {}).get("context", {})
        )
        request = context.get("request")
        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return credential_types

        from django.apps import apps

        from netbox_proxbox.integrations.openbao import is_netbox_openbao_installed

        if not is_netbox_openbao_installed():
            return credential_types
        try:
            credential_model = apps.get_model("netbox_openbao", "Credential")
        except LookupError:
            return credential_types

        rows = (
            credential_model.objects.restrict(user, "reveal")
            .filter(uuid__in=references)
            .values_list("uuid", "credential_type", "policy__groups__pk")
        )
        credential_types.update(
            _policy_authorized_credential_types(
                _group_openbao_credential_rows(rows), user
            )
        )
        return credential_types

    def _openbao_references(self, current: ProxmoxEndpoint) -> set[str]:
        """Collect only response-relevant OpenBao SSH references."""
        parent_instance = getattr(getattr(self, "parent", None), "instance", None)
        own_instance = getattr(self, "instance", None)
        if own_instance is None and getattr(self, "args", ()):
            own_instance = self.args[0]
        instances = parent_instance if parent_instance is not None else own_instance
        if instances is None:
            instances = (current,)
        if isinstance(instances, ProxmoxEndpoint):
            instances = (instances,)
        references = set()
        for endpoint in instances:
            if (
                self._effective_storage_backend(endpoint)
                != CredentialStorageBackendChoices.OPENBAO
            ):
                continue
            references.update(
                str(reference)
                for reference in (
                    endpoint.openbao_password_credential_uuid,
                    endpoint.openbao_ssh_password_credential_uuid,
                    endpoint.openbao_ssh_keypair_credential_uuid,
                )
                if reference
            )
        return references

    def _ssh_secret_presence(
        self, obj: ProxmoxEndpoint, *, uses_openbao: bool
    ) -> tuple[bool, bool, bool]:
        """Read only authorized metadata or local ciphertext presence."""
        if uses_openbao:
            credential_types = self._openbao_credential_metadata(obj)
            return (
                credential_types.get(str(obj.openbao_password_credential_uuid))
                == "password",
                credential_types.get(str(obj.openbao_ssh_password_credential_uuid))
                == "ssh-password",
                credential_types.get(str(obj.openbao_ssh_keypair_credential_uuid))
                == "ssh-keypair",
            )
        return (
            bool(obj.password_enc),
            bool(obj.ssh_password_enc),
            bool(obj.ssh_private_key_enc),
        )

    @staticmethod
    def _ssh_terminal_ready(
        obj: ProxmoxEndpoint,
        *,
        endpoint_password: bool,
        ssh_password: bool,
        ssh_private_key: bool,
    ) -> bool:
        """Combine non-secret endpoint metadata with the selected secret state."""
        if obj.ssh_credential_source == SSH_CRED_SOURCE_REUSE:
            return bool(
                obj.ssh_host
                and obj.ssh_known_host_fingerprint
                and obj.effective_ssh_username
                and endpoint_password
            )
        selected_secret = (
            ssh_private_key if obj.ssh_auth_method == AUTH_METHOD_KEY else ssh_password
        )
        return bool(
            obj.ssh_host
            and obj.ssh_username
            and obj.ssh_known_host_fingerprint
            and selected_secret
        )

    def get_has_ssh_password(self, obj: ProxmoxEndpoint) -> bool:
        return self._ssh_readiness(obj)[0]

    def get_has_ssh_private_key(self, obj: ProxmoxEndpoint) -> bool:
        return self._ssh_readiness(obj)[1]

    def get_has_ssh_terminal_credentials(self, obj: ProxmoxEndpoint) -> bool:
        return self._ssh_readiness(obj)[2]

    def get_service_monitoring_eligible(self, obj: ProxmoxEndpoint) -> bool:
        """Return secret-free, response-local service-monitoring readiness."""
        return bool(
            obj.allow_writes
            and obj.access_methods == ProxmoxAccessMethodChoices.API_SSH
            and self._ssh_readiness(obj)[2]
            and self.get_effective_rpc_enabled(obj)
        )

    def _rpc_settings_model(self) -> type | None:
        """Cache the optional companion's guarded settings-model import."""
        if hasattr(self, "_rpc_plugin_settings_model"):
            return self._rpc_plugin_settings_model

        from netbox_proxbox.integrations.rpc import is_netbox_rpc_installed

        if not is_netbox_rpc_installed():
            settings_model = None
        else:
            try:
                from netbox_rpc.models import RpcPluginSettings
            except ImportError:
                settings_model = None
            else:
                settings_model = RpcPluginSettings
        self._rpc_plugin_settings_model = settings_model
        return settings_model

    def get_effective_rpc_enabled(self, obj: ProxmoxEndpoint) -> bool:
        """Resolved netbox-rpc enablement: installed, then endpoint override/global."""
        settings_model = self._rpc_settings_model()
        if settings_model is None:
            return False
        if obj.rpc_enabled is not None:
            return bool(obj.rpc_enabled)

        enabled = getattr(self, "_global_rpc_enabled", None)
        if enabled is None:
            try:
                enabled = bool(settings_model.get_solo().enabled)
            except Exception:  # noqa: BLE001 - preserve fail-closed readiness
                enabled = False
            self._global_rpc_enabled = enabled
        return enabled

    def validate_credential_storage_backend(self, value: str) -> str:
        """Reject a newly selected unavailable companion backend."""
        from django.core.exceptions import ValidationError

        from netbox_proxbox.integrations.openbao import (
            validate_storage_backend_selection,
        )

        current = str(getattr(self.instance, "credential_storage_backend", "") or "")
        try:
            validate_storage_backend_selection(value, current=current)
        except ValidationError as exc:
            raise serializers.ValidationError(exc.messages[0]) from exc
        return value

    class Meta:
        model = ProxmoxEndpoint
        fields = (
            "id",
            "url",
            "display",
            "name",
            "ip_address",
            "domain",
            "port",
            "mode",
            "environment",
            "version",
            "repoid",
            "iana_timezone",
            "node_device_name_template",
            "username",
            "password",
            "token_name",
            "token_value",
            "credential_storage_backend",
            "verify_ssl",
            "enabled",
            "timeout",
            "max_retries",
            "retry_backoff",
            "ssh_credential_source",
            "ssh_username",
            "ssh_port",
            "ssh_auth_method",
            "ssh_known_host_fingerprint",
            "has_ssh_password",
            "has_ssh_private_key",
            "has_ssh_terminal_credentials",
            "service_monitoring_enabled",
            "service_monitoring_interval_minutes",
            "service_monitoring_units",
            "service_monitoring_last_success_at",
            "service_monitoring_last_status",
            "service_monitoring_last_error",
            "service_monitoring_eligible",
            "default_role_qemu",
            "default_role_lxc",
            "enable_tenant_name_regex",
            "tenant_name_regex_rules",
            "enable_tenant_tag_assignment",
            "enable_tenant_from_cluster",
            "allow_writes",
            "allow_packer_template_builds",
            "packer_template_builds_backend_authorized",
            "access_methods",
            *SYNC_MODE_FIELDS,
            *OVERWRITE_FIELDS,
            "rpc_enabled",
            "effective_rpc_enabled",
            "site",
            "tenant",
            "allowed_tenants",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = (
            "id",
            "url",
            "display",
            "name",
            "domain",
            "port",
            "iana_timezone",
            "node_device_name_template",
        )
        extra_kwargs = {
            "password": {"write_only": True, "required": False, "allow_null": True},
            "token_value": {"write_only": True, "required": False, "allow_blank": True},
        }

    def get_display(self, obj: ProxmoxEndpoint) -> str:
        """Label for list APIs and APISelect (e.g. schedule sync): ``Name (IP)``."""
        name_part = (obj.name or "").strip() or _("Proxmox endpoint")
        ip_part = obj.ip
        if ip_part:
            return f"{name_part} ({ip_part})"
        domain_part = (obj.domain or "").strip()
        if domain_part:
            return f"{name_part} ({domain_part})"
        return name_part

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        """Require at least one of domain or IP address for reachability."""
        attrs = super().validate(attrs)
        domain = (
            attrs.get("domain", getattr(self.instance, "domain", "")) or ""
        ).strip()
        ip_address = attrs.get("ip_address", getattr(self.instance, "ip_address", None))

        if not domain and ip_address is None:
            raise serializers.ValidationError(
                {
                    "domain": "Provide either a domain or an IP address.",
                    "ip_address": "Provide either a domain or an IP address.",
                }
            )

        template = str(
            attrs.get(
                "node_device_name_template",
                getattr(self.instance, "node_device_name_template", ""),
            )
            or ""
        ).strip()
        from django.core.exceptions import ValidationError

        from netbox_proxbox.validators import (
            validate_endpoint_node_device_name_template,
        )

        try:
            validate_endpoint_node_device_name_template(
                template,
                endpoint_id=getattr(self.instance, "pk", None),
                endpoint_name=str(
                    attrs.get("name", getattr(self.instance, "name", ""))
                ),
            )
        except ValidationError as exc:
            raise serializers.ValidationError(
                {"node_device_name_template": exc}
            ) from exc

        self._validate_service_monitoring(attrs)
        return attrs

    def _validate_service_monitoring(self, attrs: dict[str, object]) -> None:
        """Apply the model's service-monitoring eligibility policy to API writes."""
        candidate = (
            copy.copy(self.instance) if self.instance is not None else ProxmoxEndpoint()
        )
        for field_name in SERVICE_MONITORING_ELIGIBILITY_FIELDS:
            if field_name in attrs:
                setattr(candidate, field_name, attrs[field_name])

        if not getattr(candidate, "service_monitoring_enabled", False):
            return
        if candidate.service_monitoring_eligible:
            return
        if (
            "service_monitoring_enabled" not in attrs
            and candidate._should_auto_disable_service_monitoring_for_rpc()
        ):
            attrs["service_monitoring_enabled"] = False
            logger.warning(
                "Auto-disabled service monitoring for Proxmox endpoint %s "
                "because netbox-rpc is not installed or is disabled for the "
                "endpoint.",
                getattr(candidate, "pk", None) or candidate,
            )
            return
        raise serializers.ValidationError(
            {"non_field_errors": [str(SERVICE_MONITORING_INELIGIBLE_MESSAGE)]}
        )

    def _apply_allowed_tenants(
        self,
        instance: ProxmoxEndpoint,
        allowed_tenants: list[object] | None,
    ) -> None:
        if allowed_tenants is not None:
            instance.allowed_tenants.set(allowed_tenants)

    def _apply_api_secrets(
        self,
        instance: ProxmoxEndpoint,
        *,
        password: object = serializers.empty,
        token_value: object = serializers.empty,
    ) -> None:
        self._attach_api_actor(instance)
        update_fields: list[str] = []
        if password is not serializers.empty:
            instance.password = password or ""
            update_fields.extend(["password_enc", "openbao_password_credential_uuid"])
        if token_value is not serializers.empty:
            instance.token_value = token_value or ""
            update_fields.extend(["token_value_enc", "openbao_token_credential_uuid"])
        if update_fields:
            instance.save(update_fields=list(dict.fromkeys(update_fields)))

    def _attach_api_actor(self, instance: ProxmoxEndpoint) -> None:
        request = self.context.get("request")
        user = getattr(request, "user", None) if request is not None else None
        if user is not None:
            instance._openbao_actor_user = user

    def create(self, validated_data: dict[str, object]) -> ProxmoxEndpoint:
        allowed_tenants = validated_data.pop("allowed_tenants", None)
        password = validated_data.pop("password", serializers.empty)
        token_value = validated_data.pop("token_value", serializers.empty)
        instance = super().create(validated_data)
        self._apply_allowed_tenants(instance, allowed_tenants)
        self._apply_api_secrets(
            instance,
            password=password,
            token_value=token_value,
        )
        return instance

    def update(
        self,
        instance: ProxmoxEndpoint,
        validated_data: dict[str, object],
    ) -> ProxmoxEndpoint:
        allowed_tenants = validated_data.pop("allowed_tenants", None)
        password = validated_data.pop("password", serializers.empty)
        token_value = validated_data.pop("token_value", serializers.empty)
        self._attach_api_actor(instance)
        instance = super().update(instance, validated_data)
        self._apply_allowed_tenants(instance, allowed_tenants)
        self._apply_api_secrets(
            instance,
            password=password,
            token_value=token_value,
        )
        return instance


class NetBoxEndpointSerializer(NetBoxModelSerializer):
    """Remote NetBox API endpoint with v1 token or v2 key/secret validation."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:endpoints:netboxendpoint-detail",
    )
    ip_address = NestedIPAddressSerializer(required=False, allow_null=True)
    token = NestedTokenSerializer(required=False, allow_null=True)

    class Meta:
        model = NetBoxEndpoint
        fields = (
            "id",
            "url",
            "display",
            "name",
            "ip_address",
            "domain",
            "port",
            "token_version",
            "token",
            "token_key",
            "token_secret",
            "verify_ssl",
            "enabled",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "domain", "port")
        extra_kwargs = {
            "token_secret": {
                "write_only": True,
                "required": False,
                "allow_blank": True,
            },
        }

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        """Enforce host target plus consistent v1 token vs v2 key/secret auth rules."""
        attrs = super().validate(attrs)

        domain = (
            attrs.get("domain", getattr(self.instance, "domain", "")) or ""
        ).strip()
        ip_address = attrs.get("ip_address", getattr(self.instance, "ip_address", None))
        if not domain and ip_address is None:
            raise serializers.ValidationError(
                {
                    "domain": "Provide either a domain or an IP address.",
                    "ip_address": "Provide either a domain or an IP address.",
                }
            )

        token = attrs.get("token", getattr(self.instance, "token", None))
        token_version = attrs.get(
            "token_version",
            getattr(self.instance, "token_version", NetBoxTokenVersionChoices.V1),
        )
        token_key = (
            attrs.get("token_key", getattr(self.instance, "token_key", "")) or ""
        ).strip()
        token_secret = (
            attrs.get("token_secret", getattr(self.instance, "token_secret", "")) or ""
        ).strip()

        if token is not None:
            selected_token_version = (
                NetBoxTokenVersionChoices.V2
                if getattr(token, "version", None) == 2
                else NetBoxTokenVersionChoices.V1
            )
            if selected_token_version == NetBoxTokenVersionChoices.V2:
                raise serializers.ValidationError(
                    {
                        "token": (
                            "Selected NetBox v2 token cannot be used by this endpoint "
                            "because its secret is not retrievable. Provide token_key and "
                            "token_secret fields instead."
                        )
                    }
                )

            token_plaintext = (getattr(token, "plaintext", "") or "").strip()
            if not token_plaintext:
                raise serializers.ValidationError(
                    {
                        "token": (
                            "Selected NetBox v1 token does not expose a usable plaintext "
                            "value. Create a new v1 token (or use v2 key/secret fields) "
                            "and reselect it."
                        )
                    }
                )

            attrs["token_version"] = selected_token_version
            attrs["token_key"] = ""
            attrs["token_secret"] = ""
        elif token_version == NetBoxTokenVersionChoices.V2:
            if not token_key:
                raise serializers.ValidationError(
                    {"token_key": "Token key is required when using a v2 token."}
                )
            if not token_secret:
                raise serializers.ValidationError(
                    {"token_secret": "Token secret is required when using a v2 token."}
                )
            attrs["token_key"] = token_key
            attrs["token_secret"] = token_secret
        else:
            attrs["token_version"] = NetBoxTokenVersionChoices.V1
            attrs["token_key"] = ""
            attrs["token_secret"] = ""

        return attrs


class BackendKeyAdoptionValidationMixin:
    """Translate the model's fail-closed key gate into DRF validation errors."""

    @staticmethod
    def _backend_key_error(exc: object) -> serializers.ValidationError:
        messages = getattr(exc, "messages", [str(exc)])
        detail = getattr(exc, "message_dict", {"token": messages})
        return serializers.ValidationError(detail)

    def create(self, validated_data: dict[str, object]) -> FastAPIEndpoint:
        from django.core.exceptions import ValidationError as DjangoValidationError

        try:
            return super().create(validated_data)  # type: ignore[misc,no-any-return]
        except DjangoValidationError as exc:
            raise self._backend_key_error(exc) from None

    def update(
        self,
        instance: FastAPIEndpoint,
        validated_data: dict[str, object],
    ) -> FastAPIEndpoint:
        from django.core.exceptions import ValidationError as DjangoValidationError

        try:
            return super().update(  # type: ignore[misc,no-any-return]
                instance, validated_data
            )
        except DjangoValidationError as exc:
            raise self._backend_key_error(exc) from None


class FastAPIEndpointSerializer(
    BackendKeyAdoptionValidationMixin, NetBoxModelSerializer
):
    """ProxBox backend HTTP/WebSocket endpoint."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:endpoints:fastapiendpoint-detail",
    )
    token = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        allow_null=True,
        style={"input_type": "password"},
    )
    ip_address = NestedIPAddressSerializer(required=False, allow_null=True)
    credential_assignment_ready = serializers.SerializerMethodField()
    credential_assignment_detail = serializers.SerializerMethodField()
    credential_assignment_lookup = serializers.SerializerMethodField()

    class Meta:
        model = FastAPIEndpoint
        fields = (
            "id",
            "url",
            "display",
            "name",
            "ip_address",
            "domain",
            "port",
            "use_https",
            "verify_ssl",
            "enabled",
            "token",
            "credential_assignment_ready",
            "credential_assignment_detail",
            "credential_assignment_lookup",
            "use_websocket",
            "websocket_domain",
            "websocket_port",
            "server_side_websocket",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "domain", "port")

    def _assignment_state(self, obj: FastAPIEndpoint) -> tuple[bool, str]:
        from netbox_proxbox.integrations.openbao_single import (
            credential_assignment_readiness,
            owner_uses_openbao_storage,
        )

        states = getattr(self, "_credential_assignment_states", None)
        if states is None:
            states = {}
            self._credential_assignment_states = states
        key = (obj._meta.label_lower, obj.pk)
        if key not in states:
            uses_openbao = getattr(self, "_credential_assignment_uses_openbao", None)
            if uses_openbao is None:
                uses_openbao = owner_uses_openbao_storage(obj)
                self._credential_assignment_uses_openbao = uses_openbao
            states[key] = credential_assignment_readiness(
                obj,
                _uses_openbao_storage=uses_openbao,
            )
        return states[key]

    def get_credential_assignment_ready(self, obj: FastAPIEndpoint) -> bool:
        return self._assignment_state(obj)[0]

    def get_credential_assignment_detail(self, obj: FastAPIEndpoint) -> str:
        return self._assignment_state(obj)[1]

    def get_credential_assignment_lookup(
        self, obj: FastAPIEndpoint
    ) -> dict[str, str] | None:
        from netbox_proxbox.integrations.openbao_single import (
            credential_assignment_lookup,
        )

        return credential_assignment_lookup(obj)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        """Normalize partial secrets and require a backend host."""
        if self.instance is not None and "token" in attrs:
            token = attrs.get("token")
            if token is None or not str(token).strip():
                attrs.pop("token", None)
        attrs = super().validate(attrs)
        domain = (
            attrs.get("domain", getattr(self.instance, "domain", "")) or ""
        ).strip()
        ip_address = attrs.get("ip_address", getattr(self.instance, "ip_address", None))

        if not domain and ip_address is None:
            raise serializers.ValidationError(
                {
                    "domain": "Provide either a domain or an IP address.",
                    "ip_address": "Provide either a domain or an IP address.",
                }
            )

        return attrs
