"""Persisted owner, selected SSH identity, and durable receipt regressions."""

from __future__ import annotations

from ipaddress import ip_interface
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

# Reuse the existing required-real-Django environment gate and native fixtures.
from tests import test_ssh_service_chain_django as fixtures

from django.db import DatabaseError, connections, transaction
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from netbox_proxbox.choices import ProxmoxAccessMethodChoices
from netbox_proxbox.forms.proxmox import ProxmoxEndpointForm
from netbox_proxbox.models import FastAPIEndpoint, ProxmoxEndpoint, ProxmoxNode
from netbox_proxbox.services.connection_authority import (
    approved_connection_allows_secrets,
    connection_target_data,
    connection_target_fingerprint,
)
from netbox_proxbox.views import backend_sync
from netbox_proxbox import signals
from netbox_proxbox.services.connection_authority import approve_connection_target
from tests.test_cloud_image_receipt_guards import binding_payload, send_binding

_OTHER_SSH_HOST = ".".join(("192", "0", "2", "178"))


class SelectedSSHIdentityTest(TestCase):
    """Use the persisted shape produced by the real service-backed form."""

    def setUp(self) -> None:
        fixtures.SSHServiceChainTest.setUp(self)

    def _form(self, **overrides: object) -> object:
        return fixtures.SSHServiceChainTest._form(self, **overrides)

    def _bind_service(self) -> object:
        form = self._form()
        self.assertTrue(form.is_valid(), form.errors.as_data())
        self.endpoint = form.save()
        self.endpoint.refresh_from_db()
        self.assertEqual(self.endpoint.ssh_username, "")
        return self.endpoint.ssh_service.ssh_credential

    def _main_data(self, **overrides: object) -> dict[str, object]:
        data = fixtures.SSHServiceChainTest._main_form_data(self)
        data["service_monitoring_units"] = '["synthetic.service"]'
        data.update(overrides)
        return data

    def _assert_api_clear_rejected(
        self, field: str, *, provider_owned: bool = False
    ) -> None:
        credential = self._bind_service()
        credential.set_private_key("synthetic-local-private-key", key=self.key)
        credential.save()
        if provider_owned:
            credential.clear_password()
            credential.clear_private_key()
            credential.save()
            type(credential).objects.filter(pk=credential.pk).update(
                storage_backend="openbao",
                openbao_password_credential_uuid=uuid4(),
                openbao_keypair_credential_uuid=uuid4(),
            )
            credential.refresh_from_db()
            self.endpoint.refresh_from_db()
        fields = (
            "password_enc",
            "private_key_enc",
            "storage_backend",
            "openbao_password_credential_uuid",
            "openbao_keypair_credential_uuid",
        )
        before = {name: getattr(credential, name) for name in fields}
        data = self._main_data(access_methods=ProxmoxAccessMethodChoices.API)
        data[field] = "on"
        with patch(
            "netbox_proxbox.integrations.openbao_service.clear_service_secret"
        ) as provider_clear:
            form = ProxmoxEndpointForm(
                data=data, instance=self.endpoint, request_user=self.actor
            )
            self.assertFalse(form.is_valid())
            self.assertIn(field, form.errors)
            self.assertIn("API-only edits cannot clear", str(form.errors[field]))
            with self.assertRaises(ValueError):
                form.save()
            provider_clear.assert_not_called()
        credential.refresh_from_db()
        self.endpoint.refresh_from_db()
        self.assertEqual({name: getattr(credential, name) for name in fields}, before)
        self.assertEqual(self.endpoint.ssh_service_id, credential.service_id)
        self.assertEqual(
            self.endpoint.access_methods, ProxmoxAccessMethodChoices.API_SSH
        )

    def test_api_only_password_clear_is_explicitly_rejected(self) -> None:
        self._assert_api_clear_rejected("clear_ssh_password")

    def test_api_only_private_key_clear_is_explicitly_rejected(self) -> None:
        self._assert_api_clear_rejected("clear_ssh_private_key")

    def test_api_only_provider_password_clear_preserves_selected_owner(self) -> None:
        self._assert_api_clear_rejected("clear_ssh_password", provider_owned=True)

    def test_api_only_provider_key_clear_preserves_selected_owner(self) -> None:
        self._assert_api_clear_rejected("clear_ssh_private_key", provider_owned=True)

    def test_ordinary_api_only_edit_preserves_service_credentials(self) -> None:
        credential = self._bind_service()
        stored = credential.password_enc
        form = ProxmoxEndpointForm(
            data=self._main_data(access_methods=ProxmoxAccessMethodChoices.API),
            instance=self.endpoint,
            request_user=self.actor,
        )
        self.assertTrue(form.is_valid(), form.errors.as_data())
        form.save()
        credential.refresh_from_db()
        self.assertEqual(credential.password_enc, stored)

    def _cloud_service(self) -> object:
        credential = self._bind_service()
        self.endpoint.enabled = True
        self.endpoint.allow_writes = True
        self.endpoint.allow_packer_template_builds = True
        self.endpoint.cloud_image_ssh_target_node = "synthetic-node"
        self.endpoint.cloud_image_ssh_identity_file = "/srv/proxbox/ssh/image-builder"
        self.endpoint.save()
        self.endpoint.refresh_from_db()
        ProxmoxNode.objects.create(
            endpoint=self.endpoint,
            name="synthetic-node",
            ip_address=str(ip_interface(str(self.ip_address.address)).ip),
        )
        return credential

    def test_service_binding_uses_effective_login_with_blank_legacy_username(
        self,
    ) -> None:
        self._cloud_service()
        binding, revoke = backend_sync._cloud_image_ssh_binding(self.endpoint)
        self.assertFalse(revoke)
        self.assertEqual(binding["ssh_username"], "root")
        self.assertEqual(binding["ssh_host"], self.endpoint.ssh_host)
        self.assertEqual(binding["ssh_known_host_fingerprint"], fixtures.FINGERPRINT)

    def test_service_login_rotation_changes_cloud_image_authority(self) -> None:
        credential = self._cloud_service()
        before = connection_target_fingerprint(self.endpoint)
        self.assertEqual(connection_target_data(self.endpoint)["ssh_username"], "root")
        credential.username = "image-builder"
        credential.save()
        self.endpoint.refresh_from_db()
        self.assertEqual(self.endpoint.ssh_username, "")
        self.assertEqual(
            connection_target_data(self.endpoint)["ssh_username"], "image-builder"
        )
        self.assertNotEqual(connection_target_fingerprint(self.endpoint), before)

    def test_service_ip_node_validates_even_with_configured_domain(self) -> None:
        self._cloud_service()
        form = ProxmoxEndpointForm(
            data=self._main_data(
                enabled="on",
                allow_writes="on",
                allow_packer_template_builds="on",
                ssh_service=self.endpoint.ssh_service_id,
                ssh_password="",
                cloud_image_ssh_target_node=self.endpoint.cloud_image_ssh_target_node,
                cloud_image_ssh_identity_file=self.endpoint.cloud_image_ssh_identity_file,
            ),
            instance=self.endpoint,
            request_user=self.actor,
        )
        self.assertTrue(form.is_valid(), form.errors.as_data())
        self.assertNotEqual(self.endpoint.domain, self.endpoint.ssh_host)

    def test_same_login_source_switch_requires_new_host_approval(self) -> None:
        self._cloud_service()
        self.endpoint.domain = _OTHER_SSH_HOST
        self.endpoint.save()
        approved = connection_target_fingerprint(self.endpoint)
        approve_connection_target(self.endpoint, user=self.actor, fingerprint=approved)
        self.endpoint.refresh_from_db()
        self.assertTrue(approved_connection_allows_secrets(self.endpoint))
        self.endpoint.allow_packer_template_builds = False
        self.endpoint.ssh_credential_source = "dedicated"
        self.endpoint.ssh_username = "root"
        self.endpoint.save()
        self.endpoint.refresh_from_db()
        self.assertEqual(self.endpoint.effective_ssh_username, "root")
        self.assertEqual(self.endpoint.ssh_host, _OTHER_SSH_HOST)
        ProxmoxNode.objects.filter(endpoint=self.endpoint).update(
            ip_address=_OTHER_SSH_HOST
        )
        self.endpoint.allow_packer_template_builds = True
        self.endpoint.save()
        self.endpoint.refresh_from_db()
        binding, revoke = backend_sync._cloud_image_ssh_binding(self.endpoint)
        self.assertFalse(revoke)
        self.assertEqual(binding["ssh_host"], _OTHER_SSH_HOST)
        self.assertNotEqual(connection_target_fingerprint(self.endpoint), approved)
        self.assertFalse(approved_connection_allows_secrets(self.endpoint))
        approve_connection_target(
            self.endpoint,
            user=self.actor,
            fingerprint=connection_target_fingerprint(self.endpoint),
        )
        self.endpoint.refresh_from_db()
        self.assertTrue(approved_connection_allows_secrets(self.endpoint))

    def test_identical_effective_host_and_login_preserve_authority(self) -> None:
        self._cloud_service()
        self.endpoint.domain = self.endpoint.ssh_host
        self.endpoint.save()
        approved = connection_target_fingerprint(self.endpoint)
        self.endpoint.ssh_credential_source = "dedicated"
        self.endpoint.ssh_username = "root"
        self.endpoint.save()
        self.endpoint.refresh_from_db()
        self.assertEqual(connection_target_fingerprint(self.endpoint), approved)


class DurableCloudImageReceiptTest(TransactionTestCase):
    """Observe actual commits rather than TestCase's implicit savepoint."""

    def setUp(self) -> None:
        self.transport = self.enterContext(patch.object(backend_sync.requests, "put"))
        self.post = self.enterContext(patch.object(backend_sync.requests, "post"))
        self.get = self.enterContext(patch.object(backend_sync.requests, "get"))
        self.enterContext(patch.object(backend_sync, "_cache_successful_proxmox_push"))
        self.enterContext(
            patch.object(
                backend_sync, "_record_confirmed_packer_template_authorization"
            )
        )
        fixtures.SSHServiceChainTest.setUp(self)
        self.transport.reset_mock()
        self.post.reset_mock()

    def _assert_no_write(self, result: tuple[bool, str | None, int | None]) -> None:
        self.assertFalse(result[0])
        self.assertIn("Cloud Image SSH binding was not sent", result[1])
        self.transport.assert_not_called()
        self.post.assert_not_called()
        self.endpoint.refresh_from_db()
        self.assertEqual(self.endpoint.cloud_image_ssh_binding_fingerprint, "")

    def _independent_observer(self) -> object:
        primary = connections["default"]
        observer = primary.copy()
        self.addCleanup(observer.close)
        self.assertIsNot(observer, primary)
        with primary.cursor() as cursor:
            cursor.execute("SELECT pg_backend_pid()")
            primary_pid = cursor.fetchone()[0]
        with observer.cursor() as cursor:
            cursor.execute("SELECT pg_backend_pid()")
            self.assertNotEqual(cursor.fetchone()[0], primary_pid)
        return observer

    def test_database_receipt_error_prevents_value_mutation(self) -> None:
        receipt_rows = ProxmoxEndpoint.objects.using("default").filter(
            pk=self.endpoint.pk
        )
        with patch.object(
            type(receipt_rows),
            "update",
            side_effect=DatabaseError("synthetic-private-detail"),
        ) as receipt_update:
            result = send_binding(backend_sync, self.endpoint)
        receipt_update.assert_called_once_with(
            cloud_image_ssh_binding_fingerprint=backend_sync._cloud_image_ssh_binding_fingerprint(
                binding_payload()
            )
        )
        self._assert_no_write(result)
        self.assertNotIn("synthetic-private-detail", result[1])

    def test_zero_row_receipt_prevents_value_mutation(self) -> None:
        receipt_rows = ProxmoxEndpoint.objects.using("default").filter(
            pk=self.endpoint.pk
        )
        with patch.object(
            type(receipt_rows), "update", return_value=0
        ) as receipt_update:
            result = send_binding(backend_sync, self.endpoint)
        receipt_update.assert_called_once_with(
            cloud_image_ssh_binding_fingerprint=backend_sync._cloud_image_ssh_binding_fingerprint(
                binding_payload()
            )
        )
        self._assert_no_write(result)

    def test_commit_failure_rolls_back_receipt_and_prevents_value_mutation(
        self,
    ) -> None:
        with patch.object(
            connections["default"],
            "commit",
            side_effect=DatabaseError("synthetic-commit-failure"),
        ):
            result = send_binding(backend_sync, self.endpoint)
        self._assert_no_write(result)

    def test_outer_atomic_is_not_a_durable_receipt(self) -> None:
        with transaction.atomic():
            result = send_binding(backend_sync, self.endpoint)
            self._assert_no_write(result)
            self.assertIn("committed transaction", result[1])

    def test_manual_transaction_is_not_a_durable_receipt(self) -> None:
        transaction.set_autocommit(False)
        try:
            result = send_binding(backend_sync, self.endpoint)
        finally:
            transaction.set_autocommit(True)
        self._assert_no_write(result)

    def test_unsaved_owner_prevents_value_mutation(self) -> None:
        result = send_binding(backend_sync, ProxmoxEndpoint())
        self._assert_no_write(result)

    def test_deleted_owner_prevents_value_mutation(self) -> None:
        missing = ProxmoxEndpoint(pk=self.endpoint.pk + 1000000)
        self._assert_no_write(send_binding(backend_sync, missing))

    def test_receipt_is_visible_on_an_independent_connection_before_transport(
        self,
    ) -> None:
        observer = self._independent_observer()
        expected = backend_sync._cloud_image_ssh_binding_fingerprint(binding_payload())

        def observe(*_args: object, **_kwargs: object) -> object:
            with observer.cursor() as cursor:
                cursor.execute(
                    "SELECT cloud_image_ssh_binding_fingerprint FROM netbox_proxbox_proxmoxendpoint WHERE id = %s",
                    [self.endpoint.pk],
                )
                self.assertEqual(cursor.fetchone()[0], expected)
            return SimpleNamespace(raise_for_status=lambda: None)

        self.transport.side_effect = observe
        self.assertEqual(send_binding(backend_sync, self.endpoint), (True, None, None))
        self.transport.assert_called_once()

    def test_uncertain_transport_retains_committed_receipt(self) -> None:
        self.transport.side_effect = backend_sync.requests.exceptions.ReadTimeout(
            "synthetic-response-loss"
        )
        with self.assertRaises(backend_sync.requests.exceptions.ReadTimeout):
            send_binding(backend_sync, self.endpoint)
        self.endpoint.refresh_from_db()
        self.assertTrue(self.endpoint.cloud_image_ssh_binding_fingerprint)

    def test_clear_response_does_not_erase_a_newer_receipt(self) -> None:
        old = "a" * 64
        new = "b" * 64
        ProxmoxEndpoint.objects.filter(pk=self.endpoint.pk).update(
            cloud_image_ssh_binding_fingerprint=old
        )

        def replace_receipt(*_args: object, **_kwargs: object) -> object:
            ProxmoxEndpoint.objects.filter(pk=self.endpoint.pk).update(
                cloud_image_ssh_binding_fingerprint=new
            )
            return SimpleNamespace(raise_for_status=lambda: None)

        self.transport.side_effect = replace_receipt
        payload = {**binding_payload(), **backend_sync._CLOUD_IMAGE_SSH_CLEAR}
        result = backend_sync._send_approved_proxmox_payload(
            self.endpoint,
            payload=payload,
            fingerprint="synthetic",
            existing={"id": 1},
            binding_receipt=old,
            list_url="http://127.0.0.1:1/proxmox/endpoints",
            base_url="http://127.0.0.1:1",
            headers={},
            backend_verify_ssl=True,
            timeout=1.0,
            deadline=None,
        )
        self.assertEqual(result, (True, None, None))
        self.endpoint.refresh_from_db()
        self.assertEqual(self.endpoint.cloud_image_ssh_binding_fingerprint, new)

    def _prepare_approved_cloud_service(self) -> None:
        form = fixtures.SSHServiceChainTest._form(self)
        self.assertTrue(form.is_valid(), form.errors.as_data())
        self.endpoint = form.save()
        self.endpoint.password = "synthetic-api-password"
        self.endpoint.enabled = True
        self.endpoint.allow_writes = True
        self.endpoint.allow_packer_template_builds = True
        self.endpoint.cloud_image_ssh_target_node = "synthetic-node"
        self.endpoint.cloud_image_ssh_identity_file = "/srv/proxbox/ssh/image-builder"
        self.endpoint.save()
        ProxmoxNode.objects.create(
            endpoint=self.endpoint,
            name="synthetic-node",
            ip_address=str(ip_interface(str(self.ip_address.address)).ip),
        )
        approve_connection_target(
            self.endpoint,
            user=self.actor,
            fingerprint=connection_target_fingerprint(self.endpoint),
        )

    def test_real_ssh_edit_dispatches_once_after_receipt_commit(self) -> None:
        self._prepare_approved_cloud_service()
        self.assertFalse(connections["default"].settings_dict["ATOMIC_REQUESTS"])
        rows = SimpleNamespace(
            count=lambda: 1,
            order_by=lambda _field: SimpleNamespace(
                first=lambda: SimpleNamespace(pk=1, verify_ssl=True)
            ),
        )
        self.get.return_value = SimpleNamespace(
            raise_for_status=lambda: None, json=lambda: []
        )
        observer = self._independent_observer()

        def observe(_url: str, **kwargs: object) -> object:
            self.assertFalse(connections["default"].in_atomic_block)
            with observer.cursor() as cursor:
                cursor.execute(
                    "SELECT cloud_image_ssh_binding_fingerprint FROM netbox_proxbox_proxmoxendpoint WHERE id = %s",
                    [self.endpoint.pk],
                )
                expected = backend_sync._cloud_image_ssh_binding_fingerprint(
                    kwargs["json"]
                )
                self.assertTrue(expected)
                self.assertEqual(cursor.fetchone()[0], expected)
            return SimpleNamespace(raise_for_status=lambda: None)

        self.post.side_effect = observe
        data = dict(fixtures.SSHServiceChainTest._form(self).data)
        data.update(ssh_service=self.endpoint.ssh_service_id, ssh_password="")
        self.client.force_login(self.actor)
        with (
            patch.object(FastAPIEndpoint.objects, "filter", return_value=rows),
            patch.object(
                signals, "_stored_backend_token", return_value="synthetic-backend-key"
            ),
            patch.object(signals, "_register_token_with_backend", return_value=True),
            patch.object(
                signals, "_get_backend_url", return_value="http://127.0.0.1:1"
            ),
            patch(
                "netbox_proxbox.utils.get_backend_auth_headers",
                return_value={"X-Proxbox-API-Key": "synthetic-backend-key"},
            ),
        ):
            response = self.client.post(
                reverse(
                    "plugins:netbox_proxbox:proxmoxendpoint_ssh_settings",
                    args=[self.endpoint.pk],
                ),
                data,
            )
        self.assertEqual(response.status_code, 302)
        self.post.assert_called_once()
        self.transport.assert_not_called()
