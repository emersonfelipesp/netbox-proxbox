"""Tests for ``netbox_proxbox.api.device_openbao_ssh_resolver`` (issue #614).

The module is exercised as a real path-loaded module (not an AST contract):
its only hard dependencies are ``django.apps``, ``django.contrib.contenttypes``,
and ``django.core.exceptions``, all of which are cheap to stub, and everything
netbox-openbao specific is resolved through ``apps.get_model`` so it can be
stubbed per test without installing the companion plugin.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "netbox_proxbox" / "api" / "device_openbao_ssh_resolver.py"


class _FakeApps:
    """Stand-in for ``django.apps.apps`` with a mutable installed-plugin set
    and a registry of models served by ``get_model``.
    """

    def __init__(self, installed: set[str], models: dict[tuple[str, str], Any]) -> None:
        self._installed = set(installed)
        self._models = dict(models)

    def is_installed(self, label: str) -> bool:
        return label in self._installed

    def get_model(self, app_label: str, model_name: str) -> Any:
        """Mirror real Django: a model the app doesn't define raises
        ``LookupError`` — a plain ``KeyError`` would let a test pass without
        actually exercising the code's ``LookupError`` handling.
        """
        try:
            return self._models[(app_label, model_name)]
        except KeyError:
            raise LookupError(
                f"App '{app_label}' doesn't have a '{model_name}' model."
            ) from None


class _FakeContentType:
    pk = 99


_FakeContentType.objects = types.SimpleNamespace(
    get_for_model=lambda _model: _FakeContentType()
)


def _load_module(
    monkeypatch,
    *,
    installed: set[str] = frozenset(),
    models: dict[tuple[str, str], Any] | None = None,
):
    django_root = types.ModuleType("django")
    django_apps_pkg = types.ModuleType("django.apps")
    django_apps_pkg.apps = _FakeApps(installed, models or {})
    django_root.apps = django_apps_pkg

    django_contrib = types.ModuleType("django.contrib")
    django_contrib_contenttypes = types.ModuleType("django.contrib.contenttypes")
    django_contrib_contenttypes_models = types.ModuleType(
        "django.contrib.contenttypes.models"
    )
    django_contrib_contenttypes_models.ContentType = _FakeContentType

    django_core = types.ModuleType("django.core")
    django_core_exceptions = types.ModuleType("django.core.exceptions")

    class PermissionDenied(Exception):
        pass

    django_core_exceptions.PermissionDenied = PermissionDenied

    for name, module in {
        "django": django_root,
        "django.apps": django_apps_pkg,
        "django.contrib": django_contrib,
        "django.contrib.contenttypes": django_contrib_contenttypes,
        "django.contrib.contenttypes.models": django_contrib_contenttypes_models,
        "django.core": django_core,
        "django.core.exceptions": django_core_exceptions,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    spec = importlib.util.spec_from_file_location(
        "netbox_proxbox.api.device_openbao_ssh_resolver", MODULE_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.api.device_openbao_ssh_resolver", module
    )
    spec.loader.exec_module(module)
    return module, PermissionDenied


def _node(*, device: Any = "sentinel-device", pk: int = 1, endpoint: Any = None):
    return types.SimpleNamespace(pk=pk, netbox_device=device, endpoint=endpoint)


# ---------------------------------------------------------------------------
# resolve_node_ssh_from_device_openbao — orchestration
# ---------------------------------------------------------------------------


def test_no_linked_device_returns_none(monkeypatch) -> None:
    module, _ = _load_module(monkeypatch, installed={"netbox_openbao"})
    node = _node(device=None)
    assert module.resolve_node_ssh_from_device_openbao(node) is None


def test_openbao_not_installed_returns_none(monkeypatch) -> None:
    module, _ = _load_module(monkeypatch, installed=set())
    node = _node()
    assert module.resolve_node_ssh_from_device_openbao(node) is None


def test_ssh_disabled_on_owning_endpoint_denies_before_any_lookup(monkeypatch) -> None:
    module, PermissionDenied = _load_module(monkeypatch, installed={"netbox_openbao"})
    node = _node(endpoint=types.SimpleNamespace(ssh_access_enabled=False))

    def _boom(*_args, **_kwargs):
        raise AssertionError("no lookup may run once SSH is gated off")

    monkeypatch.setattr(module, "_match_openbao_endpoint", _boom)
    with pytest.raises(PermissionDenied):
        module.resolve_node_ssh_from_device_openbao(node)


def test_ssh_enabled_endpoint_allows_lookup(monkeypatch) -> None:
    module, _ = _load_module(monkeypatch, installed={"netbox_openbao"})
    node = _node(endpoint=types.SimpleNamespace(ssh_access_enabled=True))

    monkeypatch.setattr(module, "_match_openbao_endpoint", lambda *a, **k: None)
    assert module.resolve_node_ssh_from_device_openbao(node) is None


def test_no_endpoint_owner_is_not_gated(monkeypatch) -> None:
    """A node with no owning ProxmoxEndpoint has nothing to gate on."""
    module, _ = _load_module(monkeypatch, installed={"netbox_openbao"})
    node = _node(endpoint=None)

    monkeypatch.setattr(module, "_match_openbao_endpoint", lambda *a, **k: None)
    assert module.resolve_node_ssh_from_device_openbao(node) is None


def test_match_reveals_and_returns_payload(monkeypatch) -> None:
    module, _ = _load_module(
        monkeypatch,
        installed={"netbox_openbao"},
        models={},
    )
    node = _node()
    endpoint = object()

    monkeypatch.setattr(module, "_match_openbao_endpoint", lambda *a, **k: endpoint)
    monkeypatch.setattr(
        module, "_reveal_openbao_endpoint", lambda *a, **k: {"openbao": True}
    )
    assert module.resolve_node_ssh_from_device_openbao(node) == {"openbao": True}


def test_denial_propagates(monkeypatch) -> None:
    module, PermissionDenied = _load_module(monkeypatch, installed={"netbox_openbao"})
    node = _node()

    def _deny(*_args, **_kwargs):
        raise PermissionDenied("ambiguous")

    monkeypatch.setattr(module, "_match_openbao_endpoint", _deny)
    with pytest.raises(PermissionDenied):
        module.resolve_node_ssh_from_device_openbao(node)


# ---------------------------------------------------------------------------
# _match_openbao_endpoint — fail closed on ambiguity, narrow by port
# ---------------------------------------------------------------------------


class _FakeEndpointQuerySet:
    def __init__(self, candidates: list[Any]) -> None:
        self._candidates = candidates

    def filter(self, **kwargs):
        if "port" in kwargs:
            narrowed = [c for c in self._candidates if c.port == kwargs["port"]]
            return _FakeEndpointQuerySet(narrowed)
        return self

    def __getitem__(self, item):
        return self._candidates[item]


def _service_endpoint_model(candidates: list[Any]) -> Any:
    queryset = _FakeEndpointQuerySet(candidates)
    return types.SimpleNamespace(
        objects=types.SimpleNamespace(filter=lambda **_: queryset)
    )


def _endpoint(*, port: int, credential_id: int) -> Any:
    return types.SimpleNamespace(pk=port, port=port, credential_id=credential_id)


def test_match_openbao_endpoint_no_candidates_returns_none(monkeypatch) -> None:
    module, _ = _load_module(
        monkeypatch,
        installed={"netbox_openbao"},
        models={("netbox_openbao", "ServiceEndpoint"): _service_endpoint_model([])},
    )
    assert module._match_openbao_endpoint(types.SimpleNamespace(pk=5)) is None


def test_match_openbao_endpoint_single_candidate(monkeypatch) -> None:
    endpoint = _endpoint(port=22, credential_id=1)
    module, _ = _load_module(
        monkeypatch,
        installed={"netbox_openbao"},
        models={
            ("netbox_openbao", "ServiceEndpoint"): _service_endpoint_model([endpoint])
        },
    )
    assert module._match_openbao_endpoint(types.SimpleNamespace(pk=5)) is endpoint


def test_match_openbao_endpoint_ambiguous_fails_closed(monkeypatch, caplog) -> None:
    first = _endpoint(port=22, credential_id=1)
    second = _endpoint(port=2222, credential_id=2)
    module, PermissionDenied = _load_module(
        monkeypatch,
        installed={"netbox_openbao"},
        models={
            ("netbox_openbao", "ServiceEndpoint"): _service_endpoint_model(
                [first, second]
            )
        },
    )
    with pytest.raises(PermissionDenied):
        module._match_openbao_endpoint(types.SimpleNamespace(pk=42))

    # Never log credential/material — only the non-secret device identifier.
    for record in caplog.records:
        assert "credential_id" not in record.getMessage()


def test_match_openbao_endpoint_ambiguity_narrowed_by_port(monkeypatch) -> None:
    first = _endpoint(port=22, credential_id=1)
    second = _endpoint(port=2222, credential_id=2)
    module, _ = _load_module(
        monkeypatch,
        installed={"netbox_openbao"},
        models={
            ("netbox_openbao", "ServiceEndpoint"): _service_endpoint_model(
                [first, second]
            )
        },
    )
    resolved = module._match_openbao_endpoint(types.SimpleNamespace(pk=5), port=2222)
    assert resolved is second


# ---------------------------------------------------------------------------
# Feature detection — netbox-openbao installed but predating ServiceEndpoint
# ---------------------------------------------------------------------------


def test_get_openbao_model_returns_none_for_a_missing_model(monkeypatch) -> None:
    """``apps.get_model()`` raises ``LookupError`` for a model an installed
    app genuinely doesn't define — not a fictitious stand-in exception — and
    ``_get_openbao_model()`` must convert that into "not available".
    """
    module, _ = _load_module(monkeypatch, installed={"netbox_openbao"}, models={})
    assert module._get_openbao_model("netbox_openbao", "ServiceEndpoint") is None


def test_match_openbao_endpoint_returns_none_when_service_endpoint_is_undefined(
    monkeypatch,
) -> None:
    """The pinned netbox-openbao revision this CI matrix installs predates
    ``ServiceEndpoint`` (it lands upstream as netbox-openbao commit e7f94ee,
    not yet in a public release — see docs/companion-plugins/netbox-openbao.md).
    That must degrade to the existing 404 path, not an uncaught 500.
    """
    module, _ = _load_module(
        monkeypatch,
        installed={"netbox_openbao"},
        models={},  # a registry that genuinely lacks ServiceEndpoint
    )
    assert module._match_openbao_endpoint(types.SimpleNamespace(pk=5)) is None


def test_resolve_node_ssh_returns_none_when_service_endpoint_is_undefined(
    monkeypatch,
) -> None:
    """End to end through the public entry point: netbox-openbao installed,
    SSH enabled, device linked, but ``ServiceEndpoint`` undefined — must
    return ``None`` (the caller's existing 404), never raise.
    """
    module, _ = _load_module(
        monkeypatch,
        installed={"netbox_openbao"},
        models={},
    )
    node = _node(endpoint=types.SimpleNamespace(ssh_access_enabled=True))
    assert module.resolve_node_ssh_from_device_openbao(node) is None


def test_reveal_openbao_endpoint_returns_none_when_credential_is_undefined(
    monkeypatch,
) -> None:
    """The unlikely counterpart: ``ServiceEndpoint`` is defined (a match was
    found) but ``Credential`` is not — also "not available", not a crash.
    """
    module, _ = _load_module(
        monkeypatch,
        installed={"netbox_openbao"},
        models={},  # Credential absent too
    )
    endpoint = types.SimpleNamespace(credential_id=1, port=22, pk=7)
    node = types.SimpleNamespace(pk=7)
    assert (
        module._reveal_openbao_endpoint(node, endpoint, user=_authenticated_user())
        is None
    )


# ---------------------------------------------------------------------------
# _reveal_openbao_endpoint — independent identity verification, material shaping
# ---------------------------------------------------------------------------


_UNSET = object()


class _FakeCredentialQuerySet:
    """Stand-in for ``Credential.objects`` that requires ``restrict()`` first.

    ``authorized_users`` is ``None`` for tests that are not about
    authorization at all (they pass), or an explicit set of user objects that
    ``restrict(user, "reveal")`` accepts — anything else is denied, mirroring
    NetBox's ``RestrictedQuerySet.restrict()``.
    """

    def __init__(
        self,
        credential: Any,
        *,
        expected_pk: int,
        expected_endpoint: int,
        authorized_users: list[Any] | None = None,
    ) -> None:
        self._credential = credential
        self._expected_pk = expected_pk
        self._expected_endpoint = expected_endpoint
        self._authorized_users = authorized_users
        self._restrict_call = _UNSET
        self._filters: dict = {}

    def restrict(self, user, action):
        self._restrict_call = (user, action)
        return self

    def filter(self, **kwargs):
        self._filters.update(kwargs)
        return self

    def first(self):
        if self._restrict_call is _UNSET:
            raise AssertionError(
                "Credential.objects must be restrict()ed before filter()/first()"
            )
        user, action = self._restrict_call
        if action != "reveal":
            return None
        if self._authorized_users is not None and user not in self._authorized_users:
            return None
        if self._filters.get("pk") != self._expected_pk:
            return None
        if self._filters.get("service_endpoints") != self._expected_endpoint:
            return None
        return self._credential


def _credential_model(
    credential: Any,
    *,
    endpoint_pk: int,
    authorized_users: list[Any] | None = None,
) -> Any:
    queryset = _FakeCredentialQuerySet(
        credential,
        expected_pk=credential.pk,
        expected_endpoint=endpoint_pk,
        authorized_users=authorized_users,
    )
    return types.SimpleNamespace(
        objects=types.SimpleNamespace(
            restrict=lambda user, action: queryset.restrict(user, action)
        )
    )


def _authenticated_user(name: str = "caller") -> Any:
    return types.SimpleNamespace(username=name, is_authenticated=True)


def _install_reveal_stub(monkeypatch, payload: dict | Exception) -> None:
    integrations_pkg = types.ModuleType("netbox_proxbox.integrations")
    openbao_mod = types.ModuleType("netbox_proxbox.integrations.openbao")

    def _reveal(_credential, *, user=None):
        if isinstance(payload, Exception):
            raise payload
        return payload

    openbao_mod.reveal_credential_material = _reveal
    root_pkg = sys.modules.get("netbox_proxbox") or types.ModuleType("netbox_proxbox")
    monkeypatch.setitem(sys.modules, "netbox_proxbox", root_pkg)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.integrations", integrations_pkg)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.integrations.openbao", openbao_mod)


def test_reveal_openbao_endpoint_rejects_unverifiable_identity(monkeypatch) -> None:
    """The endpoint's own reverse relation must corroborate the credential."""
    credential = types.SimpleNamespace(pk=1, credential_type="ssh-password")
    endpoint = types.SimpleNamespace(credential_id=1, port=22, pk=7)
    module, PermissionDenied = _load_module(
        monkeypatch,
        installed={"netbox_openbao"},
        # endpoint_pk mismatch: the fake credential model only vouches for pk 99.
        models={
            ("netbox_openbao", "Credential"): _credential_model(
                credential, endpoint_pk=99
            )
        },
    )
    node = types.SimpleNamespace(pk=7)
    with pytest.raises(PermissionDenied):
        module._reveal_openbao_endpoint(node, endpoint, user=_authenticated_user())


def test_reveal_openbao_endpoint_rejects_non_ssh_credential_type(monkeypatch) -> None:
    credential = types.SimpleNamespace(pk=1, credential_type="api-token")
    endpoint = types.SimpleNamespace(credential_id=1, port=22, pk=7)
    module, PermissionDenied = _load_module(
        monkeypatch,
        installed={"netbox_openbao"},
        models={
            ("netbox_openbao", "Credential"): _credential_model(
                credential, endpoint_pk=7
            )
        },
    )
    node = types.SimpleNamespace(pk=7)
    with pytest.raises(PermissionDenied):
        module._reveal_openbao_endpoint(node, endpoint, user=_authenticated_user())


def test_reveal_openbao_endpoint_rejects_missing_material(monkeypatch) -> None:
    credential = types.SimpleNamespace(
        pk=1, credential_type="ssh-password", username="root"
    )
    endpoint = types.SimpleNamespace(credential_id=1, port=22, pk=7)
    module, PermissionDenied = _load_module(
        monkeypatch,
        installed={"netbox_openbao"},
        models={
            ("netbox_openbao", "Credential"): _credential_model(
                credential, endpoint_pk=7
            )
        },
    )
    _install_reveal_stub(monkeypatch, {})
    node = types.SimpleNamespace(pk=7)
    with pytest.raises(PermissionDenied):
        module._reveal_openbao_endpoint(node, endpoint, user=_authenticated_user())


def test_reveal_openbao_endpoint_password_payload(monkeypatch) -> None:
    credential = types.SimpleNamespace(
        pk=1, credential_type="ssh-password", username="root"
    )
    endpoint = types.SimpleNamespace(credential_id=1, port=2222, pk=7)
    module, _ = _load_module(
        monkeypatch,
        installed={"netbox_openbao"},
        models={
            ("netbox_openbao", "Credential"): _credential_model(
                credential, endpoint_pk=7
            )
        },
    )
    _install_reveal_stub(monkeypatch, {"password": "s3cret"})
    node = types.SimpleNamespace(pk=7)

    payload = module._reveal_openbao_endpoint(
        node, endpoint, user=_authenticated_user()
    )
    assert payload == {
        "node_id": 7,
        "username": "root",
        "port": 2222,
        "auth_method": "password",
        "known_host_fingerprint": "",
        "sudo_required": False,
        "has_password": True,
        "has_private_key": False,
        "password": "s3cret",
        "private_key": "",
    }


def test_reveal_openbao_endpoint_keypair_payload(monkeypatch) -> None:
    credential = types.SimpleNamespace(
        pk=1, credential_type="ssh-keypair", username="root"
    )
    endpoint = types.SimpleNamespace(credential_id=1, port=None, pk=7)
    module, _ = _load_module(
        monkeypatch,
        installed={"netbox_openbao"},
        models={
            ("netbox_openbao", "Credential"): _credential_model(
                credential, endpoint_pk=7
            )
        },
    )
    _install_reveal_stub(monkeypatch, {"private_key": "-----BEGIN-----"})
    node = types.SimpleNamespace(pk=7)

    payload = module._reveal_openbao_endpoint(
        node, endpoint, user=_authenticated_user()
    )
    assert payload["auth_method"] == "key"
    assert payload["has_private_key"] is True
    assert payload["has_password"] is False
    assert payload["private_key"] == "-----BEGIN-----"
    assert payload["password"] == ""
    assert payload["port"] == 22  # falls back when the endpoint has no port


def test_reveal_openbao_endpoint_never_exposes_provider_errors(monkeypatch) -> None:
    credential = types.SimpleNamespace(
        pk=1, credential_type="ssh-password", username="root"
    )
    endpoint = types.SimpleNamespace(credential_id=1, port=22, pk=7)
    module, PermissionDenied = _load_module(
        monkeypatch,
        installed={"netbox_openbao"},
        models={
            ("netbox_openbao", "Credential"): _credential_model(
                credential, endpoint_pk=7
            )
        },
    )
    forbidden = "provider-secret-must-not-escape"
    _install_reveal_stub(
        monkeypatch, RuntimeError(f"provider exploded with {forbidden}")
    )
    node = types.SimpleNamespace(pk=7)

    with pytest.raises(PermissionDenied) as caught:
        module._reveal_openbao_endpoint(node, endpoint, user=_authenticated_user())
    assert forbidden not in str(caught.value)


def test_reveal_openbao_endpoint_denies_unauthenticated_caller(monkeypatch) -> None:
    credential = types.SimpleNamespace(
        pk=1, credential_type="ssh-password", username="root"
    )
    endpoint = types.SimpleNamespace(credential_id=1, port=22, pk=7)
    module, PermissionDenied = _load_module(
        monkeypatch,
        installed={"netbox_openbao"},
        models={
            ("netbox_openbao", "Credential"): _credential_model(
                credential, endpoint_pk=7
            )
        },
    )
    node = types.SimpleNamespace(pk=7)

    with pytest.raises(PermissionDenied):
        module._reveal_openbao_endpoint(node, endpoint, user=None)


def test_reveal_openbao_endpoint_denies_a_caller_without_reveal_permission(
    monkeypatch,
) -> None:
    """A caller only authorized for the local NodeSSHCredential path (e.g. one
    holding only ``view_nodesshcredential``) must not reveal OpenBao material
    through this fallback without netbox-openbao's own ``reveal_credential``
    object permission.
    """
    credential = types.SimpleNamespace(
        pk=1, credential_type="ssh-password", username="root"
    )
    endpoint = types.SimpleNamespace(credential_id=1, port=22, pk=7)
    authorized = _authenticated_user("authorized-caller")
    unauthorized = _authenticated_user("view-only-caller")
    module, PermissionDenied = _load_module(
        monkeypatch,
        installed={"netbox_openbao"},
        models={
            ("netbox_openbao", "Credential"): _credential_model(
                credential, endpoint_pk=7, authorized_users=[authorized]
            )
        },
    )
    node = types.SimpleNamespace(pk=7)

    with pytest.raises(PermissionDenied):
        module._reveal_openbao_endpoint(node, endpoint, user=unauthorized)


def test_reveal_openbao_endpoint_allows_an_authorized_caller(monkeypatch) -> None:
    """The counterpart of the denial test: a caller netbox-openbao's own
    ``Credential.objects.restrict(user, "reveal")`` would admit succeeds.
    """
    credential = types.SimpleNamespace(
        pk=1, credential_type="ssh-password", username="root"
    )
    endpoint = types.SimpleNamespace(credential_id=1, port=22, pk=7)
    authorized = _authenticated_user("authorized-caller")
    module, _ = _load_module(
        monkeypatch,
        installed={"netbox_openbao"},
        models={
            ("netbox_openbao", "Credential"): _credential_model(
                credential, endpoint_pk=7, authorized_users=[authorized]
            )
        },
    )
    _install_reveal_stub(monkeypatch, {"password": "s3cret"})
    node = types.SimpleNamespace(pk=7)

    payload = module._reveal_openbao_endpoint(node, endpoint, user=authorized)
    assert payload["password"] == "s3cret"
