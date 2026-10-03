"""Real-Django tests: firewall preview refusals become structured API errors."""

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

from types import SimpleNamespace  # noqa: E402
from unittest.mock import patch  # noqa: E402

from django.contrib.auth import get_user_model  # noqa: E402
from django.test import TestCase  # noqa: E402
from rest_framework.test import APIRequestFactory, force_authenticate  # noqa: E402

from netbox_proxbox.api import views as api_views  # noqa: E402
from netbox_proxbox.intent.firewall_common import FirewallPushError  # noqa: E402


class FirewallPreviewRefusalTests(TestCase):
    """A preview refusal must not escape as HTTP 500."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.superuser = get_user_model().objects.create_user(
            username="fw-preview-admin"
        )
        cls.superuser.is_superuser = True
        cls.superuser.save()

    def _preview(self, viewset: type) -> object:
        request = APIRequestFactory().get("/preview/")
        force_authenticate(request, user=self.superuser)
        view = viewset.as_view({"get": "preview"})
        return view(request, pk=1)

    def test_rule_preview_returns_the_refusal_status(self) -> None:
        refusal = FirewallPushError(
            "invalid_identifier", "not a valid Proxmox identifier", status_code=400
        )
        with (
            patch.object(
                api_views.ProxmoxFirewallRuleViewSet,
                "get_object",
                return_value=SimpleNamespace(pk=1),
            ),
            patch.object(api_views, "preview_firewall_object", side_effect=refusal),
        ):
            response = self._preview(api_views.ProxmoxFirewallRuleViewSet)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["reason"], "invalid_identifier")

    def test_options_preview_returns_the_refusal_status(self) -> None:
        refusal = FirewallPushError(
            "invalid_identifier", "not a valid Proxmox identifier", status_code=400
        )
        with (
            patch.object(
                api_views.ProxmoxFirewallOptionsViewSet,
                "get_object",
                return_value=SimpleNamespace(pk=1),
            ),
            patch.object(api_views, "preview_firewall_object", side_effect=refusal),
        ):
            response = self._preview(api_views.ProxmoxFirewallOptionsViewSet)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["status"], "error")
