"""Real-Django tests: the VM config tab refuses unsafe Proxmox identifiers."""

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

from django.test import RequestFactory, TestCase  # noqa: E402

from netbox_proxbox.views import vm_config  # noqa: E402


class VMConfigIdentifierRefusalTests(TestCase):
    """No backend request, no endpoint lookup, and a clear message on refusal."""

    def _context(self, *, node: str, vm_type: str = "qemu", vmid: int = 100) -> dict:
        request = RequestFactory().get("/")
        request.user = SimpleNamespace(is_authenticated=True)
        with (
            patch.object(vm_config, "_extract_vmid", return_value=vmid),
            patch.object(vm_config, "_extract_vm_type", return_value=vm_type),
            patch.object(vm_config, "_extract_node", return_value=node),
            patch.object(
                vm_config.requests,
                "get",
                side_effect=AssertionError("no backend request may be sent"),
            ) as get,
            patch.object(
                vm_config.FastAPIEndpoint.objects,
                "restrict",
                side_effect=AssertionError("refusal happens before endpoint lookup"),
            ),
        ):
            context = vm_config.ProxmoxVMConfigTabView().get_extra_context(
                request, SimpleNamespace(name="vm-under-test")
            )
        get.assert_not_called()
        return context

    def test_traversal_node_name_is_refused(self) -> None:
        context = self._context(node="../extras")

        self.assertIn("not a valid identifier", context["detail"])
        self.assertIsNone(context["config_payload"])

    def test_invalid_guest_type_is_refused(self) -> None:
        context = self._context(node="pve01", vm_type="../qemu")

        self.assertIn("not a valid identifier", context["detail"])

    def test_invalid_vmid_is_refused(self) -> None:
        context = self._context(node="pve01", vmid=0)

        self.assertIn("not a valid identifier", context["detail"])
