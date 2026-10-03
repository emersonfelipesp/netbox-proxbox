"""Real-Django tests: HA arm/disarm honours the operational permission and scope."""

from __future__ import annotations

import os
from pathlib import Path
import sys
from unittest.mock import patch

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

from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.contenttypes.models import ContentType  # noqa: E402
from django.test import Client, TestCase, override_settings  # noqa: E402
from django.urls import reverse  # noqa: E402
from users.models import ObjectPermission  # noqa: E402

from netbox_proxbox.models import ProxmoxEndpoint  # noqa: E402
from netbox_proxbox.views import ha_actions  # noqa: E402


def _create_endpoint(name: str, **overrides: object) -> ProxmoxEndpoint:
    values: dict[str, object] = {
        "name": name,
        "domain": f"{name}.example.test",
        "enabled": True,
        "allow_writes": True,
    }
    values.update(overrides)
    return ProxmoxEndpoint.objects.create(**values)


class _Response:
    """proxbox-api HA response: HTTP 200 with one result row per cluster."""

    status_code = 200
    ok = True

    def __init__(self, body: object = None) -> None:
        self._body = [{"cluster_name": "pve", "status": "ok"}] if body is None else body

    def json(self) -> object:
        return self._body


class HaActionPermissionTests(TestCase):
    """Arm/disarm needs run_proxmox_action, object scope, and allow_writes."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.endpoint_a = _create_endpoint("ha-a")
        cls.endpoint_b = _create_endpoint("ha-b")
        cls.read_only = _create_endpoint("ha-readonly", allow_writes=False)
        user_model = get_user_model()
        cls.change_only = user_model.objects.create_user(username="ha-change-only")
        cls._grant(cls.change_only, ProxmoxEndpoint, ["change"])
        cls.scoped_operator = user_model.objects.create_user(username="ha-scoped")
        cls._grant(
            cls.scoped_operator,
            ProxmoxEndpoint,
            ["view", "run_proxmox_action"],
            constraints={"pk": cls.endpoint_a.pk},
        )
        cls.operator = user_model.objects.create_user(username="ha-operator")
        cls._grant(cls.operator, ProxmoxEndpoint, ["view", "run_proxmox_action"])

    @classmethod
    def _grant(
        cls,
        user: object,
        model: type,
        actions: list[str],
        *,
        constraints: dict[str, object] | None = None,
    ) -> None:
        permission = ObjectPermission.objects.create(
            name=f"ha {'/'.join(actions)} {model._meta.label} {user.username}",
            actions=actions,
            constraints=constraints,
        )
        permission.object_types.add(ContentType.objects.get_for_model(model))
        permission.users.add(user)

    def setUp(self) -> None:
        self.backend_ids: list[list[int]] = []
        self.posts: list[dict] = []
        self.response_body: object = None
        self.scope_error: str | None = None
        self.unresolved: set[int] = set()
        self.ctx: object = SimpleNamespace(
            http_url="https://backend.example.test", headers={}, verify_ssl=True
        )

        def _scope(**kwargs: object) -> tuple:
            ids = list(kwargs.get("endpoint_ids") or [])
            self.backend_ids.append(ids)
            mapping = {pk: pk + 1000 for pk in ids if pk not in self.unresolved}
            return {}, mapping, self.scope_error

        def _post(url: str, **kwargs: object) -> _Response:
            self.posts.append({"url": url, **kwargs})
            return _Response(self.response_body)

        for active in (
            patch.object(ha_actions, "get_fastapi_request_context", lambda: self.ctx),
            patch.object(ha_actions, "enabled_backend_endpoint_scope", _scope),
            patch.object(ha_actions.requests, "post", _post),
        ):
            active.start()
            self.addCleanup(active.stop)

    def _post_as(self, user: object, name: str = "disarm", **data: object) -> object:
        client = Client()
        client.force_login(user)
        return client.post(reverse(f"plugins:netbox_proxbox:ha_{name}"), data)

    def _posted_backend_ids(self) -> set[str]:
        return {post["params"]["proxmox_endpoint_ids"] for post in self.posts}

    def test_change_permission_alone_is_rejected(self) -> None:
        response = self._post_as(self.change_only)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.posts, [])

    def test_scoped_operator_only_reaches_permitted_endpoint(self) -> None:
        response = self._post_as(self.scoped_operator)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._posted_backend_ids(), {str(self.endpoint_a.pk + 1000)})
        result_ids = {row["endpoint_id"] for row in response.json()["results"]}
        self.assertEqual(result_ids, {self.endpoint_a.pk})

    def test_write_disabled_endpoint_is_skipped_without_backend_call(self) -> None:
        response = self._post_as(self.operator, "arm")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(str(self.read_only.pk + 1000), self._posted_backend_ids())
        self.assertEqual(
            self._posted_backend_ids(),
            {str(self.endpoint_a.pk + 1000), str(self.endpoint_b.pk + 1000)},
        )
        skipped = [
            row
            for row in response.json()["results"]
            if row["endpoint_id"] == self.read_only.pk
        ]
        self.assertEqual(skipped[0]["error"], ha_actions.WRITES_DISABLED_ERROR)
        self.assertFalse(skipped[0]["ok"])
        self.assertNotIn(self.read_only.pk, self.backend_ids[0])

    def test_endpoint_id_targets_one_endpoint(self) -> None:
        response = self._post_as(self.operator, endpoint_id=self.endpoint_b.pk)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._posted_backend_ids(), {str(self.endpoint_b.pk + 1000)})

    def test_endpoint_id_outside_scope_is_not_found(self) -> None:
        response = self._post_as(self.scoped_operator, endpoint_id=self.endpoint_b.pk)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.posts, [])

    def test_malformed_endpoint_id_is_rejected(self) -> None:
        response = self._post_as(self.operator, endpoint_id="1;2")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.posts, [])

    def test_get_is_not_allowed(self) -> None:
        client = Client()
        client.force_login(self.operator)

        response = client.get(reverse("plugins:netbox_proxbox:ha_arm"))

        self.assertEqual(response.status_code, 405)
        self.assertEqual(self.posts, [])

    def test_backend_error_rows_are_not_reported_as_success(self) -> None:
        self.response_body = [
            {"cluster_name": "pve", "status": "error", "error": "not supported"}
        ]

        response = self._post_as(self.operator, endpoint_id=self.endpoint_a.pk)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["results"][0]["ok"])

    def test_empty_or_malformed_backend_body_is_not_success(self) -> None:
        for body in ([], {"status": "ok"}, ["ok"]):
            with self.subTest(body=body):
                self.response_body = body
                response = self._post_as(self.operator, endpoint_id=self.endpoint_a.pk)
                self.assertFalse(response.json()["results"][0]["ok"])

    def test_successful_backend_rows_are_reported_as_success(self) -> None:
        response = self._post_as(self.operator, endpoint_id=self.endpoint_a.pk)

        self.assertTrue(response.json()["results"][0]["ok"])

    def test_missing_backend_context_returns_503(self) -> None:
        self.ctx = None

        response = self._post_as(self.operator)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.posts, [])

    def test_scope_error_returns_502(self) -> None:
        self.scope_error = "backend unavailable"

        response = self._post_as(self.operator)

        self.assertEqual(response.status_code, 502)
        self.assertEqual(self.posts, [])

    def test_unresolved_backend_id_is_reported_without_backend_call(self) -> None:
        self.unresolved = {self.endpoint_b.pk}

        response = self._post_as(self.operator, endpoint_id=self.endpoint_b.pk)

        self.assertEqual(self.posts, [])
        self.assertFalse(response.json()["results"][0]["ok"])

    def test_only_write_disabled_endpoints_makes_no_backend_call(self) -> None:
        response = self._post_as(self.operator, endpoint_id=self.read_only.pk)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.posts, [])
        self.assertEqual(self.backend_ids, [])

    def test_non_ascii_digit_endpoint_id_is_rejected(self) -> None:
        response = self._post_as(self.operator, endpoint_id="\u00b2")

        self.assertEqual(response.status_code, 400)

    def test_operational_action_granted_on_no_enabled_endpoint_reaches_nothing(
        self,
    ) -> None:
        user = get_user_model().objects.create_user(username="ha-no-endpoints")
        self._grant(
            user,
            ProxmoxEndpoint,
            ["run_proxmox_action"],
            constraints={"name": "does-not-exist"},
        )

        response = self._post_as(user)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], [])
        self.assertEqual(self.posts, [])

    def test_view_permission_alone_is_rejected(self) -> None:
        user = get_user_model().objects.create_user(username="ha-view-only")
        self._grant(user, ProxmoxEndpoint, ["view"])

        response = self._post_as(user)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.posts, [])

    def test_grant_matches_the_netbox_object_permission_name(self) -> None:
        from netbox_proxbox.views.proxbox_access import (
            permission_run_endpoint_action,
        )

        self.assertTrue(self.operator.has_perm(permission_run_endpoint_action()))
        self.assertFalse(self.change_only.has_perm(permission_run_endpoint_action()))

    @override_settings(LOGIN_REQUIRED=True)
    def test_api_tokens_are_not_accepted_for_ha_writes(self) -> None:
        from tests.django_support import make_api_token

        token, headers = make_api_token(self.operator)
        token.write_enabled = False
        token.save()
        client = Client()

        response = client.post(reverse("plugins:netbox_proxbox:ha_disarm"), **headers)

        self.assertNotEqual(response.status_code, 200)
        self.assertEqual(self.posts, [])
