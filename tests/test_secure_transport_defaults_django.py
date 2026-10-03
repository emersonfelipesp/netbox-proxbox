"""Real-Django tests: secure transport defaults, key quality, and security checks."""

from __future__ import annotations

import os
from pathlib import Path
import sys

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

# The mocked suite deliberately installs ``django`` as a plain module. Do not
# add the real NetBox source tree to sys.path in that process: doing so would
# make other harness-detection tests see a half-real, half-stub environment.
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

from unittest.mock import patch  # noqa: E402
from uuid import uuid4  # noqa: E402

from cryptography.fernet import Fernet  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.core.exceptions import ValidationError  # noqa: E402
from django.test import TestCase  # noqa: E402

from netbox_proxbox.api.serializers.settings import (  # noqa: E402
    ProxboxPluginSettingsSerializer,
)
from netbox_proxbox.forms.settings import (  # noqa: E402
    EncryptionKeyRotationForm,
    ProxboxPluginSettingsForm,
)
from netbox_proxbox.models import (  # noqa: E402
    FastAPIEndpoint,
    ProxboxPluginSettings,
    ProxmoxEndpoint,
)
from netbox_proxbox.security_checks import insecure_transport_check  # noqa: E402
from netbox_proxbox.services.encryption_recovery import (  # noqa: E402
    OldEncryptionKeyRejected,
    rotate_encryption_key,
)
from tests.django_support import raw_update_fields  # noqa: E402

RAW_32 = "r" * 32


def _check_ids(**kwargs: object) -> set[str]:
    return {message.id for message in insecure_transport_check(**kwargs)}


class SecureDefaultTests(TestCase):
    def test_new_backend_endpoint_defaults_to_https(self) -> None:
        self.assertTrue(FastAPIEndpoint().use_https)

    def test_new_proxmox_endpoint_defaults_to_tls_verification(self) -> None:
        self.assertTrue(ProxmoxEndpoint().verify_ssl)

    def test_backend_form_starts_with_https_enabled(self) -> None:
        from netbox_proxbox.forms.fastapi import FastAPIEndpointForm

        self.assertTrue(FastAPIEndpointForm().fields["use_https"].initial)


class EncryptionKeyWriteValidationTests(TestCase):
    def setUp(self) -> None:
        self.settings_obj = ProxboxPluginSettings.get_solo()
        raw_update_fields(
            ProxboxPluginSettings, self.settings_obj.pk, encryption_key=""
        )
        self.settings_obj.refresh_from_db()

    def test_model_save_rejects_a_new_raw_key(self) -> None:
        self.settings_obj.encryption_key = RAW_32

        with self.assertRaises(ValidationError) as error:
            self.settings_obj.save()

        self.assertIn("encryption_key", error.exception.message_dict)

    def test_model_save_accepts_a_generated_key(self) -> None:
        self.settings_obj.encryption_key = Fernet.generate_key().decode("ascii")

        self.settings_obj.save()

    def test_existing_legacy_key_keeps_working_for_other_edits(self) -> None:
        raw_update_fields(
            ProxboxPluginSettings, self.settings_obj.pk, encryption_key=RAW_32
        )
        settings_obj = ProxboxPluginSettings.objects.get(pk=self.settings_obj.pk)
        settings_obj.sync_job_timeout = 7200

        settings_obj.save()

        self.assertEqual(
            ProxboxPluginSettings.objects.get(pk=settings_obj.pk).encryption_key, RAW_32
        )

    def test_serializer_rejects_a_new_raw_key(self) -> None:
        serializer = ProxboxPluginSettingsSerializer(
            instance=self.settings_obj,
            data={"encryption_key": RAW_32},
            partial=True,
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("encryption_key", serializer.errors)

    def test_settings_form_rejects_a_raw_key(self) -> None:
        form = ProxboxPluginSettingsForm(data={"encryption_key": RAW_32})

        form.full_clean()

        self.assertIn("encryption_key", form.errors)

    def test_rotation_form_rejects_a_raw_replacement_key(self) -> None:
        form = EncryptionKeyRotationForm(
            data={
                "old_key": Fernet.generate_key().decode("ascii"),
                "new_key": RAW_32,
                "confirm_new_key": RAW_32,
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("new_key", form.errors)

    def test_rotation_service_rejects_a_raw_replacement_key(self) -> None:
        current = Fernet.generate_key().decode("ascii")
        raw_update_fields(
            ProxboxPluginSettings, self.settings_obj.pk, encryption_key=current
        )
        actor = get_user_model().objects.create_user(username="rotation-actor")

        with self.assertRaises(OldEncryptionKeyRejected):
            rotate_encryption_key(
                old_key=current,
                new_key=RAW_32,
                audit_actor=actor,
                audit_request_id=uuid4(),
            )

        self.assertEqual(
            ProxboxPluginSettings.objects.get(pk=self.settings_obj.pk).encryption_key,
            current,
        )


class InsecureTransportCheckTests(TestCase):
    def test_checks_do_nothing_without_a_database(self) -> None:
        FastAPIEndpoint.objects.bulk_create(
            [
                FastAPIEndpoint(
                    name="plain", domain="plain.example.test", use_https=False
                )
            ]
        )

        self.assertEqual(insecure_transport_check(), [])

    def test_plaintext_and_unverified_endpoints_are_reported(self) -> None:
        FastAPIEndpoint.objects.bulk_create(
            [
                FastAPIEndpoint(
                    name="plain", domain="plain.example.test", use_https=False
                ),
                FastAPIEndpoint(
                    name="unverified",
                    domain="unverified.example.test",
                    use_https=True,
                    verify_ssl=False,
                ),
            ]
        )
        ProxmoxEndpoint.objects.bulk_create(
            [ProxmoxEndpoint(name="pve", domain="pve.example.test", verify_ssl=False)]
        )

        ids = _check_ids(databases=["default"])

        self.assertTrue(
            {"netbox_proxbox.W101", "netbox_proxbox.W102", "netbox_proxbox.W103"} <= ids
        )

    def test_disabled_and_secure_endpoints_are_not_reported(self) -> None:
        FastAPIEndpoint.objects.bulk_create(
            [
                FastAPIEndpoint(
                    name="off",
                    domain="off.example.test",
                    use_https=False,
                    enabled=False,
                ),
                FastAPIEndpoint(name="secure", domain="secure.example.test"),
            ]
        )
        ProxmoxEndpoint.objects.bulk_create(
            [ProxmoxEndpoint(name="pve-secure", domain="pve-secure.example.test")]
        )

        ids = _check_ids(databases=["default"])

        self.assertFalse(
            {"netbox_proxbox.W101", "netbox_proxbox.W102", "netbox_proxbox.W103"} & ids
        )

    def test_legacy_raw_key_is_reported(self) -> None:
        settings_obj = ProxboxPluginSettings.get_solo()
        raw_update_fields(ProxboxPluginSettings, settings_obj.pk, encryption_key=RAW_32)

        self.assertIn("netbox_proxbox.W104", _check_ids(databases=["default"]))

    def test_generated_key_is_not_reported(self) -> None:
        settings_obj = ProxboxPluginSettings.get_solo()
        raw_update_fields(
            ProxboxPluginSettings,
            settings_obj.pk,
            encryption_key=Fernet.generate_key().decode("ascii"),
        )

        self.assertNotIn("netbox_proxbox.W104", _check_ids(databases=["default"]))


class ExplicitPrimaryKeySettingsTests(TestCase):
    def test_explicit_pk_insert_rejects_a_raw_key(self) -> None:
        ProxboxPluginSettings.objects.all().delete()

        with self.assertRaises(ValidationError):
            ProxboxPluginSettings(pk=424242, encryption_key=RAW_32).save()

        self.assertFalse(ProxboxPluginSettings.objects.filter(pk=424242).exists())

    def test_explicit_pk_insert_accepts_a_generated_key(self) -> None:
        ProxboxPluginSettings.objects.all().delete()

        ProxboxPluginSettings(
            pk=424243, encryption_key=Fernet.generate_key().decode("ascii")
        ).save()

        self.assertTrue(ProxboxPluginSettings.objects.filter(pk=424243).exists())


class CsvImportSecureDefaultTests(TestCase):
    """An omitted transport column keeps the secure default; explicit false wins."""

    def _fastapi_form(self, **extra: str) -> object:
        from netbox_proxbox.forms.fastapi import FastAPIEndpointImportForm

        data = {
            "name": "csv-backend",
            "domain": "csv-backend.example.test",
            "port": "8800",
            "enabled": "false",
            **extra,
        }
        return FastAPIEndpointImportForm(data=data)

    def test_omitted_backend_transport_columns_stay_secure(self) -> None:
        form = self._fastapi_form()

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.cleaned_data["use_https"])
        self.assertTrue(form.cleaned_data["verify_ssl"])

    def test_explicit_false_backend_transport_columns_are_honoured(self) -> None:
        form = self._fastapi_form(use_https="false", verify_ssl="false")

        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.cleaned_data["use_https"])
        self.assertFalse(form.cleaned_data["verify_ssl"])

    def _proxmox_form(self, **extra: str) -> object:
        from netbox_proxbox.forms.proxmox import ProxmoxEndpointImportForm

        data = {
            "name": "csv-pve",
            "domain": "csv-pve.example.test",
            "port": "8006",
            "mode": "undefined",
            "username": "root@pam",
            "enabled": "false",
            **extra,
        }
        return ProxmoxEndpointImportForm(data=data)

    def test_omitted_proxmox_verify_column_stays_secure(self) -> None:
        form = self._proxmox_form()

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.cleaned_data["verify_ssl"])

    def test_explicit_false_proxmox_verify_column_is_honoured(self) -> None:
        form = self._proxmox_form(verify_ssl="false")

        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.cleaned_data["verify_ssl"])


class InsecureTransportCheckFailureTests(TestCase):
    def test_an_inspection_failure_never_hides_other_warnings(self) -> None:
        from django.db import DatabaseError

        from netbox_proxbox import security_checks

        FastAPIEndpoint.objects.bulk_create(
            [
                FastAPIEndpoint(
                    name="plain", domain="plain.example.test", use_https=False
                )
            ]
        )
        with patch.object(
            security_checks,
            "_legacy_key_warnings",
            side_effect=DatabaseError("permission denied for table"),
        ):
            ids = _check_ids(databases=["default"])

        self.assertIn("netbox_proxbox.W101", ids)
        self.assertIn("netbox_proxbox.W100", ids)

    def test_missing_tables_before_migration_are_silent(self) -> None:
        from django.db import ProgrammingError

        from netbox_proxbox import security_checks

        missing = ProgrammingError(
            'relation "netbox_proxbox_fastapiendpoint" does not exist'
        )
        names = (
            "_plaintext_backend_warnings",
            "_unverified_backend_warnings",
            "_unverified_proxmox_warnings",
            "_legacy_key_warnings",
        )
        patches = [
            patch.object(security_checks, name, side_effect=missing) for name in names
        ]
        for active in patches:
            active.start()
            self.addCleanup(active.stop)

        self.assertEqual(_check_ids(databases=["default"]), set())

    def test_a_later_inspection_failure_keeps_earlier_warnings(self) -> None:
        from django.db import DatabaseError

        from netbox_proxbox import security_checks

        FastAPIEndpoint.objects.bulk_create(
            [
                FastAPIEndpoint(
                    name="plain", domain="plain.example.test", use_https=False
                )
            ]
        )
        with patch.object(
            security_checks,
            "_unverified_proxmox_warnings",
            side_effect=DatabaseError("permission denied for table"),
        ):
            ids = _check_ids(databases=["default"])

        self.assertIn("netbox_proxbox.W101", ids)
        self.assertIn("netbox_proxbox.W100", ids)

    def test_a_missing_column_is_reported_not_silenced(self) -> None:
        from django.db import ProgrammingError

        from netbox_proxbox import security_checks

        drift = ProgrammingError(
            "column netbox_proxbox_proxmoxendpoint.verify_ssl does not exist"
        )
        with patch.object(
            security_checks, "_unverified_proxmox_warnings", side_effect=drift
        ):
            ids = _check_ids(databases=["default"])

        self.assertIn("netbox_proxbox.W100", ids)

    def _ids_while_pending(self, error: Exception) -> set[str]:
        from netbox_proxbox import security_checks

        pending = {
            "netbox_proxbox_netboxendpoint.approved_connection_target_fingerprint"
        }
        with (
            patch.object(
                security_checks, "_unverified_proxmox_warnings", side_effect=error
            ),
            patch.object(
                security_checks, "_pending_plugin_columns", return_value=pending
            ),
        ):
            return _check_ids(databases=["default"])

    def test_column_added_by_a_pending_migration_is_silent(self) -> None:
        from django.db import ProgrammingError

        error = ProgrammingError(
            "column netbox_proxbox_netboxendpoint.approved_connection_target_"
            "fingerprint does not exist"
        )
        self.assertNotIn("netbox_proxbox.W100", self._ids_while_pending(error))

    def test_unrelated_missing_column_is_reported_while_pending(self) -> None:
        from django.db import ProgrammingError

        error = ProgrammingError(
            "column netbox_proxbox_proxmoxendpoint.verify_ssl does not exist"
        )
        self.assertIn("netbox_proxbox.W100", self._ids_while_pending(error))

    def test_permission_failure_is_reported_while_pending(self) -> None:
        from django.db import DatabaseError

        error = DatabaseError("permission denied for table netbox_proxbox_x")
        self.assertIn("netbox_proxbox.W100", self._ids_while_pending(error))

    def test_fully_migrated_database_has_no_pending_plugin_columns(self) -> None:
        from netbox_proxbox import security_checks

        self.assertEqual(security_checks._pending_plugin_columns(["default"]), set())
