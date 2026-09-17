"""ORM behavior tests for the local node SSH credential audit."""

from __future__ import annotations

from io import StringIO
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
NETBOX_ROOT = ROOT.parent / "netbox" / "netbox"
for candidate in (ROOT, NETBOX_ROOT):
    if candidate.exists() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

require_django = os.environ.get("NETBOX_PROXBOX_REQUIRE_DJANGO", "").lower() in {
    "1",
    "true",
    "yes",
}
try:
    import django
except ModuleNotFoundError:
    if require_django:
        raise
    pytest.skip("Django/NetBox dependencies are unavailable", allow_module_level=True)

os.environ.setdefault("NETBOX_CONFIGURATION", "tests.netbox_test_configuration")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netbox.settings")
try:
    django.setup()
except Exception as exc:
    if require_django:
        raise
    pytest.skip(
        f"NetBox test environment is unavailable: {exc}", allow_module_level=True
    )

from django.core.management import call_command  # noqa: E402
from django.core.management.base import CommandError  # noqa: E402
from django.test import TestCase  # noqa: E402

from netbox_proxbox.choices import ProxmoxAccessMethodChoices  # noqa: E402
from netbox_proxbox.models import (  # noqa: E402
    NodeSSHCredential,
    ProxmoxEndpoint,
    ProxmoxNode,
)


class NodeSSHCredentialAuditTest(TestCase):
    """Only enabled endpoints capable of SSH may block an upgrade."""

    def _node(self, endpoint: ProxmoxEndpoint, name: str, address: str) -> ProxmoxNode:
        return ProxmoxNode.objects.create(
            endpoint=endpoint,
            name=name,
            ip_address=address,
        )

    def test_enabled_ssh_nodes_block_while_disabled_and_api_only_are_informational(
        self,
    ) -> None:
        active_ssh = ProxmoxEndpoint.objects.create(
            name="active-ssh",
            enabled=True,
            access_methods=ProxmoxAccessMethodChoices.API_SSH,
        )
        disabled_ssh = ProxmoxEndpoint.objects.create(
            name="disabled-ssh",
            enabled=False,
            access_methods=ProxmoxAccessMethodChoices.API_SSH,
        )
        active_api = ProxmoxEndpoint.objects.create(
            name="active-api",
            enabled=True,
            access_methods=ProxmoxAccessMethodChoices.API,
        )
        blocking_node = self._node(active_ssh, "blocking", "127.0.0.1")
        self._node(disabled_ssh, "disabled", "127.0.0.1")
        self._node(active_api, "api-only", "127.0.0.1")

        output = StringIO()
        with self.assertRaises(CommandError):
            call_command(
                "audit_node_ssh_credentials",
                fail_on_missing=True,
                stdout=output,
            )
        report = output.getvalue()
        self.assertIn("blocking_missing_local_credentials=1", report)
        self.assertIn("informational_missing_local_credentials=2", report)
        self.assertIn("reason=disabled_endpoint", report)
        self.assertIn("reason=api_only", report)

        NodeSSHCredential.objects.create(
            node=blocking_node,
            username="auditor",
            known_host_fingerprint="SHA256:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        )
        output = StringIO()
        call_command(
            "audit_node_ssh_credentials",
            fail_on_missing=True,
            stdout=output,
        )
        self.assertIn("blocking_missing_local_credentials=0", output.getvalue())
        self.assertIn("informational_missing_local_credentials=2", output.getvalue())
