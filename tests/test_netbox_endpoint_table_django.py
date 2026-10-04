"""Real-Django tests: NetBox endpoint list table renders on real NetBox."""

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

from django.contrib.auth import get_user_model  # noqa: E402
from django.test import TestCase  # noqa: E402
from users.models import Token  # noqa: E402

from netbox_proxbox.models import NetBoxEndpoint  # noqa: E402
from netbox_proxbox.tables import NetBoxEndpointTable  # noqa: E402


class NetBoxEndpointTablePrefetchTests(TestCase):
    """The token column must prefetch a valid relation and show only its ID."""

    def test_table_prefetches_and_renders_token_identity(self) -> None:
        user = get_user_model().objects.create_user(username="table-user")
        token = Token.objects.create(user=user)
        NetBoxEndpoint.objects.create(
            name="table-netbox",
            domain="netbox.example.test",
            port=443,
            token=token,
            enabled=False,
        )
        table = NetBoxEndpointTable(NetBoxEndpoint.objects.all())
        table.columns.show("token")
        table._apply_prefetching(columns=["token"])

        rows = list(table.data.data)
        self.assertEqual(len(rows), 1)
        self.assertEqual(table.rows[0].get_cell_value("token"), f"Token {token.pk}")
