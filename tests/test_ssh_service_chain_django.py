"""Real-NetBox coverage for endpoint-owned SSH application-service chains."""

from __future__ import annotations

import json
import os
from ipaddress import ip_interface
from pathlib import Path
import sys
from uuid import uuid4
from types import SimpleNamespace

from cryptography.fernet import Fernet
import pytest

from tests.netbox_test_paths import netbox_source_roots


REPO_ROOT = Path(__file__).resolve().parents[1]
for candidate in (REPO_ROOT, *netbox_source_roots(REPO_ROOT)):
    candidate_string = str(candidate)
    if candidate.exists() and candidate_string not in sys.path:
        sys.path.insert(0, candidate_string)

_REQUIRE_DJANGO = os.environ.get("NETBOX_PROXBOX_REQUIRE_DJANGO", "").lower() in (
    "1",
    "true",
    "yes",
)

try:
    import django
except ModuleNotFoundError:
    if _REQUIRE_DJANGO:
        raise
    pytest.skip("Django/NetBox is unavailable.", allow_module_level=True)

if not hasattr(django, "__path__"):
    pytest.skip("The mocked suite does not provide Django.", allow_module_level=True)

os.environ.setdefault("NETBOX_CONFIGURATION", "tests.netbox_test_configuration")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netbox.settings")

try:
    django.setup()
except Exception as exc:  # pragma: no cover - external harness availability
    if _REQUIRE_DJANGO:
        raise
    pytest.skip(
        f"NetBox test environment is unavailable: {exc}", allow_module_level=True
    )

from django.core.exceptions import ValidationError  # noqa: E402
from django.contrib.auth.models import Permission  # noqa: E402
from django.test import TestCase  # noqa: E402
from django.urls import reverse  # noqa: E402
from ipam.models import IPAddress  # noqa: E402
from utilities.exceptions import AbortRequest  # noqa: E402

from netbox_proxbox.api.ssh_credentials import (  # noqa: E402
    ProxmoxEndpointSSHCredentialSecretsAPIView,
)
from netbox_proxbox.choices import (  # noqa: E402
    CredentialStorageBackendChoices,
    ProxmoxAccessMethodChoices,
)
from netbox_proxbox.forms.proxmox import (  # noqa: E402
    ProxmoxEndpointForm,
    ProxmoxEndpointSSHSettingsForm,
)
from netbox_proxbox.models import (  # noqa: E402
    ProxmoxEndpoint,
    ProxmoxEndpointService,
    ProxboxPluginSettings,
    ServiceSSHCredential,
)
from netbox_proxbox.models.ssh_credential import (  # noqa: E402
    AUTH_METHOD_PASSWORD,
    SSH_CRED_SOURCE_DEDICATED,
    SSH_CRED_SOURCE_REUSE,
    SSH_CRED_SOURCE_SERVICE,
)
from tests.django_support import (  # noqa: E402
    grant_user_permissions,
    make_user,
    raw_update_fields,
)


FINGERPRINT = "SHA256:" + "A" * 43


class SSHServiceChainTest(TestCase):
    def setUp(self) -> None:
        self.key = Fernet.generate_key().decode()
        settings = ProxboxPluginSettings.get_solo()
        settings.credential_storage_backend = (
            CredentialStorageBackendChoices.LEGACY_ENCRYPTED
        )
        settings.encryption_key = self.key
        settings.save(update_fields=("credential_storage_backend", "encryption_key"))
        self.actor = make_user("ssh-service-admin", is_superuser=True)
        address = ".".join(("192", "0", "2", "177"))
        self.ip_address = IPAddress.objects.create(address=f"{address}/32")
        self.endpoint = ProxmoxEndpoint.objects.create(
            name="service-chain",
            domain="service-chain.example.invalid",
            ip_address=self.ip_address,
            username="root@pam",
            enabled=False,
            access_methods=ProxmoxAccessMethodChoices.API_SSH,
        )

    def _form(self, **overrides: object) -> ProxmoxEndpointSSHSettingsForm:
        data: dict[str, object] = {
            "ip_address": self.ip_address.pk,
            "ssh_credential_source": SSH_CRED_SOURCE_SERVICE,
            "ssh_service": "",
            "ssh_storage": CredentialStorageBackendChoices.LEGACY_ENCRYPTED,
            "ssh_username": "root",
            "ssh_port": 22,
            "ssh_auth_method": AUTH_METHOD_PASSWORD,
            "ssh_known_host_fingerprint": FINGERPRINT,
            "ssh_password": "service-password",
            "ssh_private_key": "",
        }
        data.update(overrides)
        return ProxmoxEndpointSSHSettingsForm(
            instance=self.endpoint,
            data=data,
            request_user=self.actor,
        )

    def _grant(self, actor, *codenames: str) -> None:
        grant_user_permissions(
            actor,
            (Permission.objects.get(codename=codename) for codename in codenames),
        )

    def _main_form_data(self) -> dict[str, object]:
        data = dict(self._form().data)
        data.update(
            {
                "name": self.endpoint.name,
                "node_device_name_template": "",
                "domain": self.endpoint.domain,
                "port": self.endpoint.port,
                "username": self.endpoint.username,
                "password": "api-password",
                "token_name": "",
                "token_value": "",
                "credential_storage_backend": "legacy_encrypted",
                "verify_ssl": "on",
                "enabled": "",
                "allow_writes": "",
                "allow_packer_template_builds": "",
                "access_methods": ProxmoxAccessMethodChoices.API_SSH,
                "service_monitoring_enabled": "",
                "service_monitoring_interval_minutes": 5,
                "service_monitoring_units": [],
                "environment": "",
                "site": "",
                "tenant": "",
                "allowed_tenants": [],
                "tags": [],
            }
        )
        return data

    def _local_delete_graph(self, suffix: str):
        endpoint = ProxmoxEndpoint.objects.create(
            name=f"delete-{suffix}",
            domain=f"delete-{suffix}.example.invalid",
            username="root@pam",
            enabled=False,
        )
        service = ProxmoxEndpointService.objects.create(
            endpoint=endpoint,
            name="ssh",
            protocol="tcp",
            ports=[22],
        )
        owner = ServiceSSHCredential.objects.create(
            service=service,
            username="root",
            auth_method=AUTH_METHOD_PASSWORD,
        )
        return endpoint, service, owner

    @staticmethod
    def _delete_url(target: object, *, bulk: bool) -> str:
        model_name = target._meta.model_name
        action = f"{model_name}_bulk_delete" if bulk else f"{model_name}_delete"
        kwargs = {} if bulk else {"pk": target.pk}
        return reverse(f"plugins:netbox_proxbox:{action}", kwargs=kwargs)

    def test_unconfigured_ssh_form_defaults_to_service_source(self) -> None:
        form = ProxmoxEndpointSSHSettingsForm(
            instance=self.endpoint,
            request_user=self.actor,
        )

        self.assertEqual(form.initial["ssh_credential_source"], SSH_CRED_SOURCE_SERVICE)

    def test_provider_boundary_detects_submitted_and_inherited_backend_changes(
        self,
    ) -> None:
        from netbox_proxbox.integrations.openbao_service import (
            _request_requires_provider,
        )

        self.endpoint.credential_storage_backend = "legacy_encrypted"

        self.assertTrue(
            _request_requires_provider(
                self.endpoint, {"credential_storage_backend": "openbao"}
            )
        )
        self.assertTrue(
            _request_requires_provider(
                self.endpoint, {"credential_storage_backend": ""}
            )
        )

    def test_form_creates_service_ip_binding_and_legacy_credential(self) -> None:
        form = self._form()
        self.assertTrue(form.is_valid(), form.errors.as_data())

        endpoint = form.save()

        endpoint.refresh_from_db()
        service = endpoint.ssh_service
        self.assertIsNotNone(service)
        self.assertEqual(service.name, "ssh")
        self.assertEqual(service.protocol, "tcp")
        self.assertEqual(service.ports, [22])
        self.assertEqual(list(service.ipaddresses.all()), [self.ip_address])
        self.assertEqual(endpoint.ssh_port, 22)
        self.assertEqual(
            service.ssh_credential.get_password(key=self.key), "service-password"
        )

    def test_bulk_destroy_result_check_supports_every_netbox_contract(self) -> None:
        from netbox_proxbox.api.views import (
            _BulkDestroyIncomplete,
            _raise_if_bulk_incomplete,
        )

        self.assertIsNone(_raise_if_bulk_incomplete(None))
        self.assertEqual(_raise_if_bulk_incomplete(([], 2, None)), ([], 2, None))
        failed = ([{"id": 1, "errors": {}}], 1, 409)
        with self.assertRaises(_BulkDestroyIncomplete) as raised:
            _raise_if_bulk_incomplete(failed)
        self.assertEqual(raised.exception.result, failed)

    def test_rest_bulk_delete_removes_service_and_endpoint(self) -> None:
        form = self._form()
        self.assertTrue(form.is_valid(), form.errors.as_data())
        endpoint = form.save()
        service = endpoint.ssh_service
        credential_pk = service.ssh_credential.pk
        self.client.force_login(self.actor)

        response = self.client.delete(
            reverse("plugins-api:netbox_proxbox-api:proxmoxendpointservice-list"),
            data=json.dumps([{"id": service.pk}]),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 204, response.content)
        self.assertFalse(ProxmoxEndpointService.objects.filter(pk=service.pk).exists())
        self.assertFalse(ServiceSSHCredential.objects.filter(pk=credential_pk).exists())

        response = self.client.delete(
            reverse("plugins-api:netbox_proxbox-api:endpoints:proxmoxendpoint-list"),
            data=json.dumps([{"id": endpoint.pk}]),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 204, response.content)
        self.assertFalse(ProxmoxEndpoint.objects.filter(pk=endpoint.pk).exists())

    def test_legacy_setters_create_rotate_and_clear_with_guards_installed(self) -> None:
        service = ProxmoxEndpointService.objects.create(
            endpoint=self.endpoint, name="guarded-ssh", protocol="tcp", ports=[22]
        )
        credential = ServiceSSHCredential(
            service=service,
            username="root",
            auth_method=AUTH_METHOD_PASSWORD,
        )
        credential.set_password("created", key=self.key)
        credential.save()
        self.assertEqual(credential.get_password(key=self.key), "created")

        credential.set_password("rotated", key=self.key)
        credential.save()
        credential.refresh_from_db()
        self.assertEqual(credential.get_password(key=self.key), "rotated")

        credential.clear_password()
        credential.save()
        credential.refresh_from_db()
        self.assertEqual(credential.password_enc, "")

        credential.set_private_key("created-key", key=self.key)
        credential.save()
        credential.set_private_key("rotated-key", key=self.key)
        credential.save()
        credential.refresh_from_db()
        self.assertEqual(credential.get_private_key(key=self.key), "rotated-key")
        credential.clear_private_key()
        credential.save()
        credential.refresh_from_db()
        self.assertEqual(credential.private_key_enc, "")

    def test_form_reuses_matching_service(self) -> None:
        service = ProxmoxEndpointService.objects.create(
            endpoint=self.endpoint, name="management-ssh", protocol="tcp", ports=[22]
        )
        service.ipaddresses.add(self.ip_address)

        form = self._form()
        self.assertTrue(form.is_valid(), form.errors.as_data())
        form.save()

        self.endpoint.refresh_from_db()
        self.assertEqual(self.endpoint.ssh_service, service)
        self.assertEqual(
            ProxmoxEndpointService.objects.filter(endpoint=self.endpoint).count(), 1
        )

    def test_hidden_name_collision_uses_nondisclosing_fallback_name(self) -> None:
        ProxmoxEndpointService.objects.create(
            endpoint=self.endpoint, name="ssh", protocol="tcp", ports=[2222]
        )
        actor = make_user("ssh-service-hidden-collision")
        self._grant(
            actor,
            "add_proxmoxendpointservice",
            "view_servicesshcredential",
            "add_servicesshcredential",
            "change_servicesshcredential",
        )
        allowed = {
            "netbox_proxbox.add_proxmoxendpointservice",
            "netbox_proxbox.view_servicesshcredential",
            "netbox_proxbox.add_servicesshcredential",
            "netbox_proxbox.change_servicesshcredential",
        }
        actor.has_perm = lambda permission: permission in allowed
        form = ProxmoxEndpointSSHSettingsForm(
            instance=self.endpoint,
            data=self._form().data,
            request_user=actor,
        )

        self.assertTrue(form.is_valid(), form.errors.as_data())
        form.save()
        self.endpoint.refresh_from_db()
        self.assertEqual(self.endpoint.ssh_service.name, "ssh-22")

    def test_selected_service_is_bound_to_the_endpoint_ip(self) -> None:
        service = ProxmoxEndpointService.objects.create(
            endpoint=self.endpoint, name="operator-ssh", protocol="tcp", ports=[2222]
        )

        form = self._form(ssh_service=service.pk, ssh_port=22)
        self.assertTrue(form.is_valid(), form.errors.as_data())
        form.save()

        self.endpoint.refresh_from_db()
        self.assertEqual(self.endpoint.ssh_service, service)
        self.assertEqual(self.endpoint.ssh_port, 2222)
        self.assertTrue(service.ipaddresses.filter(pk=self.ip_address.pk).exists())

    def test_selected_service_without_credential_requires_new_material(self) -> None:
        service = ProxmoxEndpointService.objects.create(
            endpoint=self.endpoint, name="empty-ssh", protocol="tcp", ports=[22]
        )

        form = self._form(ssh_service=service.pk, ssh_password="")

        self.assertFalse(form.is_valid())
        self.assertIn("ssh_password", form.errors)
        self.assertFalse(ServiceSSHCredential.objects.filter(service=service).exists())

    def test_save_rejects_backend_and_reference_drift_after_validation(self) -> None:
        initial = self._form()
        self.assertTrue(initial.is_valid(), initial.errors.as_data())
        endpoint = initial.save()
        owner = endpoint.ssh_service.ssh_credential
        update = self._form(
            ssh_service=endpoint.ssh_service_id,
            ssh_password="",
        )
        self.assertTrue(update.is_valid(), update.errors.as_data())
        concurrent_reference = uuid4()
        raw_update_fields(
            ServiceSSHCredential,
            owner.pk,
            storage_backend=CredentialStorageBackendChoices.OPENBAO,
            password_enc="",
            openbao_password_credential_uuid=concurrent_reference,
        )

        with self.assertRaises(AbortRequest) as raised:
            update.save()

        self.assertIn("changed after validation", raised.exception.message)
        owner.refresh_from_db()
        self.assertEqual(owner.storage_backend, CredentialStorageBackendChoices.OPENBAO)
        self.assertEqual(owner.openbao_password_credential_uuid, concurrent_reference)

    def test_creation_requires_application_service_add_permission(self) -> None:
        actor = make_user("ssh-service-no-add")
        form = ProxmoxEndpointSSHSettingsForm(
            instance=self.endpoint,
            data=self._form().data,
            request_user=actor,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("ssh_service", form.errors)
        self.assertIn("permission", str(form.errors["ssh_service"]).lower())

    def test_storing_a_credential_requires_credential_permission(self) -> None:
        actor = make_user("ssh-service-no-credential")
        self._grant(actor, "add_proxmoxendpointservice")
        form = ProxmoxEndpointSSHSettingsForm(
            instance=self.endpoint,
            data=self._form().data,
            request_user=actor,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("ssh_username", form.errors)
        self.assertIn("permission", str(form.errors["ssh_username"]).lower())

    def test_service_source_connects_to_the_bound_ip_not_the_domain(self) -> None:
        self.endpoint.ssh_credential_source = SSH_CRED_SOURCE_SERVICE
        expected = str(ip_interface(str(self.ip_address.address)).ip)
        self.assertEqual(self.endpoint.ssh_host, expected)
        self.endpoint.ssh_credential_source = "dedicated"
        self.assertEqual(self.endpoint.ssh_host, "service-chain.example.invalid")

    def test_secret_release_requires_service_credential_view_access(self) -> None:
        from netbox_proxbox.api.ssh_credentials import _service_credential_visible

        service = ProxmoxEndpointService.objects.create(
            endpoint=self.endpoint, name="ssh", protocol="tcp", ports=[22]
        )
        ServiceSSHCredential.objects.create(
            service=service, username="root", auth_method=AUTH_METHOD_PASSWORD
        )
        self.endpoint.ssh_service = service
        self.endpoint.ssh_credential_source = SSH_CRED_SOURCE_SERVICE
        viewer = make_user("credential-viewer")
        self._grant(viewer, "view_servicesshcredential")
        outsider = make_user("credential-outsider")

        self.assertTrue(_service_credential_visible(self.endpoint, viewer))
        self.assertFalse(_service_credential_visible(self.endpoint, outsider))

    def test_endpoint_refuses_another_endpoints_ssh_service(self) -> None:
        other = ProxmoxEndpoint.objects.create(
            name="service-owner",
            domain="service-owner.example.invalid",
            username="root@pam",
            enabled=False,
        )
        foreign = ProxmoxEndpointService.objects.create(
            endpoint=other, name="ssh", protocol="tcp", ports=[22]
        )
        self.endpoint.ssh_service = foreign
        self.endpoint.ssh_credential_source = "dedicated"

        with self.assertRaises(ValidationError) as caught:
            self.endpoint.full_clean()
        self.assertIn("ssh_service", caught.exception.message_dict)

    def test_service_name_is_unique_per_endpoint_and_supports_crud(self) -> None:
        service = ProxmoxEndpointService.objects.create(
            endpoint=self.endpoint, name="ssh", protocol="tcp", ports=[22]
        )
        duplicate = ProxmoxEndpointService(
            endpoint=self.endpoint, name="ssh", protocol="tcp", ports=[2222]
        )

        with self.assertRaises(ValidationError):
            duplicate.full_clean()

        service.name = "remote-login"
        service.save()
        self.assertEqual(
            ProxmoxEndpointService.objects.get(pk=service.pk).name, "remote-login"
        )
        service.delete()
        self.assertFalse(ProxmoxEndpointService.objects.filter(pk=service.pk).exists())

    def test_facade_selects_dedicated_reused_and_service_credentials(self) -> None:
        self.endpoint.ssh_credential_source = SSH_CRED_SOURCE_DEDICATED
        self.endpoint.ssh_username = "dedicated-user"
        self.endpoint.ssh_auth_method = AUTH_METHOD_PASSWORD
        self.endpoint.set_ssh_password("dedicated-password", key=self.key)
        self.assertEqual(self.endpoint.effective_ssh_username, "dedicated-user")
        self.assertEqual(
            self.endpoint.get_ssh_password(key=self.key), "dedicated-password"
        )

        self.endpoint.ssh_credential_source = SSH_CRED_SOURCE_REUSE
        self.endpoint.username = "api-user@pam"
        self.endpoint.password = "api-password"
        self.assertEqual(self.endpoint.effective_ssh_username, "api-user")

        service = ProxmoxEndpointService.objects.create(
            endpoint=self.endpoint, name="ssh", protocol="tcp", ports=[22]
        )
        service.ipaddresses.add(self.ip_address)
        credential = ServiceSSHCredential.objects.create(
            service=service,
            username="service-user",
            auth_method=AUTH_METHOD_PASSWORD,
        )
        credential.set_password("service-password", key=self.key)
        credential.save()
        self.endpoint.ssh_service = service
        self.endpoint.ssh_credential_source = SSH_CRED_SOURCE_SERVICE
        self.assertEqual(self.endpoint.effective_ssh_username, "service-user")
        self.assertEqual(
            self.endpoint.get_ssh_password(key=self.key), "service-password"
        )

    def test_selected_storage_backend_never_falls_back(self) -> None:
        service = ProxmoxEndpointService.objects.create(
            endpoint=self.endpoint, name="ssh", protocol="tcp", ports=[22]
        )
        credential = ServiceSSHCredential.objects.create(
            service=service,
            username="root",
            auth_method=AUTH_METHOD_PASSWORD,
            storage_backend=CredentialStorageBackendChoices.LEGACY_ENCRYPTED,
            openbao_password_credential_uuid=None,
        )
        credential.openbao_password_credential_uuid = uuid4()
        self.assertFalse(credential.has_password)
        self.assertEqual(credential.get_password(key=self.key), "")

        credential.password_enc = Fernet(self.key.encode()).encrypt(b"local").decode()
        credential.openbao_password_credential_uuid = None
        credential.storage_backend = CredentialStorageBackendChoices.OPENBAO
        self.assertFalse(credential.has_password)
        with self.assertRaises(ValidationError):
            credential.get_password(key=self.key)

    def test_service_storage_does_not_inherit_endpoint_openbao_backend(self) -> None:
        service = ProxmoxEndpointService.objects.create(
            endpoint=self.endpoint, name="ssh", protocol="tcp", ports=[22]
        )
        service.ipaddresses.add(self.ip_address)
        credential = ServiceSSHCredential.objects.create(
            service=service,
            username="root",
            auth_method=AUTH_METHOD_PASSWORD,
        )
        credential.set_password("local-service-password", key=self.key)
        credential.save()
        self.endpoint.ssh_service = service
        self.endpoint.ssh_credential_source = SSH_CRED_SOURCE_SERVICE
        self.endpoint.credential_storage_backend = (
            CredentialStorageBackendChoices.OPENBAO
        )

        response = (
            ProxmoxEndpointSSHCredentialSecretsAPIView._dedicated_credentials_response(
                self.endpoint
            )
        )

        self.assertEqual(response.data["password"], "local-service-password")

    def test_secrets_payload_shape_is_unchanged_for_service_source(self) -> None:
        form = self._form()
        self.assertTrue(form.is_valid(), form.errors.as_data())
        endpoint = form.save()

        response = (
            ProxmoxEndpointSSHCredentialSecretsAPIView._dedicated_credentials_response(
                endpoint
            )
        )

        self.assertEqual(
            set(response.data),
            {
                "endpoint_id",
                "host",
                "username",
                "port",
                "auth_method",
                "known_host_fingerprint",
                "has_password",
                "has_private_key",
                "password",
                "private_key",
            },
        )
        self.assertEqual(response.data["password"], "service-password")
        self.assertEqual(response.data["username"], "root")

    def test_api_only_endpoint_ignores_service_chain_input(self) -> None:
        data = {
            "name": "api-only-service-source",
            "domain": "api-only.example.invalid",
            "port": "8006",
            "username": "root@pam",
            "password": "api-password",
            "token_name": "",
            "token_value": "",
            "credential_storage_backend": "legacy_encrypted",
            "verify_ssl": "",
            "enabled": "",
            "allow_writes": "",
            "access_methods": ProxmoxAccessMethodChoices.API,
            "service_monitoring_interval_minutes": "5",
            "environment": "",
            "ssh_credential_source": SSH_CRED_SOURCE_SERVICE,
            "ssh_service": "999999",
            "ssh_storage": "legacy_encrypted",
            "ssh_username": "ignored",
            "ssh_port": "0",
            "ssh_auth_method": AUTH_METHOD_PASSWORD,
            "ssh_known_host_fingerprint": "invalid",
            "ssh_password": "ignored-secret",
        }
        form = ProxmoxEndpointForm(data=data, request_user=self.actor)

        self.assertTrue(form.is_valid(), form.errors.as_data())
        endpoint = form.save()
        self.assertIsNone(endpoint.ssh_service)
        self.assertEqual(endpoint.ssh_credential_source, SSH_CRED_SOURCE_DEDICATED)

    def test_ssh_tab_client_post_resolves_current_request_actor(self) -> None:
        self.client.force_login(self.actor)
        response = self.client.post(
            reverse(
                "plugins:netbox_proxbox:proxmoxendpoint_ssh_settings",
                args=[self.endpoint.pk],
            ),
            self._form().data,
        )

        form_errors = response.context["form"].errors if response.context else None
        self.assertEqual(response.status_code, 302, form_errors)
        self.endpoint.refresh_from_db()
        self.assertIsNotNone(self.endpoint.ssh_service_id)

    def test_main_edit_client_post_resolves_current_request_actor(self) -> None:
        self.client.force_login(self.actor)
        response = self.client.post(
            reverse(
                "plugins:netbox_proxbox:proxmoxendpoint_edit",
                args=[self.endpoint.pk],
            ),
            self._main_form_data(),
        )

        form_errors = response.context["form"].errors if response.context else None
        self.assertEqual(response.status_code, 302, form_errors)
        self.endpoint.refresh_from_db()
        self.assertIsNotNone(self.endpoint.ssh_service_id)

    def test_service_ui_mutations_require_parent_endpoint_change_access(self) -> None:
        service = ProxmoxEndpointService.objects.create(
            endpoint=self.endpoint, name="parent-auth", protocol="tcp", ports=[22]
        )
        actor = make_user("service-parent-denied")
        self._grant(
            actor,
            "view_proxmoxendpointservice",
            "change_proxmoxendpointservice",
            "delete_proxmoxendpointservice",
        )
        self.client.force_login(actor)

        edit = self.client.get(
            reverse(
                "plugins:netbox_proxbox:proxmoxendpointservice_edit",
                args=[service.pk],
            )
        )
        delete = self.client.post(
            reverse(
                "plugins:netbox_proxbox:proxmoxendpointservice_delete",
                args=[service.pk],
            ),
            {"confirm": True},
        )
        bulk = self.client.post(
            reverse("plugins:netbox_proxbox:proxmoxendpointservice_bulk_delete"),
            {"pk": [service.pk], "confirm": True},
        )

        self.assertEqual(edit.status_code, 403)
        self.assertEqual(delete.status_code, 403)
        self.assertEqual(bulk.status_code, 403)
        self.assertTrue(ProxmoxEndpointService.objects.filter(pk=service.pk).exists())

    def test_credential_ui_deletion_requires_parent_endpoint_change_access(
        self,
    ) -> None:
        _endpoint, _service, owner = self._local_delete_graph("cred-parent")
        actor = make_user("credential-parent-denied")
        self._grant(actor, "view_servicesshcredential", "delete_servicesshcredential")
        self.client.force_login(actor)

        delete = self.client.post(
            self._delete_url(owner, bulk=False), {"confirm": True, "_confirm": True}
        )
        bulk = self.client.post(
            self._delete_url(owner, bulk=True),
            {"pk": [owner.pk], "confirm": True, "_confirm": True},
        )

        self.assertIn(delete.status_code, (403, 404))
        self.assertIn(bulk.status_code, (302, 403))
        self.assertTrue(ServiceSSHCredential.objects.filter(pk=owner.pk).exists())

    def test_partial_service_serializer_authorizes_the_stored_parent(self) -> None:
        from netbox_proxbox.api.serializers.proxmox_endpoint_service import (
            ProxmoxEndpointServiceSerializer,
        )

        service = ProxmoxEndpointService.objects.create(
            endpoint=self.endpoint, name="partial-auth", protocol="tcp", ports=[22]
        )
        actor = make_user("service-partial-parent-denied")
        serializer = ProxmoxEndpointServiceSerializer(
            service,
            data={"ports": [2222]},
            partial=True,
            context={"request": SimpleNamespace(user=actor)},
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("endpoint", serializer.errors)

    def test_delete_preview_cancel_and_invalid_form_preserve_each_graph(self) -> None:
        self.client.force_login(self.actor)
        for target_kind in ("endpoint", "service", "credential"):
            for bulk in (False, True):
                with self.subTest(target_kind=target_kind, bulk=bulk):
                    endpoint, service, owner = self._local_delete_graph(
                        f"nonexecute-{target_kind}-{bulk}"
                    )
                    target = {
                        "endpoint": endpoint,
                        "service": service,
                        "credential": owner,
                    }[target_kind]
                    url = self._delete_url(target, bulk=bulk)
                    if bulk:
                        responses = (
                            self.client.post(url, {"pk": [target.pk]}),
                            self.client.post(
                                url, {"pk": [target.pk], "cancel": "Cancel"}
                            ),
                            self.client.post(
                                url,
                                {
                                    "_confirm": "on",
                                    "pk": [target.pk],
                                    "confirm": "on",
                                    "changelog_message": "x" * 201,
                                },
                            ),
                        )
                    else:
                        responses = (
                            self.client.get(url),
                            self.client.post(url, {"cancel": "Cancel"}),
                            self.client.post(
                                url,
                                {
                                    "confirm": "on",
                                    "changelog_message": "x" * 201,
                                },
                            ),
                        )
                    self.assertTrue(
                        all(response.status_code < 500 for response in responses)
                    )
                    self.assertTrue(type(target).objects.filter(pk=target.pk).exists())
                    self.assertTrue(
                        ServiceSSHCredential.objects.filter(pk=owner.pk).exists()
                    )

    def test_refused_delete_discards_queued_events(self) -> None:
        from unittest import mock

        from django.db.models import ProtectedError, RestrictedError
        from django.db.models.signals import pre_delete
        from utilities.exceptions import AbortRequest

        refusals = {
            "protected": lambda instance: ProtectedError("test refusal", {instance}),
            "restricted": lambda instance: RestrictedError("test refusal", {instance}),
            "aborted": lambda instance: AbortRequest("test refusal"),
        }
        self.client.force_login(self.actor)
        for refusal, build_refusal in refusals.items():
            for target_kind in ("endpoint", "service", "credential"):
                for bulk in (False, True):
                    with self.subTest(
                        refusal=refusal, target_kind=target_kind, bulk=bulk
                    ):
                        endpoint, service, owner = self._local_delete_graph(
                            f"events-{refusal}-{target_kind}-{bulk}"
                        )
                        target = {
                            "endpoint": endpoint,
                            "service": service,
                            "credential": owner,
                        }[target_kind]
                        dispatch_uid = (
                            f"test_chain_events_{refusal}_{target_kind}_{bulk}"
                        )
                        refused: list[int] = []

                        def refuse_delete(sender, instance, **kwargs):
                            del sender, kwargs
                            if instance.pk == target.pk:
                                refused.append(instance.pk)
                                raise build_refusal(instance)

                        pre_delete.connect(
                            refuse_delete,
                            sender=target.__class__,
                            weak=False,
                            dispatch_uid=dispatch_uid,
                        )
                        data = {"confirm": "on"}
                        if bulk:
                            data.update({"_confirm": "on", "pk": [target.pk]})
                        try:
                            with mock.patch(
                                "netbox.context_managers.flush_events"
                            ) as flush:
                                response = self.client.post(
                                    self._delete_url(target, bulk=bulk), data
                                )
                        finally:
                            pre_delete.disconnect(
                                sender=target.__class__, dispatch_uid=dispatch_uid
                            )
                        self.assertEqual(refused, [target.pk])
                        self.assertEqual(response.status_code, 302)
                        self.assertTrue(
                            type(target).objects.filter(pk=target.pk).exists()
                        )
                        flush.assert_not_called()

    def test_confirmed_delete_still_flushes_its_deletion_event(self) -> None:
        from unittest import mock

        self.client.force_login(self.actor)
        for bulk in (False, True):
            with self.subTest(bulk=bulk):
                endpoint, _service, _owner = self._local_delete_graph(
                    f"events-success-{bulk}"
                )
                data = {"confirm": "on"}
                if bulk:
                    data.update({"_confirm": "on", "pk": [endpoint.pk]})
                with mock.patch("netbox.context_managers.flush_events") as flush:
                    response = self.client.post(
                        self._delete_url(endpoint, bulk=bulk), data
                    )
                self.assertLess(response.status_code, 400)
                self.assertFalse(
                    ProxmoxEndpoint.objects.filter(pk=endpoint.pk).exists()
                )
                events = [
                    event for call in flush.call_args_list for event in call.args[0]
                ]
                self.assertTrue(
                    any(
                        event["event_type"] == "object_deleted"
                        and event["object_id"] == endpoint.pk
                        for event in events
                    ),
                    events,
                )

    def test_protected_delete_rolls_back_each_confirmed_path(self) -> None:
        from django.db.models import ProtectedError
        from django.db.models.signals import pre_delete

        self.client.force_login(self.actor)
        for target_kind in ("endpoint", "service", "credential"):
            for bulk in (False, True):
                with self.subTest(target_kind=target_kind, bulk=bulk):
                    endpoint, service, owner = self._local_delete_graph(
                        f"protected-{target_kind}-{bulk}"
                    )
                    target = {
                        "endpoint": endpoint,
                        "service": service,
                        "credential": owner,
                    }[target_kind]
                    dispatch_uid = f"test_chain_protected_{target_kind}_{bulk}"

                    def refuse_delete(sender, instance, **kwargs):
                        del sender, kwargs
                        if instance.pk == target.pk:
                            raise ProtectedError("test protected delete", {instance})

                    pre_delete.connect(
                        refuse_delete,
                        sender=target.__class__,
                        weak=False,
                        dispatch_uid=dispatch_uid,
                    )
                    try:
                        data = {"confirm": "on"}
                        if bulk:
                            data.update({"_confirm": "on", "pk": [target.pk]})
                        response = self.client.post(
                            self._delete_url(target, bulk=bulk), data
                        )
                    finally:
                        pre_delete.disconnect(
                            sender=target.__class__, dispatch_uid=dispatch_uid
                        )
                    self.assertLess(response.status_code, 500)
                    self.assertTrue(type(target).objects.filter(pk=target.pk).exists())
                    self.assertTrue(
                        ServiceSSHCredential.objects.filter(pk=owner.pk).exists()
                    )
