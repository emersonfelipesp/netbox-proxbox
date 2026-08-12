"""Real-NetBox contracts for plugin encryption-key recovery."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
from unittest.mock import patch
import uuid

from cryptography.fernet import Fernet
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
NETBOX_ROOTS = (
    REPO_ROOT.parent / "netbox" / "netbox",
    REPO_ROOT.parents[1] / "nmulticloud-context" / "netbox" / "netbox",
)
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

from django.apps import apps  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.auth.models import Permission  # noqa: E402
from django.core.exceptions import FieldDoesNotExist, ValidationError  # noqa: E402
from django.db import DatabaseError, connection, connections, transaction  # noqa: E402
from django.db.models.signals import post_save  # noqa: E402
from django.test import Client, TestCase, TransactionTestCase  # noqa: E402
from django.test import RequestFactory  # noqa: E402
from django.urls import reverse  # noqa: E402
from django.views.debug import ExceptionReporter  # noqa: E402
from core.models import ObjectChange  # noqa: E402
from ipam.models import IPAddress  # noqa: E402
from utilities.testing import create_test_virtualmachine  # noqa: E402

from netbox_proxbox.api.serializers.settings import (  # noqa: E402
    ProxboxPluginSettingsSerializer,
)
from netbox_proxbox.api.serializers.vm_cloudinit import (  # noqa: E402
    ProxmoxVMCloudInitSerializer,
)


_RESET_REPORTER_MARKER = "legacy-plaintext-reset-reporter-marker"
from netbox_proxbox.forms.settings import (  # noqa: E402
    EncryptedSecretResetForm,
    ProxboxPluginSettingsForm,
)
from netbox_proxbox.models import (  # noqa: E402
    FastAPIEndpoint,
    FirecrackerHost,
    FirecrackerHostPool,
    NodeSSHCredential,
    PBSEndpoint,
    PDMEndpoint,
    ProxmoxEndpoint,
    ProxmoxNode,
    ProxboxPluginSettings,
    ProxmoxVMCloudInit,
)
from netbox_proxbox.services.encryption_recovery import (  # noqa: E402
    BackendEncryptionDependencyError,
    ENCRYPTED_FIELD_FAMILIES,
    RESET_CONFIRMATION_PHRASE,
    CiphertextVerificationFailed,
    EncryptionRecoveryConfigurationError,
    OldEncryptionKeyRejected,
    _locked_encrypted_queryset_update,
    _locked_recovery_conflict_bulk_create,
    available_encrypted_field_families,
    encrypted_family_statuses,
    install_encrypted_writer_guards,
    reset_encrypted_families,
    rotate_encryption_key,
)
from netbox_proxbox.services.backend_key_adoption import (  # noqa: E402
    backend_key_target_fingerprint,
)
from netbox_proxbox.signals import (  # noqa: E402
    ensure_fastapi_endpoint_token,
    ensure_proxmox_endpoint_has_fastapi_token,
)
from netbox_proxbox.utils import encryption as enc_helpers  # noqa: E402
from netbox_proxbox.views.endpoints.proxmox import (  # noqa: E402
    ProxmoxEndpointSSHTerminalSessionView,
)
from netbox_proxbox.views.settings import SettingsView  # noqa: E402


def _raw_update_fields(model: type, pk: object, **updates: object) -> None:
    """Inject legacy/corrupt storage state without exercising guarded write APIs."""

    quote_name = connection.ops.quote_name
    table_name = quote_name(model._meta.db_table)
    assignments = ", ".join(
        f"{quote_name(model._meta.get_field(field_name).column)} = %s"
        for field_name in updates
    )
    pk_column = quote_name(model._meta.pk.column)
    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE {table_name} SET {assignments} WHERE {pk_column} = %s",
            [*updates.values(), pk],
        )


class EncryptionKeyRecoveryTest(TestCase):
    """Exercise atomic rotation and destructive recovery across the registry."""

    def setUp(self) -> None:
        self.old_key = Fernet.generate_key().decode("ascii")
        self.new_key = Fernet.generate_key().decode("ascii")
        settings_obj = ProxboxPluginSettings.get_solo()
        _raw_update_fields(
            ProxboxPluginSettings,
            settings_obj.pk,
            encryption_key=self.old_key,
        )
        self.settings_obj = ProxboxPluginSettings.objects.get(pk=settings_obj.pk)
        self.operator = get_user_model().objects.create_user(
            username="direct-recovery-operator"
        )

        secret = lambda value: enc_helpers.encrypt(value, key=self.old_key)  # noqa: E731
        self.plaintexts = {
            "password_enc": "pve-password-recovery-test",
            "token_value_enc": "pve-token-recovery-test",
            "ssh_password_enc": "pve-ssh-password-recovery-test",
            "ssh_private_key_enc": "pve-private-key-recovery-test",
            "token_enc": "backend-key-recovery-test",
            "pbs_token_secret_enc": "pbs-secret-recovery-test",
            "pdm_token_secret_enc": "pdm-secret-recovery-test",
            "node_password_enc": "node-password-recovery-test",
            "node_private_key_enc": "node-private-key-recovery-test",
            "sshkeys_enc": "ssh-ed25519 recovery-test-public-key",
            "agent_token_enc": "firecracker-agent-recovery-test",
        }

        self.proxmox = ProxmoxEndpoint(
            name="recovery-pve",
            domain="recovery-pve.example.test",
            pushed_credential_fingerprint="pve-push-receipt",
            ssh_known_host_fingerprint="SHA256:" + "A" * 43,
        )
        ProxmoxEndpoint.objects.bulk_create([self.proxmox])
        _raw_update_fields(
            ProxmoxEndpoint,
            self.proxmox.pk,
            password_enc=secret(self.plaintexts["password_enc"]),
            token_value_enc=secret(self.plaintexts["token_value_enc"]),
            ssh_password_enc=secret(self.plaintexts["ssh_password_enc"]),
            ssh_private_key_enc=secret(self.plaintexts["ssh_private_key_enc"]),
        )
        self.proxmox.refresh_from_db()
        self.node = ProxmoxNode.objects.create(
            endpoint=self.proxmox,
            name="recovery-node",
            ip_address="192.0.2.10",
        )
        self.node_credential = NodeSSHCredential(
            node=self.node,
            username="proxbox-discovery",
            known_host_fingerprint="SHA256:" + "B" * 43,
        )
        NodeSSHCredential.objects.bulk_create([self.node_credential])
        _raw_update_fields(
            NodeSSHCredential,
            self.node_credential.pk,
            password_enc=secret(self.plaintexts["node_password_enc"]),
            private_key_enc=secret(self.plaintexts["node_private_key_enc"]),
        )
        self.node_credential.refresh_from_db()

        self.fastapi = FastAPIEndpoint(
            name="recovery-backend",
            domain="recovery-backend.example.test",
            enabled=True,
        )
        self.fastapi.backend_key_target_fingerprint = backend_key_target_fingerprint(
            self.fastapi
        )
        FastAPIEndpoint.objects.bulk_create([self.fastapi])
        _raw_update_fields(
            FastAPIEndpoint,
            self.fastapi.pk,
            token_enc=secret(self.plaintexts["token_enc"]),
        )
        self.fastapi.refresh_from_db()
        independent_attestation = SimpleNamespace(
            status_code=200,
            json=lambda: {
                "attestation_version": 1,
                "active_key_source": "env",
                "encrypted_credentials_verified": True,
            },
            close=lambda: None,
        )
        attestation_patcher = patch(
            "netbox_proxbox.services.encryption_recovery.requests.get",
            return_value=independent_attestation,
        )
        attestation_patcher.start()
        self.addCleanup(attestation_patcher.stop)
        self.pbs = PBSEndpoint(
            name="recovery-pbs",
            domain="recovery-pbs.example.test",
            token_id="root@pam!recovery",
            fingerprint="pbs-trust-receipt",
        )
        PBSEndpoint.objects.bulk_create([self.pbs])
        _raw_update_fields(
            PBSEndpoint,
            self.pbs.pk,
            token_secret_enc=secret(self.plaintexts["pbs_token_secret_enc"]),
        )
        self.pbs.refresh_from_db()
        self.pdm = PDMEndpoint(
            name="recovery-pdm",
            domain="recovery-pdm.example.test",
            token_id="root@pam!recovery",
            fingerprint="pdm-trust-receipt",
        )
        PDMEndpoint.objects.bulk_create([self.pdm])
        _raw_update_fields(
            PDMEndpoint,
            self.pdm.pk,
            token_secret_enc=secret(self.plaintexts["pdm_token_secret_enc"]),
        )
        self.pdm.refresh_from_db()

        self.vm = create_test_virtualmachine("recovery-cloud-init-vm")
        self.cloud_init = ProxmoxVMCloudInit.objects.create(
            virtual_machine=self.vm,
            sshkeys_enc=secret(self.plaintexts["sshkeys_enc"]),
        )
        self.pool = FirecrackerHostPool.objects.create(
            name="Recovery pool", slug="recovery-pool"
        )
        self.firecracker = FirecrackerHost(
            pool=self.pool,
            name="recovery-firecracker-host",
            agent_base_url="https://firecracker-agent.example.test",
        )
        FirecrackerHost.objects.bulk_create([self.firecracker])
        _raw_update_fields(
            FirecrackerHost,
            self.firecracker.pk,
            agent_token_enc=secret(self.plaintexts["agent_token_enc"]),
        )
        self.firecracker.refresh_from_db()

    def _ciphertext_snapshot(self) -> dict[tuple[str, object], tuple[object, ...]]:
        snapshot: dict[tuple[str, object], tuple[object, ...]] = {}
        for family in available_encrypted_field_families():
            model = apps.get_model(family.model_label)
            fields = (*family.encrypted_fields, *family.trust_fields)
            for values in model.objects.values_list("pk", *fields).order_by("pk"):
                snapshot[(family.key, values[0])] = tuple(values[1:])
        return snapshot

    def test_rotation_reencrypts_every_registered_field_family(self) -> None:
        request_id = uuid.uuid4()
        result = rotate_encryption_key(
            old_key=self.old_key,
            new_key=self.new_key,
            audit_actor=self.operator,
            audit_request_id=request_id,
        )

        self.assertEqual(result.rows_rotated, 7)
        self.assertEqual(result.ciphertext_values_rotated, 11)
        self.settings_obj.refresh_from_db()
        self.assertEqual(self.settings_obj.encryption_key, self.new_key)

        expected_plaintexts = iter(self.plaintexts.values())
        for family in available_encrypted_field_families():
            model = apps.get_model(family.model_label)
            row = model.objects.get()
            for field_name in family.encrypted_fields:
                ciphertext = str(getattr(row, field_name))
                self.assertEqual(
                    enc_helpers.decrypt(ciphertext, key=self.new_key),
                    next(expected_plaintexts),
                )
                with self.assertRaises(enc_helpers.DecryptionFailed):
                    enc_helpers.decrypt(ciphertext, key=self.old_key)

        audit = ObjectChange.objects.get(request_id=request_id)
        self.assertEqual(audit.user, self.operator)
        self.assertEqual(
            audit.postchange_data["encryption_recovery"]["operation"], "rotate"
        )
        audit_text = str(audit.postchange_data)
        self.assertNotIn(self.old_key, audit_text)
        self.assertNotIn(self.new_key, audit_text)
        for plaintext in self.plaintexts.values():
            self.assertNotIn(plaintext, audit_text)

    def test_queryset_update_rejects_encrypted_fields(self) -> None:
        original = self.proxmox.password_enc

        with self.assertRaises(ValidationError):
            ProxmoxEndpoint.objects.filter(pk=self.proxmox.pk).update(
                password_enc=enc_helpers.encrypt("queryset-write", key=self.old_key)
            )

        self.proxmox.refresh_from_db()
        self.assertEqual(self.proxmox.password_enc, original)

    def test_base_manager_queryset_update_rejects_encrypted_fields(self) -> None:
        original = self.proxmox.password_enc

        with self.assertRaises(ValidationError):
            ProxmoxEndpoint._base_manager.filter(pk=self.proxmox.pk).update(
                password_enc=enc_helpers.encrypt(
                    "base-manager-queryset-write", key=self.old_key
                )
            )

        self.proxmox.refresh_from_db()
        self.assertEqual(self.proxmox.password_enc, original)

    def test_bulk_update_rejects_encrypted_fields(self) -> None:
        original = self.proxmox.password_enc
        self.proxmox.password_enc = enc_helpers.encrypt(
            "bulk-update-write", key=self.old_key
        )

        with self.assertRaises(ValidationError):
            ProxmoxEndpoint.objects.bulk_update([self.proxmox], fields=["password_enc"])

        self.proxmox.refresh_from_db()
        self.assertEqual(self.proxmox.password_enc, original)

    def test_base_manager_bulk_update_rejects_encrypted_fields(self) -> None:
        original = self.proxmox.password_enc
        self.proxmox.password_enc = enc_helpers.encrypt(
            "base-manager-bulk-update", key=self.old_key
        )

        with self.assertRaises(ValidationError):
            ProxmoxEndpoint._base_manager.bulk_update(
                [self.proxmox], fields=["password_enc"]
            )

        self.proxmox.refresh_from_db()
        self.assertEqual(self.proxmox.password_enc, original)

    def test_bulk_create_rejects_nonempty_encrypted_fields(self) -> None:
        endpoint = ProxmoxEndpoint(
            name="forbidden-bulk-create-pve",
            domain="forbidden-bulk-create-pve.example.test",
            password_enc=enc_helpers.encrypt("bulk-create-write", key=self.old_key),
        )

        with self.assertRaises(ValidationError):
            ProxmoxEndpoint.objects.bulk_create([endpoint])

        self.assertFalse(ProxmoxEndpoint.objects.filter(name=endpoint.name).exists())

    def test_base_manager_bulk_create_rejects_nonempty_encrypted_fields(self) -> None:
        endpoint = ProxmoxEndpoint(
            name="forbidden-base-manager-bulk-create-pve",
            domain="forbidden-base-manager-bulk-create-pve.example.test",
            password_enc=enc_helpers.encrypt(
                "base-manager-bulk-create", key=self.old_key
            ),
        )

        with self.assertRaises(ValidationError):
            ProxmoxEndpoint._base_manager.bulk_create([endpoint])

        self.assertFalse(ProxmoxEndpoint.objects.filter(name=endpoint.name).exists())

    def test_queryset_update_rejects_settings_key_mutation(self) -> None:
        with self.assertRaises(ValidationError):
            ProxboxPluginSettings.objects.filter(pk=self.settings_obj.pk).update(
                encryption_key=self.new_key
            )

        self.settings_obj.refresh_from_db()
        self.assertEqual(self.settings_obj.encryption_key, self.old_key)

    def test_base_manager_queryset_update_rejects_settings_key_mutation(self) -> None:
        with self.assertRaises(ValidationError):
            ProxboxPluginSettings._base_manager.filter(pk=self.settings_obj.pk).update(
                encryption_key=self.new_key
            )

        self.settings_obj.refresh_from_db()
        self.assertEqual(self.settings_obj.encryption_key, self.old_key)

    def test_bulk_update_rejects_settings_key_mutation(self) -> None:
        candidate = ProxboxPluginSettings.objects.get(pk=self.settings_obj.pk)
        candidate.encryption_key = self.new_key

        with self.assertRaises(ValidationError):
            ProxboxPluginSettings._base_manager.bulk_update(
                [candidate], fields=["encryption_key"]
            )

        self.settings_obj.refresh_from_db()
        self.assertEqual(self.settings_obj.encryption_key, self.old_key)

    def test_internal_queryset_bypass_validates_the_locked_current_key(self) -> None:
        original = self.proxmox.password_enc
        wrong_key_ciphertext = enc_helpers.encrypt(
            "wrong-key-internal-write", key=self.new_key
        )

        with self.assertRaises(EncryptionRecoveryConfigurationError):
            _locked_encrypted_queryset_update(
                ProxmoxEndpoint.objects.filter(pk=self.proxmox.pk),
                password_enc=wrong_key_ciphertext,
            )

        self.proxmox.refresh_from_db()
        self.assertEqual(self.proxmox.password_enc, original)

    def test_internal_conflict_upsert_permit_updates_protected_field(self) -> None:
        conflict = FirecrackerHost(
            pool=self.pool,
            name=self.firecracker.name,
            agent_base_url=self.firecracker.agent_base_url,
            status="ready",
        )

        _locked_recovery_conflict_bulk_create(
            FirecrackerHost._base_manager.all(),
            [conflict],
            update_conflicts=True,
            update_fields=["status"],
            unique_fields=["pool", "name"],
        )

        self.firecracker.refresh_from_db()
        self.assertEqual(self.firecracker.status, "ready")

    def test_rotation_repairs_a_drifted_stored_key_when_ciphertext_proves_old_key(
        self,
    ) -> None:
        drifted_stored_key = Fernet.generate_key().decode("ascii")
        _raw_update_fields(
            ProxboxPluginSettings,
            self.settings_obj.pk,
            encryption_key=drifted_stored_key,
        )

        result = rotate_encryption_key(
            old_key=self.old_key,
            new_key=self.new_key,
            audit_actor=self.operator,
            audit_request_id=uuid.uuid4(),
        )

        self.assertEqual(result.ciphertext_values_rotated, 11)
        self.settings_obj.refresh_from_db()
        self.assertEqual(self.settings_obj.encryption_key, self.new_key)
        self.proxmox.refresh_from_db()
        self.assertEqual(
            enc_helpers.decrypt(self.proxmox.password_enc, key=self.new_key),
            self.plaintexts["password_enc"],
        )

    def test_rotation_blocks_legacy_source_only_backend_attestation(self) -> None:
        fingerprint = backend_key_target_fingerprint(self.fastapi)
        FastAPIEndpoint.objects.filter(pk=self.fastapi.pk).update(
            enabled=True,
            backend_key_target_fingerprint=fingerprint,
        )
        response = SimpleNamespace(
            status_code=200,
            # This is the current proxbox-api response. Even ``source=env``
            # cannot prove that the cached key or existing ciphertext migrated.
            json=lambda: {"configured": True, "source": "env"},
            close=lambda: None,
        )

        with (
            patch(
                "netbox_proxbox.services.encryption_recovery.requests.get",
                return_value=response,
            ),
            self.assertRaises(BackendEncryptionDependencyError),
        ):
            rotate_encryption_key(
                old_key=self.old_key,
                new_key=self.new_key,
                audit_actor=self.operator,
                audit_request_id=uuid.uuid4(),
            )

        self.settings_obj.refresh_from_db()
        self.assertEqual(self.settings_obj.encryption_key, self.old_key)
        self.assertEqual(
            enc_helpers.decrypt(self.proxmox.password_enc, key=self.old_key),
            self.plaintexts["password_enc"],
        )

    def test_rotation_accepts_independent_backend_encryption_attestation(self) -> None:
        fingerprint = backend_key_target_fingerprint(self.fastapi)
        FastAPIEndpoint.objects.filter(pk=self.fastapi.pk).update(
            enabled=True,
            backend_key_target_fingerprint=fingerprint,
        )
        response = SimpleNamespace(
            status_code=200,
            json=lambda: {
                "attestation_version": 1,
                "active_key_source": "env",
                "encrypted_credentials_verified": True,
            },
            close=lambda: None,
        )

        with patch(
            "netbox_proxbox.services.encryption_recovery.requests.get",
            return_value=response,
        ) as get_status:
            rotate_encryption_key(
                old_key=self.old_key,
                new_key=self.new_key,
                audit_actor=self.operator,
                audit_request_id=uuid.uuid4(),
            )

        get_status.assert_called_once()
        self.settings_obj.refresh_from_db()
        self.assertEqual(self.settings_obj.encryption_key, self.new_key)

    def test_rotation_never_contacts_a_disabled_backend(self) -> None:
        FastAPIEndpoint.objects.filter(pk=self.fastapi.pk).update(enabled=False)

        with patch(
            "netbox_proxbox.services.encryption_recovery.requests.get"
        ) as get_status:
            rotate_encryption_key(
                old_key=self.old_key,
                new_key=self.new_key,
                audit_actor=self.operator,
                audit_request_id=uuid.uuid4(),
            )

        get_status.assert_not_called()
        self.fastapi.refresh_from_db()
        self.assertFalse(self.fastapi.enabled)
        self.assertEqual(
            enc_helpers.decrypt(self.fastapi.token_enc, key=self.new_key),
            self.plaintexts["token_enc"],
        )

    def test_attestation_dials_one_captured_ip_target(self) -> None:
        old_ip = IPAddress.objects.create(address="192.0.2.80/32")
        new_address = "192.0.2.81/32"
        FastAPIEndpoint.objects.filter(pk=self.fastapi.pk).update(
            domain="",
            ip_address=old_ip,
        )
        endpoint = FastAPIEndpoint.objects.get(pk=self.fastapi.pk)
        FastAPIEndpoint.objects.filter(pk=endpoint.pk).update(
            backend_key_target_fingerprint=backend_key_target_fingerprint(endpoint)
        )
        original_resolver = FastAPIEndpoint.backend_key_ip_address_for_trust
        resolver_calls = 0

        def mutate_after_capture(instance: FastAPIEndpoint) -> object | None:
            nonlocal resolver_calls
            resolver_calls += 1
            captured = original_resolver(instance)
            if resolver_calls == 1:
                IPAddress.objects.filter(pk=old_ip.pk).update(address=new_address)
            return captured

        response = SimpleNamespace(
            status_code=200,
            json=lambda: {
                "attestation_version": 1,
                "active_key_source": "env",
                "encrypted_credentials_verified": True,
            },
            close=lambda: None,
        )
        with (
            patch.object(
                FastAPIEndpoint,
                "backend_key_ip_address_for_trust",
                autospec=True,
                side_effect=mutate_after_capture,
            ),
            patch(
                "netbox_proxbox.services.encryption_recovery.requests.get",
                return_value=response,
            ) as get_status,
        ):
            rotate_encryption_key(
                old_key=self.old_key,
                new_key=self.new_key,
                audit_actor=self.operator,
                audit_request_id=uuid.uuid4(),
            )

        self.assertEqual(resolver_calls, 1)
        called_url = str(get_status.call_args.args[0])
        self.assertIn("192.0.2.80", called_url)
        self.assertNotIn("192.0.2.81", called_url)

    def test_absent_optional_pbs_app_is_the_only_skipped_registry_state(self) -> None:
        self.assertFalse(apps.is_installed("netbox_pbs"))
        self.assertIn(
            "pbs_fallback_api", {family.key for family in ENCRYPTED_FIELD_FAMILIES}
        )
        self.assertNotIn(
            "pbs_fallback_api",
            {family.key for family in available_encrypted_field_families()},
        )

    def test_dormant_optional_pbs_ciphertext_blocks_rotation(self) -> None:
        if connection.vendor != "postgresql":
            self.skipTest("Dormant companion locking is PostgreSQL-specific.")

        dormant_ciphertext = enc_helpers.encrypt(
            "dormant-pbs-fallback-key", key=self.old_key
        )
        table_name = "netbox_pbs_pbspluginsettings"
        quoted_table = connection.ops.quote_name(table_name)
        quoted_column = connection.ops.quote_name("proxbox_api_key_enc")
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE TABLE {quoted_table} "
                f"(id bigint PRIMARY KEY, {quoted_column} text NOT NULL)"
            )
            cursor.execute(
                f"INSERT INTO {quoted_table} (id, {quoted_column}) VALUES (%s, %s)",
                [1, dormant_ciphertext],
            )
        try:
            with self.assertRaises(EncryptionRecoveryConfigurationError):
                rotate_encryption_key(
                    old_key=self.old_key,
                    new_key=self.new_key,
                    audit_actor=self.operator,
                    audit_request_id=uuid.uuid4(),
                )
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT {quoted_column} FROM {quoted_table} WHERE id = %s", [1]
                )
                stored = cursor.fetchone()
            self.assertIsNotNone(stored)
            self.assertEqual(
                enc_helpers.decrypt(str(stored[0]), key=self.old_key),
                "dormant-pbs-fallback-key",
            )
        finally:
            with connection.cursor() as cursor:
                cursor.execute(f"DROP TABLE {quoted_table}")

    def test_installed_optional_pbs_app_with_unresolved_model_fails_closed(
        self,
    ) -> None:
        real_get_app_config = apps.get_app_config
        real_get_model = apps.get_model

        def get_app_config(app_label: str) -> object:
            if app_label == "netbox_pbs":
                return object()
            return real_get_app_config(app_label)

        def get_model(model_label: str) -> type | None:
            if model_label == "netbox_pbs.PBSPluginSettings":
                return None
            return real_get_model(model_label)

        with (
            patch.object(apps, "get_app_config", side_effect=get_app_config),
            patch.object(apps, "get_model", side_effect=get_model),
            self.assertRaises(EncryptionRecoveryConfigurationError),
        ):
            available_encrypted_field_families()

        with (
            patch.object(apps, "get_app_config", side_effect=get_app_config),
            patch.object(apps, "get_model", side_effect=get_model),
            patch(
                "netbox_proxbox.services.encryption_recovery.logger.critical"
            ) as critical,
        ):
            install_encrypted_writer_guards()
        critical.assert_called_once()

    def test_installed_optional_pbs_app_with_missing_table_fails_closed(self) -> None:
        real_get_app_config = apps.get_app_config
        real_get_model = apps.get_model

        class MissingTableManager:
            def filter(self, *_args: object, **_kwargs: object) -> object:
                raise DatabaseError("simulated missing netbox-pbs settings table")

        class InstalledPBSSettingsMeta:
            db_table = "netbox_pbs_pbspluginsettings"

            @staticmethod
            def get_field(_field_name: str) -> object:
                return type("InstalledPBSField", (), {"null": False})()

        class InstalledPBSSettings:
            objects = MissingTableManager()
            _meta = InstalledPBSSettingsMeta()

        def get_app_config(app_label: str) -> object:
            if app_label == "netbox_pbs":
                return object()
            return real_get_app_config(app_label)

        def get_model(model_label: str) -> type | None:
            if model_label == "netbox_pbs.PBSPluginSettings":
                return InstalledPBSSettings
            return real_get_model(model_label)

        request = RequestFactory().get("/plugins/proxbox/settings/")
        with (
            patch.object(apps, "get_app_config", side_effect=get_app_config),
            patch.object(apps, "get_model", side_effect=get_model),
        ):
            try:
                encrypted_family_statuses(key=self.old_key)
            except EncryptionRecoveryConfigurationError as exc:
                report = ExceptionReporter(
                    request,
                    type(exc),
                    exc,
                    exc.__traceback__,
                ).get_traceback_text()
            else:  # pragma: no cover - the installed owner must fail closed
                self.fail("The simulated missing companion table was accepted.")

        self.assertNotIn(self.old_key, report)

    def test_installed_optional_pbs_app_with_schema_drift_fails_closed(self) -> None:
        real_get_app_config = apps.get_app_config
        real_get_model = apps.get_model

        class DriftedPBSSettingsMeta:
            @staticmethod
            def get_field(_field_name: str) -> object:
                raise FieldDoesNotExist("simulated missing encrypted field")

        class DriftedPBSSettings:
            _meta = DriftedPBSSettingsMeta()

        def get_app_config(app_label: str) -> object:
            if app_label == "netbox_pbs":
                return object()
            return real_get_app_config(app_label)

        def get_model(model_label: str) -> type | None:
            if model_label == "netbox_pbs.PBSPluginSettings":
                return DriftedPBSSettings
            return real_get_model(model_label)

        request = RequestFactory().get("/plugins/proxbox/settings/")
        with (
            patch.object(apps, "get_app_config", side_effect=get_app_config),
            patch.object(apps, "get_model", side_effect=get_model),
        ):
            try:
                encrypted_family_statuses(key=self.old_key)
            except EncryptionRecoveryConfigurationError as exc:
                report = ExceptionReporter(
                    request,
                    type(exc),
                    exc,
                    exc.__traceback__,
                ).get_traceback_text()
            else:  # pragma: no cover - the installed owner must fail closed
                self.fail("The simulated companion schema drift was accepted.")

        self.assertNotIn(self.old_key, report)

    def test_optional_pbs_setter_ciphertext_can_cross_its_serializer_probe(
        self,
    ) -> None:
        """The installed companion's write-only API probe remains a valid writer."""

        encryption_key = self.old_key
        persisted = {
            "ciphertext": enc_helpers.encrypt("old-fallback-key", key=encryption_key)
        }

        class CompanionQuery:
            fields: tuple[str, ...] = ()
            model: type | None = None

            def __init__(self, model: type | None = None) -> None:
                self.model = model

            def values_list(self, *fields: str) -> CompanionQuery:
                self.fields = fields
                return self

            def first(self) -> tuple[str, ...]:
                return tuple(persisted["ciphertext"] for _field in self.fields)

            def update(self, **_updates: object) -> int:
                return 0

            def bulk_update(
                self, _objs: object, _fields: object, **_kwargs: object
            ) -> int:
                return 0

            def bulk_create(self, objs: object, **_kwargs: object) -> object:
                return objs

        class CompanionManager:
            model: type | None = None

            def using(self, _using: str) -> CompanionManager:
                return self

            def filter(self, **_kwargs: object) -> CompanionQuery:
                return CompanionQuery()

            def all(self) -> CompanionQuery:
                return CompanionQuery(self.model)

        class CompanionMeta:
            db_table = "netbox_pbs_pbspluginsettings"

            @staticmethod
            def get_field(_field_name: str) -> object:
                return object()

        class InstalledPBSSettings:
            objects = CompanionManager()
            _default_manager = objects
            _base_manager = objects
            _meta = CompanionMeta()

            def __init__(self, *, pk: int | None = None) -> None:
                self.pk = pk
                self._state = SimpleNamespace(db=None)
                self.proxbox_api_key_enc = persisted["ciphertext"] if pk else ""

            def set_proxbox_api_key(self, plaintext: str) -> None:
                self.proxbox_api_key_enc = enc_helpers.encrypt(
                    plaintext, key=encryption_key
                )

            def save(self, *_args: object, **_kwargs: object) -> None:
                persisted["ciphertext"] = str(self.proxbox_api_key_enc)

        InstalledPBSSettings.objects.model = InstalledPBSSettings

        real_get_app_config = apps.get_app_config
        real_get_model = apps.get_model

        def get_app_config(app_label: str) -> object:
            if app_label == "netbox_pbs":
                return object()
            return real_get_app_config(app_label)

        def get_model(model_label: str) -> type | None:
            if model_label == "netbox_pbs.PBSPluginSettings":
                return InstalledPBSSettings
            return real_get_model(model_label)

        with (
            patch.object(apps, "get_app_config", side_effect=get_app_config),
            patch.object(apps, "get_model", side_effect=get_model),
        ):
            install_encrypted_writer_guards()
            probe = InstalledPBSSettings()
            # netbox-pbs validates on this temporary object, then copies the
            # resulting ciphertext through its serializer's validated_data.
            probe.set_proxbox_api_key("replacement-fallback-key")
            persisted_instance = InstalledPBSSettings(pk=1)
            persisted_instance.proxbox_api_key_enc = probe.proxbox_api_key_enc
            persisted_instance.save(update_fields=("proxbox_api_key_enc",))

        self.assertEqual(
            enc_helpers.decrypt(persisted["ciphertext"], key=self.old_key),
            "replacement-fallback-key",
        )
        self.assertIs(type(persisted_instance.proxbox_api_key_enc), str)

        persisted_instance.proxbox_api_key_enc = enc_helpers.encrypt(
            "unmarked-direct-write", key=self.old_key
        )
        with self.assertRaises(ValidationError):
            persisted_instance.save(update_fields=("proxbox_api_key_enc",))

    def test_wrong_old_key_changes_nothing(self) -> None:
        before = self._ciphertext_snapshot()
        wrong_key = Fernet.generate_key().decode("ascii")

        with self.assertRaises(OldEncryptionKeyRejected):
            rotate_encryption_key(
                old_key=wrong_key,
                new_key=self.new_key,
                audit_actor=self.operator,
                audit_request_id=uuid.uuid4(),
            )

        self.assertEqual(self._ciphertext_snapshot(), before)
        self.settings_obj.refresh_from_db()
        self.assertEqual(self.settings_obj.encryption_key, self.old_key)

    def test_one_corrupt_value_rolls_back_the_entire_rotation(self) -> None:
        _raw_update_fields(
            FirecrackerHost,
            self.firecracker.pk,
            agent_token_enc="corrupt-ciphertext-recovery-test",
        )
        before = self._ciphertext_snapshot()

        with self.assertRaises(CiphertextVerificationFailed):
            rotate_encryption_key(
                old_key=self.old_key,
                new_key=self.new_key,
                audit_actor=self.operator,
                audit_request_id=uuid.uuid4(),
            )

        self.assertEqual(self._ciphertext_snapshot(), before)
        self.settings_obj.refresh_from_db()
        self.assertEqual(self.settings_obj.encryption_key, self.old_key)

    def test_unexpected_rotation_failure_masks_every_secret_frame_local(self) -> None:
        request = RequestFactory().post(
            "/plugins/proxbox/settings/encryption-key/rotate/",
            {
                "old_key": self.old_key,
                "new_key": self.new_key,
                "confirm_new_key": self.new_key,
            },
        )
        request.sensitive_post_parameters = (
            "old_key",
            "new_key",
            "confirm_new_key",
        )

        with patch.object(
            enc_helpers,
            "encrypt",
            side_effect=RuntimeError("simulated unexpected encryption failure"),
        ):
            try:
                rotate_encryption_key(
                    old_key=self.old_key,
                    new_key=self.new_key,
                    audit_actor=self.operator,
                    audit_request_id=uuid.uuid4(),
                )
            except RuntimeError as exc:
                report = ExceptionReporter(
                    request,
                    type(exc),
                    exc,
                    exc.__traceback__,
                ).get_traceback_text()
            else:  # pragma: no cover - test must exercise the unexpected path
                self.fail("The injected encryption failure did not escape.")

        self.assertNotIn(self.old_key, report)
        self.assertNotIn(self.new_key, report)
        for plaintext in self.plaintexts.values():
            self.assertNotIn(plaintext, report)

    def test_unexpected_reset_failure_masks_key_and_collected_credential_material(
        self,
    ) -> None:
        _raw_update_fields(
            ProxmoxEndpoint,
            self.proxmox.pk,
            password_enc=_RESET_REPORTER_MARKER,
        )
        request = RequestFactory().post(
            "/plugins/proxbox/settings/encrypted-secrets/reset/",
            {
                "families": ["proxmox_api"],
                "confirmation": RESET_CONFIRMATION_PHRASE,
            },
        )

        with patch(
            "netbox_proxbox.services.encryption_recovery."
            "record_encryption_recovery_event",
            side_effect=RuntimeError("simulated post-collection reset failure"),
        ):
            try:
                reset_encrypted_families(
                    family_keys=["proxmox_api"],
                    confirmation=RESET_CONFIRMATION_PHRASE,
                    audit_actor=self.operator,
                    audit_request_id=uuid.uuid4(),
                )
            except RuntimeError as exc:
                report = ExceptionReporter(
                    request,
                    type(exc),
                    exc,
                    exc.__traceback__,
                ).get_traceback_html()
            else:  # pragma: no cover - test must exercise the unexpected path
                self.fail("The injected reset failure did not escape.")

        self.assertNotIn(self.old_key, report)
        self.assertNotIn(_RESET_REPORTER_MARKER, report)
        self.assertNotIn(self.proxmox.token_value_enc, report)
        self.proxmox.refresh_from_db()
        self.assertEqual(self.proxmox.password_enc, _RESET_REPORTER_MARKER)

    def test_ordinary_model_and_api_key_replacement_are_rejected(self) -> None:
        self.settings_obj.encryption_key = self.new_key
        with self.assertRaises(ValidationError):
            self.settings_obj.save(update_fields=["encryption_key"])

        serializer = ProxboxPluginSettingsSerializer(
            instance=ProxboxPluginSettings.objects.get(pk=self.settings_obj.pk),
            data={"encryption_key": ""},
            partial=True,
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("encryption_key", serializer.errors)

        form = ProxboxPluginSettingsForm(
            encryption_key_configured=True,
            encryption_key_locked=True,
        )
        self.assertTrue(form.fields["encryption_key"].disabled)
        self.assertTrue(form.fields["encryption_enabled"].disabled)

    def test_initial_settings_key_failure_masks_post_and_frame_locals(self) -> None:
        submitted_key = Fernet.generate_key().decode("ascii")
        settings_obj = ProxboxPluginSettings.objects.get(pk=self.settings_obj.pk)
        _raw_update_fields(ProxboxPluginSettings, settings_obj.pk, encryption_key="")
        cleaned_data = {
            "use_guest_agent_interface_name": False,
            "proxbox_fetch_max_concurrency": 8,
            "ignore_ipv6_link_local_addresses": False,
            "primary_ip_preference": "ipv4",
            "backend_log_file_path": "",
            "netbox_max_concurrent": 1,
            "netbox_timeout": 120,
            "netbox_write_concurrency": 8,
            "proxmox_fetch_concurrency": 8,
            "netbox_max_retries": 5,
            "netbox_retry_delay": 2.0,
            "netbox_get_cache_ttl": 60.0,
            "netbox_get_cache_max_entries": 4096,
            "netbox_get_cache_max_bytes": 52_428_800,
            "bulk_batch_size": 50,
            "bulk_batch_delay_ms": 500,
            "backup_batch_size": 5,
            "backup_batch_delay_ms": 200,
            "interface_batch_size": 5,
            "interface_batch_delay_ms": 100,
            "vm_sync_max_concurrency": 4,
            "reconciliation_engine": "python",
            "proxmox_timeout": 5,
            "proxmox_max_retries": 0,
            "proxmox_retry_backoff": 0.5,
            "ceph_task_timeout": 300,
            "ceph_task_poll_interval": 1,
            "ceph_run_lease_seconds": 360,
            "encryption_enabled": True,
            "encryption_key": submitted_key,
        }

        class AcceptedSettingsForm:
            def __init__(self, *_args: object, **_kwargs: object) -> None:
                self.cleaned_data = cleaned_data

            def is_valid(self) -> bool:
                return True

        request = RequestFactory().post(
            "/plugins/proxbox/settings/",
            {"encryption_key": submitted_key},
        )
        request.user = get_user_model().objects.create_superuser(
            username="initial-key-reporter", password="not-a-secret"
        )
        with (
            patch(
                "netbox_proxbox.views.settings.ProxboxPluginSettingsForm",
                AcceptedSettingsForm,
            ),
            patch.object(
                ProxboxPluginSettings,
                "save",
                side_effect=RuntimeError("simulated initial-key save failure"),
            ),
        ):
            try:
                SettingsView.as_view()(request)
            except RuntimeError as exc:
                report = ExceptionReporter(
                    request,
                    type(exc),
                    exc,
                    exc.__traceback__,
                ).get_traceback_text()
            else:  # pragma: no cover - test must exercise the unexpected path
                self.fail("The injected settings failure did not escape.")

        self.assertNotIn(submitted_key, report)

    def test_real_settings_save_failure_masks_loaded_previous_key(self) -> None:
        settings_obj = ProxboxPluginSettings.objects.get(pk=self.settings_obj.pk)
        request = RequestFactory().get("/plugins/proxbox/settings/")
        parent_model = ProxboxPluginSettings.__mro__[1]

        with patch.object(
            parent_model,
            "save",
            side_effect=DatabaseError("simulated database settings-save failure"),
        ):
            try:
                settings_obj.save(update_fields=["encryption_key"])
            except DatabaseError as exc:
                report = ExceptionReporter(
                    request,
                    type(exc),
                    exc,
                    exc.__traceback__,
                ).get_traceback_text()
            else:  # pragma: no cover - test must exercise the real save frame
                self.fail("The injected parent-model save failure did not escape.")

        self.assertIn("simulated database settings-save failure", report)
        self.assertNotIn(self.old_key, report)

    def test_settings_serializer_save_failure_masks_validated_key(self) -> None:
        serializer = ProxboxPluginSettingsSerializer(
            instance=ProxboxPluginSettings.objects.get(pk=self.settings_obj.pk),
            data={"encryption_key": self.old_key},
            partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        request = RequestFactory().patch("/api/plugins/proxbox/settings/1/")
        parent_model = ProxboxPluginSettings.__mro__[1]

        with patch.object(
            parent_model,
            "save",
            side_effect=DatabaseError("simulated serializer settings-save failure"),
        ):
            try:
                serializer.save()
            except DatabaseError as exc:
                report = ExceptionReporter(
                    request,
                    type(exc),
                    exc,
                    exc.__traceback__,
                ).get_traceback_text()
            else:  # pragma: no cover - test must exercise serializer mutation frames
                self.fail("The injected serializer save failure did not escape.")

        self.assertIn("simulated serializer settings-save failure", report)
        self.assertNotIn(self.old_key, report)

    def test_selective_reset_clears_trust_state_without_save_signals(self) -> None:
        calls: list[object] = []
        stale_proxmox = ProxmoxEndpoint.objects.get(pk=self.proxmox.pk)
        _raw_update_fields(
            ProxmoxEndpoint, self.proxmox.pk, password_enc="corrupt-proxmox-password"
        )
        _raw_update_fields(
            PBSEndpoint,
            self.pbs.pk,
            token_secret_enc="corrupt-pbs-token",
        )

        def record_save(*, instance: object, **_kwargs: object) -> None:
            calls.append(instance)

        post_save.connect(
            record_save,
            sender=ProxmoxEndpoint,
            dispatch_uid="test_recovery_reset_proxmox_no_save",
        )
        post_save.connect(
            record_save,
            sender=PBSEndpoint,
            dispatch_uid="test_recovery_reset_pbs_no_save",
        )
        try:
            result = reset_encrypted_families(
                family_keys=["proxmox_api", "pbs_api"],
                confirmation=RESET_CONFIRMATION_PHRASE,
                audit_actor=self.operator,
                audit_request_id=uuid.uuid4(),
            )
        finally:
            post_save.disconnect(
                sender=ProxmoxEndpoint,
                dispatch_uid="test_recovery_reset_proxmox_no_save",
            )
            post_save.disconnect(
                sender=PBSEndpoint,
                dispatch_uid="test_recovery_reset_pbs_no_save",
            )

        self.assertEqual(result.rows_matched, 2)
        self.assertEqual(calls, [])
        self.proxmox.refresh_from_db()
        self.pbs.refresh_from_db()
        self.assertEqual(self.proxmox.password_enc, "")
        self.assertEqual(
            enc_helpers.decrypt(self.proxmox.token_value_enc, key=self.old_key),
            self.plaintexts["token_value_enc"],
        )
        self.assertEqual(self.proxmox.pushed_credential_fingerprint, "")
        self.assertFalse(self.proxmox.enabled)
        self.assertNotEqual(self.proxmox.ssh_password_enc, "")
        self.assertNotEqual(self.proxmox.ssh_known_host_fingerprint, "")
        self.assertEqual(self.pbs.token_secret_enc, "")
        self.assertIsNone(self.pbs.fingerprint)
        self.assertFalse(self.pbs.enabled)
        self.pdm.refresh_from_db()
        self.assertNotEqual(self.pdm.token_secret_enc, "")

        with self.assertRaises(ValidationError):
            stale_proxmox.save()
        self.proxmox.refresh_from_db()
        self.assertEqual(self.proxmox.password_enc, "")
        self.assertFalse(self.proxmox.enabled)

    def test_family_reset_preserves_healthy_fields_and_rows(self) -> None:
        healthy_password = enc_helpers.encrypt("healthy-password", key=self.old_key)
        healthy_token = enc_helpers.encrypt("healthy-token", key=self.old_key)
        healthy = ProxmoxEndpoint(
            name="healthy-recovery-pve",
            domain="healthy-recovery-pve.example.test",
            enabled=True,
            pushed_credential_fingerprint="healthy-push-receipt",
        )
        ProxmoxEndpoint.objects.bulk_create([healthy])
        _raw_update_fields(
            ProxmoxEndpoint,
            healthy.pk,
            password_enc=healthy_password,
            token_value_enc=healthy_token,
        )
        healthy.refresh_from_db()
        original_token = self.proxmox.token_value_enc
        _raw_update_fields(
            ProxmoxEndpoint, self.proxmox.pk, password_enc="corrupt-selected-password"
        )

        result = reset_encrypted_families(
            family_keys=["proxmox_api"],
            confirmation=RESET_CONFIRMATION_PHRASE,
            audit_actor=self.operator,
            audit_request_id=uuid.uuid4(),
        )

        self.assertEqual(result.rows_matched, 1)
        self.proxmox.refresh_from_db()
        healthy.refresh_from_db()
        self.assertEqual(self.proxmox.password_enc, "")
        self.assertEqual(self.proxmox.token_value_enc, original_token)
        self.assertFalse(self.proxmox.enabled)
        self.assertEqual(self.proxmox.pushed_credential_fingerprint, "")
        self.assertEqual(healthy.password_enc, healthy_password)
        self.assertEqual(healthy.token_value_enc, healthy_token)
        self.assertTrue(healthy.enabled)
        self.assertEqual(healthy.pushed_credential_fingerprint, "healthy-push-receipt")

    def test_explicit_credential_reentry_after_reset_is_allowed(self) -> None:
        _raw_update_fields(
            ProxmoxEndpoint,
            self.proxmox.pk,
            password_enc="corrupt-password-for-reentry",
        )
        reset_encrypted_families(
            family_keys=["proxmox_api"],
            confirmation=RESET_CONFIRMATION_PHRASE,
            audit_actor=self.operator,
            audit_request_id=uuid.uuid4(),
        )
        endpoint = ProxmoxEndpoint.objects.get(pk=self.proxmox.pk)
        endpoint.password = "replacement-after-reset"

        endpoint.save(update_fields=["password_enc"])

        endpoint.refresh_from_db()
        self.assertEqual(endpoint.password, "replacement-after-reset")
        self.assertFalse(endpoint.enabled)

    def test_cloud_init_api_reentry_after_reset_uses_guarded_setter(self) -> None:
        _raw_update_fields(
            ProxmoxVMCloudInit,
            self.cloud_init.pk,
            sshkeys_enc="corrupt-cloud-init-key-bundle",
        )
        reset_encrypted_families(
            family_keys=["cloud_init_ssh_keys"],
            confirmation=RESET_CONFIRMATION_PHRASE,
            audit_actor=self.operator,
            audit_request_id=uuid.uuid4(),
        )
        self.cloud_init.refresh_from_db()
        serializer = ProxmoxVMCloudInitSerializer(
            instance=self.cloud_init,
            data={"sshkeys_intent": "ssh-ed25519 replacement-after-reset"},
            partial=True,
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        updated = serializer.save()

        self.assertEqual(updated.get_sshkeys(), "ssh-ed25519 replacement-after-reset")

    def test_terminal_store_can_switch_between_credential_secret_families(self) -> None:
        request = SimpleNamespace(
            user=SimpleNamespace(has_perm=lambda _permission: True)
        )
        view = ProxmoxEndpointSSHTerminalSessionView()
        fingerprint = "SHA256:" + "C" * 43

        password_result = view._apply_node_credential(
            request,
            self.node,
            {
                "username": "proxbox-discovery",
                "port": 22,
                "auth_method": "password",
                "password": "replacement-terminal-password",
                "known_host_fingerprint": fingerprint,
            },
            True,
            {},
        )
        self.assertIsNone(password_result)
        self.node_credential.refresh_from_db()
        self.assertEqual(self.node_credential.private_key_enc, "")
        self.assertEqual(
            self.node_credential.get_password(key=self.old_key),
            "replacement-terminal-password",
        )

        key_result = view._apply_node_credential(
            request,
            self.node,
            {
                "username": "proxbox-discovery",
                "port": 22,
                "auth_method": "key",
                "private_key": "replacement-terminal-private-key",
                "known_host_fingerprint": fingerprint,
            },
            True,
            {},
        )
        self.assertIsNone(key_result)
        self.node_credential.refresh_from_db()
        self.assertEqual(self.node_credential.password_enc, "")
        self.assertEqual(
            self.node_credential.get_private_key(key=self.old_key),
            "replacement-terminal-private-key",
        )

    def test_terminal_encryption_failure_is_secret_free(self) -> None:
        plaintext_marker = "terminal-password-must-not-leak"
        request = SimpleNamespace(
            user=SimpleNamespace(has_perm=lambda _permission: True)
        )
        with patch.object(
            enc_helpers,
            "encrypt",
            side_effect=enc_helpers.EncryptionKeyInvalid("simulated invalid key"),
        ):
            response = ProxmoxEndpointSSHTerminalSessionView()._apply_node_credential(
                request,
                self.node,
                {
                    "username": "proxbox-discovery",
                    "port": 22,
                    "auth_method": "password",
                    "password": plaintext_marker,
                    "known_host_fingerprint": "SHA256:" + "D" * 43,
                },
                True,
                {},
            )

        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(plaintext_marker, response.content.decode())

    def test_terminal_database_failure_masks_plaintext_reporter_locals(self) -> None:
        plaintext_marker = "terminal-database-secret-must-not-leak"
        request = RequestFactory().post("/plugins/proxbox/terminal/")
        request.user = SimpleNamespace(has_perm=lambda _permission: True)
        with patch.object(
            NodeSSHCredential,
            "save",
            side_effect=DatabaseError("simulated terminal database failure"),
        ):
            try:
                ProxmoxEndpointSSHTerminalSessionView()._apply_node_credential(
                    request,
                    self.node,
                    {
                        "username": "proxbox-discovery",
                        "port": 22,
                        "auth_method": "password",
                        "password": plaintext_marker,
                        "known_host_fingerprint": "SHA256:" + "E" * 43,
                    },
                    True,
                    {},
                )
            except DatabaseError as exc:
                report = ExceptionReporter(
                    request,
                    type(exc),
                    exc,
                    exc.__traceback__,
                ).get_traceback_text()
            else:  # pragma: no cover - test must exercise the unexpected path
                self.fail("The injected terminal database failure did not escape.")

        self.assertNotIn(plaintext_marker, report)

    def test_reset_form_requires_acknowledgement_and_exact_phrase(self) -> None:
        invalid = EncryptedSecretResetForm(
            data={
                "families": ["proxmox_api"],
                "acknowledge_data_loss": True,
                "confirmation": RESET_CONFIRMATION_PHRASE.lower(),
            }
        )
        self.assertFalse(invalid.is_valid())
        self.assertIn("confirmation", invalid.errors)

        valid = EncryptedSecretResetForm(
            data={
                "families": ["proxmox_api"],
                "acknowledge_data_loss": True,
                "confirmation": RESET_CONFIRMATION_PHRASE,
            }
        )
        self.assertTrue(valid.is_valid(), valid.errors)

    def test_destructive_view_requires_the_separate_custom_permission(self) -> None:
        user_model = get_user_model()
        user = user_model.objects.create_user(
            username="recovery-operator", password="not-a-secret"
        )
        client = Client()
        client.force_login(user)
        url = reverse("plugins:netbox_proxbox:encrypted_secret_reset")
        payload = {
            "families": ["proxmox_api"],
            "acknowledge_data_loss": "on",
            "confirmation": RESET_CONFIRMATION_PHRASE,
        }

        denied = client.post(url, payload)
        self.assertEqual(denied.status_code, 403)
        self.proxmox.refresh_from_db()
        self.assertNotEqual(self.proxmox.password_enc, "")

        _raw_update_fields(
            ProxmoxEndpoint,
            self.proxmox.pk,
            password_enc="corrupt-password-for-permissioned-reset",
        )

        permission = Permission.objects.get(
            content_type__app_label="netbox_proxbox",
            codename="reset_encrypted_secrets",
        )
        user.user_permissions.add(permission)
        if hasattr(user, "_perm_cache"):
            delattr(user, "_perm_cache")
        allowed = client.post(url, payload)
        self.assertEqual(allowed.status_code, 302)
        self.proxmox.refresh_from_db()
        self.assertEqual(self.proxmox.password_enc, "")

    def test_settings_and_home_remain_usable_without_disclosing_corrupt_data(
        self,
    ) -> None:
        corrupt_marker = "corrupt-ciphertext-must-not-render"
        _raw_update_fields(
            ProxmoxEndpoint,
            self.proxmox.pk,
            password_enc=corrupt_marker,
        )
        user = get_user_model().objects.create_superuser(
            username="recovery-admin", password="not-a-secret"
        )
        client = Client()
        client.force_login(user)

        for route_name in ("settings", "home"):
            response = client.get(reverse(f"plugins:netbox_proxbox:{route_name}"))
            self.assertEqual(response.status_code, 200)
            body = response.content.decode("utf-8")
            self.assertNotIn(corrupt_marker, body)
            self.assertNotIn(self.old_key, body)
            for plaintext in self.plaintexts.values():
                self.assertNotIn(plaintext, body)
        self.assertContains(response, "Recovery required")

    def test_signal_boundaries_skip_undecryptable_backend_ciphertext(self) -> None:
        _raw_update_fields(
            FastAPIEndpoint,
            self.fastapi.pk,
            enabled=True,
            token_enc="corrupt-backend-ciphertext",
        )
        self.fastapi.refresh_from_db()

        with patch("netbox_proxbox.websocket_client.stop_websocket") as stop:
            ensure_fastapi_endpoint_token(
                sender=FastAPIEndpoint,
                instance=self.fastapi,
                created=False,
            )
        stop.assert_called_once_with(int(self.fastapi.pk))

        with patch("netbox_proxbox.signals._register_token_with_backend") as register:
            ensure_proxmox_endpoint_has_fastapi_token(
                sender=ProxmoxEndpoint,
                instance=self.proxmox,
                created=False,
            )
        register.assert_not_called()


@pytest.mark.django_db(transaction=True)
class EncryptionRecoveryTableLockTest(TransactionTestCase):
    """Prove the PostgreSQL recovery lock excludes a concurrent secret write."""

    reset_sequences = True

    def _pause_reset_before_commit(
        self,
        *,
        family_key: str,
        actor: object,
        reset_paused: threading.Event,
        allow_commit: threading.Event,
        errors: list[BaseException],
    ) -> threading.Thread:
        def pause_event(**_kwargs: object) -> None:
            reset_paused.set()
            if not allow_commit.wait(timeout=5):
                raise RuntimeError("timed out waiting to finish recovery reset")

        def run_reset() -> None:
            try:
                connections["default"].close()
                with patch(
                    "netbox_proxbox.services.encryption_recovery."
                    "record_encryption_recovery_event",
                    side_effect=pause_event,
                ):
                    reset_encrypted_families(
                        family_keys=[family_key],
                        confirmation=RESET_CONFIRMATION_PHRASE,
                        audit_actor=actor,
                        audit_request_id=uuid.uuid4(),
                    )
            except BaseException as exc:  # pragma: no cover - reported in main thread
                errors.append(exc)
            finally:
                connections["default"].close()

        reset_thread = threading.Thread(target=run_reset, daemon=True)
        reset_thread.start()
        return reset_thread

    def test_partial_save_started_during_reset_cannot_reenable_endpoint(self) -> None:
        if connection.vendor != "postgresql":
            self.skipTest("The production recovery lock is PostgreSQL-specific.")

        old_key = Fernet.generate_key().decode("ascii")
        settings_obj = ProxboxPluginSettings.get_solo()
        _raw_update_fields(
            ProxboxPluginSettings,
            settings_obj.pk,
            encryption_key=old_key,
        )
        endpoint = ProxmoxEndpoint(
            name="partial-save-reset-pve",
            domain="partial-save-reset-pve.example.test",
            enabled=True,
        )
        ProxmoxEndpoint.objects.bulk_create([endpoint])
        _raw_update_fields(
            ProxmoxEndpoint,
            endpoint.pk,
            password_enc="corrupt-partial-save-ciphertext",
        )
        stale_endpoint = ProxmoxEndpoint.objects.get(pk=endpoint.pk)
        actor = get_user_model().objects.create_user(username="partial-save-reset")
        reset_paused = threading.Event()
        allow_commit = threading.Event()
        reset_errors: list[BaseException] = []
        writer_started = threading.Event()
        writer_finished = threading.Event()
        writer_errors: list[BaseException] = []

        reset_thread = self._pause_reset_before_commit(
            family_key="proxmox_api",
            actor=actor,
            reset_paused=reset_paused,
            allow_commit=allow_commit,
            errors=reset_errors,
        )
        self.assertTrue(reset_paused.wait(timeout=5))

        def save_enabled() -> None:
            try:
                connections["default"].close()
                writer_started.set()
                stale_endpoint.enabled = True
                stale_endpoint.save(update_fields=["enabled"])
            except BaseException as exc:  # pragma: no cover - asserted below
                writer_errors.append(exc)
            finally:
                writer_finished.set()
                connections["default"].close()

        writer = threading.Thread(target=save_enabled, daemon=True)
        writer.start()
        self.assertTrue(writer_started.wait(timeout=2))
        self.assertFalse(writer_finished.wait(timeout=0.25))
        allow_commit.set()
        reset_thread.join(timeout=5)
        writer.join(timeout=5)

        self.assertFalse(reset_thread.is_alive())
        self.assertFalse(writer.is_alive())
        self.assertEqual(reset_errors, [])
        self.assertEqual(len(writer_errors), 1)
        self.assertIsInstance(writer_errors[0], ValidationError)
        endpoint.refresh_from_db()
        self.assertEqual(endpoint.password_enc, "")
        self.assertFalse(endpoint.enabled)

    def test_base_manager_update_started_during_reset_cannot_restore_host_online(
        self,
    ) -> None:
        if connection.vendor != "postgresql":
            self.skipTest("The production recovery lock is PostgreSQL-specific.")

        old_key = Fernet.generate_key().decode("ascii")
        settings_obj = ProxboxPluginSettings.get_solo()
        _raw_update_fields(
            ProxboxPluginSettings,
            settings_obj.pk,
            encryption_key=old_key,
        )
        pool = FirecrackerHostPool.objects.create(
            name="Concurrent recovery pool", slug="concurrent-recovery-pool"
        )
        host = FirecrackerHost(
            pool=pool,
            name="concurrent-recovery-host",
            agent_base_url="https://concurrent-firecracker.example.test",
            status="ready",
        )
        FirecrackerHost.objects.bulk_create([host])
        _raw_update_fields(
            FirecrackerHost,
            host.pk,
            agent_token_enc="corrupt-concurrent-firecracker-token",
        )
        actor = get_user_model().objects.create_user(username="bulk-status-reset")
        reset_paused = threading.Event()
        allow_commit = threading.Event()
        reset_errors: list[BaseException] = []
        writer_started = threading.Event()
        writer_finished = threading.Event()
        writer_errors: list[BaseException] = []
        updated_counts: list[int] = []

        reset_thread = self._pause_reset_before_commit(
            family_key="firecracker_agent",
            actor=actor,
            reset_paused=reset_paused,
            allow_commit=allow_commit,
            errors=reset_errors,
        )
        self.assertTrue(reset_paused.wait(timeout=5))

        def mark_ready() -> None:
            try:
                connections["default"].close()
                writer_started.set()
                updated_counts.append(
                    FirecrackerHost._base_manager.filter(pk=host.pk).update(
                        status="ready"
                    )
                )
            except BaseException as exc:  # pragma: no cover - asserted below
                writer_errors.append(exc)
            finally:
                writer_finished.set()
                connections["default"].close()

        writer = threading.Thread(target=mark_ready, daemon=True)
        writer.start()
        self.assertTrue(writer_started.wait(timeout=2))
        self.assertFalse(writer_finished.wait(timeout=0.25))
        allow_commit.set()
        reset_thread.join(timeout=5)
        writer.join(timeout=5)

        self.assertFalse(reset_thread.is_alive())
        self.assertFalse(writer.is_alive())
        self.assertEqual(reset_errors, [])
        self.assertEqual(writer_errors, [])
        self.assertEqual(updated_counts, [0])
        host.refresh_from_db()
        self.assertEqual(host.agent_token_enc, "")
        self.assertEqual(host.status, "offline")

    def test_conflict_upsert_started_during_reset_cannot_restore_host_online(
        self,
    ) -> None:
        if connection.vendor != "postgresql":
            self.skipTest("The production recovery lock is PostgreSQL-specific.")

        old_key = Fernet.generate_key().decode("ascii")
        settings_obj = ProxboxPluginSettings.get_solo()
        _raw_update_fields(
            ProxboxPluginSettings,
            settings_obj.pk,
            encryption_key=old_key,
        )
        pool = FirecrackerHostPool.objects.create(
            name="Conflict upsert recovery pool",
            slug="conflict-upsert-recovery-pool",
        )
        host = FirecrackerHost(
            pool=pool,
            name="conflict-upsert-recovery-host",
            agent_base_url="https://conflict-upsert-firecracker.example.test",
            status="ready",
        )
        FirecrackerHost.objects.bulk_create([host])
        _raw_update_fields(
            FirecrackerHost,
            host.pk,
            agent_token_enc="corrupt-conflict-upsert-firecracker-token",
        )
        actor = get_user_model().objects.create_user(username="conflict-upsert-reset")
        reset_paused = threading.Event()
        allow_commit = threading.Event()
        reset_errors: list[BaseException] = []
        writer_finished = threading.Event()
        writer_errors: list[BaseException] = []

        reset_thread = self._pause_reset_before_commit(
            family_key="firecracker_agent",
            actor=actor,
            reset_paused=reset_paused,
            allow_commit=allow_commit,
            errors=reset_errors,
        )
        self.assertTrue(reset_paused.wait(timeout=5))

        def upsert_ready() -> None:
            try:
                connections["default"].close()
                conflict = FirecrackerHost(
                    pool=pool,
                    name=host.name,
                    agent_base_url=host.agent_base_url,
                    status="ready",
                )
                FirecrackerHost._base_manager.bulk_create(
                    [conflict],
                    update_conflicts=True,
                    update_fields=["status"],
                    unique_fields=["pool", "name"],
                )
            except BaseException as exc:  # pragma: no cover - asserted below
                writer_errors.append(exc)
            finally:
                writer_finished.set()
                connections["default"].close()

        writer = threading.Thread(target=upsert_ready, daemon=True)
        writer.start()
        self.assertTrue(writer_finished.wait(timeout=2))
        allow_commit.set()
        reset_thread.join(timeout=5)
        writer.join(timeout=5)

        self.assertFalse(reset_thread.is_alive())
        self.assertFalse(writer.is_alive())
        self.assertEqual(reset_errors, [])
        self.assertEqual(len(writer_errors), 1)
        self.assertIsInstance(writer_errors[0], ValidationError)
        self.assertIn("status", str(writer_errors[0]))
        host.refresh_from_db()
        self.assertEqual(host.agent_token_enc, "")
        self.assertEqual(host.status, "offline")

    def test_old_key_queryset_update_started_during_rotation_is_rejected(self) -> None:
        if connection.vendor != "postgresql":
            self.skipTest("The production recovery lock is PostgreSQL-specific.")

        old_key = Fernet.generate_key().decode("ascii")
        new_key = Fernet.generate_key().decode("ascii")
        settings_obj = ProxboxPluginSettings.get_solo()
        _raw_update_fields(
            ProxboxPluginSettings,
            settings_obj.pk,
            encryption_key=old_key,
        )
        endpoint = ProxmoxEndpoint(
            name="recovery-lock-pve",
            domain="recovery-lock-pve.example.test",
        )
        ProxmoxEndpoint.objects.bulk_create([endpoint])
        _raw_update_fields(
            ProxmoxEndpoint,
            endpoint.pk,
            password_enc=enc_helpers.encrypt("current-secret", key=old_key),
        )
        late_ciphertext = enc_helpers.encrypt("late-secret", key=old_key)
        operator = get_user_model().objects.create_user(username="queryset-race")
        rotation_paused = threading.Event()
        allow_commit = threading.Event()
        rotation_errors: list[BaseException] = []
        writer_started = threading.Event()
        writer_finished = threading.Event()
        writer_errors: list[BaseException] = []

        def pause_rotation(**_kwargs: object) -> None:
            rotation_paused.set()
            if not allow_commit.wait(timeout=5):
                raise RuntimeError("timed out waiting to finish key rotation")

        def run_rotation() -> None:
            try:
                connections["default"].close()
                with patch(
                    "netbox_proxbox.services.encryption_recovery."
                    "record_encryption_recovery_event",
                    side_effect=pause_rotation,
                ):
                    rotate_encryption_key(
                        old_key=old_key,
                        new_key=new_key,
                        audit_actor=operator,
                        audit_request_id=uuid.uuid4(),
                    )
            except BaseException as exc:  # pragma: no cover - asserted below
                rotation_errors.append(exc)
            finally:
                connections["default"].close()

        def write_ciphertext() -> None:
            try:
                connections["default"].close()
                writer_started.set()
                with transaction.atomic():
                    ProxmoxEndpoint._base_manager.filter(pk=endpoint.pk).update(
                        password_enc=late_ciphertext
                    )
            except BaseException as exc:  # pragma: no cover - asserted below
                writer_errors.append(exc)
            finally:
                writer_finished.set()
                connections["default"].close()

        rotation = threading.Thread(target=run_rotation, daemon=True)
        rotation.start()
        self.assertTrue(rotation_paused.wait(timeout=5))

        writer = threading.Thread(target=write_ciphertext, daemon=True)
        writer.start()
        self.assertTrue(writer_started.wait(timeout=2))
        writer_finished_before_commit = writer_finished.wait(timeout=0.5)
        allow_commit.set()
        rotation.join(timeout=5)
        writer.join(timeout=5)

        self.assertTrue(writer_finished_before_commit)
        self.assertFalse(rotation.is_alive())
        self.assertFalse(writer.is_alive())
        self.assertEqual(rotation_errors, [])
        self.assertEqual(len(writer_errors), 1)
        self.assertIsInstance(writer_errors[0], ValidationError)
        endpoint.refresh_from_db()
        self.assertEqual(
            enc_helpers.decrypt(endpoint.password_enc, key=new_key),
            "current-secret",
        )
        with self.assertRaises(enc_helpers.DecryptionFailed):
            enc_helpers.decrypt(endpoint.password_enc, key=old_key)

    def test_writer_that_captured_old_key_cannot_commit_after_rotation(self) -> None:
        if connection.vendor != "postgresql":
            self.skipTest("The production recovery lock is PostgreSQL-specific.")

        old_key = Fernet.generate_key().decode("ascii")
        new_key = Fernet.generate_key().decode("ascii")
        settings_obj = ProxboxPluginSettings.get_solo()
        _raw_update_fields(
            ProxboxPluginSettings,
            settings_obj.pk,
            encryption_key=old_key,
        )
        endpoint = ProxmoxEndpoint(
            name="stale-writer-pve",
            domain="stale-writer-pve.example.test",
        )
        ProxmoxEndpoint.objects.bulk_create([endpoint])
        _raw_update_fields(
            ProxmoxEndpoint,
            endpoint.pk,
            password_enc=enc_helpers.encrypt("current-secret", key=old_key),
        )
        stale_writer = ProxmoxEndpoint.objects.get(pk=endpoint.pk)
        stale_writer.password_enc = enc_helpers.encrypt("late-secret", key=old_key)
        operator = get_user_model().objects.create_user(username="stale-writer")

        rotate_encryption_key(
            old_key=old_key,
            new_key=new_key,
            audit_actor=operator,
            audit_request_id=uuid.uuid4(),
        )

        with self.assertRaises(ValidationError):
            stale_writer.save(update_fields=["password_enc"])

        endpoint.refresh_from_db()
        self.assertEqual(
            enc_helpers.decrypt(endpoint.password_enc, key=new_key),
            "current-secret",
        )
