"""Fail-closed contracts for proxbox-api key bootstrap and adoption."""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
from pathlib import Path
import sys
import types
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = "candidate-super-secret-0123456789abcdef"
INITIALIZED_STATUS = {"needs_bootstrap": False, "has_db_keys": True}
EMPTY_STATUS = {"needs_bootstrap": True, "has_db_keys": False}
KEY_LIST = {
    "keys": [
        {
            "id": 1,
            "label": "netbox",
            "is_active": True,
            "created_at": 1.0,
        }
    ]
}
REGISTERED = {"detail": "API key registered."}


@pytest.fixture
def adoption_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[types.ModuleType, types.ModuleType]:
    """Load the pure services without importing the NetBox plugin package."""
    package = types.ModuleType("netbox_proxbox")
    package.__path__ = [str(REPO_ROOT / "netbox_proxbox")]  # type: ignore[attr-defined]
    services = types.ModuleType("netbox_proxbox.services")
    services.__path__ = [  # type: ignore[attr-defined]
        str(REPO_ROOT / "netbox_proxbox" / "services")
    ]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", package)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", services)

    def load(name: str, path: Path) -> types.ModuleType:
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
        return module

    http_module = load(
        "netbox_proxbox.services.http_client",
        REPO_ROOT / "netbox_proxbox" / "services" / "http_client.py",
    )
    adoption_module = load(
        "netbox_proxbox.services.backend_key_adoption",
        REPO_ROOT / "netbox_proxbox" / "services" / "backend_key_adoption.py",
    )
    return adoption_module, http_module


@dataclass(frozen=True)
class _Response:
    status_code: int
    payload: object | None = None
    text: str = ""

    def json(self) -> object:
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class _Client:
    def __init__(
        self,
        *,
        status: _Response | Exception,
        authenticated: _Response | Exception | None = None,
        registration: _Response | Exception | None = None,
    ) -> None:
        self.responses = [status, authenticated]
        self.registration = registration
        self.get_calls: list[tuple[str, dict[str, object]]] = []
        self.post_calls: list[tuple[str, dict[str, object]]] = []

    def get(self, url: str, **kwargs: object) -> _Response:
        self.get_calls.append((url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        assert response is not None
        return response

    def post(self, url: str, **kwargs: object) -> _Response:
        self.post_calls.append((url, kwargs))
        response = self.registration
        if isinstance(response, Exception):
            raise response
        assert response is not None
        return response


def _endpoint(*, enabled: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        pk=7,
        enabled=enabled,
        domain="backend.example",
        ip_address=None,
        port=8800,
        use_https=True,
        verify_ssl=False,
        use_websocket=False,
        websocket_domain=None,
        websocket_port=None,
        server_side_websocket=False,
    )


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (
            {
                "exists": False,
                "current_enabled": True,
                "previous_enabled": False,
                "token_changed": True,
                "connection_changed": False,
            },
            "preflight",
        ),
        (
            {
                "exists": False,
                "current_enabled": False,
                "previous_enabled": False,
                "token_changed": True,
                "connection_changed": False,
            },
            "no_remote_check",
        ),
        (
            {
                "exists": True,
                "current_enabled": False,
                "previous_enabled": False,
                "token_changed": True,
                "connection_changed": False,
            },
            "reject_disabled_change",
        ),
        (
            {
                "exists": True,
                "current_enabled": True,
                "previous_enabled": False,
                "token_changed": False,
                "connection_changed": False,
            },
            "preflight",
        ),
        (
            {
                "exists": True,
                "current_enabled": True,
                "previous_enabled": True,
                "token_changed": True,
                "connection_changed": False,
            },
            "preflight",
        ),
        (
            {
                "exists": True,
                "current_enabled": True,
                "previous_enabled": True,
                "token_changed": False,
                "connection_changed": True,
            },
            "preflight",
        ),
        (
            {
                "exists": True,
                "current_enabled": True,
                "previous_enabled": True,
                "token_changed": False,
                "connection_changed": False,
            },
            "no_remote_check",
        ),
    ],
)
def test_transition_planner_is_fail_closed(
    state: dict[str, bool],
    expected: str,
    adoption_modules: tuple[types.ModuleType, types.ModuleType],
) -> None:
    adoption, _http = adoption_modules
    assert adoption.plan_backend_key_transition(**state) == expected


def test_valid_rotation_authenticates_once_and_never_calls_register(
    adoption_modules: tuple[types.ModuleType, types.ModuleType],
) -> None:
    adoption, _http = adoption_modules
    client = _Client(
        status=_Response(200, INITIALIZED_STATUS),
        authenticated=_Response(200, KEY_LIST),
    )

    proof = adoption.adopt_rotated_backend_key(
        _endpoint(), CANDIDATE, http_client=client
    )

    assert proof.action == "adopted"
    assert [call[0] for call in client.get_calls] == [
        "https://backend.example:8800/auth/bootstrap-status",
        "https://backend.example:8800/auth/keys",
    ]
    assert client.get_calls[1][1] == {
        "headers": {"X-Proxbox-API-Key": CANDIDATE},
        "verify": False,
        "timeout": 5,
        "allow_redirects": False,
    }
    assert client.post_calls == []


def test_initial_bootstrap_requires_exactly_one_successful_registration(
    adoption_modules: tuple[types.ModuleType, types.ModuleType],
) -> None:
    adoption, _http = adoption_modules
    client = _Client(
        status=_Response(200, EMPTY_STATUS),
        registration=_Response(201, REGISTERED),
    )

    proof = adoption.bootstrap_backend_key_at_url(
        "https://backend.example:8800",
        False,
        CANDIDATE,
        label="netbox-fastapi-7",
        http_client=client,
    )

    assert proof.action == "bootstrapped"
    assert len(client.get_calls) == 1
    assert client.post_calls == [
        (
            "https://backend.example:8800/auth/register-key",
            {
                "json": {
                    "api_key": CANDIDATE,
                    "label": "netbox-fastapi-7",
                },
                "verify": False,
                "timeout": 10,
                "allow_redirects": False,
            },
        )
    ]


@pytest.mark.parametrize("status", [401, 403, 409, 429, 500])
def test_rejected_candidate_fails_closed_without_secret_disclosure(
    status: int,
    adoption_modules: tuple[types.ModuleType, types.ModuleType],
) -> None:
    adoption, _http = adoption_modules
    client = _Client(
        status=_Response(200, INITIALIZED_STATUS),
        authenticated=_Response(status, {"detail": CANDIDATE}),
    )

    with pytest.raises(adoption.BackendKeyAdoptionError) as exc_info:
        adoption.adopt_rotated_backend_key(_endpoint(), CANDIDATE, http_client=client)

    assert CANDIDATE not in str(exc_info.value)
    assert client.post_calls == []
    assert len(client.get_calls) == 2


@pytest.mark.parametrize(
    "failure_name",
    [
        "HttpTimeoutError",
        "HttpSslError",
        "HttpConnectionError",
        "HttpError",
    ],
)
def test_transport_failures_are_single_attempt_and_secret_safe(
    failure_name: str,
    adoption_modules: tuple[types.ModuleType, types.ModuleType],
) -> None:
    adoption, http = adoption_modules
    failure = getattr(http, failure_name)(CANDIDATE)
    client = _Client(
        status=_Response(200, INITIALIZED_STATUS),
        authenticated=failure,
    )

    with pytest.raises(adoption.BackendKeyAdoptionError) as exc_info:
        adoption.adopt_rotated_backend_key(_endpoint(), CANDIDATE, http_client=client)

    assert CANDIDATE not in str(exc_info.value)
    assert len(client.get_calls) == 2
    assert client.post_calls == []


def test_bootstrap_conflict_is_not_treated_as_success(
    adoption_modules: tuple[types.ModuleType, types.ModuleType],
) -> None:
    adoption, _http = adoption_modules
    client = _Client(
        status=_Response(200, EMPTY_STATUS),
        registration=_Response(409, {"detail": CANDIDATE}),
    )

    with pytest.raises(adoption.BackendKeyAdoptionError) as exc_info:
        adoption.bootstrap_backend_key_at_url(
            "https://backend.example:8800",
            False,
            CANDIDATE,
            label="netbox-fastapi-7",
            http_client=client,
        )

    assert exc_info.value.code == "bootstrap_conflict"
    assert CANDIDATE not in str(exc_info.value)


def test_ordinary_adoption_never_mutates_an_uninitialized_backend(
    adoption_modules: tuple[types.ModuleType, types.ModuleType],
) -> None:
    adoption, _http = adoption_modules
    client = _Client(status=_Response(200, EMPTY_STATUS))

    with pytest.raises(adoption.BackendKeyAdoptionError) as exc_info:
        adoption.adopt_rotated_backend_key(_endpoint(), CANDIDATE, http_client=client)

    assert exc_info.value.code == "bootstrap_required"
    assert len(client.get_calls) == 1
    assert client.post_calls == []


def test_disabled_endpoint_never_connects(
    adoption_modules: tuple[types.ModuleType, types.ModuleType],
) -> None:
    adoption, _http = adoption_modules
    client = _Client(status=_Response(200, INITIALIZED_STATUS))

    with pytest.raises(adoption.BackendKeyAdoptionError) as exc_info:
        adoption.adopt_rotated_backend_key(
            _endpoint(enabled=False), CANDIDATE, http_client=client
        )

    assert exc_info.value.code == "endpoint_disabled"
    assert client.get_calls == []
    assert client.post_calls == []


def test_target_resolution_and_proof_are_bound_to_key_url_and_tls(
    adoption_modules: tuple[types.ModuleType, types.ModuleType],
) -> None:
    adoption, _http = adoption_modules
    endpoint = _endpoint()
    endpoint.domain = None
    endpoint.ip_address = SimpleNamespace(address="192.0.2.10/24")
    client = _Client(
        status=_Response(200, INITIALIZED_STATUS),
        authenticated=_Response(200, KEY_LIST),
    )

    proof = adoption.adopt_rotated_backend_key(endpoint, CANDIDATE, http_client=client)

    assert client.get_calls[0][0].startswith("https://192.0.2.10:8800/")
    assert adoption.backend_key_proof_matches(proof, endpoint, CANDIDATE)
    assert not adoption.backend_key_proof_matches(proof, endpoint, "different")
    assert not adoption.backend_key_proof_matches(object(), endpoint, CANDIDATE)
    endpoint.port = 0
    assert not adoption.backend_key_proof_matches(proof, endpoint, CANDIDATE)


def test_ipv6_target_uses_a_bracketed_authority(
    adoption_modules: tuple[types.ModuleType, types.ModuleType],
) -> None:
    adoption, _http = adoption_modules
    endpoint = _endpoint()
    endpoint.domain = None
    endpoint.ip_address = SimpleNamespace(address="2001:db8::10/128")
    client = _Client(
        status=_Response(200, INITIALIZED_STATUS),
        authenticated=_Response(200, KEY_LIST),
    )

    adoption.adopt_rotated_backend_key(endpoint, CANDIDATE, http_client=client)

    assert [url for url, _kwargs in client.get_calls] == [
        "https://[2001:db8::10]:8800/auth/bootstrap-status",
        "https://[2001:db8::10]:8800/auth/keys",
    ]


def test_target_fingerprint_binds_fallback_ip_even_when_domain_is_primary(
    adoption_modules: tuple[types.ModuleType, types.ModuleType],
) -> None:
    adoption, _http = adoption_modules
    endpoint = _endpoint()
    endpoint.ip_address = SimpleNamespace(address="192.0.2.10/24")

    initial = adoption.backend_key_target_fingerprint(endpoint)
    endpoint.ip_address = SimpleNamespace(address="192.0.2.11/24")

    assert adoption.backend_key_target_fingerprint(endpoint) != initial


def test_target_fingerprint_binds_every_websocket_authority_and_flag(
    adoption_modules: tuple[types.ModuleType, types.ModuleType],
) -> None:
    adoption, _http = adoption_modules
    endpoint = _endpoint()
    endpoint.use_websocket = True
    endpoint.server_side_websocket = True
    endpoint.websocket_domain = "stream.example"
    endpoint.websocket_port = 9443
    initial = adoption.backend_key_target_fingerprint(endpoint)

    for field, value in (
        ("websocket_domain", "other-stream.example"),
        ("websocket_port", 9444),
        ("server_side_websocket", False),
        ("use_websocket", False),
    ):
        changed = _endpoint()
        changed.use_websocket = True
        changed.server_side_websocket = True
        changed.websocket_domain = "stream.example"
        changed.websocket_port = 9443
        setattr(changed, field, value)
        if field == "use_websocket" and value is False:
            changed.server_side_websocket = False
        assert adoption.backend_key_target_fingerprint(changed) != initial


def test_server_websocket_cannot_be_enabled_without_websocket_policy(
    adoption_modules: tuple[types.ModuleType, types.ModuleType],
) -> None:
    adoption, _http = adoption_modules
    endpoint = _endpoint()
    endpoint.server_side_websocket = True

    with pytest.raises(adoption.BackendKeyAdoptionError) as exc_info:
        adoption.backend_key_target_fingerprint(endpoint)

    assert exc_info.value.code == "endpoint_websocket_policy_invalid"


def test_runtime_trust_requires_exact_durable_target_fingerprint(
    adoption_modules: tuple[types.ModuleType, types.ModuleType],
) -> None:
    adoption, _http = adoption_modules
    endpoint = _endpoint()
    endpoint.backend_key_target_fingerprint = ""
    assert not adoption.backend_key_runtime_is_trusted(endpoint)

    endpoint.backend_key_target_fingerprint = adoption.backend_key_target_fingerprint(
        endpoint
    )
    assert adoption.backend_key_runtime_is_trusted(endpoint)

    endpoint.port += 1
    assert not adoption.backend_key_runtime_is_trusted(endpoint)


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"domain": None, "ip_address": None}, "endpoint_address_missing"),
        (
            {"domain": "trusted.example@evil.example", "ip_address": None},
            "endpoint_domain_invalid",
        ),
        (
            {
                "domain": None,
                "ip_address": SimpleNamespace(address="not-an-ip/24"),
            },
            "endpoint_ip_invalid",
        ),
        ({"port": 0}, "endpoint_port_invalid"),
        ({"port": 65536}, "endpoint_port_invalid"),
    ],
)
def test_invalid_target_is_rejected_before_network(
    changes: dict[str, object],
    code: str,
    adoption_modules: tuple[types.ModuleType, types.ModuleType],
) -> None:
    adoption, _http = adoption_modules
    endpoint = _endpoint()
    for name, value in changes.items():
        setattr(endpoint, name, value)
    client = _Client(status=_Response(200, INITIALIZED_STATUS))

    with pytest.raises(adoption.BackendKeyAdoptionError) as exc_info:
        adoption.adopt_rotated_backend_key(endpoint, CANDIDATE, http_client=client)

    assert exc_info.value.code == code
    assert client.get_calls == []


@pytest.mark.parametrize(
    "base_url",
    [
        "https://trusted.example@evil.example:8800",
        "https://backend.example:8800/path",
        "https://backend.example:8800?candidate=secret",
        "ftp://backend.example:21",
        "https://2001:db8::10:8800",
    ],
)
def test_raw_base_url_rejects_noncanonical_authorities_before_network(
    base_url: str,
    adoption_modules: tuple[types.ModuleType, types.ModuleType],
) -> None:
    adoption, _http = adoption_modules
    client = _Client(status=_Response(200, INITIALIZED_STATUS))

    with pytest.raises(adoption.BackendKeyAdoptionError):
        adoption.inspect_backend_key_at_url(
            base_url,
            False,
            CANDIDATE,
            http_client=client,
        )

    assert client.get_calls == []
    assert client.post_calls == []


def test_missing_candidate_is_rejected_before_network(
    adoption_modules: tuple[types.ModuleType, types.ModuleType],
) -> None:
    adoption, _http = adoption_modules
    client = _Client(status=_Response(200, INITIALIZED_STATUS))

    with pytest.raises(adoption.BackendKeyAdoptionError) as exc_info:
        adoption.adopt_rotated_backend_key(_endpoint(), "  ", http_client=client)

    assert exc_info.value.code == "candidate_missing"
    assert client.get_calls == []


@pytest.mark.parametrize(
    ("status", "expected_code"),
    [
        ("timeout", "backend_timeout"),
        (_Response(503, {}), "bootstrap_status_http_503"),
        (_Response(200, ValueError(CANDIDATE)), "bootstrap_status_invalid"),
        (_Response(200, {}), "bootstrap_status_invalid"),
        (
            _Response(
                200,
                {"needs_bootstrap": True, "has_db_keys": True},
            ),
            "bootstrap_status_invalid",
        ),
        (
            _Response(
                200,
                {"needs_bootstrap": False, "has_db_keys": False},
            ),
            "bootstrap_status_invalid",
        ),
        (
            _Response(200, {"needs_bootstrap": "yes", "has_db_keys": False}),
            "bootstrap_status_invalid",
        ),
    ],
)
def test_bootstrap_status_failures_are_secret_safe(
    status: object,
    expected_code: str,
    adoption_modules: tuple[types.ModuleType, types.ModuleType],
) -> None:
    adoption, http = adoption_modules
    first_response = http.HttpTimeoutError(CANDIDATE) if status == "timeout" else status
    client = _Client(status=first_response)

    with pytest.raises(adoption.BackendKeyAdoptionError) as exc_info:
        adoption.adopt_rotated_backend_key(_endpoint(), CANDIDATE, http_client=client)

    assert exc_info.value.code == expected_code
    assert CANDIDATE not in str(exc_info.value)
    assert len(client.get_calls) == 1


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"keys": []},
        {"keys": "not-a-list"},
        {"keys": [{"id": 1}]},
        {
            "keys": [
                {
                    "id": True,
                    "label": "bad",
                    "is_active": True,
                    "created_at": 1.0,
                }
            ]
        },
        ValueError(CANDIDATE),
    ],
)
def test_authenticated_key_list_requires_the_exact_route_contract(
    payload: object,
    adoption_modules: tuple[types.ModuleType, types.ModuleType],
) -> None:
    adoption, _http = adoption_modules
    client = _Client(
        status=_Response(200, INITIALIZED_STATUS),
        authenticated=_Response(200, payload),
    )

    with pytest.raises(adoption.BackendKeyAdoptionError) as exc_info:
        adoption.adopt_rotated_backend_key(_endpoint(), CANDIDATE, http_client=client)

    assert exc_info.value.code == "key_list_invalid"
    assert CANDIDATE not in str(exc_info.value)
    assert client.post_calls == []


@pytest.mark.parametrize("redirect_status", [*range(300, 309), 399])
@pytest.mark.parametrize("phase", ["status", "validation", "bootstrap"])
def test_all_adoption_requests_reject_redirects_without_forwarding_credentials(
    redirect_status: int,
    phase: str,
    adoption_modules: tuple[types.ModuleType, types.ModuleType],
) -> None:
    adoption, _http = adoption_modules
    if phase == "status":
        client = _Client(status=_Response(redirect_status, {}))
        operation = lambda: adoption.adopt_rotated_backend_key(  # noqa: E731
            _endpoint(), CANDIDATE, http_client=client
        )
    elif phase == "validation":
        client = _Client(
            status=_Response(200, INITIALIZED_STATUS),
            authenticated=_Response(redirect_status, {}),
        )
        operation = lambda: adoption.adopt_rotated_backend_key(  # noqa: E731
            _endpoint(), CANDIDATE, http_client=client
        )
    else:
        client = _Client(
            status=_Response(200, EMPTY_STATUS),
            registration=_Response(redirect_status, {}),
        )
        operation = lambda: adoption.bootstrap_backend_key_at_url(  # noqa: E731
            "https://backend.example:8800",
            False,
            CANDIDATE,
            label="netbox-fastapi-7",
            http_client=client,
        )

    with pytest.raises(adoption.BackendKeyAdoptionError):
        operation()

    assert all(
        kwargs.get("allow_redirects") is False
        for _url, kwargs in [*client.get_calls, *client.post_calls]
    )


@pytest.mark.parametrize("payload", [{}, [], ValueError(CANDIDATE)])
def test_bootstrap_requires_the_exact_success_response(
    payload: object,
    adoption_modules: tuple[types.ModuleType, types.ModuleType],
) -> None:
    adoption, _http = adoption_modules
    client = _Client(
        status=_Response(200, EMPTY_STATUS),
        registration=_Response(201, payload),
    )

    with pytest.raises(adoption.BackendKeyAdoptionError) as exc_info:
        adoption.bootstrap_backend_key_at_url(
            "https://backend.example:8800",
            False,
            CANDIDATE,
            label="netbox-fastapi-7",
            http_client=client,
        )

    assert exc_info.value.code == "bootstrap_response_invalid"
    assert CANDIDATE not in str(exc_info.value)


def test_bootstrap_transport_failure_is_secret_safe(
    adoption_modules: tuple[types.ModuleType, types.ModuleType],
) -> None:
    adoption, http = adoption_modules
    client = _Client(
        status=_Response(200, EMPTY_STATUS),
        registration=http.HttpConnectionError(CANDIDATE),
    )

    with pytest.raises(adoption.BackendKeyAdoptionError) as exc_info:
        adoption.bootstrap_backend_key_at_url(
            "https://backend.example:8800",
            False,
            CANDIDATE,
            label="netbox-fastapi-7",
            http_client=client,
        )

    assert exc_info.value.code == "backend_unreachable"
    assert CANDIDATE not in str(exc_info.value)
    assert len(client.post_calls) == 1


def test_read_only_inspection_rejects_disabled_and_empty_url(
    adoption_modules: tuple[types.ModuleType, types.ModuleType],
) -> None:
    adoption, _http = adoption_modules
    client = _Client(status=_Response(200, INITIALIZED_STATUS))

    with pytest.raises(adoption.BackendKeyAdoptionError) as disabled:
        adoption.inspect_backend_key(
            _endpoint(enabled=False), CANDIDATE, http_client=client
        )
    with pytest.raises(adoption.BackendKeyAdoptionError) as missing:
        adoption.inspect_backend_key_at_url("", False, CANDIDATE, http_client=client)

    assert disabled.value.code == "endpoint_disabled"
    assert missing.value.code == "endpoint_address_missing"
    assert client.get_calls == []


def test_all_persistence_entry_points_use_the_shared_gate() -> None:
    model_source = (REPO_ROOT / "netbox_proxbox/models/fastapi_endpoint.py").read_text(
        encoding="utf-8"
    )
    form_source = (REPO_ROOT / "netbox_proxbox/forms/fastapi.py").read_text(
        encoding="utf-8"
    )
    serializer_source = (
        REPO_ROOT / "netbox_proxbox/api/serializers/endpoints.py"
    ).read_text(encoding="utf-8")
    signal_source = (REPO_ROOT / "netbox_proxbox/signals.py").read_text(
        encoding="utf-8"
    )
    command_source = (
        REPO_ROOT / "netbox_proxbox/management/commands/proxbox_fix_tokens.py"
    ).read_text(encoding="utf-8")

    assert "prepare_backend_key_transition" in model_source
    assert model_source.index("prepare_backend_key_transition") < model_source.index(
        "super().save"
    )
    assert "class BackendKeyAdoptionFormMixin" in form_source
    assert "instance.save()" in form_source
    assert "AbortRequest" in form_source
    assert "BackendKeyAdoptionValidationMixin" in serializer_source
    assert "adopt_rotated_backend_key" in signal_source
    assert "status_code == 409" not in signal_source
    assert "Token Preview" not in command_source
    assert "import requests" not in command_source
    assert "inspect_backend_key" in command_source
