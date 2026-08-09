"""Real-Django permission contracts for the PDM endpoint detail override."""

from __future__ import annotations

import os
from pathlib import Path
import sys

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
except Exception as exc:  # pragma: no cover - external test harness availability
    if _REQUIRE_DJANGO:
        raise
    pytest.skip(
        f"NetBox test environment is not available: {exc}",
        allow_module_level=True,
    )

from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.auth.models import Permission  # noqa: E402
from django.contrib.contenttypes.models import ContentType  # noqa: E402
from django.test import RequestFactory, TestCase  # noqa: E402
from users.models import ObjectPermission  # noqa: E402

from netbox_proxbox.models import PDMEndpoint, PDMRemote  # noqa: E402
from netbox_proxbox.views.endpoints.pdm import PDMEndpointView  # noqa: E402


class PDMEndpointRemotePermissionTest(TestCase):
    """Ensure endpoint visibility never implies visibility of child remotes."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.endpoint = PDMEndpoint.objects.create(
            name="permission-test-pdm",
            domain="pdm-permission.example.test",
            token_id="root@pam!permission-test",
        )
        cls.visible_remote = PDMRemote.objects.create(
            pdm_endpoint=cls.endpoint,
            name="visible-remote",
            type="pve",
            hostname="visible.example.test",
        )
        cls.hidden_remote = PDMRemote.objects.create(
            pdm_endpoint=cls.endpoint,
            name="hidden-remote",
            type="pbs",
            hostname="hidden.example.test",
        )
        endpoint_content_type = ContentType.objects.get_for_model(PDMEndpoint)
        endpoint_permission = Permission.objects.get(
            content_type=endpoint_content_type,
            codename="view_pdmendpoint",
        )

        cls.endpoint_only_user = get_user_model().objects.create_user(
            username="pdm-endpoint-only-viewer",
            is_staff=True,
        )
        cls.endpoint_only_user.user_permissions.add(endpoint_permission)

        cls.restricted_remote_user = get_user_model().objects.create_user(
            username="pdm-object-restricted-viewer",
            is_staff=True,
        )
        cls.restricted_remote_user.user_permissions.add(endpoint_permission)
        remote_permission = ObjectPermission.objects.create(
            name="View only the allowed PDM remote",
            actions=["view"],
            constraints={"name": cls.visible_remote.name},
        )
        remote_permission.object_types.add(ContentType.objects.get_for_model(PDMRemote))
        remote_permission.users.add(cls.restricted_remote_user)

    def _rendered_remote_names(self, user) -> list[str]:
        request = RequestFactory().get("/plugins/proxbox/pdm/endpoints/")
        request.user = user
        context = PDMEndpointView().get_extra_context(request, self.endpoint)
        return [record.name for record in context["remotes_table"].data]

    def test_user_without_view_pdmremote_sees_no_children(self) -> None:
        self.assertTrue(
            self.endpoint_only_user.has_perm("netbox_proxbox.view_pdmendpoint")
        )
        self.assertFalse(
            self.endpoint_only_user.has_perm("netbox_proxbox.view_pdmremote")
        )

        self.assertEqual(self._rendered_remote_names(self.endpoint_only_user), [])

    def test_object_restriction_limits_children_to_allowed_remote(self) -> None:
        self.assertEqual(
            self._rendered_remote_names(self.restricted_remote_user),
            [self.visible_remote.name],
        )
