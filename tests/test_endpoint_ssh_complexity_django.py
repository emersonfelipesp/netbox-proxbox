"""Characterize endpoint SSH form and terminal-session branch behavior."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from cryptography.fernet import Fernet
import pytest

from tests.netbox_test_paths import netbox_source_roots


REPO_ROOT = Path(__file__).resolve().parents[1]
NETBOX_ROOTS = netbox_source_roots(REPO_ROOT)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

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
    pytest.skip(
        "Django/NetBox test dependencies are not installed in this environment.",
        allow_module_level=True,
    )

if not hasattr(django, "__path__"):
    pytest.skip(
        "The mocked suite does not provide a real Django package.",
        allow_module_level=True,
    )

for candidate_path in NETBOX_ROOTS:
    candidate_string = str(candidate_path)
    if candidate_path.exists() and candidate_string not in sys.path:
        sys.path.insert(0, candidate_string)

os.environ.setdefault("NETBOX_CONFIGURATION", "tests.netbox_test_configuration")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netbox.settings")

try:
    django.setup()
except Exception as exc:  # pragma: no cover - external test harness availability
    if _REQUIRE_DJANGO:
        raise
    pytest.skip(
        f"NetBox test environment is not available: {exc}",
        allow_module_level=True,
    )

from django.core.exceptions import ValidationError  # noqa: E402
from django.db import transaction  # noqa: E402
from django.http import JsonResponse  # noqa: E402
from django.test import SimpleTestCase, TestCase  # noqa: E402

from netbox_proxbox.choices import ProxmoxAccessMethodChoices  # noqa: E402
from netbox_proxbox.forms.proxmox import (  # noqa: E402
    ProxmoxEndpointForm,
    ProxmoxEndpointSSHSettingsForm,
)
from netbox_proxbox.models import (  # noqa: E402
    ProxboxPluginSettings,
    ProxmoxEndpoint,
    ProxmoxNode,
)
from netbox_proxbox.models.ssh_credential import (  # noqa: E402
    AUTH_METHOD_KEY,
    AUTH_METHOD_PASSWORD,
    SSH_CRED_SOURCE_DEDICATED,
    SSH_CRED_SOURCE_REUSE,
)
from netbox_proxbox.utils import encryption as enc_helpers  # noqa: E402
from netbox_proxbox.views.endpoints import proxmox as view_module  # noqa: E402


FINGERPRINT = "SHA256:" + "A" * 43
PASSWORD = "endpoint-password"
PRIVATE_KEY = "endpoint-private-key"
CLOUD_IMAGE_IP = ".".join(("192", "0", "2", "22"))
CLOUD_IMAGE_OTHER_IP = ".".join(("192", "0", "2", "23"))


def _main_form_data(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "name": "branch-pve",
        "domain": "pve.example.test",
        "port": "8006",
        "username": "root@pam",
        "password": PASSWORD,
        "token_name": "",
        "token_value": "",
        "credential_storage_backend": "legacy_encrypted",
        "verify_ssl": "",
        "enabled": "on",
        "allow_writes": "",
        "access_methods": ProxmoxAccessMethodChoices.API_SSH,
        "service_monitoring_interval_minutes": "5",
        "environment": "",
        "ssh_credential_source": SSH_CRED_SOURCE_DEDICATED,
        "ssh_username": "",
        "ssh_port": "22",
        "ssh_auth_method": AUTH_METHOD_PASSWORD,
        "ssh_known_host_fingerprint": "",
    }
    data.update(overrides)
    return data


def _helper_form(
    endpoint: object,
    cleaned_data: dict[str, object],
) -> tuple[ProxmoxEndpointForm, list[tuple[str, str]]]:
    form = ProxmoxEndpointForm.__new__(ProxmoxEndpointForm)
    form.instance = endpoint
    form.cleaned_data = cleaned_data
    errors: list[tuple[str, str]] = []
    form.add_error = lambda field, message: errors.append((field, str(message)))
    return form, errors


class _PasswordFailureEndpoint:
    domain = "pve.example.test"
    ip_address = None
    username = "root@pam"
    ssh_credential_source = SSH_CRED_SOURCE_REUSE

    @property
    def password(self) -> str:
        raise ValidationError("unavailable")


class EndpointSSHFormBranchTest(TestCase):
    def setUp(self) -> None:
        settings_obj = ProxboxPluginSettings.get_solo()
        settings_obj.encryption_key = Fernet.generate_key().decode()
        settings_obj.credential_storage_backend = "legacy_encrypted"
        settings_obj.save(
            update_fields=("encryption_key", "credential_storage_backend")
        )

    def _cloud_image_form(self, endpoint, target_node, **overrides):
        data = _main_form_data(
            name=endpoint.name,
            domain=CLOUD_IMAGE_IP,
            password="",
            allow_writes="on",
            allow_packer_template_builds="on",
            ssh_credential_source=SSH_CRED_SOURCE_REUSE,
            ssh_known_host_fingerprint=FINGERPRINT,
            cloud_image_ssh_target_node=target_node,
            cloud_image_ssh_identity_file="/srv/proxbox/ssh/image-builder",
        )
        data.update(overrides)
        return ProxmoxEndpointForm(
            instance=endpoint,
            data=data,
        )

    def test_cloud_image_target_node_must_match_the_endpoint_ssh_host(self) -> None:
        endpoint = ProxmoxEndpoint.objects.create(
            name="cloud-image-form",
            domain=CLOUD_IMAGE_IP,
            username="root@pam",
        )
        endpoint.password = PASSWORD
        endpoint.save()
        ProxmoxNode.objects.create(
            endpoint=endpoint, name="node-a", ip_address=CLOUD_IMAGE_IP
        )
        ProxmoxNode.objects.create(
            endpoint=endpoint, name="node-b", ip_address=CLOUD_IMAGE_OTHER_IP
        )

        mismatch = self._cloud_image_form(endpoint, "node-b")
        matching = self._cloud_image_form(endpoint, "node-a")

        self.assertFalse(mismatch.is_valid())
        self.assertIn("cloud_image_ssh_target_node", mismatch.errors)
        self.assertTrue(matching.is_valid(), matching.errors.as_data())

    def test_cloud_image_stale_target_does_not_block_closing_a_gate(self) -> None:
        endpoint = ProxmoxEndpoint.objects.create(
            name="cloud-image-disable-form",
            domain=CLOUD_IMAGE_IP,
            username="root@pam",
        )
        endpoint.password = PASSWORD
        endpoint.save()

        closed_states = (
            {"enabled": ""},
            {"access_methods": ProxmoxAccessMethodChoices.API},
            {"allow_writes": ""},
            {"allow_packer_template_builds": ""},
        )
        for overrides in closed_states:
            with self.subTest(overrides=overrides):
                form = self._cloud_image_form(endpoint, "missing-node", **overrides)
                form.is_valid()
                self.assertNotIn("cloud_image_ssh_target_node", form.errors)

        open_form = self._cloud_image_form(endpoint, "missing-node")
        self.assertFalse(open_form.is_valid())
        self.assertIn("cloud_image_ssh_target_node", open_form.errors)

    def test_dedicated_clean_reports_each_missing_requirement(self) -> None:
        endpoint = SimpleNamespace(
            ssh_credential_source=SSH_CRED_SOURCE_DEDICATED,
            ssh_password_enc="",
            ssh_private_key_enc="",
            openbao_ssh_password_credential_uuid=None,
            openbao_ssh_keypair_credential_uuid=None,
        )
        cleaned_data = {
            "ssh_credential_source": SSH_CRED_SOURCE_DEDICATED,
            "ssh_username": "configured",
            "ssh_known_host_fingerprint": "",
            "ssh_auth_method": AUTH_METHOD_PASSWORD,
            "ssh_password": "",
            "ssh_private_key": "",
            "clear_ssh_password": False,
            "clear_ssh_private_key": False,
        }
        form, errors = _helper_form(endpoint, cleaned_data)

        with patch(
            "netbox_proxbox.integrations.openbao.endpoint_uses_openbao_storage",
            return_value=False,
        ):
            form._clean_ssh_credentials()

        self.assertEqual(
            [field for field, _message in errors],
            ["ssh_known_host_fingerprint", "ssh_password"],
        )

    def test_dedicated_clean_accepts_empty_or_complete_configuration(self) -> None:
        endpoint = SimpleNamespace(
            ssh_credential_source=SSH_CRED_SOURCE_DEDICATED,
            ssh_password_enc="",
            ssh_private_key_enc="",
            openbao_ssh_password_credential_uuid=None,
            openbao_ssh_keypair_credential_uuid=None,
        )
        cases = (
            {
                "ssh_credential_source": SSH_CRED_SOURCE_DEDICATED,
                "ssh_username": "",
                "ssh_known_host_fingerprint": "",
                "ssh_auth_method": AUTH_METHOD_PASSWORD,
                "ssh_password": "",
                "ssh_private_key": "",
            },
            {
                "ssh_credential_source": SSH_CRED_SOURCE_DEDICATED,
                "ssh_username": "root",
                "ssh_known_host_fingerprint": FINGERPRINT,
                "ssh_auth_method": AUTH_METHOD_KEY,
                "ssh_password": "",
                "ssh_private_key": PRIVATE_KEY,
            },
        )

        for cleaned_data in cases:
            with self.subTest(cleaned_data=cleaned_data):
                form, errors = _helper_form(endpoint, cleaned_data)
                with patch(
                    "netbox_proxbox.integrations.openbao.endpoint_uses_openbao_storage",
                    return_value=False,
                ):
                    form._clean_ssh_credentials()
                self.assertEqual(errors, [])

    def test_dedicated_clean_applies_clear_flags_to_local_and_openbao_secrets(
        self,
    ) -> None:
        for uses_openbao, stored_field in (
            (False, "ssh_password_enc"),
            (True, "openbao_ssh_password_credential_uuid"),
        ):
            endpoint = SimpleNamespace(
                ssh_credential_source=SSH_CRED_SOURCE_DEDICATED,
                ssh_password_enc="ciphertext" if not uses_openbao else "",
                ssh_private_key_enc="",
                openbao_ssh_password_credential_uuid=(
                    "11111111-1111-4111-8111-111111111111" if uses_openbao else None
                ),
                openbao_ssh_keypair_credential_uuid=None,
            )
            for clear, expected_errors in ((False, []), (True, ["ssh_password"])):
                with self.subTest(
                    uses_openbao=uses_openbao,
                    stored_field=stored_field,
                    clear=clear,
                ):
                    form, errors = _helper_form(
                        endpoint,
                        {
                            "ssh_credential_source": SSH_CRED_SOURCE_DEDICATED,
                            "ssh_username": "root",
                            "ssh_known_host_fingerprint": FINGERPRINT,
                            "ssh_auth_method": AUTH_METHOD_PASSWORD,
                            "ssh_password": "",
                            "ssh_private_key": "",
                            "clear_ssh_password": clear,
                            "clear_ssh_private_key": False,
                        },
                    )
                    with patch(
                        "netbox_proxbox.integrations.openbao.endpoint_uses_openbao_storage",
                        return_value=uses_openbao,
                    ):
                        form._clean_ssh_credentials()
                    self.assertEqual(
                        [field for field, _message in errors], expected_errors
                    )

    def test_dedicated_clean_requires_encryption_key_for_new_local_secret(
        self,
    ) -> None:
        settings_obj = ProxboxPluginSettings.get_solo()
        settings_obj.encryption_key = ""
        settings_obj.save(update_fields=("encryption_key",))
        endpoint = SimpleNamespace(
            ssh_credential_source=SSH_CRED_SOURCE_DEDICATED,
            ssh_password_enc="",
            ssh_private_key_enc="",
            openbao_ssh_password_credential_uuid=None,
            openbao_ssh_keypair_credential_uuid=None,
        )
        form, errors = _helper_form(
            endpoint,
            {
                "ssh_credential_source": SSH_CRED_SOURCE_DEDICATED,
                "ssh_username": "root",
                "ssh_known_host_fingerprint": FINGERPRINT,
                "ssh_auth_method": AUTH_METHOD_PASSWORD,
                "ssh_password": PASSWORD,
                "ssh_private_key": "",
            },
        )

        with patch(
            "netbox_proxbox.integrations.openbao.endpoint_uses_openbao_storage",
            return_value=False,
        ):
            form._clean_ssh_credentials()

        self.assertEqual([field for field, _message in errors], ["ssh_password"])

    def test_reuse_clean_defers_all_rules_to_model_validation(self) -> None:
        form, errors = _helper_form(
            SimpleNamespace(ssh_credential_source=SSH_CRED_SOURCE_REUSE),
            {
                "ssh_credential_source": SSH_CRED_SOURCE_REUSE,
                "ssh_known_host_fingerprint": "",
            },
        )

        form._clean_ssh_credentials()

        self.assertEqual(errors, [])

    def test_monitoring_readiness_reuse_requires_every_value(self) -> None:
        complete = {
            "ssh_credential_source": SSH_CRED_SOURCE_REUSE,
            "domain": "pve.example.test",
            "ip_address": None,
            "username": "root@pam",
            "password": PASSWORD,
            "ssh_known_host_fingerprint": FINGERPRINT,
        }
        endpoint = SimpleNamespace(
            domain="",
            ip_address=None,
            username="",
            ssh_credential_source=SSH_CRED_SOURCE_REUSE,
        )
        for missing in (
            None,
            "domain",
            "username",
            "password",
            "ssh_known_host_fingerprint",
        ):
            with self.subTest(missing=missing):
                cleaned_data = dict(complete)
                if missing is not None:
                    cleaned_data[missing] = ""
                form, _errors = _helper_form(endpoint, cleaned_data)
                self.assertEqual(
                    form._submitted_service_monitoring_credentials_ready(),
                    missing is None,
                )

    def test_monitoring_readiness_reuse_fails_closed_on_password_error(self) -> None:
        form, _errors = _helper_form(
            _PasswordFailureEndpoint(),
            {
                "ssh_credential_source": SSH_CRED_SOURCE_REUSE,
                "domain": "pve.example.test",
                "username": "root@pam",
                "ssh_known_host_fingerprint": FINGERPRINT,
            },
        )

        self.assertFalse(form._submitted_service_monitoring_credentials_ready())

    def test_monitoring_readiness_dedicated_honors_method_storage_and_clear(
        self,
    ) -> None:
        for uses_openbao, auth_method, clear_field, stored_fields in (
            (
                False,
                AUTH_METHOD_PASSWORD,
                "clear_ssh_password",
                {
                    "ssh_password_enc": "password-ciphertext",
                    "ssh_private_key_enc": "",
                    "openbao_ssh_password_credential_uuid": None,
                    "openbao_ssh_keypair_credential_uuid": None,
                },
            ),
            (
                False,
                AUTH_METHOD_KEY,
                "clear_ssh_private_key",
                {
                    "ssh_password_enc": "",
                    "ssh_private_key_enc": "key-ciphertext",
                    "openbao_ssh_password_credential_uuid": None,
                    "openbao_ssh_keypair_credential_uuid": None,
                },
            ),
            (
                True,
                AUTH_METHOD_PASSWORD,
                "clear_ssh_password",
                {
                    "ssh_password_enc": "",
                    "ssh_private_key_enc": "",
                    "openbao_ssh_password_credential_uuid": (
                        "11111111-1111-4111-8111-111111111111"
                    ),
                    "openbao_ssh_keypair_credential_uuid": None,
                },
            ),
            (
                True,
                AUTH_METHOD_KEY,
                "clear_ssh_private_key",
                {
                    "ssh_password_enc": "",
                    "ssh_private_key_enc": "",
                    "openbao_ssh_password_credential_uuid": None,
                    "openbao_ssh_keypair_credential_uuid": (
                        "22222222-2222-4222-8222-222222222222"
                    ),
                },
            ),
        ):
            with self.subTest(uses_openbao=uses_openbao, auth_method=auth_method):
                endpoint = SimpleNamespace(
                    domain="pve.example.test",
                    ip_address=None,
                    ssh_credential_source=SSH_CRED_SOURCE_DEDICATED,
                    **stored_fields,
                )
                data = {
                    "ssh_credential_source": SSH_CRED_SOURCE_DEDICATED,
                    "domain": "pve.example.test",
                    "ssh_username": "root",
                    "ssh_known_host_fingerprint": FINGERPRINT,
                    "ssh_auth_method": auth_method,
                    "ssh_password": "",
                    "ssh_private_key": "",
                    "clear_ssh_password": False,
                    "clear_ssh_private_key": False,
                }
                form, _errors = _helper_form(endpoint, data)
                with patch(
                    "netbox_proxbox.integrations.openbao.endpoint_uses_openbao_storage",
                    return_value=uses_openbao,
                ):
                    self.assertTrue(
                        form._submitted_service_monitoring_credentials_ready()
                    )
                    data[clear_field] = True
                    self.assertFalse(
                        form._submitted_service_monitoring_credentials_ready()
                    )

    def test_save_persists_both_dedicated_secrets_and_preserves_blanks(self) -> None:
        endpoint = ProxmoxEndpoint.objects.create(
            name="replace-dedicated",
            domain="replace.example.test",
            username="root@pam",
            access_methods=ProxmoxAccessMethodChoices.API_SSH,
            ssh_username="root",
            ssh_known_host_fingerprint=FINGERPRINT,
        )
        key = ProxboxPluginSettings.get_solo().encryption_key
        endpoint.set_ssh_password("previous-password", key=key)
        endpoint.save()
        form = ProxmoxEndpointSSHSettingsForm(
            instance=endpoint,
            data={
                "ssh_credential_source": SSH_CRED_SOURCE_DEDICATED,
                "ssh_username": "root",
                "ssh_port": 22,
                "ssh_auth_method": AUTH_METHOD_PASSWORD,
                "ssh_known_host_fingerprint": FINGERPRINT,
                "ssh_password": "ssh-password",
                "ssh_private_key": PRIVATE_KEY,
            },
        )
        self.assertTrue(form.is_valid(), form.errors.as_data())

        endpoint = form.save()
        self.assertEqual(endpoint.get_ssh_password(key=key), "ssh-password")
        self.assertEqual(endpoint.get_ssh_private_key(key=key), PRIVATE_KEY)

        edit = ProxmoxEndpointSSHSettingsForm(
            instance=endpoint,
            data={
                "ssh_credential_source": SSH_CRED_SOURCE_DEDICATED,
                "ssh_username": "root",
                "ssh_port": 22,
                "ssh_auth_method": AUTH_METHOD_PASSWORD,
                "ssh_known_host_fingerprint": FINGERPRINT,
            },
        )
        self.assertTrue(edit.is_valid(), edit.errors.as_data())
        saved = edit.save()
        self.assertEqual(saved.get_ssh_password(key=key), "ssh-password")
        self.assertEqual(saved.get_ssh_private_key(key=key), PRIVATE_KEY)

    def test_save_clear_flags_remove_each_local_dedicated_secret(self) -> None:
        endpoint = ProxmoxEndpoint.objects.create(
            name="clear-dedicated",
            domain="clear.example.test",
            username="root@pam",
            ssh_username="root",
            ssh_known_host_fingerprint=FINGERPRINT,
        )
        key = ProxboxPluginSettings.get_solo().encryption_key
        endpoint.set_ssh_password("ssh-password", key=key)
        endpoint.set_ssh_private_key(PRIVATE_KEY, key=key)
        endpoint.save()
        form = ProxmoxEndpointSSHSettingsForm(
            instance=endpoint,
            data={
                "ssh_credential_source": SSH_CRED_SOURCE_DEDICATED,
                "ssh_username": "root",
                "ssh_port": 22,
                "ssh_auth_method": AUTH_METHOD_PASSWORD,
                "ssh_known_host_fingerprint": FINGERPRINT,
                "clear_ssh_password": "on",
                "clear_ssh_private_key": "on",
            },
        )

        self.assertFalse(form.is_valid())
        self.assertIn("ssh_password", form.errors)
        form.cleaned_data["ssh_password"] = "replacement"
        form._errors.pop("ssh_password", None)
        saved = form.save()
        saved.refresh_from_db()
        self.assertEqual(saved.get_ssh_password(key=key), "replacement")
        self.assertEqual(saved.ssh_private_key_enc, "")

    def test_save_reuse_ignores_dedicated_secret_inputs(self) -> None:
        form = ProxmoxEndpointForm(
            data=_main_form_data(
                ssh_credential_source=SSH_CRED_SOURCE_REUSE,
                ssh_known_host_fingerprint=FINGERPRINT,
                ssh_password="ignored-password",
                ssh_private_key="ignored-key",
            )
        )
        self.assertTrue(form.is_valid(), form.errors.as_data())

        endpoint = form.save()

        self.assertEqual(endpoint.ssh_password_enc, "")
        self.assertEqual(endpoint.ssh_private_key_enc, "")

    def test_save_commit_false_attaches_actor_without_writing(self) -> None:
        actor = object()
        form = ProxmoxEndpointForm(
            data=_main_form_data(),
            request_user=actor,
        )
        self.assertTrue(form.is_valid(), form.errors.as_data())

        endpoint = form.save(commit=False)

        self.assertIs(endpoint._openbao_actor_user, actor)
        self.assertIsNone(endpoint.pk)

    def test_save_openbao_standin_persists_owner_before_material(
        self,
    ) -> None:
        actor = object()
        observed_owner_ids: list[int] = []

        def store_password(
            endpoint: ProxmoxEndpoint,
            _password: str,
            *,
            user: object,
        ) -> None:
            self.assertIsNotNone(endpoint.pk)
            self.assertTrue(ProxmoxEndpoint.objects.filter(pk=endpoint.pk).exists())
            self.assertIs(user, actor)
            observed_owner_ids.append(endpoint.pk)

        with (
            patch(
                "netbox_proxbox.integrations.openbao.is_netbox_openbao_installed",
                return_value=True,
            ),
            patch(
                "netbox_proxbox.integrations.openbao.openbao_prerequisites_errors",
                return_value=[],
            ),
            patch(
                "netbox_proxbox.integrations.openbao.store_endpoint_password",
                side_effect=store_password,
            ) as store_password_mock,
        ):
            form = ProxmoxEndpointForm(
                data=_main_form_data(
                    credential_storage_backend="openbao",
                    ssh_credential_source=SSH_CRED_SOURCE_REUSE,
                    ssh_known_host_fingerprint=FINGERPRINT,
                ),
                request_user=actor,
            )
            self.assertTrue(form.is_valid(), form.errors.as_data())
            endpoint = form.save()

        self.assertEqual(observed_owner_ids, [endpoint.pk])
        store_password_mock.assert_called_once_with(endpoint, PASSWORD, user=actor)
        endpoint.refresh_from_db()
        self.assertEqual(endpoint.credential_storage_backend, "openbao")
        self.assertEqual(endpoint.password_enc, "")

    def test_save_openbao_standin_provider_failure_rolls_back_new_owner(
        self,
    ) -> None:
        with (
            patch(
                "netbox_proxbox.integrations.openbao.is_netbox_openbao_installed",
                return_value=True,
            ),
            patch(
                "netbox_proxbox.integrations.openbao.openbao_prerequisites_errors",
                return_value=[],
            ),
            patch(
                "netbox_proxbox.integrations.openbao.store_endpoint_password",
                side_effect=RuntimeError("provider write failed"),
            ),
        ):
            form = ProxmoxEndpointForm(
                data=_main_form_data(
                    name="openbao-provider-failure",
                    credential_storage_backend="openbao",
                    ssh_credential_source=SSH_CRED_SOURCE_REUSE,
                    ssh_known_host_fingerprint=FINGERPRINT,
                )
            )
            self.assertTrue(form.is_valid(), form.errors.as_data())

            with self.assertRaisesRegex(RuntimeError, "provider write failed"):
                with transaction.atomic():
                    form.save()

        self.assertFalse(
            ProxmoxEndpoint.objects.filter(name="openbao-provider-failure").exists()
        )

    def test_save_openbao_clear_dispatches_each_dedicated_secret(self) -> None:
        endpoint = ProxmoxEndpoint.objects.create(
            name="clear-openbao",
            domain="clear-openbao.example.test",
            username="root@pam",
            ssh_username="root",
            ssh_known_host_fingerprint=FINGERPRINT,
        )
        key = ProxboxPluginSettings.get_solo().encryption_key
        endpoint.set_ssh_password("ssh-password", key=key)
        endpoint.set_ssh_private_key(PRIVATE_KEY, key=key)
        endpoint.save()
        cases = (
            (
                AUTH_METHOD_PASSWORD,
                "clear_ssh_private_key",
                "openbao_ssh_keypair_credential_uuid",
            ),
            (
                AUTH_METHOD_KEY,
                "clear_ssh_password",
                "openbao_ssh_password_credential_uuid",
            ),
        )
        for auth_method, clear_field, reference_field in cases:
            with self.subTest(clear_field=clear_field):
                form = ProxmoxEndpointSSHSettingsForm(
                    instance=endpoint,
                    data={
                        "ssh_credential_source": SSH_CRED_SOURCE_DEDICATED,
                        "ssh_username": "root",
                        "ssh_port": 22,
                        "ssh_auth_method": auth_method,
                        "ssh_known_host_fingerprint": FINGERPRINT,
                        clear_field: "on",
                    },
                )
                self.assertTrue(form.is_valid(), form.errors.as_data())
                with (
                    patch(
                        "netbox_proxbox.integrations.openbao.endpoint_uses_openbao_storage",
                        return_value=True,
                    ),
                    patch(
                        "netbox_proxbox.integrations.openbao.clear_endpoint_openbao_credential"
                    ) as clear_credential,
                ):
                    form.save(commit=False)
                clear_credential.assert_called_once_with(
                    endpoint,
                    reference_field,
                    user=None,
                )


class _RestrictManager:
    def restrict(self, *_args: object) -> _RestrictManager:
        return self


class _TerminalUser:
    def __init__(self, *, authenticated: bool = True, permitted: bool = True) -> None:
        self.is_authenticated = authenticated
        self._permitted = permitted
        self.username = "terminal-user"

    def has_perm(self, _permission: str) -> bool:
        return self._permitted

    def __str__(self) -> str:
        return self.username


def _json(response: JsonResponse) -> dict[str, object]:
    return json.loads(response.content)


class TerminalSessionPostBranchTest(SimpleTestCase):
    def _post(
        self,
        payload: dict[str, object] | None = None,
        *,
        raw_body: bytes | None = None,
        user: _TerminalUser | None = None,
        endpoint: object | None = None,
        node: object | None = None,
        backend_context: object | None = None,
        backend_response: object | None = None,
        fastapi_result: tuple[object | None, object | None] | None = None,
        post_side_effect: object | None = None,
        candidates: list[tuple[str, bool]] | None = None,
    ) -> tuple[JsonResponse, MagicMock, dict[str, object]]:
        request = SimpleNamespace(
            user=user or _TerminalUser(),
            body=(
                raw_body
                if raw_body is not None
                else json.dumps(payload or {"target_type": "endpoint"}).encode()
            ),
        )
        endpoint = endpoint or SimpleNamespace(
            pk=7,
            enabled=True,
            ssh_access_enabled=True,
            ssh_host="pve.example.test",
            has_ssh_terminal_credentials=True,
        )
        context = backend_context or SimpleNamespace(
            http_url="https://api.example.test",
            ip_address_url=None,
            verify_ssl=True,
            headers={"Authorization": "Bearer test"},
            detail={"websocket_url": "wss://api.example.test"},
        )
        response = backend_response or SimpleNamespace(
            status_code=200,
            text="",
            json=lambda: {
                "session_id": "session-1",
                "ticket": "ticket-1",
                "websocket_path": "/ssh/session-1",
                "expires_at": "2030-01-01T00:00:00Z",
            },
        )
        request_post = MagicMock(
            return_value=response,
            side_effect=post_side_effect,
        )
        node_queryset = MagicMock()
        node_queryset.filter.return_value.first.return_value = node
        backend_payload: dict[str, object] = {}

        def capture_post(_url: str, **kwargs: object) -> object:
            backend_payload.update(kwargs["json"])
            return request_post(_url, **kwargs)

        self.fastapi_getter = MagicMock(
            return_value=fastapi_result or (SimpleNamespace(websocket_url=""), context)
        )
        self.node_queryset = node_queryset
        with (
            patch.object(
                view_module,
                "ProxmoxEndpoint",
                SimpleNamespace(objects=_RestrictManager()),
            ),
            patch.object(
                view_module,
                "ProxmoxNode",
                SimpleNamespace(objects=node_queryset),
            ),
            patch.object(view_module, "get_object_or_404", return_value=endpoint),
            patch.object(
                view_module,
                "get_fastapi_endpoint_with_token",
                self.fastapi_getter,
            ),
            patch.object(
                view_module,
                "_build_request_candidates",
                return_value=candidates
                or [("https://api.example.test/ssh/sessions", True)],
            ),
            patch.object(view_module.requests, "post", side_effect=capture_post),
        ):
            result = view_module.ProxmoxEndpointSSHTerminalSessionView().post(
                request, 7
            )
        return result, request_post, backend_payload

    def test_authentication_and_permission_failures(self) -> None:
        unauthenticated, _post, _payload = self._post(
            user=_TerminalUser(authenticated=False)
        )
        forbidden, _post, _payload = self._post(user=_TerminalUser(permitted=False))

        self.assertEqual(
            (unauthenticated.status_code, _json(unauthenticated)),
            (401, {"error": "Authentication required."}),
        )
        self.assertEqual(
            (forbidden.status_code, _json(forbidden)),
            (403, {"error": "Permission denied."}),
        )

    def test_payload_and_terminal_size_validation(self) -> None:
        invalid_json, _post, _payload = self._post(raw_body=b"{")
        invalid_size, _post, _payload = self._post(
            {"target_type": "endpoint", "cols": "wide"}
        )

        self.assertEqual(invalid_json.status_code, 400)
        self.assertEqual(_json(invalid_json), {"error": "Invalid JSON payload."})
        self.assertEqual(invalid_size.status_code, 400)
        self.assertEqual(_json(invalid_size), {"error": "Invalid terminal size."})

    def test_inline_credential_requires_endpoint_ssh_access(self) -> None:
        endpoint = SimpleNamespace(
            pk=7,
            enabled=True,
            ssh_access_enabled=False,
            ssh_host="pve.example.test",
            has_ssh_terminal_credentials=False,
        )
        response, request_post, _payload = self._post(
            {"target_type": "endpoint", "credential": {}}, endpoint=endpoint
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            _json(response),
            {
                "error": (
                    "SSH access is disabled on this endpoint. Set the access "
                    "method to 'API + SSH' to use the terminal."
                )
            },
        )
        request_post.assert_not_called()

    def test_disabled_endpoint_refuses_every_target_and_credential_mode(self) -> None:
        endpoint = SimpleNamespace(
            pk=7,
            enabled=False,
            ssh_access_enabled=True,
            ssh_host="pve.example.test",
            has_ssh_terminal_credentials=True,
        )
        credential = {"password": "must-not-be-forwarded"}
        cases = (
            {"target_type": "endpoint"},
            {"target_type": "endpoint", "credential": credential},
            {"target_type": "endpoint", "credential": credential, "store": True},
            {"target_type": "node", "node_id": 19},
            {"target_type": "node", "node_id": 19, "credential": credential},
            {
                "target_type": "node",
                "node_id": 19,
                "credential": credential,
                "store": True,
            },
        )
        with (
            patch.object(
                view_module.ProxmoxEndpointSSHTerminalSessionView,
                "_apply_node_credential",
            ) as apply_node_credential,
            patch.object(view_module, "NodeSSHCredential") as credential_model,
        ):
            for payload in cases:
                with self.subTest(payload=payload):
                    response, request_post, backend_payload = self._post(
                        payload,
                        endpoint=endpoint,
                        node=SimpleNamespace(pk=19, ip_address="node.example.test"),
                    )

                    self.assertEqual(response.status_code, 409)
                    self.assertEqual(
                        _json(response),
                        {"error": "Proxmox endpoint is disabled."},
                    )
                    self.assertEqual(backend_payload, {})
                    request_post.assert_not_called()
                    self.fastapi_getter.assert_not_called()
                    self.node_queryset.filter.assert_not_called()

        apply_node_credential.assert_not_called()
        credential_model.assert_not_called()

    def test_target_validation_failures(self) -> None:
        cases = (
            (
                {"target_type": "node", "node_id": 99},
                None,
                None,
                404,
                {"error": "Node not found for endpoint."},
            ),
            (
                {"target_type": "endpoint", "credential": {}, "store": True},
                None,
                None,
                400,
                {
                    "error": (
                        "Store endpoint SSH credentials from the endpoint's "
                        "SSH settings tab, not the terminal modal."
                    )
                },
            ),
            (
                {"target_type": "endpoint", "credential": {}},
                SimpleNamespace(
                    pk=7,
                    enabled=True,
                    ssh_access_enabled=True,
                    ssh_host="",
                    has_ssh_terminal_credentials=False,
                ),
                None,
                422,
                {"error": "Endpoint has no resolvable SSH host."},
            ),
            (
                {"target_type": "endpoint"},
                SimpleNamespace(
                    pk=7,
                    enabled=True,
                    ssh_access_enabled=True,
                    ssh_host="pve.example.test",
                    has_ssh_terminal_credentials=False,
                ),
                None,
                409,
                {"error": "Endpoint SSH fallback credentials are not configured."},
            ),
            (
                {"target_type": "unsupported"},
                None,
                None,
                400,
                {"error": "Unsupported terminal target."},
            ),
        )
        for payload, endpoint, node, status, expected_payload in cases:
            with self.subTest(payload=payload, status=status):
                response, request_post, _backend_payload = self._post(
                    payload, endpoint=endpoint, node=node
                )
                self.assertEqual(response.status_code, status)
                self.assertEqual(_json(response), expected_payload)
                request_post.assert_not_called()
                self.fastapi_getter.assert_not_called()

    def test_endpoint_one_shot_validation_and_payload(self) -> None:
        valid_data = {
            "username": "root",
            "port": 22,
            "auth_method": "password",
            "password": "one-shot-password",
            "known_host_fingerprint": FINGERPRINT,
        }
        with patch.object(
            view_module,
            "validate_terminal_credential",
            side_effect=(({}, "invalid credential"), (valid_data, None)),
        ):
            invalid, invalid_post, _payload = self._post(
                {"target_type": "endpoint", "credential": {}}
            )
            valid, valid_post, backend_payload = self._post(
                {
                    "target_type": "endpoint",
                    "credential": {},
                    "cols": 999,
                    "rows": 1,
                }
            )

        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(_json(invalid), {"error": "invalid credential"})
        invalid_post.assert_not_called()
        self.assertEqual(valid.status_code, 200)
        valid_post.assert_called_once()
        self.assertEqual((backend_payload["cols"], backend_payload["rows"]), (400, 5))
        self.assertEqual(backend_payload["one_shot_credential"]["username"], "root")

    def test_node_credential_forwards_store_flag_and_controls_payload(self) -> None:
        node = SimpleNamespace(pk=19, ip_address="node.example.test")
        credential_error = JsonResponse({"error": "bad node credential"}, status=400)
        supplied_credential = {"username": "root"}
        calls: list[tuple[object, object, bool, dict[str, object]]] = []

        def apply_credential(
            _view: object,
            request: object,
            target_node: object,
            credential: object,
            store: bool,
            backend_payload: dict[str, object],
        ) -> JsonResponse | None:
            calls.append((request, target_node, store, dict(backend_payload)))
            self.assertEqual(credential, supplied_credential)
            if len(calls) == 1:
                return credential_error
            if not store:
                backend_payload["one_shot_credential"] = {"username": "root"}
            return None

        with patch.object(
            view_module.ProxmoxEndpointSSHTerminalSessionView,
            "_apply_node_credential",
            autospec=True,
            side_effect=apply_credential,
        ) as apply_node_credential:
            invalid, invalid_post, _payload = self._post(
                {
                    "target_type": "node",
                    "node_id": 19,
                    "credential": supplied_credential,
                    "store": True,
                },
                node=node,
            )
            one_shot, one_shot_post, one_shot_payload = self._post(
                {
                    "target_type": "node",
                    "node_id": 19,
                    "credential": supplied_credential,
                    "store": False,
                },
                node=node,
            )
            stored, stored_post, stored_payload = self._post(
                {
                    "target_type": "node",
                    "node_id": 19,
                    "credential": supplied_credential,
                    "store": True,
                },
                node=node,
            )

        self.assertIs(invalid, credential_error)
        self.assertEqual(_json(invalid), {"error": "bad node credential"})
        invalid_post.assert_not_called()
        self.assertEqual(one_shot.status_code, 200)
        one_shot_post.assert_called_once()
        self.assertEqual(
            one_shot_payload["one_shot_credential"],
            {"username": "root"},
        )
        self.assertEqual(stored.status_code, 200)
        stored_post.assert_called_once()
        self.assertNotIn("one_shot_credential", stored_payload)
        self.assertEqual([call[2] for call in calls], [True, False, True])
        for _request, target_node, _store, payload in calls:
            self.assertIs(target_node, node)
            self.assertEqual(payload["node_id"], 19)
            self.assertEqual(payload["host"], "node.example.test")
        self.assertEqual(apply_node_credential.call_count, 3)

    def test_missing_backend_is_unavailable(self) -> None:
        response, request_post, _payload = self._post(fastapi_result=(None, None))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(_json(response), {"error": "No FastAPI endpoint configured."})
        request_post.assert_not_called()

    def test_backend_http_and_response_failures(self) -> None:
        for status_code, expected in ((400, 400), (503, 502)):
            with self.subTest(status_code=status_code):
                response, request_post, _payload = self._post(
                    backend_response=SimpleNamespace(
                        status_code=status_code,
                        text="backend refusal",
                    )
                )
                self.assertEqual(response.status_code, expected)
                self.assertEqual(_json(response), {"error": "backend refusal"})
                request_post.assert_called_once()

        non_json, _post, _payload = self._post(
            backend_response=SimpleNamespace(
                status_code=200,
                text="",
                json=MagicMock(side_effect=ValueError("not json")),
            )
        )
        self.assertEqual(non_json.status_code, 502)
        self.assertEqual(
            _json(non_json),
            {"error": "proxbox-api returned a non-JSON terminal response."},
        )

        context = SimpleNamespace(
            http_url="https://api.example.test",
            ip_address_url=None,
            verify_ssl=True,
            headers={},
            detail={},
        )
        no_websocket, _post, _payload = self._post(backend_context=context)
        self.assertEqual(no_websocket.status_code, 503)
        self.assertEqual(
            _json(no_websocket),
            {"error": "FastAPI endpoint WebSocket URL is not configured."},
        )

    def test_request_exception_tries_next_candidate_then_succeeds(self) -> None:
        calls = 0

        def fail_then_succeed(*args: object, **kwargs: object) -> object:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise view_module.requests.RequestException("first failed")
            return SimpleNamespace(
                status_code=200,
                text="",
                json=lambda: {
                    "session_id": "session-2",
                    "ticket": "ticket-2",
                    "websocket_path": "/ssh/session-2",
                    "expires_at": None,
                },
            )

        response, _request_post, _payload = self._post(
            post_side_effect=fail_then_succeed,
            candidates=[
                ("https://first.example.test/ssh/sessions", True),
                ("https://second.example.test/ssh/sessions", True),
            ],
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(_json(response)["session_id"], "session-2")

    def test_all_request_candidates_failing_returns_last_error(self) -> None:
        response, _request_post, _payload = self._post(
            post_side_effect=view_module.requests.RequestException("last failed"),
            candidates=[("https://only.example.test/ssh/sessions", True)],
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(_json(response), {"error": "last failed"})
