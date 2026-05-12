"""Tests for Issue #376 sub-PR B: operational verbs gate.

Pins the two halves of the gate contract:

1. ``ProxmoxEndpoint.allow_writes`` exists, defaults to ``False``.
2. The ``core.run_proxmox_action`` permission row exists (created by data
   migration ``0041_run_proxmox_action_permission``) AND a user granted that
   permission resolves ``user.has_perm("core.run_proxmox_action")`` to True.

The literal permission string is non-negotiable — it's pinned by
``docs/design/operational-verbs.md`` §3 and by the helper
``netbox_proxbox.views.proxbox_access.permission_run_proxmox_action``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
NETBOX_ROOT = REPO_ROOT.parent / "netbox" / "netbox"

for candidate in (REPO_ROOT, NETBOX_ROOT):
    candidate_str = str(candidate)
    if candidate.exists() and candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

try:
    import django
except ModuleNotFoundError:
    pytest.skip(
        "Django/NetBox test dependencies are not installed in this environment.",
        allow_module_level=True,
    )

os.environ.setdefault("NETBOX_CONFIGURATION", "tests.netbox_test_configuration")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netbox.settings")

try:
    django.setup()
except Exception as exc:  # pragma: no cover - depends on external test services
    pytest.skip(
        f"NetBox test environment is not available: {exc}", allow_module_level=True
    )

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from utilities.testing import create_test_user

from netbox_proxbox.models import ProxmoxEndpoint
from netbox_proxbox.views.proxbox_access import (
    PROXMOX_ACTION_PERMISSION,
    permission_run_proxmox_action,
)


class ProxmoxActionPermissionContractTest(TestCase):
    """The literal ``core.run_proxmox_action`` string must round-trip through Django."""

    def test_permission_string_helper(self):
        self.assertEqual(PROXMOX_ACTION_PERMISSION, "core.run_proxmox_action")
        self.assertEqual(permission_run_proxmox_action(), "core.run_proxmox_action")

    def test_permission_row_exists(self):
        ct = ContentType.objects.get(app_label="core", model="objecttype")
        self.assertTrue(
            Permission.objects.filter(
                content_type=ct, codename="run_proxmox_action"
            ).exists(),
            "Migration 0041 must create the run_proxmox_action permission row "
            "attached to core.ObjectType so the literal 'core.run_proxmox_action' "
            "string resolves via user.has_perm().",
        )

    def test_user_has_perm_with_grant(self):
        user = create_test_user(username="verb-operator")
        ct = ContentType.objects.get(app_label="core", model="objecttype")
        perm = Permission.objects.get(content_type=ct, codename="run_proxmox_action")
        user.user_permissions.add(perm)
        # Refresh from DB so the permissions cache is rebuilt.
        user = type(user).objects.get(pk=user.pk)
        self.assertTrue(
            user.has_perm("core.run_proxmox_action"),
            "Granting the permission must make 'core.run_proxmox_action' resolve True.",
        )

    def test_ungranted_user_lacks_perm(self):
        user = create_test_user(username="verb-bystander")
        user = type(user).objects.get(pk=user.pk)
        self.assertFalse(
            user.has_perm("core.run_proxmox_action"),
            "Default users must not hold the run_proxmox_action permission.",
        )


class ProxmoxEndpointAllowWritesTest(TestCase):
    """``ProxmoxEndpoint.allow_writes`` defaults to False (write gate closed)."""

    def test_default_is_false(self):
        endpoint = ProxmoxEndpoint.objects.create(name="lab-cluster")
        self.assertFalse(endpoint.allow_writes)

    def test_field_persists(self):
        endpoint = ProxmoxEndpoint.objects.create(
            name="prod-cluster", allow_writes=True
        )
        endpoint.refresh_from_db()
        self.assertTrue(endpoint.allow_writes)
