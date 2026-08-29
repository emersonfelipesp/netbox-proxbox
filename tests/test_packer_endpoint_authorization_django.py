"""Real-NetBox persistence and REST deletion checks for Packer authority."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
NETBOX_ROOTS = (
    REPO_ROOT.parent / "netbox" / "netbox",
    REPO_ROOT.parents[1] / "nmulticloud-context" / "netbox" / "netbox",
)
_REQUIRE_DJANGO = os.environ.get("NETBOX_PROXBOX_REQUIRE_DJANGO", "").lower() in (
    "1",
    "true",
    "yes",
)

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

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
    if _REQUIRE_DJANGO:
        raise RuntimeError("A real Django package is required for this test module.")
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
except Exception as exc:  # pragma: no cover - external harness availability
    if _REQUIRE_DJANGO:
        raise
    pytest.skip(
        f"NetBox test environment is not available: {exc}", allow_module_level=True
    )

from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.contenttypes.models import ContentType  # noqa: E402
from django.core.exceptions import ValidationError  # noqa: E402
from django.db import transaction  # noqa: E402
from django.test import TestCase, TransactionTestCase  # noqa: E402
from django.urls import reverse  # noqa: E402
from users.models import ObjectPermission, Token  # noqa: E402

from netbox_proxbox.models import ProxmoxEndpoint  # noqa: E402


def _create_endpoint(name: str, **overrides: object) -> ProxmoxEndpoint:
    values: dict[str, object] = {
        "name": name,
        "domain": f"{name}.example.test",
        "enabled": True,
        "allow_writes": True,
        "allow_packer_template_builds": False,
    }
    values.update(overrides)
    return ProxmoxEndpoint.objects.create(**values)


class PackerAuthorizationCommitBoundaryTest(TransactionTestCase):
    """Backend synchronization must observe committed, current endpoint policy."""

    reset_sequences = True

    def test_rolled_back_endpoint_save_never_runs_backend_sync(self) -> None:
        with patch(
            "netbox_proxbox.signals.ensure_proxmox_endpoint_has_fastapi_token"
        ) as committed_sync:
            with self.assertRaises(RuntimeError), transaction.atomic():
                _create_endpoint(
                    "rolled-back-packer-grant",
                    allow_packer_template_builds=True,
                )
                raise RuntimeError("force rollback")

        committed_sync.assert_not_called()
        self.assertFalse(
            ProxmoxEndpoint.objects.filter(name="rolled-back-packer-grant").exists()
        )

    def test_committed_callback_reloads_latest_row_state(self) -> None:
        with patch(
            "netbox_proxbox.signals.ensure_proxmox_endpoint_has_fastapi_token"
        ) as committed_sync:
            with transaction.atomic():
                endpoint = _create_endpoint(
                    "pending-packer-grant",
                    allow_packer_template_builds=True,
                )
                endpoint.allow_packer_template_builds = False
                endpoint.save(update_fields=["allow_packer_template_builds"])
                committed_sync.assert_not_called()

        self.assertEqual(committed_sync.call_count, 2)
        for call in committed_sync.call_args_list:
            committed = call.kwargs["instance"]
            self.assertEqual(committed.pk, endpoint.pk)
            self.assertFalse(committed.allow_packer_template_builds)
            self.assertTrue(call.kwargs["_after_commit"])


class PackerAuthorizationDeletionAPITest(TestCase):
    """Single and bulk REST deletion share the confirmed-revocation invariant."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = get_user_model().objects.create_user(
            username="packer-delete-operator",
            is_staff=True,
        )
        cls.token = Token.objects.create(user=cls.user)
        permission = ObjectPermission.objects.create(
            name="delete-proxmox-endpoints-after-packer-revocation",
            actions=["view", "delete"],
        )
        permission.object_types.add(ContentType.objects.get_for_model(ProxmoxEndpoint))
        permission.users.add(cls.user)

    def _auth_headers(self) -> dict[str, str]:
        return {"HTTP_AUTHORIZATION": f"Token {self.token.key}"}

    def test_failed_revocation_state_blocks_single_rest_delete(self) -> None:
        endpoint = _create_endpoint("failed-revocation")
        ProxmoxEndpoint.objects.filter(pk=endpoint.pk).update(
            packer_template_builds_backend_authorized=True
        )
        url = reverse(
            "plugins-api:netbox_proxbox-api:endpoints:proxmoxendpoint-detail",
            args=[endpoint.pk],
        )

        response = self.client.delete(url, **self._auth_headers())

        self.assertEqual(response.status_code, 409, response.content)
        self.assertTrue(ProxmoxEndpoint.objects.filter(pk=endpoint.pk).exists())

    def test_active_local_grant_blocks_bulk_rest_delete(self) -> None:
        endpoint = _create_endpoint(
            "active-local-grant",
            allow_packer_template_builds=True,
        )
        url = reverse("plugins-api:netbox_proxbox-api:endpoints:proxmoxendpoint-list")

        response = self.client.delete(
            url,
            data=json.dumps([{"id": endpoint.pk}]),
            content_type="application/json",
            **self._auth_headers(),
        )

        self.assertEqual(response.status_code, 409, response.content)
        self.assertTrue(ProxmoxEndpoint.objects.filter(pk=endpoint.pk).exists())

    def test_confirmed_revocation_allows_model_delete(self) -> None:
        endpoint = _create_endpoint("confirmed-revocation")
        ProxmoxEndpoint.objects.filter(pk=endpoint.pk).update(
            packer_template_builds_backend_authorized=True
        )
        endpoint.refresh_from_db()
        with self.assertRaises(ValidationError):
            endpoint.delete()

        ProxmoxEndpoint.objects.filter(pk=endpoint.pk).update(
            packer_template_builds_backend_authorized=False
        )
        endpoint.refresh_from_db()
        endpoint_pk = endpoint.pk
        endpoint.delete()

        self.assertFalse(ProxmoxEndpoint.objects.filter(pk=endpoint_pk).exists())
