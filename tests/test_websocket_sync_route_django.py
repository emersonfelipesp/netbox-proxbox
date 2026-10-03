"""Real-Django tests: the websocket sync route never starts a sync from GET."""

from __future__ import annotations

import os
from pathlib import Path
import sys
from types import SimpleNamespace
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

from core.models import Job  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.contenttypes.models import ContentType  # noqa: E402
from django.test import Client, TestCase  # noqa: E402
from django.urls import reverse  # noqa: E402
from users.models import ObjectPermission  # noqa: E402

import netbox_proxbox.websocket_client as websocket_module  # noqa: E402
from netbox_proxbox.models import FastAPIEndpoint  # noqa: E402


class WebSocketSyncRouteTests(TestCase):
    """GET is read-only; POST needs CSRF plus the job-enqueue permission."""

    @classmethod
    def setUpTestData(cls) -> None:
        user_model = get_user_model()
        cls.viewer = user_model.objects.create_user(username="ws-viewer")
        cls._grant(cls.viewer, FastAPIEndpoint, "view")
        cls.operator = user_model.objects.create_user(username="ws-operator")
        cls._grant(cls.operator, FastAPIEndpoint, "view")
        cls._grant(cls.operator, Job, "add")

    @classmethod
    def _grant(cls, user: object, model: type, action: str) -> None:
        permission = ObjectPermission.objects.create(
            name=f"ws {action} {model._meta.label} {user.username}",
            actions=[action],
        )
        permission.object_types.add(ContentType.objects.get_for_model(model))
        permission.users.add(user)

    def setUp(self) -> None:
        self.sent: list[str] = []
        self.endpoint_pk = 1
        patches = (
            patch.object(
                websocket_module.WebSocketView,
                "_ensure_worker",
                side_effect=lambda _request: (self.endpoint_pk, None),
            ),
            patch.object(
                websocket_module,
                "send_message",
                lambda command, **_kw: self.sent.append(command),
            ),
            patch.object(
                websocket_module, "websocket_task_identity", (1, "test-identity")
            ),
            patch.dict(
                websocket_module.ws_sync_button_state,
                {
                    "full-update": "not-started",
                    "devices": "not-started",
                    "virtual-machines": "not-started",
                },
            ),
        )
        for active in patches:
            active.start()
            self.addCleanup(active.stop)
        websocket_module.GLOBAL_WEBSOCKET_MESSAGES.clear()
        self.addCleanup(websocket_module.GLOBAL_WEBSOCKET_MESSAGES.clear)

    @staticmethod
    def _url(kind: str) -> str:
        return reverse("plugins:netbox_proxbox:websocket", kwargs={"message": kind})

    def _client(self, user: object) -> Client:
        client = Client(enforce_csrf_checks=True)
        client.force_login(user)
        return client

    def _csrf_token(self, client: Client) -> str:
        client.get(reverse("home"))
        return client.cookies["csrftoken"].value

    def test_get_with_sync_kind_never_sends_a_command(self) -> None:
        client = self._client(self.operator)
        for kind in ("full-update", "devices", "virtual-machines"):
            response = client.get(self._url(kind), {"json_response": "true"})
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.sent, [])
        self.assertEqual(
            set(websocket_module.ws_sync_button_state.values()), {"not-started"}
        )

    def test_post_without_csrf_token_is_rejected(self) -> None:
        response = self._client(self.operator).post(self._url("full-update"))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.sent, [])

    def test_post_without_job_permission_is_rejected(self) -> None:
        client = self._client(self.viewer)
        token = self._csrf_token(client)

        response = client.post(self._url("full-update"), HTTP_X_CSRFTOKEN=token)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.sent, [])

    def test_post_with_csrf_and_permission_queues_once(self) -> None:
        client = self._client(self.operator)
        token = self._csrf_token(client)

        first = client.post(self._url("devices"), HTTP_X_CSRFTOKEN=token)
        second = client.post(self._url("devices"), HTTP_X_CSRFTOKEN=token)

        self.assertEqual(first.status_code, 202)
        self.assertEqual(first.json()["queued"], True)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(self.sent, ["Sync Nodes"])

    def test_unknown_kind_is_not_found(self) -> None:
        client = self._client(self.operator)
        token = self._csrf_token(client)

        response = client.post(self._url("everything"), HTTP_X_CSRFTOKEN=token)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.sent, [])

    def test_post_refuses_when_the_authorized_worker_changed(self) -> None:
        client = self._client(self.operator)
        token = self._csrf_token(client)

        with patch.object(websocket_module, "websocket_task_identity", (2, "other")):
            response = client.post(self._url("devices"), HTTP_X_CSRFTOKEN=token)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.sent, [])

    def test_only_one_sync_kind_runs_at_a_time(self) -> None:
        client = self._client(self.operator)
        token = self._csrf_token(client)

        first = client.post(self._url("virtual-machines"), HTTP_X_CSRFTOKEN=token)
        second = client.post(self._url("full-update"), HTTP_X_CSRFTOKEN=token)

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(self.sent, ["Sync Virtual Machines"])

    def test_cursor_reads_do_not_consume_messages_for_other_users(self) -> None:
        for index in range(3):
            websocket_module.record_websocket_message(
                f'{{"n": {index}}}', endpoint_id=self.endpoint_pk
            )
        operator = self._client(self.operator)
        viewer = self._client(self.viewer)

        first = operator.get(self._url("devices"), {"json_response": "true"})
        second = viewer.get(self._url("devices"), {"json_response": "true"})
        cursor = first[websocket_module.NEXT_CURSOR_HEADER]
        after = operator.get(
            self._url("devices"), {"json_response": "true", "after": cursor}
        )

        self.assertEqual(len(first.json()), 3)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(after.json(), [])
        self.assertEqual(after[websocket_module.NEXT_CURSOR_HEADER], cursor)

    def test_malformed_cursor_is_rejected(self) -> None:
        response = self._client(self.viewer).get(
            self._url("devices"), {"json_response": "true", "after": "not-a-cursor"}
        )

        self.assertEqual(response.status_code, 400)

    def test_messages_are_isolated_per_endpoint(self) -> None:
        websocket_module.record_websocket_message('{"n": "a"}', endpoint_id=1)
        websocket_module.record_websocket_message('{"n": "b"}', endpoint_id=2)
        self.endpoint_pk = 2

        response = self._client(self.viewer).get(
            self._url("devices"), {"json_response": "true"}
        )

        self.assertEqual(response.json(), ['{"n": "b"}'])

    def test_foreign_generation_cursor_is_reset(self) -> None:
        websocket_module.record_websocket_message('{"n": 1}', endpoint_id=1)
        foreign = "0123456789abcdef.999"
        self.assertNotEqual(websocket_module.BUFFER_GENERATION, "0123456789abcdef")

        response = self._client(self.viewer).get(
            self._url("devices"), {"json_response": "true", "after": foreign}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response[websocket_module.CURSOR_RESET_HEADER], "1")
        self.assertEqual(response.json(), ['{"n": 1}'])

    def test_evicted_messages_are_reported_as_a_gap(self) -> None:
        first = websocket_module.record_websocket_message("0", endpoint_id=1)
        for index in range(websocket_module.GLOBAL_WEBSOCKET_MESSAGES.maxlen + 5):
            websocket_module.record_websocket_message(str(index), endpoint_id=1)

        response = self._client(self.viewer).get(
            self._url("devices"),
            {
                "json_response": "true",
                "after": websocket_module.format_message_cursor(first),
            },
        )

        self.assertEqual(response[websocket_module.CURSOR_GAP_HEADER], "1")


class WebSocketEndpointAuthorizationTests(TestCase):
    """The worker only ever starts for an endpoint the caller may view."""

    @classmethod
    def setUpTestData(cls) -> None:
        common = {
            "enabled": True,
            "use_websocket": True,
            "server_side_websocket": True,
            "port": 8800,
        }
        FastAPIEndpoint.objects.bulk_create(
            [
                # Explicit ids keep the fixture independent of sequence state
                # left behind by transactional tests in the same session.
                FastAPIEndpoint(
                    pk=910001, name="ws-first", domain="first.example.test", **common
                ),
                FastAPIEndpoint(
                    pk=910002, name="ws-second", domain="second.example.test", **common
                ),
            ]
        )
        cls.first = FastAPIEndpoint.objects.get(name="ws-first")
        cls.second = FastAPIEndpoint.objects.get(name="ws-second")
        cls.scoped = get_user_model().objects.create_user(username="ws-scoped")
        permission = ObjectPermission.objects.create(
            name="ws scoped view",
            actions=["view"],
            constraints={"pk": cls.second.pk},
        )
        permission.object_types.add(ContentType.objects.get_for_model(FastAPIEndpoint))
        permission.users.add(cls.scoped)
        cls.unpermitted = get_user_model().objects.create_user(username="ws-none")

    def test_selection_refuses_the_worker_endpoint_outside_constraints(self) -> None:
        # The worker always serves the first eligible endpoint; a user whose
        # view permission covers only the second endpoint gets nothing rather
        # than a worker restarted for "their" endpoint.
        request = SimpleNamespace(user=self.scoped)

        self.assertIsNone(websocket_module.WebSocketView._select_endpoint(request))

    def test_selection_returns_the_worker_endpoint_when_permitted(self) -> None:
        permitted = get_user_model().objects.create_user(username="ws-first-viewer")
        permission = ObjectPermission.objects.create(
            name="ws first view",
            actions=["view"],
            constraints={"pk": self.first.pk},
        )
        permission.object_types.add(ContentType.objects.get_for_model(FastAPIEndpoint))
        permission.users.add(permitted)

        selected = websocket_module.WebSocketView._select_endpoint(
            SimpleNamespace(user=permitted)
        )

        self.assertEqual(selected.pk, self.first.pk)

    def test_selection_returns_nothing_without_view_permission(self) -> None:
        request = SimpleNamespace(user=self.unpermitted)

        self.assertIsNone(websocket_module.WebSocketView._select_endpoint(request))


class WebSocketStateTransitionTests(TestCase):
    """Terminal publication, cursor capture, and worker replacement."""

    def setUp(self) -> None:
        websocket_module.GLOBAL_WEBSOCKET_MESSAGES.clear()
        self.addCleanup(websocket_module.GLOBAL_WEBSOCKET_MESSAGES.clear)
        state = patch.dict(
            websocket_module.ws_sync_button_state,
            {
                "full-update": "syncing",
                "devices": "syncing",
                "virtual-machines": "syncing",
            },
        )
        state.start()
        self.addCleanup(state.stop)

    def test_device_terminal_keeps_a_running_full_update_latched(self) -> None:
        sequence = websocket_module.publish_backend_message(
            '{"object": "device", "end": true}', endpoint_id=1
        )

        state = websocket_module.ws_sync_button_state
        self.assertEqual(state["devices"], "not-started")
        self.assertEqual(state["full-update"], "syncing")
        self.assertEqual(state["virtual-machines"], "syncing")
        self.assertEqual(websocket_module.GLOBAL_WEBSOCKET_MESSAGES[-1][0], sequence)

    def test_vm_terminal_releases_virtual_machines_and_full_update(self) -> None:
        websocket_module.publish_backend_message(
            '{"object": "virtual_machine", "end": true}', endpoint_id=1
        )

        state = websocket_module.ws_sync_button_state
        self.assertEqual(state["virtual-machines"], "not-started")
        self.assertEqual(state["full-update"], "not-started")
        self.assertEqual(state["devices"], "syncing")

    def test_progress_messages_release_nothing(self) -> None:
        websocket_module.publish_backend_message(
            '{"object": "device", "end": false}', endpoint_id=1
        )
        websocket_module.publish_backend_message("not json", endpoint_id=1)

        self.assertEqual(
            set(websocket_module.ws_sync_button_state.values()), {"syncing"}
        )

    def test_stopping_the_worker_discards_queued_commands(self) -> None:
        websocket_module.websocket_task_identity = (1, "identity")
        self.addCleanup(setattr, websocket_module, "websocket_task_identity", None)
        websocket_module.send_message("Sync Nodes", endpoint_id=1, identity="identity")

        self.assertTrue(websocket_module.stop_websocket(1))

        state = websocket_module.ws_sync_button_state
        self.assertTrue(websocket_module.message_queue.empty())
        # Only the dropped (never sent) command releases its button; runs the
        # backend may already be executing stay latched.
        self.assertEqual(state["devices"], "not-started")
        self.assertEqual(state["full-update"], "syncing")
        self.assertEqual(state["virtual-machines"], "syncing")

    def test_relay_drops_commands_bound_to_another_worker(self) -> None:
        foreign = websocket_module.QueuedCommand(
            endpoint_id=1, identity="old-identity", command="Sync Nodes"
        )

        self.assertIsNone(
            websocket_module._command_for_worker(foreign, 2, "new-identity")
        )
        self.assertIsNone(
            websocket_module._command_for_worker("Sync Nodes", 1, "old-identity")
        )
        self.assertEqual(
            websocket_module.ws_sync_button_state["devices"], "not-started"
        )

    def test_relay_forwards_commands_bound_to_itself(self) -> None:
        own = websocket_module.QueuedCommand(
            endpoint_id=2, identity="identity", command="Full Update"
        )

        self.assertEqual(
            websocket_module._command_for_worker(own, 2, "identity"), "Full Update"
        )

    def test_idle_sync_latch_expires_instead_of_locking_out_syncs(self) -> None:
        with (
            patch.object(websocket_module, "_last_sync_activity", 0.0),
            patch.object(
                websocket_module.time,
                "monotonic",
                return_value=websocket_module.SYNC_LATCH_IDLE_TIMEOUT_SEC + 1,
            ),
        ):
            with websocket_module.websocket_lock:
                websocket_module._expire_idle_sync_latch_locked()

        self.assertEqual(
            set(websocket_module.ws_sync_button_state.values()), {"not-started"}
        )

    def test_recent_activity_keeps_the_sync_latch(self) -> None:
        with (
            patch.object(websocket_module, "_last_sync_activity", 100.0),
            patch.object(websocket_module.time, "monotonic", return_value=101.0),
        ):
            with websocket_module.websocket_lock:
                websocket_module._expire_idle_sync_latch_locked()

        self.assertEqual(
            set(websocket_module.ws_sync_button_state.values()), {"syncing"}
        )
