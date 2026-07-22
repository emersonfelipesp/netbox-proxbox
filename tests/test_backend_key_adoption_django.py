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
from django.db import IntegrityError, transaction  # noqa: E402
from django.db.models.signals import post_save  # noqa: E402
from django.test import TransactionTestCase  # noqa: E402
from ipam.models import IPAddress  # noqa: E402

from netbox_proxbox.api.serializers.endpoints import (  # noqa: E402
    FastAPIEndpointSerializer,
)
from netbox_proxbox.forms.fastapi import (  # noqa: E402
    FastAPIEndpointForm,
    FastAPIEndpointImportForm,
)
from netbox_proxbox.models import FastAPIEndpoint  # noqa: E402
from netbox_proxbox.services.backend_auth import (  # noqa: E402
    ensure_backend_key_registered,
)
from netbox_proxbox.services.backend_key_adoption import (  # noqa: E402
    backend_key_runtime_is_trusted,
)
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

    def setUp(self) -> None:
        self.backend = _StatefulBackend()
        self._client_patch = patch(
            "netbox_proxbox.services.backend_key_adoption.get_default_http_client",
            return_value=self.backend,
        )
        self._client_patch.start()

    def tearDown(self) -> None:
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

        endpoint.refresh_from_db()
        self.assertEqual(endpoint.token_enc, "")
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

    def test_new_enabled_blank_is_rejected_without_http_or_row(self) -> None:
        endpoint = self._new_endpoint("enabled-blank")

        with self.assertRaises(ValidationError):
            endpoint.save()

        self.assertFalse(FastAPIEndpoint.objects.filter(name="enabled-blank").exists())
        self.assertEqual(self.backend.calls, [])

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

    def test_activation_requires_explicit_resubmission(self) -> None:
        endpoint = self._create_enabled("explicit-activation")
        endpoint.enabled = False
        endpoint.save(update_fields={"enabled"})
        endpoint.refresh_from_db()
        self.backend.clear()

        endpoint.enabled = True
        with self.assertRaises(ValidationError):
            endpoint.save(update_fields={"enabled"})

        self.assertFalse(FastAPIEndpoint.objects.get(pk=endpoint.pk).enabled)
        self.assertEqual(self.backend.calls, [])

        endpoint.refresh_from_db()
        endpoint.enabled = True
        endpoint.token = OLD_KEY
        endpoint.save(update_fields={"enabled"})
        self.assertTrue(FastAPIEndpoint.objects.get(pk=endpoint.pk).enabled)
        self.assertEqual(
            [method for method, _url, _kwargs in self.backend.calls],
            ["GET", "GET"],
        )

    def test_target_change_requires_key_and_validates_exact_next_target(self) -> None:
        endpoint = self._create_enabled("target-change")
        endpoint.refresh_from_db()
        original_ciphertext = endpoint.token_enc
        endpoint.domain = "changed.example.test"
        self.backend.clear()

        with self.assertRaises(ValidationError):
            endpoint.save(update_fields={"domain"})
        self.assertEqual(self.backend.calls, [])

        endpoint.token = OLD_KEY
        endpoint.save(update_fields={"domain"})
        self.assertTrue(
            all(
                url.startswith("https://changed.example.test:8800/")
                for _method, url, _kwargs in self.backend.calls
            )
        )
        self.assertEqual(
            FastAPIEndpoint.objects.get(pk=endpoint.pk).token_enc,
            original_ciphertext,
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

    def test_websocket_authority_change_requires_explicit_key_and_uses_primary_server_url(
        self,
    ) -> None:
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
        with self.assertRaises(ValidationError):
            endpoint.save(update_fields={"websocket_domain"})
        self.assertEqual(self.backend.calls, [])

        endpoint.token = OLD_KEY
        endpoint.save(update_fields={"websocket_domain"})
        self.assertEqual(
            [method for method, _url, _kwargs in self.backend.calls],
            ["GET", "GET"],
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
