"""Django behavior tests for the bounded Ceph runtime timing settings."""

from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
NETBOX_ROOT = REPO_ROOT.parent / "netbox" / "netbox"

for candidate in (REPO_ROOT, NETBOX_ROOT):
    candidate_str = str(candidate)
    if candidate.exists() and candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

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

os.environ.setdefault("NETBOX_CONFIGURATION", "tests.netbox_test_configuration")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netbox.settings")

try:
    django.setup()
except Exception as exc:  # pragma: no cover - depends on external test services
    if _REQUIRE_DJANGO:
        raise
    pytest.skip(
        f"NetBox test environment is not available: {exc}", allow_module_level=True
    )

from django.core.exceptions import ValidationError as DjangoValidationError  # noqa: E402
from django.db import connection  # noqa: E402
from django.db.migrations.executor import MigrationExecutor  # noqa: E402
from django.test import SimpleTestCase, TestCase, TransactionTestCase  # noqa: E402
from netbox.models import NetBoxModel  # noqa: E402
from rest_framework.exceptions import ValidationError as DRFValidationError  # noqa: E402

from netbox_proxbox.api.serializers.settings import (  # noqa: E402
    ProxboxPluginSettingsSerializer,
)
from netbox_proxbox.forms.settings import ProxboxPluginSettingsForm  # noqa: E402
from netbox_proxbox.models import ProxboxPluginSettings  # noqa: E402


class CephRuntimeSettingsValidationTest(TestCase):
    """Verify model, form, and API boundaries enforce the same ranges."""

    CONTRACTS = {
        "ceph_task_timeout": (Decimal("300.00"), Decimal("1.00"), Decimal("3600.00")),
        "ceph_task_poll_interval": (
            Decimal("1.00"),
            Decimal("0.10"),
            Decimal("60.00"),
        ),
        "ceph_run_lease_seconds": (
            Decimal("360.00"),
            Decimal("1.00"),
            Decimal("3600.00"),
        ),
    }

    def test_defaults_and_ranges_match_across_model_form_and_serializer(self) -> None:
        form = ProxboxPluginSettingsForm()
        serializer = ProxboxPluginSettingsSerializer()

        for name, (default, minimum, maximum) in self.CONTRACTS.items():
            model_field = ProxboxPluginSettings._meta.get_field(name)
            self.assertEqual(model_field.get_default(), default)
            model_field.run_validators(minimum)
            model_field.run_validators(maximum)
            with self.assertRaises(DjangoValidationError):
                model_field.run_validators(minimum - Decimal("0.01"))
            with self.assertRaises(DjangoValidationError):
                model_field.run_validators(maximum + Decimal("0.01"))

            form_field = form.fields[name]
            self.assertEqual(Decimal(str(form_field.initial)), default)
            self.assertEqual(form_field.clean(str(minimum)), minimum)
            self.assertEqual(form_field.clean(str(maximum)), maximum)
            with self.assertRaises(DjangoValidationError):
                form_field.clean(str(minimum - Decimal("0.01")))
            with self.assertRaises(DjangoValidationError):
                form_field.clean(str(maximum + Decimal("0.01")))

            api_field = serializer.fields[name]
            self.assertEqual(api_field.run_validation(str(minimum)), minimum)
            self.assertEqual(api_field.run_validation(str(maximum)), maximum)
            with self.assertRaises(DRFValidationError):
                api_field.run_validation(str(minimum - Decimal("0.01")))
            with self.assertRaises(DRFValidationError):
                api_field.run_validation(str(maximum + Decimal("0.01")))

    def test_poll_interval_must_not_exceed_timeout_at_every_boundary(self) -> None:
        settings = ProxboxPluginSettings(
            ceph_task_timeout=Decimal("1.00"),
            ceph_task_poll_interval=Decimal("60.00"),
        )
        with self.assertRaises(DjangoValidationError) as model_error:
            settings.full_clean()
        self.assertIn("ceph_task_poll_interval", model_error.exception.message_dict)

        form = ProxboxPluginSettingsForm(
            data={
                "ceph_task_timeout": "1.00",
                "ceph_task_poll_interval": "60.00",
            }
        )
        form.full_clean()
        self.assertIn("ceph_task_poll_interval", form.errors)

        serializer = ProxboxPluginSettingsSerializer(
            instance=ProxboxPluginSettings(
                ceph_task_timeout=Decimal("300.00"),
                ceph_task_poll_interval=Decimal("60.00"),
            ),
            data={"ceph_task_timeout": "1.00"},
            partial=True,
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("ceph_task_poll_interval", serializer.errors)

        serializer = ProxboxPluginSettingsSerializer(
            instance=ProxboxPluginSettings(
                ceph_task_timeout=Decimal("300.00"),
                ceph_task_poll_interval=Decimal("1.00"),
            ),
            data={"ceph_task_timeout": "1.00", "ceph_task_poll_interval": "60.00"},
            partial=True,
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("ceph_task_poll_interval", serializer.errors)


class CephRuntimeSettingsNullValidationTest(SimpleTestCase):
    """Exercise malformed programmatic model input without requiring a database."""

    def test_null_timing_values_report_field_errors_without_model_type_error(
        self,
    ) -> None:
        settings = ProxboxPluginSettings(
            ceph_task_timeout=None,
            ceph_task_poll_interval=None,
        )

        with (
            patch.object(NetBoxModel, "clean", return_value=None),
            self.assertRaises(DjangoValidationError) as model_error,
        ):
            settings.full_clean(validate_unique=False, validate_constraints=False)

        self.assertIn("ceph_task_timeout", model_error.exception.message_dict)
        self.assertIn("ceph_task_poll_interval", model_error.exception.message_dict)


class CephRuntimeSettingsMigrationTest(TransactionTestCase):
    """Apply migration 0077 and verify existing rows receive safe defaults."""

    migrate_from = (
        "netbox_proxbox",
        "0076_pluginsettings_hardware_discovery_sync_nic_macs",
    )
    migrate_to = ("netbox_proxbox", "0077_ceph_runtime_timing_settings")

    def _migrate_to(self, target: tuple[str, str]):
        executor = MigrationExecutor(connection)
        executor.migrate([target])
        executor = MigrationExecutor(connection)
        return executor.loader.project_state([target]).apps

    def test_existing_settings_row_receives_runtime_timing_defaults(self) -> None:
        try:
            apps_0076 = self._migrate_to(self.migrate_from)
            Settings0076 = apps_0076.get_model(
                "netbox_proxbox", "ProxboxPluginSettings"
            )
            settings_row, _ = Settings0076.objects.get_or_create(
                singleton_key="default"
            )

            apps_0077 = self._migrate_to(self.migrate_to)
            Settings0077 = apps_0077.get_model(
                "netbox_proxbox", "ProxboxPluginSettings"
            )
            migrated = Settings0077.objects.get(pk=settings_row.pk)

            self.assertEqual(migrated.ceph_task_timeout, Decimal("300.00"))
            self.assertEqual(migrated.ceph_task_poll_interval, Decimal("1.00"))
            self.assertEqual(migrated.ceph_run_lease_seconds, Decimal("360.00"))
        finally:
            self._migrate_to(self.migrate_to)
