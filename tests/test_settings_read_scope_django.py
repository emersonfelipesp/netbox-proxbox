"""Real-Django tests: plugin settings reads and HA data honour NetBox permissions."""

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
from django.contrib.auth.models import AnonymousUser  # noqa: E402
from django.contrib.contenttypes.models import ContentType  # noqa: E402
from django.test import TestCase, override_settings  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402
from users.models import ObjectPermission  # noqa: E402

from cryptography.fernet import Fernet  # noqa: E402

from netbox_proxbox.api import ha as api_ha  # noqa: E402
from netbox_proxbox.views import ha as views_ha  # noqa: E402
from netbox_proxbox.models import (  # noqa: E402
    NetBoxEndpoint,
    ProxboxPluginSettings,
    ProxmoxEndpoint,
)
from tests.django_support import make_api_token, raw_update_fields  # noqa: E402
from netbox_proxbox.services.endpoint_scope import (  # noqa: E402
    viewable_enabled_endpoint_ids,
)

SETTINGS_URL = "/api/plugins/proxbox/settings/"
RUNTIME_URL = "/api/plugins/proxbox/settings/runtime/"


def _grant(
    user: object, model: type, actions: list[str], **constraints: object
) -> None:
    permission = ObjectPermission.objects.create(
        name=f"{model._meta.label} {'/'.join(actions)} {user.username}",
        actions=actions,
        constraints=constraints or None,
    )
    permission.object_types.add(ContentType.objects.get_for_model(model))
    permission.users.add(user)


class SettingsReadPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        ProxboxPluginSettings.get_solo()
        user_model = get_user_model()
        cls.plain = user_model.objects.create_user(username="settings-plain")
        cls.viewer = user_model.objects.create_user(username="settings-viewer")
        _grant(cls.viewer, ProxboxPluginSettings, ["view"])

    def _client(self, user: object) -> APIClient:
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def test_authenticated_user_without_view_permission_cannot_read(self) -> None:
        client = self._client(self.plain)

        self.assertEqual(client.get(SETTINGS_URL).status_code, 403)
        self.assertEqual(client.get(RUNTIME_URL).status_code, 403)

    def test_view_permission_reads_settings_without_the_key(self) -> None:
        client = self._client(self.viewer)

        listing = client.get(SETTINGS_URL)
        runtime = client.get(RUNTIME_URL)

        self.assertEqual(listing.status_code, 200)
        self.assertEqual(runtime.status_code, 200)
        self.assertEqual(runtime.json()["encryption_key"], "")

    @override_settings(LOGIN_REQUIRED=False, EXEMPT_VIEW_PERMISSIONS=[])
    def test_anonymous_callers_cannot_read_runtime_settings(self) -> None:
        response = APIClient().get(RUNTIME_URL)

        self.assertIn(response.status_code, (401, 403, 404))


class HAEndpointScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.endpoint_a = ProxmoxEndpoint.objects.create(
            name="ha-scope-a", domain="ha-scope-a.example.test", enabled=True
        )
        cls.endpoint_b = ProxmoxEndpoint.objects.create(
            name="ha-scope-b", domain="ha-scope-b.example.test", enabled=True
        )
        cls.scoped = get_user_model().objects.create_user(username="ha-scoped-viewer")
        _grant(cls.scoped, ProxmoxEndpoint, ["view"], pk=cls.endpoint_a.pk)

    def test_scope_is_limited_to_viewable_endpoints(self) -> None:
        self.assertEqual(
            viewable_enabled_endpoint_ids(self.scoped), [self.endpoint_a.pk]
        )

    @override_settings(LOGIN_REQUIRED=False, EXEMPT_VIEW_PERMISSIONS=[])
    def test_anonymous_scope_is_empty_without_exemption(self) -> None:
        self.assertEqual(viewable_enabled_endpoint_ids(AnonymousUser()), [])

    def test_ha_summary_api_scopes_the_backend_request(self) -> None:
        captured: dict[str, object] = {}

        def _scope(**kwargs: object) -> tuple:
            captured.update(kwargs)
            return None, {}, None

        ctx = SimpleNamespace(
            http_url="https://backend.example.test", headers={}, verify_ssl=True
        )
        client = APIClient()
        client.force_authenticate(user=self.scoped)
        with (
            patch.object(api_ha, "get_fastapi_request_context", return_value=ctx),
            patch.object(api_ha, "enabled_backend_endpoint_scope", _scope),
        ):
            response = client.get("/api/plugins/proxbox/ha/summary/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["endpoint_ids"], [self.endpoint_a.pk])


class SettingsReadDetailTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.settings_obj = ProxboxPluginSettings.get_solo()
        raw_update_fields(
            ProxboxPluginSettings,
            cls.settings_obj.pk,
            encryption_key=Fernet.generate_key().decode("ascii"),
        )
        user_model = get_user_model()
        cls.viewer = user_model.objects.create_user(username="settings-detail-viewer")
        _grant(cls.viewer, ProxboxPluginSettings, ["view"])
        cls.mismatched = user_model.objects.create_user(username="settings-mismatch")
        _grant(
            cls.mismatched,
            ProxboxPluginSettings,
            ["view"],
            pk=cls.settings_obj.pk + 1000,
        )

    def _client(self, user: object) -> APIClient:
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def test_viewer_reads_detail_but_never_the_configured_key(self) -> None:
        client = self._client(self.viewer)

        detail = client.get(f"{SETTINGS_URL}{self.settings_obj.pk}/")
        runtime = client.get(RUNTIME_URL)

        self.assertEqual(detail.status_code, 200)
        self.assertNotIn("encryption_key", detail.json())
        self.assertTrue(runtime.json()["encryption_key_configured"])
        self.assertEqual(runtime.json()["encryption_key"], "")

    def test_constraint_that_excludes_the_row_hides_it(self) -> None:
        client = self._client(self.mismatched)

        self.assertEqual(
            client.get(f"{SETTINGS_URL}{self.settings_obj.pk}/").status_code, 404
        )
        self.assertEqual(client.get(RUNTIME_URL).status_code, 404)


class HAPageScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.endpoint = ProxmoxEndpoint.objects.create(
            name="ha-page-a", domain="ha-page-a.example.test", enabled=True
        )
        ProxmoxEndpoint.objects.create(
            name="ha-page-b", domain="ha-page-b.example.test", enabled=True
        )
        cls.scoped = get_user_model().objects.create_user(username="ha-page-viewer")
        _grant(cls.scoped, ProxmoxEndpoint, ["view"], pk=cls.endpoint.pk)

    def test_ha_status_page_scopes_the_backend_request(self) -> None:
        from django.test import Client

        captured: dict[str, object] = {}

        def _scope(**kwargs: object) -> tuple:
            captured.update(kwargs)
            return None, {}, None

        ctx = SimpleNamespace(
            http_url="https://backend.example.test", headers={}, verify_ssl=True
        )
        client = Client()
        client.force_login(self.scoped)
        with (
            patch.object(views_ha, "get_fastapi_request_context", return_value=ctx),
            patch.object(views_ha, "enabled_backend_endpoint_scope", _scope),
        ):
            response = client.get("/plugins/proxbox/ha/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["endpoint_ids"], [self.endpoint.pk])


class BackendSettingsAccessCheckTests(TestCase):
    """W105 warns when proxbox-api's configured token cannot read settings."""

    @classmethod
    def setUpTestData(cls) -> None:
        ProxboxPluginSettings.get_solo()
        cls.service_user = get_user_model().objects.create_user(username="svc-check")
        cls.token, _headers = make_api_token(cls.service_user)

    def _endpoint(self, **fields: object) -> None:
        NetBoxEndpoint.objects.bulk_create(
            [
                NetBoxEndpoint(
                    name="svc-check-netbox",
                    domain="netbox.example.test",
                    port=443,
                    enabled=True,
                    **fields,
                )
            ]
        )

    @staticmethod
    def _ids() -> set[str]:
        from netbox_proxbox.security_checks import insecure_transport_check

        return {m.id for m in insecure_transport_check(databases=["default"])}

    def test_token_without_settings_view_permission_is_reported(self) -> None:
        self._endpoint(token=self.token)

        self.assertIn("netbox_proxbox.W105", self._ids())

    def test_token_with_settings_view_permission_is_not_reported(self) -> None:
        _grant(self.service_user, ProxboxPluginSettings, ["view"])
        self._endpoint(token=self.token)

        self.assertNotIn("netbox_proxbox.W105", self._ids())

    def test_v2_key_identity_is_resolved_too(self) -> None:
        self._endpoint(token=None, token_version="v2", token_key=self.token.key)

        self.assertIn("netbox_proxbox.W105", self._ids())

    def test_disabled_endpoint_is_ignored(self) -> None:
        self._endpoint(token=self.token)
        NetBoxEndpoint.objects.filter(name="svc-check-netbox").update(enabled=False)

        self.assertNotIn("netbox_proxbox.W105", self._ids())

    def test_prefixed_v2_key_is_resolved(self) -> None:
        self._endpoint(
            token=None, token_version="v2", token_key=f"nbt_{self.token.key}"
        )

        self.assertIn("netbox_proxbox.W105", self._ids())

    def test_unresolvable_configured_identity_is_reported(self) -> None:
        self._endpoint(token=None, token_version="v2", token_key="nbt_doesnotexist0")

        self.assertIn("netbox_proxbox.W105", self._ids())


class BackendSettingsReadMigrationTests(TestCase):
    """Migration 0104 keeps existing backend tokens able to read settings."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.settings_obj = ProxboxPluginSettings.get_solo()
        user_model = get_user_model()
        cls.v1_user = user_model.objects.create_user(username="migr-v1")
        cls.v1_token, _ = make_api_token(cls.v1_user)
        cls.v2_user = user_model.objects.create_user(username="migr-v2")
        cls.v2_token, _ = make_api_token(cls.v2_user)
        cls.off_user = user_model.objects.create_user(username="migr-off")
        cls.off_token, _ = make_api_token(cls.off_user)
        common = {"domain": "netbox.example.test", "port": 443}
        NetBoxEndpoint.objects.bulk_create(
            [
                NetBoxEndpoint(name="m-v1", token=cls.v1_token, enabled=True, **common),
                NetBoxEndpoint(
                    name="m-v2",
                    token=None,
                    token_version="v2",
                    token_key=f"nbt_{cls.v2_token.key}",
                    enabled=True,
                    **common,
                ),
                NetBoxEndpoint(
                    name="m-off", token=cls.off_token, enabled=False, **common
                ),
            ]
        )

    def _run(self) -> None:
        import importlib

        from django.apps import apps as live_apps
        from django.db import connection

        migration = importlib.import_module(
            "netbox_proxbox.migrations.0104_security_hardening"
        )
        migration.grant_backend_settings_read(
            live_apps, SimpleNamespace(connection=connection)
        )

    def _can_read(self, user: object) -> bool:
        user = get_user_model().objects.get(pk=user.pk)  # drop permission cache
        return (
            ProxboxPluginSettings.objects.restrict(user, "view")
            .filter(pk=self.settings_obj.pk)
            .exists()
        )

    def test_enabled_backend_tokens_gain_view_only_access(self) -> None:
        self._run()
        self._run()  # idempotent

        self.assertTrue(self._can_read(self.v1_user))
        self.assertTrue(self._can_read(self.v2_user))
        self.assertFalse(self._can_read(self.off_user))
        permission = ObjectPermission.objects.get(
            name="Proxbox backend: read plugin settings"
        )
        self.assertEqual(permission.actions, ["view"])
        self.assertEqual(
            [ct.model for ct in permission.object_types.all()],
            ["proxboxpluginsettings"],
        )

    def test_broader_same_named_permission_is_never_reused(self) -> None:
        from django.contrib.contenttypes.models import ContentType

        broader = ObjectPermission.objects.create(
            name="Proxbox backend: read plugin settings",
            enabled=True,
            actions=["view", "change", "delete"],
        )
        broader.object_types.add(ContentType.objects.get_for_model(NetBoxEndpoint))
        disabled = ObjectPermission.objects.create(
            name="Proxbox backend: read plugin settings",
            enabled=False,
            actions=["view"],
        )
        disabled.object_types.add(
            ContentType.objects.get_for_model(ProxboxPluginSettings)
        )

        self._run()

        self.assertFalse(broader.users.exists())
        self.assertFalse(disabled.users.exists())
        self.assertEqual(broader.actions, ["view", "change", "delete"])
        self.assertEqual(
            [ct.model for ct in broader.object_types.all()], ["netboxendpoint"]
        )
        granted = ObjectPermission.objects.exclude(pk__in=[broader.pk, disabled.pk])
        self.assertEqual(granted.count(), 1)
        self.assertEqual(granted.get().actions, ["view"])
        self.assertTrue(self._can_read(self.v1_user))
        self.assertFalse(
            NetBoxEndpoint.objects.restrict(
                get_user_model().objects.get(pk=self.v1_user.pk), "change"
            ).exists()
        )
