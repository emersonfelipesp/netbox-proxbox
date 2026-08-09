"""NetBox-backed persistence contracts for backend API-key adoption."""

from __future__ import annotations

import asyncio
from io import StringIO
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import patch

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
NETBOX_ROOTS = (
    REPO_ROOT.parent / "netbox" / "netbox",
    REPO_ROOT.parents[1] / "nmulticloud-context" / "netbox" / "netbox",
)
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

from django.core.exceptions import ValidationError  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.db import IntegrityError, transaction  # noqa: E402
from django.db.models.signals import post_save  # noqa: E402
from django.test import TransactionTestCase, override_settings  # noqa: E402
from ipam.models import IPAddress  # noqa: E402

from netbox_proxbox.api.serializers.endpoints import (  # noqa: E402
    FastAPIEndpointSerializer,
)
from netbox_proxbox.forms.fastapi import (  # noqa: E402
    FastAPIEndpointForm,
    FastAPIEndpointImportForm,
)
from netbox_proxbox.models import FastAPIEndpoint, NetBoxEndpoint  # noqa: E402
from netbox_proxbox.services.backend_auth import (  # noqa: E402
    ensure_backend_key_registered,
)
from netbox_proxbox.services.backend_key_adoption import (  # noqa: E402
    backend_key_runtime_is_trusted,
)
from netbox_proxbox.services.endpoint_autoconfiguration import (  # noqa: E402
    EndpointAutoConfigurationResult,
    autoconfigure_fastapi_endpoint,
    autoconfigure_netbox_endpoint,
    configured_backend_url_is_allowed,
    discover_backend_urls,
)
import netbox_proxbox.services.endpoint_autoconfiguration as auto_module  # noqa: E402
from users.models import Token  # noqa: E402
from netbox_proxbox.signals import (  # noqa: E402
    _register_token_with_backend,
    ensure_fastapi_endpoint_token,
    ensure_proxmox_endpoint_has_fastapi_token,
    sync_netbox_endpoint_to_backend,
)
from netbox_proxbox.views.storage import ProxmoxStorageView  # noqa: E402
from netbox_proxbox.utils import get_backend_auth_headers, get_fastapi_url  # noqa: E402
import netbox_proxbox.websocket_client as websocket_module  # noqa: E402
from netbox_proxbox.websocket_client import (  # noqa: E402
    WebSocketView,
    _load_websocket_credentials,
)


OLD_KEY = "old-backend-key-0123456789abcdef0123456789"
NEW_KEY = "new-backend-key-0123456789abcdef0123456789"
OTHER_KEY = "other-backend-key-0123456789abcdef01234567"


class TestEndpointAutoconfigurationHelpers:
    """Cover fail-closed parsing/orchestration branches without database I/O."""

    @override_settings(PLUGINS_CONFIG=[])
    def test_non_mapping_plugin_configuration_is_ignored(self) -> None:
        assert auto_module._plugin_config() == {}

    @override_settings(PLUGINS_CONFIG={"netbox_proxbox": []})
    def test_non_mapping_plugin_entry_is_ignored(self) -> None:
        assert auto_module._plugin_config() == {}

    def test_trusted_origin_parser_rejects_unsafe_or_malformed_values(self) -> None:
        assert auto_module._normalized_origin("backend.example.test") == (
            "https://backend.example.test"
        )
        assert (
            auto_module._normalized_origin("https://backend.example.test:bad") is None
        )
        assert (
            auto_module._normalized_origin("https://backend.example.test/path") is None
        )
        assert (
            auto_module._normalized_origin("https://user@backend.example.test") is None
        )
        assert auto_module._normalized_origin("https://localhost") is None
        assert auto_module._configured_hostname("") == ""
        assert auto_module._configured_hostname("https://[broken") == ""

    @override_settings(
        PLUGINS_CONFIG={
            "netbox_proxbox": {"netbox_url": "https://inventory.example.test"}
        },
        CSRF_TRUSTED_ORIGINS=(),
        ALLOWED_HOSTS=(),
    )
    def test_non_netbox_public_name_does_not_expand_backend_candidates(self) -> None:
        assert discover_backend_urls() == ()

    def test_backend_identity_probe_treats_parse_failure_as_not_live(self) -> None:
        class _InvalidJsonClient:
            def get(self, _url: str, **_kwargs: object) -> _Response:
                raise ValueError("invalid JSON")

        assert not auto_module._is_proxbox_backend(
            "https://backend.example.test", True, _InvalidJsonClient()
        )

    def test_invalid_explicit_discovery_target_is_rejected(self) -> None:
        with patch.object(
            auto_module,
            "backend_key_target",
            side_effect=auto_module.BackendKeyAdoptionError(
                "invalid_target", "invalid target"
            ),
        ):
            assert (
                auto_module.discover_live_backend_url(
                    configured_endpoint=SimpleNamespace()
                )
                is None
            )
            assert not configured_backend_url_is_allowed(
                "https://backend.example.test",
                configured_endpoint=SimpleNamespace(),
            )

        assert not configured_backend_url_is_allowed("https://bad.example:invalid")

    def test_combined_autoconfiguration_returns_both_results(self) -> None:
        backend = EndpointAutoConfigurationResult("configured", "backend ready", 1)
        netbox = EndpointAutoConfigurationResult("configured", "netbox ready", 2)
        with (
            patch.object(
                auto_module,
                "autoconfigure_fastapi_endpoint",
                return_value=backend,
            ),
            patch.object(
                auto_module,
                "autoconfigure_netbox_endpoint",
                return_value=netbox,
            ),
        ):
            assert auto_module.autoconfigure_endpoints() == (backend, netbox)


class _Response:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> object:
        return self._payload


class _StatefulBackend:
    """Small stateful implementation of proxbox-api's three real auth routes."""

    def __init__(self, *accepted_keys: str) -> None:
        self.accepted_keys = set(accepted_keys)
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def clear(self) -> None:
        self.calls.clear()

    def get(self, url: str, **kwargs: object) -> _Response:
        self.calls.append(("GET", url, kwargs))
        if url.endswith("/health"):
            return _Response(200, {"status": "ready", "init_ok": True})
        if url.endswith("/"):
            return _Response(
                200, {"message": "Proxbox Backend made in FastAPI framework"}
            )
        if url.endswith("/auth/bootstrap-status"):
            has_keys = bool(self.accepted_keys)
            return _Response(
                200,
                {
                    "needs_bootstrap": not has_keys,
                    "has_db_keys": has_keys,
                },
            )
        if url.endswith("/auth/keys"):
            headers = kwargs.get("headers")
            supplied = (
                headers.get("X-Proxbox-API-Key") if isinstance(headers, dict) else None
            )
            if supplied not in self.accepted_keys:
                return _Response(401, {"detail": "rejected"})
            return _Response(
                200,
                {
                    "keys": [
                        {
                            "id": 1,
                            "label": "netbox",
                            "is_active": True,
                            "created_at": 1.0,
                        }
                    ]
                },
            )
        raise AssertionError(f"unexpected GET route: {url}")

    def post(self, url: str, **kwargs: object) -> _Response:
        self.calls.append(("POST", url, kwargs))
        if not url.endswith("/auth/register-key"):
            raise AssertionError(f"unexpected POST route: {url}")
        if self.accepted_keys:
            return _Response(409, {"detail": "already initialized"})
        payload = kwargs.get("json")
        assert isinstance(payload, dict)
        candidate = payload.get("api_key")
        assert isinstance(candidate, str)
        self.accepted_keys.add(candidate)
        return _Response(201, {"detail": "API key registered."})


class BackendKeyPersistenceTests(TransactionTestCase):
    """Exercise the real model/form/import/serializer/database entry points."""

    reset_sequences = True
    backend: _StatefulBackend
    _client_patch: ClassVar[object]
    _discovery_client_patch: ClassVar[object]

    def setUp(self) -> None:
        self.backend = _StatefulBackend()
        self._client_patch = patch(
            "netbox_proxbox.services.backend_key_adoption.get_default_http_client",
            return_value=self.backend,
        )
        self._discovery_client_patch = patch(
            "netbox_proxbox.services.endpoint_autoconfiguration.get_default_http_client",
            return_value=self.backend,
        )
        self._client_patch.start()
        self._discovery_client_patch.start()

    def tearDown(self) -> None:
        self._discovery_client_patch.stop()
        self._client_patch.stop()

    @staticmethod
    def _new_endpoint(name: str, *, enabled: bool = True) -> FastAPIEndpoint:
        return FastAPIEndpoint(
            name=name,
            domain=f"{name}.example.test",
            port=8800,
            use_https=True,
            verify_ssl=False,
            enabled=enabled,
        )

    def _create_enabled(
        self,
        name: str,
        key: str = OLD_KEY,
    ) -> FastAPIEndpoint:
        self.backend.accepted_keys.add(key)
        endpoint = self._new_endpoint(name)
        endpoint.token = key
        endpoint.save()
        return endpoint

    def test_new_disabled_blank_is_local_only(self) -> None:
        endpoint = self._new_endpoint("disabled-new", enabled=False)
        endpoint.save()
        result = autoconfigure_fastapi_endpoint(http_client=self.backend)

        endpoint.refresh_from_db()
        self.assertEqual(endpoint.token_enc, "")
        self.assertEqual(result.state, "skipped")
        self.assertEqual(self.backend.calls, [])

    def test_new_disabled_explicit_candidate_is_rejected_without_http(self) -> None:
        endpoint = self._new_endpoint("disabled-staged", enabled=False)
        endpoint.token = OLD_KEY

        with self.assertRaises(ValidationError):
            endpoint.save()

        self.assertFalse(
            FastAPIEndpoint.objects.filter(name="disabled-staged").exists()
        )
        self.assertEqual(self.backend.calls, [])

    def test_new_enabled_blank_is_saved_pending_without_http(self) -> None:
        endpoint = self._new_endpoint("enabled-blank")
        with patch(
            "netbox_proxbox.services.endpoint_autoconfiguration.discover_live_backend_url",
            return_value=None,
        ):
            endpoint.save()

        persisted = FastAPIEndpoint.objects.get(name="enabled-blank")
        self.assertTrue(persisted.token)
        self.assertNotEqual(persisted.token_enc, persisted.token)
        self.assertEqual(persisted.backend_key_target_fingerprint, "")
        self.assertFalse(backend_key_runtime_is_trusted(persisted))
        self.assertEqual(self.backend.calls, [])

    def test_generated_candidate_is_retained_before_commit_bootstrap(self) -> None:
        endpoint = self._new_endpoint("commit-safe-bootstrap")

        with transaction.atomic():
            endpoint.save()
            pending = FastAPIEndpoint.objects.get(pk=endpoint.pk)
            self.assertTrue(pending.token)
            self.assertEqual(pending.backend_key_target_fingerprint, "")
            self.assertEqual(self.backend.calls, [])

        endpoint.refresh_from_db()
        self.assertTrue(backend_key_runtime_is_trusted(endpoint))
        self.assertIn(endpoint.token, self.backend.accepted_keys)

    def test_outer_rollback_never_bootstraps_generated_candidate(self) -> None:
        endpoint = self._new_endpoint("rollback-generated-bootstrap")

        with self.assertRaises(RuntimeError), transaction.atomic():
            endpoint.save()
            raise RuntimeError("force rollback")

        self.assertFalse(
            FastAPIEndpoint.objects.filter(name="rollback-generated-bootstrap").exists()
        )
        self.assertEqual(self.backend.calls, [])

    def test_service_generated_candidate_is_not_sent_before_outer_commit(
        self,
    ) -> None:
        endpoint = self._new_endpoint("service-rollback-generated", enabled=False)
        endpoint.save()
        FastAPIEndpoint.objects.filter(pk=endpoint.pk).update(enabled=True)
        self.backend.clear()

        with self.assertRaises(RuntimeError), transaction.atomic():
            result = autoconfigure_fastapi_endpoint(http_client=self.backend)

            self.assertEqual(result.state, "pending")
            self.assertEqual(
                [method for method, _url, _kwargs in self.backend.calls],
                ["GET", "GET"],
            )
            self.assertEqual(self.backend.accepted_keys, set())
            raise RuntimeError("force rollback")

        endpoint.refresh_from_db()
        self.assertEqual(endpoint.token_enc, "")
        self.assertEqual(self.backend.accepted_keys, set())

    @override_settings(
        CSRF_TRUSTED_ORIGINS=["https://netbox.example.test"],
        ALLOWED_HOSTS=["netbox.example.test"],
        PLUGINS_CONFIG={},
    )
    def test_new_enabled_blank_discovers_and_bootstraps_automatically(self) -> None:
        endpoint = FastAPIEndpoint(
            name="auto-bootstrap",
            domain="backend.proxbox.example.test",
            port=443,
            use_https=True,
            verify_ssl=True,
            enabled=True,
        )
        endpoint.save()

        endpoint.refresh_from_db()
        self.assertTrue(endpoint.token)
        self.assertTrue(backend_key_runtime_is_trusted(endpoint))
        self.assertIn(endpoint.token, self.backend.accepted_keys)
        self.assertEqual(endpoint.domain, "backend.proxbox.example.test")
        self.assertEqual(
            [method for method, _url, _kwargs in self.backend.calls],
            ["GET", "GET", "GET", "POST"],
        )

    @override_settings(
        CSRF_TRUSTED_ORIGINS=["https://netbox.example.test"],
        ALLOWED_HOSTS=["*"],
        PLUGINS_CONFIG={},
    )
    def test_missing_backend_row_uses_same_site_allowlist(self) -> None:
        result = autoconfigure_fastapi_endpoint(http_client=self.backend)

        endpoint = FastAPIEndpoint.objects.get(pk=result.endpoint_id)
        self.assertEqual(result.state, "configured")
        self.assertEqual(endpoint.domain, "backend.proxbox.example.test")
        self.assertEqual(endpoint.port, 443)
        self.assertTrue(endpoint.token)
        self.assertTrue(backend_key_runtime_is_trusted(endpoint))
        self.assertIn(endpoint.token, self.backend.accepted_keys)

    @override_settings(
        CSRF_TRUSTED_ORIGINS=["https://netbox.example.test"],
        ALLOWED_HOSTS=["*"],
        PLUGINS_CONFIG={},
    )
    def test_missing_backend_row_outer_rollback_never_sends_generated_key(
        self,
    ) -> None:
        with self.assertRaises(RuntimeError), transaction.atomic():
            result = autoconfigure_fastapi_endpoint(http_client=self.backend)

            self.assertEqual(result.state, "pending")
            self.assertEqual(
                [method for method, _url, _kwargs in self.backend.calls],
                ["GET", "GET"],
            )
            self.assertEqual(self.backend.accepted_keys, set())
            raise RuntimeError("force rollback")

        self.assertFalse(FastAPIEndpoint.objects.exists())
        self.assertEqual(
            [method for method, _url, _kwargs in self.backend.calls],
            ["GET", "GET"],
        )
        self.assertEqual(self.backend.accepted_keys, set())

    @override_settings(
        CSRF_TRUSTED_ORIGINS=[],
        ALLOWED_HOSTS=["*"],
        PLUGINS_CONFIG={
            "netbox_proxbox": {
                "backend_url": "https://192.0.2.55:8800",
                "backend_verify_ssl": False,
            }
        },
    )
    def test_missing_backend_row_accepts_only_explicitly_configured_ip(self) -> None:
        result = autoconfigure_fastapi_endpoint(http_client=self.backend)

        endpoint = FastAPIEndpoint.objects.get(pk=result.endpoint_id)
        self.assertEqual(result.state, "configured")
        self.assertIsNone(endpoint.domain)
        self.assertEqual(str(endpoint.ip_address.address), "192.0.2.55/32")
        self.assertEqual(endpoint.port, 8800)
        self.assertTrue(endpoint.use_https)
        self.assertFalse(endpoint.verify_ssl)
        self.assertTrue(backend_key_runtime_is_trusted(endpoint))
        self.assertTrue(
            all(
                kwargs.get("verify") is False
                for _method, _url, kwargs in self.backend.calls
            )
        )

    @override_settings(
        CSRF_TRUSTED_ORIGINS=["https://netbox.example.test"],
        ALLOWED_HOSTS=["*"],
        PLUGINS_CONFIG={},
    )
    def test_existing_encrypted_key_repairs_blank_target_fingerprint(self) -> None:
        endpoint = self._create_enabled("legacy-binding")
        FastAPIEndpoint.objects.filter(pk=endpoint.pk).update(
            domain="proxbox.backend.example.test",
            backend_key_target_fingerprint="",
        )
        self.backend.clear()

        result = autoconfigure_fastapi_endpoint(http_client=self.backend)

        endpoint.refresh_from_db()
        self.assertEqual(result.state, "configured")
        self.assertEqual(endpoint.domain, "proxbox.backend.example.test")
        self.assertEqual(endpoint.token, OLD_KEY)
        self.assertTrue(backend_key_runtime_is_trusted(endpoint))
        self.assertFalse(any(method == "POST" for method, *_rest in self.backend.calls))

    def test_ui_endpoint_is_the_exact_discovery_allowlist(self) -> None:
        endpoint = self._new_endpoint("configured-ui-target")

        self.assertTrue(
            configured_backend_url_is_allowed(
                "https://configured-ui-target.example.test:8800",
                configured_endpoint=endpoint,
            )
        )
        self.assertFalse(
            configured_backend_url_is_allowed(
                "https://unlisted.example.test:8800",
                configured_endpoint=endpoint,
            )
        )

    def test_ui_ip_endpoint_is_the_exact_discovery_allowlist(self) -> None:
        ip_object = IPAddress.objects.create(address="192.0.2.44/32")
        endpoint = self._new_endpoint("configured-ui-ip")
        endpoint.domain = None
        endpoint.ip_address = ip_object

        self.assertTrue(
            configured_backend_url_is_allowed(
                "https://192.0.2.44:8800",
                configured_endpoint=endpoint,
            )
        )
        self.assertFalse(
            configured_backend_url_is_allowed(
                "https://192.0.2.45:8800",
                configured_endpoint=endpoint,
            )
        )

    @override_settings(
        CSRF_TRUSTED_ORIGINS=["https://netbox.example.test"],
        ALLOWED_HOSTS=["*"],
        PLUGINS_CONFIG={},
    )
    def test_initialized_backend_without_local_key_remains_pending(self) -> None:
        self.backend.accepted_keys.add(OTHER_KEY)
        endpoint = FastAPIEndpoint(
            name="missing-local-key",
            domain="backend.proxbox.example.test",
            port=443,
            use_https=True,
            verify_ssl=True,
            enabled=True,
        )
        endpoint.save()

        endpoint.refresh_from_db()
        self.assertTrue(endpoint.token)
        self.assertNotIn(endpoint.token, self.backend.accepted_keys)
        self.assertEqual(endpoint.backend_key_target_fingerprint, "")
        self.assertFalse(backend_key_runtime_is_trusted(endpoint))
        self.assertFalse(any(method == "POST" for method, *_rest in self.backend.calls))

    @override_settings(
        CSRF_TRUSTED_ORIGINS=["https://netbox.example.test"],
        ALLOWED_HOSTS=["*"],
        PLUGINS_CONFIG={},
    )
    def test_discovery_candidates_are_bounded_and_canonical_first(self) -> None:
        self.assertEqual(
            discover_backend_urls(),
            (
                "https://backend.proxbox.example.test",
                "https://proxbox.backend.example.test",
            ),
        )

    @override_settings(
        CSRF_TRUSTED_ORIGINS=["https://netbox.example.test"],
        ALLOWED_HOSTS=["*"],
        PLUGINS_CONFIG={},
    )
    def test_local_netbox_and_unique_service_token_are_discovered(self) -> None:
        user = get_user_model().objects.create_user(username="proxbox-service")
        Token.objects.create(
            user=user,
            version=1,
            token="z" * 40,
            description="proxbox disabled service token",
            enabled=False,
            write_enabled=True,
        )
        token = Token.objects.create(
            user=user,
            version=1,
            token="a" * 40,
            description="proxbox backend service token",
            write_enabled=True,
        )

        result = autoconfigure_netbox_endpoint()

        endpoint = NetBoxEndpoint.objects.get(pk=result.endpoint_id)
        self.assertEqual(result.state, "configured")
        self.assertEqual(endpoint.domain, "netbox.example.test")
        self.assertEqual(endpoint.port, 443)
        self.assertEqual(endpoint.token_id, token.pk)
        self.assertTrue(endpoint.verify_ssl)

    @override_settings(
        CSRF_TRUSTED_ORIGINS=[],
        ALLOWED_HOSTS=["*"],
        PLUGINS_CONFIG={"netbox_proxbox": {"netbox_url": "http://192.0.2.60:8080"}},
    )
    def test_explicit_netbox_ip_and_service_token_are_discovered(self) -> None:
        user = get_user_model().objects.create_user(username="proxbox-ip-service")
        token = Token.objects.create(
            user=user,
            version=1,
            token="i" * 40,
            description="proxbox IP service token",
            write_enabled=True,
        )

        result = autoconfigure_netbox_endpoint()

        endpoint = NetBoxEndpoint.objects.get(pk=result.endpoint_id)
        self.assertEqual(result.state, "configured")
        self.assertIsNone(endpoint.domain)
        self.assertEqual(str(endpoint.ip_address.address), "192.0.2.60/32")
        self.assertEqual(endpoint.port, 8080)
        self.assertEqual(endpoint.token_id, token.pk)
        self.assertFalse(endpoint.verify_ssl)

    @override_settings(
        CSRF_TRUSTED_ORIGINS=["https://netbox.example.test"],
        ALLOWED_HOSTS=["*"],
        PLUGINS_CONFIG={},
    )
    def test_existing_netbox_endpoint_discovers_unique_service_token(self) -> None:
        user = get_user_model().objects.create_user(username="proxbox-existing")
        disabled_token = Token.objects.create(
            user=user,
            version=1,
            token="d" * 40,
            description="proxbox disabled existing token",
            enabled=False,
            write_enabled=True,
        )
        endpoint = NetBoxEndpoint.objects.create(
            name="configured-netbox",
            domain="netbox.example.test",
            port=443,
            token=disabled_token,
            verify_ssl=True,
            enabled=True,
        )
        token = Token.objects.create(
            user=user,
            version=1,
            token="e" * 40,
            description="proxbox existing service token",
            write_enabled=True,
        )

        result = autoconfigure_netbox_endpoint()

        endpoint.refresh_from_db()
        self.assertEqual(result.state, "configured")
        self.assertEqual(endpoint.token_id, token.pk)

    def test_netbox_endpoint_signal_never_sends_token_before_outer_commit(
        self,
    ) -> None:
        self._create_enabled("netbox-signal-rollback")
        user = get_user_model().objects.create_user(username="proxbox-signal")
        token = Token.objects.create(
            user=user,
            version=1,
            token="s" * 40,
            description="proxbox signal service token",
            write_enabled=True,
        )
        self.backend.clear()

        with self.assertRaises(RuntimeError), transaction.atomic():
            NetBoxEndpoint.objects.create(
                name="rollback-netbox",
                domain="netbox.example.test",
                port=443,
                token=token,
                verify_ssl=True,
                enabled=True,
            )
            self.assertEqual(self.backend.calls, [])
            raise RuntimeError("force rollback")

        self.assertFalse(NetBoxEndpoint.objects.exists())
        self.assertEqual(self.backend.calls, [])

    def test_multiple_netbox_endpoints_block_automatic_selection(self) -> None:
        for index in range(2):
            NetBoxEndpoint.objects.create(
                name=f"netbox-{index}",
                domain=f"netbox-{index}.example.test",
                port=443,
                verify_ssl=True,
                enabled=True,
            )

        result = autoconfigure_netbox_endpoint()

        self.assertEqual(result.state, "pending")
        self.assertIn("Multiple NetBox endpoints", result.detail)

    @override_settings(
        CSRF_TRUSTED_ORIGINS=["https://netbox.example.test"],
        ALLOWED_HOSTS=["*"],
        PLUGINS_CONFIG={},
    )
    def test_ambiguous_netbox_service_tokens_remain_pending(self) -> None:
        user = get_user_model().objects.create_user(username="proxbox-ambiguous")
        for index in range(2):
            Token.objects.create(
                user=user,
                version=1,
                token=str(index) * 40,
                description=f"proxbox service token {index}",
                write_enabled=True,
            )

        result = autoconfigure_netbox_endpoint()

        self.assertEqual(result.state, "pending")
        self.assertFalse(NetBoxEndpoint.objects.exists())

    def test_new_enabled_explicit_candidate_bootstraps_once(self) -> None:
        endpoint = self._new_endpoint("initial-bootstrap")
        endpoint.token = OLD_KEY
        endpoint.save()

        methods = [method for method, _url, _kwargs in self.backend.calls]
        self.assertEqual(methods, ["GET", "POST"])
        self.assertEqual(endpoint.token, OLD_KEY)
        self.assertNotEqual(endpoint.token_enc, OLD_KEY)
        self.assertTrue(
            all(
                kwargs.get("allow_redirects") is False
                for _method, _url, kwargs in self.backend.calls
            )
        )

    def test_valid_rotation_authenticates_once_and_persists(self) -> None:
        endpoint = self._create_enabled("valid-rotation")
        self.backend.accepted_keys.add(NEW_KEY)
        self.backend.clear()
        endpoint.refresh_from_db()

        endpoint.token = NEW_KEY
        endpoint.save()

        endpoint.refresh_from_db()
        self.assertEqual(endpoint.token, NEW_KEY)
        self.assertEqual(
            [method for method, _url, _kwargs in self.backend.calls],
            ["GET", "GET"],
        )
        self.assertFalse(
            any(
                url.endswith("/auth/register-key")
                for _method, url, _kwargs in self.backend.calls
            )
        )

    def test_explicit_replacement_recovers_corrupt_stored_ciphertext(self) -> None:
        endpoint = self._create_enabled("corrupt-replacement")
        FastAPIEndpoint.objects.filter(pk=endpoint.pk).update(
            token_enc="corrupt-backend-key-ciphertext"
        )
        endpoint = FastAPIEndpoint.objects.get(pk=endpoint.pk)
        self.backend.accepted_keys.add(NEW_KEY)
        self.backend.clear()

        endpoint.token = NEW_KEY
        endpoint.save()

        endpoint.refresh_from_db()
        self.assertEqual(endpoint.token, NEW_KEY)
        self.assertTrue(backend_key_runtime_is_trusted(endpoint))
        self.assertEqual(
            [method for method, _url, _kwargs in self.backend.calls],
            ["GET", "GET"],
        )
        self.assertFalse(
            any(method == "POST" for method, _url, _kwargs in self.backend.calls)
        )

    def test_corrupt_stored_ciphertext_requires_explicit_replacement(self) -> None:
        endpoint = self._create_enabled("corrupt-no-replacement")
        FastAPIEndpoint.objects.filter(pk=endpoint.pk).update(
            token_enc="corrupt-backend-key-ciphertext"
        )
        endpoint = FastAPIEndpoint.objects.get(pk=endpoint.pk)
        self.backend.clear()

        with self.assertRaises(ValidationError) as raised:
            endpoint.save()

        self.assertIn("explicit replacement", str(raised.exception))
        self.assertNotIn("corrupt-backend-key-ciphertext", str(raised.exception))
        self.assertEqual(self.backend.calls, [])

    def test_invalid_rotation_preserves_exact_ciphertext(self) -> None:
        endpoint = self._create_enabled("invalid-rotation")
        endpoint.refresh_from_db()
        prior_ciphertext = endpoint.token_enc
        self.backend.clear()

        endpoint.token = NEW_KEY
        with self.assertRaises(ValidationError) as raised:
            endpoint.save()

        persisted = FastAPIEndpoint.objects.get(pk=endpoint.pk)
        self.assertEqual(persisted.token_enc, prior_ciphertext)
        self.assertNotIn(OLD_KEY, str(raised.exception))
        self.assertNotIn(NEW_KEY, str(raised.exception))
        self.assertFalse(
            any(method == "POST" for method, _url, _kwargs in self.backend.calls)
        )

    def test_disabled_replacement_is_rejected_without_http(self) -> None:
        endpoint = self._create_enabled("disabled-replacement")
        endpoint.enabled = False
        endpoint.save(update_fields={"enabled"})
        endpoint.refresh_from_db()
        prior_ciphertext = endpoint.token_enc
        self.backend.clear()

        endpoint.token = NEW_KEY
        with self.assertRaises(ValidationError):
            endpoint.save()

        self.assertEqual(
            FastAPIEndpoint.objects.get(pk=endpoint.pk).token_enc,
            prior_ciphertext,
        )
        self.assertEqual(self.backend.calls, [])

    def test_activation_without_resubmission_reuses_configured_key(self) -> None:
        endpoint = self._create_enabled("explicit-activation")
        endpoint.enabled = False
        endpoint.save(update_fields={"enabled"})
        endpoint.refresh_from_db()
        self.backend.clear()

        endpoint.enabled = True
        endpoint.save(update_fields={"enabled"})

        persisted = FastAPIEndpoint.objects.get(pk=endpoint.pk)
        self.assertTrue(persisted.enabled)
        self.assertTrue(backend_key_runtime_is_trusted(persisted))
        self.assertEqual(
            [method for method, _url, _kwargs in self.backend.calls],
            ["GET", "GET", "GET", "GET"],
        )

    def test_target_change_without_key_authenticates_exact_ui_target(self) -> None:
        endpoint = self._create_enabled("target-change")
        endpoint.refresh_from_db()
        original_ciphertext = endpoint.token_enc
        endpoint.domain = "changed.example.test"
        self.backend.clear()

        endpoint.save(update_fields={"domain"})
        self.assertTrue(
            all(
                url.startswith("https://changed.example.test:8800/")
                for _method, url, _kwargs in self.backend.calls
            )
        )
        self.assertEqual(
            [method for method, _url, _kwargs in self.backend.calls],
            ["GET", "GET", "GET", "GET"],
        )
        self.assertEqual(
            FastAPIEndpoint.objects.get(pk=endpoint.pk).token_enc,
            original_ciphertext,
        )
        self.assertTrue(
            backend_key_runtime_is_trusted(FastAPIEndpoint.objects.get(pk=endpoint.pk))
        )

    def test_mutated_related_ip_blocks_every_runtime_credential_path(self) -> None:
        ip_address = IPAddress.objects.create(address="192.0.2.120/32")
        self.backend.accepted_keys.add(OLD_KEY)
        endpoint = self._new_endpoint("mutable-ip")
        endpoint.ip_address = ip_address
        endpoint.token = OLD_KEY
        endpoint.save()
        endpoint.refresh_from_db()
        adopted_fingerprint = endpoint.backend_key_target_fingerprint
        self.backend.clear()

        ip_address.address = "192.0.2.121/32"
        ip_address.save(update_fields={"address"})
        endpoint.refresh_from_db()

        self.assertEqual(
            endpoint.backend_key_target_fingerprint,
            adopted_fingerprint,
        )
        self.assertFalse(backend_key_runtime_is_trusted(endpoint))
        self.assertEqual(get_fastapi_url(endpoint), {})
        self.assertEqual(get_backend_auth_headers(endpoint), {})
        self.assertFalse(_register_token_with_backend(endpoint))
        self.assertEqual(self.backend.calls, [])

    def test_websocket_authority_change_is_automatically_verified(self) -> None:
        self.backend.accepted_keys.add(OLD_KEY)
        endpoint = self._new_endpoint("websocket-target")
        endpoint.use_websocket = True
        endpoint.websocket_domain = "browser-stream.example.test"
        endpoint.websocket_port = 9443
        endpoint.server_side_websocket = True
        endpoint.token = OLD_KEY
        endpoint.save()
        endpoint.refresh_from_db()
        detail = get_fastapi_url(endpoint)
        self.assertEqual(
            detail["websocket_url"],
            "wss://browser-stream.example.test:9443/ws",
        )
        self.assertEqual(
            detail["server_websocket_url"],
            "wss://websocket-target.example.test:8800/ws",
        )
        credentials = _load_websocket_credentials(int(endpoint.pk))
        self.assertIsNotNone(credentials)
        assert credentials is not None
        self.assertEqual(credentials.uri, detail["server_websocket_url"])

        endpoint.websocket_domain = "changed-stream.example.test"
        self.backend.clear()
        endpoint.save(update_fields={"websocket_domain"})
        self.assertTrue(
            backend_key_runtime_is_trusted(FastAPIEndpoint.objects.get(pk=endpoint.pk))
        )
        self.assertEqual(
            [method for method, _url, _kwargs in self.backend.calls],
            ["GET", "GET", "GET", "GET"],
        )

    def test_direct_model_rejects_authority_injection_before_http(self) -> None:
        endpoint = FastAPIEndpoint(
            name="authority-injection",
            domain="trusted.example@evil.example",
            port=8800,
            use_https=True,
            verify_ssl=False,
            enabled=True,
        )
        endpoint.token = OLD_KEY

        with self.assertRaises(ValidationError):
            endpoint.save()

        self.assertFalse(
            FastAPIEndpoint.objects.filter(name="authority-injection").exists()
        )
        self.assertEqual(self.backend.calls, [])

    def test_direct_model_ipv6_target_is_bracketed(self) -> None:
        ip_address = IPAddress.objects.create(address="2001:db8::10/128")
        self.backend.accepted_keys.add(OLD_KEY)
        endpoint = FastAPIEndpoint(
            name="ipv6-target",
            ip_address=ip_address,
            port=8800,
            use_https=True,
            verify_ssl=False,
            enabled=True,
        )
        endpoint.token = OLD_KEY

        endpoint.save()

        self.assertEqual(
            [url for _method, url, _kwargs in self.backend.calls],
            [
                "https://[2001:db8::10]:8800/auth/bootstrap-status",
                "https://[2001:db8::10]:8800/auth/keys",
            ],
        )

    def test_update_fields_ignores_excluded_dirty_target(self) -> None:
        endpoint = self._create_enabled("partial-safe")
        endpoint.refresh_from_db()
        original_domain = endpoint.domain
        original_ciphertext = endpoint.token_enc
        endpoint.name = "partial-safe-renamed"
        endpoint.domain = "must-not-be-contacted.example.test"
        self.backend.clear()

        endpoint.save(update_fields={"name"})

        persisted = FastAPIEndpoint.objects.get(pk=endpoint.pk)
        self.assertEqual(persisted.name, "partial-safe-renamed")
        self.assertEqual(persisted.domain, original_domain)
        self.assertEqual(persisted.token_enc, original_ciphertext)
        self.assertEqual(self.backend.calls, [])

    def test_generator_update_fields_is_not_consumed_before_django_save(self) -> None:
        endpoint = self._create_enabled("generator-update-fields")
        endpoint.name = "generator-update-fields-renamed"
        self.backend.clear()

        endpoint.save(update_fields=(field for field in ("name",)))

        endpoint.refresh_from_db()
        self.assertEqual(endpoint.name, "generator-update-fields-renamed")
        self.assertEqual(self.backend.calls, [])

    def test_update_fields_rejects_excluded_replacement_candidate(self) -> None:
        endpoint = self._create_enabled("partial-token")
        endpoint.refresh_from_db()
        prior_ciphertext = endpoint.token_enc
        endpoint.name = "partial-token-renamed"
        endpoint.token = NEW_KEY
        self.backend.clear()

        with self.assertRaises(ValidationError):
            endpoint.save(update_fields={"name"})

        persisted = FastAPIEndpoint.objects.get(pk=endpoint.pk)
        self.assertNotEqual(persisted.name, "partial-token-renamed")
        self.assertEqual(persisted.token_enc, prior_ciphertext)
        self.assertEqual(self.backend.calls, [])

    def test_stale_sensitive_save_is_rejected_before_http(self) -> None:
        endpoint = self._create_enabled("stale-sensitive")
        first = FastAPIEndpoint.objects.get(pk=endpoint.pk)
        winner = FastAPIEndpoint.objects.get(pk=endpoint.pk)
        self.backend.accepted_keys.update({NEW_KEY, OTHER_KEY})
        winner.token = NEW_KEY
        winner.save()
        winner.refresh_from_db()
        winning_ciphertext = winner.token_enc
        self.backend.clear()

        first.token = OTHER_KEY
        with self.assertRaises(ValidationError):
            first.save()

        self.assertEqual(
            FastAPIEndpoint.objects.get(pk=endpoint.pk).token_enc,
            winning_ciphertext,
        )
        self.assertEqual(self.backend.calls, [])

    def test_stale_nonsecurity_partial_save_cannot_revert_winner(self) -> None:
        endpoint = self._create_enabled("stale-nonsecurity")
        stale = FastAPIEndpoint.objects.get(pk=endpoint.pk)
        winner = FastAPIEndpoint.objects.get(pk=endpoint.pk)
        self.backend.accepted_keys.add(NEW_KEY)
        winner.token = NEW_KEY
        winner.save()
        winner.refresh_from_db()
        winning_ciphertext = winner.token_enc
        original_domain = winner.domain
        self.backend.clear()

        stale.name = "stale-safe-name"
        stale.domain = "excluded-stale-target.example.test"
        stale.save(update_fields={"name"})

        persisted = FastAPIEndpoint.objects.get(pk=endpoint.pk)
        self.assertEqual(persisted.name, "stale-safe-name")
        self.assertEqual(persisted.domain, original_domain)
        self.assertEqual(persisted.token_enc, winning_ciphertext)
        self.assertEqual(self.backend.calls, [])

    def test_bootstrap_candidate_recovers_after_outer_rollback(self) -> None:
        candidate = OLD_KEY
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                endpoint = self._new_endpoint("rollback-bootstrap")
                endpoint.token = candidate
                endpoint.save()
                raise RuntimeError("force rollback")

        self.assertFalse(
            FastAPIEndpoint.objects.filter(name="rollback-bootstrap").exists()
        )
        self.assertEqual(
            [method for method, _url, _kwargs in self.backend.calls],
            ["GET", "POST"],
        )
        self.backend.clear()

        retry = self._new_endpoint("rollback-bootstrap")
        retry.token = candidate
        retry.save()
        self.assertEqual(
            [method for method, _url, _kwargs in self.backend.calls],
            ["GET", "GET"],
        )

    def test_integrity_failure_after_bootstrap_is_recoverable(self) -> None:
        ip_address = IPAddress.objects.create(address="192.0.2.99/32")
        FastAPIEndpoint.objects.create(
            name="duplicate-bootstrap",
            ip_address=ip_address,
            domain="existing.example.test",
            enabled=False,
        )
        endpoint = self._new_endpoint("duplicate-bootstrap")
        endpoint.ip_address = ip_address
        endpoint.token = OLD_KEY

        with self.assertRaises(IntegrityError):
            endpoint.save()

        self.assertIn(OLD_KEY, self.backend.accepted_keys)
        self.backend.clear()
        retry = self._new_endpoint("unique-after-bootstrap")
        retry.token = OLD_KEY
        retry.save()
        self.assertEqual(
            [method for method, _url, _kwargs in self.backend.calls],
            ["GET", "GET"],
        )

    def test_post_save_failure_after_bootstrap_is_recoverable(self) -> None:
        def fail_after_save(**_kwargs: object) -> None:
            raise RuntimeError("forced post-save failure")

        post_save.connect(
            fail_after_save,
            sender=FastAPIEndpoint,
            dispatch_uid="test_backend_key_post_save_failure",
        )
        try:
            endpoint = self._new_endpoint("signal-rollback")
            endpoint.token = OLD_KEY
            with self.assertRaises(RuntimeError):
                endpoint.save()
        finally:
            post_save.disconnect(
                sender=FastAPIEndpoint,
                dispatch_uid="test_backend_key_post_save_failure",
            )

        self.assertFalse(
            FastAPIEndpoint.objects.filter(name="signal-rollback").exists()
        )
        self.backend.clear()
        retry = self._new_endpoint("signal-rollback")
        retry.token = OLD_KEY
        retry.save()
        self.assertEqual(
            [method for method, _url, _kwargs in self.backend.calls],
            ["GET", "GET"],
        )

    def test_form_commit_false_has_no_http_and_save_uses_model_gate(self) -> None:
        self.backend.accepted_keys.add(OLD_KEY)
        form = FastAPIEndpointForm(
            data={
                "name": "form-path",
                "domain": "form-path.example.test",
                "port": 8800,
                "use_https": True,
                "verify_ssl": False,
                "enabled": True,
                "token": OLD_KEY,
                "use_websocket": False,
                "server_side_websocket": False,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        instance = form.save(commit=False)
        self.assertIsNone(instance.pk)
        self.assertEqual(self.backend.calls, [])

        form.save()
        self.assertEqual(
            [method for method, _url, _kwargs in self.backend.calls],
            ["GET", "GET"],
        )

    def test_import_form_and_api_serializer_use_the_same_gate(self) -> None:
        self.backend.accepted_keys.update({OLD_KEY, NEW_KEY})
        import_form = FastAPIEndpointImportForm(
            data={
                "name": "import-path",
                "domain": "import-path.example.test",
                "port": "8800",
                "use_https": "true",
                "verify_ssl": "false",
                "enabled": "true",
                "token": OLD_KEY,
                "use_websocket": "false",
                "server_side_websocket": "false",
            }
        )
        self.assertTrue(import_form.is_valid(), import_form.errors)
        import_form.save()
        self.assertEqual(
            [method for method, _url, _kwargs in self.backend.calls],
            ["GET", "GET"],
        )

        self.backend.clear()
        serializer = FastAPIEndpointSerializer(
            data={
                "name": "serializer-path",
                "domain": "serializer-path.example.test",
                "port": 8800,
                "use_https": True,
                "verify_ssl": False,
                "enabled": True,
                "token": NEW_KEY,
                "use_websocket": False,
                "server_side_websocket": False,
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        self.assertEqual(
            [method for method, _url, _kwargs in self.backend.calls],
            ["GET", "GET"],
        )

    def test_api_blank_token_update_preserves_exact_ciphertext(self) -> None:
        endpoint = self._create_enabled("serializer-blank")
        endpoint.refresh_from_db()
        original_ciphertext = endpoint.token_enc
        self.backend.clear()

        for blank_value in ("", None):
            serializer = FastAPIEndpointSerializer(
                endpoint,
                data={
                    "name": f"serializer-{blank_value is None}",
                    "token": blank_value,
                },
                partial=True,
            )
            self.assertTrue(serializer.is_valid(), serializer.errors)
            endpoint = serializer.save()
            endpoint.refresh_from_db()
            self.assertEqual(endpoint.token_enc, original_ciphertext)
            self.assertEqual(endpoint.token, OLD_KEY)

        self.assertEqual(self.backend.calls, [])

    def test_fastapi_post_save_receiver_never_rechecks_or_persists(self) -> None:
        endpoint = self._create_enabled("signal-fastapi")
        endpoint.refresh_from_db()
        original_ciphertext = endpoint.token_enc
        self.backend.clear()

        ensure_fastapi_endpoint_token(
            sender=FastAPIEndpoint,
            instance=endpoint,
            created=False,
        )
        ensure_fastapi_endpoint_token(
            sender=FastAPIEndpoint,
            instance=endpoint,
            created=False,
        )

        endpoint.refresh_from_db()
        self.assertEqual(endpoint.token_enc, original_ciphertext)
        self.assertEqual(self.backend.calls, [])

    def test_downstream_receivers_never_bootstrap_or_bypass_persistence(self) -> None:
        endpoint = self._create_enabled("signal-downstream")
        endpoint.refresh_from_db()
        original_ciphertext = endpoint.token_enc
        self.backend.accepted_keys.clear()
        self.backend.clear()

        ensure_proxmox_endpoint_has_fastapi_token(
            sender=object,
            instance=SimpleNamespace(pk=91, name="pve", enabled=True),
            created=False,
        )
        self.assertEqual(
            [method for method, _url, _kwargs in self.backend.calls],
            ["GET"],
        )
        self.assertFalse(
            any(method == "POST" for method, _url, _kwargs in self.backend.calls)
        )

        self.backend.clear()
        sync_netbox_endpoint_to_backend(
            sender=object,
            instance=SimpleNamespace(pk=92, name="netbox", enabled=True),
            created=False,
        )
        self.assertEqual(
            [method for method, _url, _kwargs in self.backend.calls],
            ["GET"],
        )
        self.assertFalse(
            any(method == "POST" for method, _url, _kwargs in self.backend.calls)
        )

        endpoint.refresh_from_db()
        self.assertEqual(endpoint.token_enc, original_ciphertext)

    def test_disabled_endpoint_websocket_view_performs_no_network_setup(self) -> None:
        endpoint = self._new_endpoint("disabled-websocket", enabled=False)
        endpoint.save()
        self.backend.clear()

        with (
            patch(
                "netbox_proxbox.websocket_client.get_fastapi_url",
                side_effect=AssertionError("disabled endpoint URL must not be built"),
            ) as get_url,
            patch(
                "netbox_proxbox.websocket_client.start_websocket",
                side_effect=AssertionError("disabled endpoint must not connect"),
            ) as start_websocket,
        ):
            response = WebSocketView().get(SimpleNamespace(GET={}), "full-update")

        self.assertEqual(response.status_code, 404)
        get_url.assert_not_called()
        start_websocket.assert_not_called()
        self.assertEqual(self.backend.calls, [])

    def test_server_websocket_loader_requires_both_feature_flags(self) -> None:
        endpoint = self._create_enabled("websocket-flags")

        self.assertIsNone(_load_websocket_credentials(int(endpoint.pk)))

    def test_websocket_rechecks_after_handshake_before_sending_key(self) -> None:
        credentials = websocket_module._WebSocketCredentials(
            uri="wss://trusted.example.test/ws",
            api_key=OLD_KEY,
            identity="identity-a",
        )
        loads = iter((credentials, None))

        class _Socket:
            def __init__(self) -> None:
                self.sent: list[str] = []

            async def send(self, value: str) -> None:
                self.sent.append(value)

        class _Connect:
            def __init__(self, socket: _Socket) -> None:
                self.socket = socket
                self.uri = credentials.uri

            async def __aenter__(self) -> _Socket:
                return self.socket

            async def __aexit__(self, *_args: object) -> None:
                return None

        socket = _Socket()
        with (
            patch.object(
                websocket_module,
                "_load_websocket_credentials",
                side_effect=lambda *_args: next(loads),
            ),
            patch.object(
                websocket_module.websockets,
                "connect",
                return_value=_Connect(socket),
            ),
        ):
            asyncio.run(websocket_module.websocket_client(7, "identity-a"))

        self.assertEqual(socket.sent, [])

    def test_busy_websocket_stream_cannot_starve_runtime_rechecks(self) -> None:
        credentials = websocket_module._WebSocketCredentials(
            uri="wss://trusted.example.test/ws",
            api_key=OLD_KEY,
            identity="identity-b",
        )
        loads = iter((credentials, credentials, None))

        class _Socket:
            def __init__(self) -> None:
                self.sent: list[str] = []
                self.recv_calls = 0

            async def send(self, value: str) -> None:
                self.sent.append(value)

            async def recv(self) -> str:
                self.recv_calls += 1
                return '{"event":"busy"}'

        class _Connect:
            def __init__(self, socket: _Socket) -> None:
                self.socket = socket
                self.uri = credentials.uri

            async def __aenter__(self) -> _Socket:
                return self.socket

            async def __aexit__(self, *_args: object) -> None:
                return None

        socket = _Socket()
        with (
            patch.object(
                websocket_module,
                "_load_websocket_credentials",
                side_effect=lambda *_args: next(loads),
            ),
            patch.object(
                websocket_module.websockets,
                "connect",
                return_value=_Connect(socket),
            ),
            patch.object(websocket_module, "_WS_RUNTIME_RECHECK_SEC", 0),
        ):
            asyncio.run(websocket_module.websocket_client(8, "identity-b"))

        self.assertEqual(len(socket.sent), 1)
        self.assertEqual(socket.recv_calls, 0)

    def test_websocket_rechecks_before_forwarding_each_queued_command(self) -> None:
        credentials = websocket_module._WebSocketCredentials(
            uri="wss://trusted.example.test/ws",
            api_key=OLD_KEY,
            identity="identity-c",
        )
        loads = iter((credentials, credentials, None))

        class _Socket:
            def __init__(self) -> None:
                self.sent: list[str] = []

            async def send(self, value: str) -> None:
                self.sent.append(value)

        class _Connect:
            def __init__(self, socket: _Socket) -> None:
                self.socket = socket
                self.uri = credentials.uri

            async def __aenter__(self) -> _Socket:
                return self.socket

            async def __aexit__(self, *_args: object) -> None:
                return None

        socket = _Socket()
        websocket_module.message_queue.put("Full Update")
        try:
            with (
                patch.object(
                    websocket_module,
                    "_load_websocket_credentials",
                    side_effect=lambda *_args: next(loads),
                ),
                patch.object(
                    websocket_module.websockets,
                    "connect",
                    return_value=_Connect(socket),
                ),
            ):
                asyncio.run(websocket_module.websocket_client(9, "identity-c"))
        finally:
            while not websocket_module.message_queue.empty():
                websocket_module.message_queue.get_nowait()

        self.assertEqual(len(socket.sent), 1)

    def test_websocket_redirect_never_receives_the_backend_key(self) -> None:
        credentials = websocket_module._WebSocketCredentials(
            uri="wss://trusted.example.test/ws",
            api_key=OLD_KEY,
            identity="identity-redirect",
        )
        loads = iter((credentials,))

        class _Socket:
            def __init__(self) -> None:
                self.sent: list[str] = []

            async def send(self, value: str) -> None:
                self.sent.append(value)

        class _RedirectedConnect:
            uri = "wss://attacker.example.test/ws"

            def __init__(self, socket: _Socket) -> None:
                self.socket = socket

            async def __aenter__(self) -> _Socket:
                return self.socket

            async def __aexit__(self, *_args: object) -> None:
                return None

        socket = _Socket()
        with (
            patch.object(
                websocket_module,
                "_load_websocket_credentials",
                side_effect=lambda *_args: next(loads),
            ),
            patch.object(
                websocket_module.websockets,
                "connect",
                return_value=_RedirectedConnect(socket),
            ) as connect,
        ):
            asyncio.run(websocket_module.websocket_client(11, "identity-redirect"))

        self.assertEqual(socket.sent, [])
        self.assertIsNone(connect.call_args.kwargs["proxy"])

    def test_websocket_start_replaces_a_stale_task_identity(self) -> None:
        credentials = websocket_module._WebSocketCredentials(
            uri="wss://trusted.example.test/ws",
            api_key=OLD_KEY,
            identity="new-identity",
        )

        class _Task:
            def __init__(self) -> None:
                self.cancelled = False

            def done(self) -> bool:
                return False

            def cancel(self) -> bool:
                self.cancelled = True
                return True

        class _Loop:
            @staticmethod
            def is_closed() -> bool:
                return False

        old_task = _Task()
        new_task = _Task()
        previous = (
            websocket_module.websocket_task,
            websocket_module.websocket_loop,
            websocket_module.websocket_task_identity,
        )
        websocket_module.websocket_task = old_task  # type: ignore[assignment]
        websocket_module.websocket_loop = _Loop()  # type: ignore[assignment]
        websocket_module.websocket_task_identity = (10, "old-identity")

        def submit(coroutine: object, _loop: object) -> _Task:
            coroutine.close()  # type: ignore[attr-defined]
            return new_task

        try:
            with (
                patch.object(
                    websocket_module,
                    "_load_websocket_credentials",
                    return_value=credentials,
                ),
                patch.object(
                    websocket_module.asyncio,
                    "run_coroutine_threadsafe",
                    side_effect=submit,
                ),
            ):
                self.assertTrue(websocket_module.start_websocket(10))

            self.assertTrue(old_task.cancelled)
            self.assertEqual(
                websocket_module.websocket_task_identity,
                (10, "new-identity"),
            )
            self.assertIs(websocket_module.websocket_task, new_task)
        finally:
            (
                websocket_module.websocket_task,
                websocket_module.websocket_loop,
                websocket_module.websocket_task_identity,
            ) = previous

    def test_endpoint_save_cancels_any_long_lived_websocket(self) -> None:
        endpoint = self._create_enabled("websocket-cancel")
        endpoint.name = "websocket-cancel-renamed"

        with patch.object(websocket_module, "stop_websocket") as stop:
            endpoint.save(update_fields={"name"})

        stop.assert_called_once_with(int(endpoint.pk))

    def test_disabled_endpoint_storage_view_builds_no_url_header_or_request(
        self,
    ) -> None:
        disabled_endpoint = SimpleNamespace(pk=93, enabled=False, token=OLD_KEY)

        class _VisibleEndpoints:
            def filter(self, **kwargs: object) -> _VisibleEndpoints:
                self.assert_enabled = kwargs
                return self

            def first(self) -> object:
                return disabled_endpoint

        class _EmptyRelated:
            def count(self) -> int:
                return 0

            def only(self, *_fields: str) -> tuple[()]:
                return ()

        visible = _VisibleEndpoints()
        storage = SimpleNamespace(
            pk=1,
            name="local",
            cluster=SimpleNamespace(name="cluster-a"),
            nodes="",
            vm_backups=_EmptyRelated(),
            vm_snapshots=_EmptyRelated(),
        )

        with (
            patch(
                "netbox_proxbox.views.storage.FastAPIEndpoint.objects.restrict",
                return_value=visible,
            ),
            patch(
                "netbox_proxbox.views.storage.VirtualDisk.objects.filter",
                return_value=_EmptyRelated(),
            ),
            patch(
                "netbox_proxbox.views.storage.get_fastapi_url",
                side_effect=AssertionError("disabled endpoint URL must not be built"),
            ) as get_url,
            patch(
                "netbox_proxbox.views.storage.get_backend_auth_headers",
                side_effect=AssertionError(
                    "disabled endpoint header must not be built"
                ),
            ) as get_headers,
            patch(
                "netbox_proxbox.views.storage.requests.get",
                side_effect=AssertionError("disabled endpoint must not connect"),
            ) as request_get,
        ):
            context = ProxmoxStorageView().get_extra_context(
                SimpleNamespace(user=SimpleNamespace()),
                storage,
            )

        self.assertEqual(visible.assert_enabled, {"enabled": True})
        self.assertIn("No enabled FastAPI endpoint", context["storage_usage_detail"])
        get_url.assert_not_called()
        get_headers.assert_not_called()
        request_get.assert_not_called()
        self.assertEqual(self.backend.calls, [])

    def test_signal_job_helper_and_command_check_only_stored_key(self) -> None:
        endpoint = self._create_enabled("stored-consumers")
        self.backend.clear()

        self.assertTrue(_register_token_with_backend(endpoint))
        self.assertEqual(
            [method for method, _url, _kwargs in self.backend.calls],
            ["GET", "GET"],
        )
        self.backend.clear()

        ok, _message = ensure_backend_key_registered(endpoint_id=endpoint.pk)
        self.assertTrue(ok)
        self.assertEqual(
            [method for method, _url, _kwargs in self.backend.calls],
            ["GET", "GET"],
        )
        self.backend.clear()

        output = StringIO()
        call_command("proxbox_fix_tokens", stdout=output)
        self.assertIn("Registered with backend", output.getvalue())
        self.assertNotIn(OLD_KEY, output.getvalue())
        self.assertEqual(
            [method for method, _url, _kwargs in self.backend.calls],
            ["GET", "GET"],
        )

    def test_fix_command_never_contacts_a_disabled_endpoint(self) -> None:
        endpoint = self._create_enabled("disabled-command")
        endpoint.enabled = False
        endpoint.save(update_fields={"enabled"})
        self.backend.clear()

        output = StringIO()
        call_command("proxbox_fix_tokens", "--fix", stdout=output)

        self.assertIn("no network check was performed", output.getvalue())
        self.assertNotIn(OLD_KEY, output.getvalue())
        self.assertEqual(self.backend.calls, [])

    def test_fix_command_adopts_only_a_blank_legacy_fingerprint(self) -> None:
        endpoint = self._create_enabled("legacy-command")
        FastAPIEndpoint.objects.filter(pk=endpoint.pk).update(
            backend_key_target_fingerprint=""
        )
        self.backend.clear()

        output = StringIO()
        call_command("proxbox_fix_tokens", "--fix", stdout=output)

        endpoint.refresh_from_db()
        self.assertTrue(endpoint.backend_key_target_fingerprint)
        self.assertTrue(backend_key_runtime_is_trusted(endpoint))
        self.assertIn("target fingerprint recorded", output.getvalue())
        self.assertNotIn(OLD_KEY, output.getvalue())
        self.assertEqual(
            [method for method, _url, _kwargs in self.backend.calls],
            ["GET", "GET"],
        )

    def test_fix_command_default_mode_never_contacts_blank_legacy_target(
        self,
    ) -> None:
        endpoint = self._create_enabled("legacy-diagnostic")
        FastAPIEndpoint.objects.filter(pk=endpoint.pk).update(
            backend_key_target_fingerprint=""
        )
        self.backend.clear()

        output = StringIO()
        call_command("proxbox_fix_tokens", stdout=output)

        endpoint.refresh_from_db()
        self.assertEqual(endpoint.backend_key_target_fingerprint, "")
        self.assertIn("no network check was performed", output.getvalue())
        self.assertNotIn(OLD_KEY, output.getvalue())
        self.assertEqual(self.backend.calls, [])

    def test_fix_command_refuses_drift_before_any_network_or_save(self) -> None:
        ip_address = IPAddress.objects.create(address="192.0.2.130/32")
        self.backend.accepted_keys.add(OLD_KEY)
        endpoint = self._new_endpoint("drift-command")
        endpoint.ip_address = ip_address
        endpoint.token = OLD_KEY
        endpoint.save()
        endpoint.refresh_from_db()
        original_fingerprint = endpoint.backend_key_target_fingerprint
        self.backend.clear()

        ip_address.address = "192.0.2.131/32"
        ip_address.save(update_fields={"address"})
        output = StringIO()
        call_command("proxbox_fix_tokens", "--fix", stdout=output)

        endpoint.refresh_from_db()
        self.assertEqual(
            endpoint.backend_key_target_fingerprint,
            original_fingerprint,
        )
        self.assertIn("adopted target has drifted", output.getvalue())
        self.assertNotIn(OLD_KEY, output.getvalue())
        self.assertEqual(self.backend.calls, [])
