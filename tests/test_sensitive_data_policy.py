"""Behavioral tests for the default-off sensitive-disclosure authorization rule."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest


class PolicyDatabaseError(Exception):
    """Synthetic database failure used without a live NetBox database."""


class PolicyPermissionDenied(Exception):
    """Synthetic Django policy rejection."""


@pytest.fixture
def policy(monkeypatch):
    """Load actual policy logic with only its storage and exception dependencies stubbed."""
    exceptions = ModuleType("django.core.exceptions")
    exceptions.ObjectDoesNotExist = type("ObjectDoesNotExist", (Exception,), {})
    exceptions.PermissionDenied = PolicyPermissionDenied
    database = ModuleType("django.db")
    database.DatabaseError = PolicyDatabaseError
    manager = Mock()
    manager.filter.return_value.exists.return_value = False
    models = ModuleType("netbox_proxbox.models.sensitive_data_access")
    models.ProxboxSensitiveDataAccess = SimpleNamespace(objects=manager)
    monkeypatch.setitem(sys.modules, "django.core.exceptions", exceptions)
    monkeypatch.setitem(sys.modules, "django.db", database)
    monkeypatch.setitem(sys.modules, models.__name__, models)
    path = Path(__file__).resolve().parents[1] / "netbox_proxbox/sensitive_data.py"
    spec = importlib.util.spec_from_file_location("tested_sensitive_data_policy", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, manager


def user(**overrides):
    """Return only synthetic user state, never a live credential or grant."""
    fields = dict(
        pk=17,
        is_active=True,
        is_authenticated=True,
        is_superuser=False,
        is_staff=True,
        has_perm=lambda permission: True,
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


@pytest.mark.parametrize("flag", [False, True])
@pytest.mark.parametrize("superuser", [False, True])
@pytest.mark.parametrize("active", [False, True])
@pytest.mark.parametrize("authenticated", [False, True])
def test_sensitive_policy_matrix(policy, flag, superuser, active, authenticated):
    module, manager = policy
    manager.filter.return_value.exists.return_value = flag
    principal = user(
        is_active=active, is_authenticated=authenticated, is_superuser=superuser
    )
    expected = active and authenticated and (superuser or flag)
    assert module.can_access_sensitive_data(principal) is expected
    if not active or not authenticated or superuser:
        manager.filter.assert_not_called()
    else:
        manager.filter.assert_called_once_with(
            user_id=17, can_access_sensitive_data=True
        )


def test_revocation_ignores_cached_positive_relation(policy):
    module, manager = policy
    principal = user(
        proxbox_sensitive_data_access=SimpleNamespace(can_access_sensitive_data=True)
    )
    manager.filter.return_value.exists.side_effect = [True, False]
    assert module.can_access_sensitive_data(principal) is True
    assert module.can_access_sensitive_data(principal) is False
    assert manager.filter.call_count == 2


def test_unavailable_policy_fails_closed(policy):
    module, manager = policy
    manager.filter.side_effect = PolicyDatabaseError("synthetic unavailable policy")
    assert module.can_access_sensitive_data(user()) is False
    with pytest.raises(PolicyPermissionDenied, match="not authorized"):
        module.require_sensitive_data_access(user())


def test_model_permissions_and_staff_do_not_confer_access(policy):
    module, manager = policy
    assert module.can_access_sensitive_data(user()) is False
    assert module.is_active_superuser(user()) is False


def test_missing_user_identity_fails_closed(policy):
    module, manager = policy
    assert module.can_access_sensitive_data(user(pk=None)) is False
    manager.filter.assert_not_called()


def test_superuser_needs_no_grant_row(policy):
    module, manager = policy
    module.require_sensitive_data_access(user(is_superuser=True))
    manager.filter.assert_not_called()


@pytest.fixture
def export_helpers(policy, monkeypatch):
    """Execute the real export helpers with synthetic storage and provider I/O."""
    module, manager = policy
    monkeypatch.setitem(sys.modules, "netbox_proxbox.sensitive_data", module)
    models = ModuleType("netbox_proxbox.models")
    for name in ("ProxmoxEndpoint", "NetBoxEndpoint", "FastAPIEndpoint"):
        setattr(models, name, SimpleNamespace)
    monkeypatch.setitem(sys.modules, models.__name__, models)
    vault = ModuleType("netbox_proxbox.integrations.openbao")
    vault.endpoint_uses_openbao_storage = Mock(return_value=False)
    vault.resolve_endpoint_password = Mock(return_value="vault-password-sentinel")
    vault.resolve_endpoint_token_value = Mock(return_value="vault-token-sentinel")
    single = ModuleType("netbox_proxbox.integrations.openbao_single")
    single.owner_uses_openbao_storage = Mock(return_value=False)
    single.resolve_single_secret = Mock(return_value="vault-backend-sentinel")
    monkeypatch.setitem(sys.modules, vault.__name__, vault)
    monkeypatch.setitem(sys.modules, single.__name__, single)
    helpers = {}
    root = Path(__file__).resolve().parents[1]
    for kind in ("proxmox", "netbox", "fastapi"):
        path = root / f"netbox_proxbox/views/endpoints/{kind}_export.py"
        spec = importlib.util.spec_from_file_location(f"tested_{kind}_export", path)
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        helpers[kind] = helper
    return helpers, manager, vault, single


def export_endpoint(kind):
    """Track secret reads independently of the export's field allowlist."""
    reads = []

    class Endpoint(SimpleNamespace):
        @property
        def password(self):
            reads.append("password")
            return "password-sentinel"

        @property
        def token_value(self):
            reads.append("token_value")
            return "proxmox-token-sentinel"

        @property
        def token(self):
            reads.append("token")
            if kind == "netbox":
                return SimpleNamespace(
                    key="core-v1-key-sentinel", plaintext="core-v1-token-sentinel"
                )
            return "backend-token-sentinel"

        @property
        def token_key(self):
            reads.append("token_key")
            return "netbox-v2-key-sentinel"

        @property
        def token_secret(self):
            reads.append("token_secret")
            return "netbox-v2-secret-sentinel"

    endpoint = Endpoint(
        pk=7,
        name="synthetic-endpoint",
        domain="pve.example.test",
        ip_address=None,
        port=8006,
        mode="cluster",
        version="8.3",
        repoid="",
        username="root@pam",
        verify_ssl=True,
        site=None,
        tenant=None,
        token_name="",
        token_version="v1",
        use_https=True,
        use_websocket=False,
        websocket_domain="",
        websocket_port=None,
        server_side_websocket=False,
        tags=SimpleNamespace(all=lambda: []),
        openbao_password_credential_uuid=None,
        openbao_token_credential_uuid=None,
    )
    return endpoint, reads


@pytest.mark.parametrize("kind", ["proxmox", "netbox", "fastapi"])
def test_safe_export_never_reads_secret_properties(export_helpers, kind):
    helpers, manager, vault, single = export_helpers
    endpoint, reads = export_endpoint(kind)
    row = getattr(helpers[kind], f"_serialize_{kind}_endpoint")(endpoint, False)
    assert reads == []
    assert not any("sentinel" in value for value in row.values())
    manager.filter.assert_not_called()
    vault.endpoint_uses_openbao_storage.assert_not_called()
    single.owner_uses_openbao_storage.assert_not_called()


@pytest.mark.parametrize("kind", ["proxmox", "netbox", "fastapi"])
@pytest.mark.parametrize("principal", [None, user(), user(is_active=False)])
def test_denied_helper_resolves_no_material(export_helpers, kind, principal):
    helpers, manager, vault, single = export_helpers
    endpoint, reads = export_endpoint(kind)
    with pytest.raises(PolicyPermissionDenied, match="not authorized"):
        getattr(helpers[kind], f"_serialize_{kind}_endpoint")(
            endpoint, True, user=principal
        )
    assert reads == []
    vault.endpoint_uses_openbao_storage.assert_not_called()
    single.owner_uses_openbao_storage.assert_not_called()


@pytest.mark.parametrize("kind", ["proxmox", "netbox", "fastapi"])
@pytest.mark.parametrize("superuser", [False, True])
def test_authorized_legacy_export_and_revocation(export_helpers, kind, superuser):
    helpers, manager, vault, single = export_helpers
    manager.filter.return_value.exists.return_value = True
    principal = user(is_superuser=superuser)
    endpoint, reads = export_endpoint(kind)
    serialize = getattr(helpers[kind], f"_serialize_{kind}_endpoint")
    row = serialize(endpoint, True, user=principal)
    expected = {
        "proxmox": {
            "password": "password-sentinel",
            "token_value": "proxmox-token-sentinel",
        },
        "netbox": {
            "token": "core-v1-token-sentinel",
            "token_key": "netbox-v2-key-sentinel",
            "token_secret": "netbox-v2-secret-sentinel",
        },
        "fastapi": {"token": "backend-token-sentinel"},
    }
    for field, value in expected[kind].items():
        assert row[field] == value
    if not superuser:
        manager.filter.return_value.exists.return_value = False
        reads.clear()
        with pytest.raises(PolicyPermissionDenied):
            serialize(endpoint, True, user=principal)
        assert reads == []


@pytest.mark.parametrize("kind", ["proxmox", "fastapi"])
def test_vault_export_uses_actor_and_never_falls_back(export_helpers, kind):
    helpers, manager, vault, single = export_helpers
    principal = user(is_superuser=True)
    endpoint, reads = export_endpoint(kind)
    vault.endpoint_uses_openbao_storage.return_value = True
    single.owner_uses_openbao_storage.return_value = True
    resolver = (
        vault.resolve_endpoint_password
        if kind == "proxmox"
        else single.resolve_single_secret
    )
    serialize = getattr(helpers[kind], f"_serialize_{kind}_endpoint")
    serialize(endpoint, True, user=principal)
    resolver.assert_called_once_with(endpoint, user=principal)
    assert reads == []
    resolver.side_effect = PolicyPermissionDenied("provider reveal denied")
    with pytest.raises(PolicyPermissionDenied, match="provider reveal denied"):
        serialize(endpoint, True, user=principal)
    assert reads == []


@pytest.mark.parametrize(
    "token, expected",
    [
        (None, ""),
        (SimpleNamespace(key="legacy-v1-sentinel"), "legacy-v1-sentinel"),
        (SimpleNamespace(version=1, plaintext="v1-sentinel", key=None), "v1-sentinel"),
        (SimpleNamespace(version=2, plaintext=None, key="nbt_identifier"), ""),
    ],
)
def test_netbox_core_token_compatibility(export_helpers, token, expected):
    helpers, _, _, _ = export_helpers
    assert (
        helpers["netbox"]._legacy_token_material(SimpleNamespace(token=token))
        == expected
    )


@pytest.fixture
def protected_export(policy, monkeypatch):
    """Run the real failure boundary without a database, network, or real secret."""
    module, manager = policy
    monkeypatch.setitem(sys.modules, "netbox_proxbox.sensitive_data", module)

    class Response(dict):
        def __init__(self, content, status=200):
            super().__init__()
            self.content = content.encode()
            self.status_code = status

    http = ModuleType("django.http")
    http.HttpRequest = object
    http.HttpResponse = Response
    database_models = ModuleType("django.db.models")
    database_models.QuerySet = object
    debug = ModuleType("django.views.decorators.debug")
    debug.sensitive_variables = lambda: lambda function: function
    query = ModuleType("utilities.query")
    query.reapply_model_ordering = lambda queryset: queryset
    for dependency in (http, database_models, debug, query):
        monkeypatch.setitem(sys.modules, dependency.__name__, dependency)
    path = (
        Path(__file__).resolve().parents[1]
        / "netbox_proxbox/views/endpoints/sensitive_export.py"
    )
    spec = importlib.util.spec_from_file_location("tested_protected_export", path)
    boundary = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(boundary)
    view = boundary.SensitiveExportMixin()
    view.queryset = SimpleNamespace(
        model=SimpleNamespace(_meta=SimpleNamespace(label_lower="netbox_proxbox.test"))
    )
    view._export_response = Mock(return_value=Response("synthetic-export-sentinel"))
    request = SimpleNamespace(
        user=user(),
        POST={"token": "submitted-token-sentinel"},
        META={"HTTP_AUTHORIZATION": "Bearer header-token-sentinel"},
    )
    return view, request, manager, Response


def test_protected_export_denies_before_serialization(protected_export, caplog):
    import logging

    view, request, manager, _ = protected_export
    with caplog.at_level(logging.INFO, logger="netbox_proxbox.sensitive_export"):
        response = view.protected_export_response(
            request, include_sensitive=True, data_format="json"
        )
    assert response.status_code == 403
    assert response["Cache-Control"] == "no-store"
    view._export_response.assert_not_called()
    assert "result=denied actor_id=17" in caplog.text
    assert "object_ids=() format=json" in caplog.text
    assert not any("sentinel" in record.getMessage() for record in caplog.records)
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.parametrize(
    "failure, status, result",
    [
        (PolicyPermissionDenied("provider-secret-sentinel"), 403, "denied"),
        (ValueError("decryption-secret-sentinel"), 503, "unavailable"),
        (RuntimeError("provider-secret-sentinel"), 503, "unavailable"),
    ],
)
def test_protected_export_contains_secret_bearing_failures(
    protected_export, caplog, failure, status, result
):
    import logging
    from uuid import UUID

    view, request, manager, _ = protected_export
    manager.filter.return_value.exists.return_value = True
    view._export_response.side_effect = failure
    with caplog.at_level(logging.INFO, logger="netbox_proxbox.sensitive_export"):
        response = view.protected_export_response(
            request, include_sensitive=True, data_format="yaml"
        )
    assert response.status_code == status
    assert response["Cache-Control"] == "no-store"
    UUID(response["X-Export-Correlation-ID"])
    assert "sentinel" not in response.content.decode()
    assert "sentinel" not in repr(dict(response))
    assert "sentinel" not in caplog.text
    assert f"result={result}" in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


def test_protected_export_audits_identifiers_not_material(protected_export, caplog):
    import logging

    view, request, manager, Response = protected_export
    manager.filter.return_value.exists.return_value = True

    def serialize(*args, **kwargs):
        view._export_object_ids = (7, 9)
        return Response("synthetic-export-sentinel")

    view._export_response.side_effect = serialize
    with caplog.at_level(logging.INFO, logger="netbox_proxbox.sensitive_export"):
        response = view.protected_export_response(
            request, include_sensitive=True, data_format="csv"
        )
    assert response.status_code == 200
    assert response.content == b"synthetic-export-sentinel"
    assert "object_ids=(7, 9) format=csv" in caplog.text
    assert "result=success" in caplog.text
    assert "sentinel" not in caplog.text


def test_safe_response_does_not_query_sensitive_policy(protected_export):
    view, request, manager, _ = protected_export
    response = view.protected_export_response(
        request, include_sensitive=False, data_format="csv"
    )
    assert response.status_code == 200
    manager.filter.assert_not_called()


def test_protected_export_revocation_on_next_request(protected_export):
    view, request, manager, _ = protected_export
    manager.filter.return_value.exists.side_effect = [True, False]
    assert (
        view.protected_export_response(
            request, include_sensitive=True, data_format="json"
        ).status_code
        == 200
    )
    assert (
        view.protected_export_response(
            request, include_sensitive=True, data_format="json"
        ).status_code
        == 403
    )
    assert view._export_response.call_count == 1


class ExportParameters(dict):
    """Represent repeated request parameters without Django or real input."""

    def getlist(self, name):
        return self.get(name, [])


@pytest.fixture
def scoped_export(protected_export, monkeypatch):
    """Execute real selection logic against a storage-only synthetic queryset."""
    original, request, manager, _ = protected_export
    request.GET = ExportParameters()
    request.POST = ExportParameters()
    events = []
    actor = request.user

    class StorageQuerySet:
        def __init__(self, rows):
            self.rows = tuple(rows)

        def restrict(self, principal, action):
            assert principal is actor
            assert action == "view"
            events.append(("restrict", principal, action))
            return StorageQuerySet(pk for pk in self.rows if pk in {7, 9})

        def filter(self, *, pk__in):
            events.append(("filter", frozenset(pk__in)))
            return StorageQuerySet(pk for pk in self.rows if pk in pk__in)

        def values_list(self, name, *, flat):
            assert name == "pk"
            assert flat is True
            events.append(("values_list", self.rows))
            return self.rows

    source = Mock(return_value=StorageQuerySet((7, 9, 11)))

    class StorageSource:
        def get_queryset(self, actual_request):
            return source(actual_request)

    class ScopedView(type(original), StorageSource):
        pass

    view = ScopedView()
    view.queryset = original.queryset
    view.filterset = None
    ordering = Mock(side_effect=lambda queryset: queryset)
    monkeypatch.setitem(
        view.authorized_export_queryset.__func__.__globals__,
        "reapply_model_ordering",
        ordering,
    )
    return view, request, manager, source, ordering, events


@pytest.mark.parametrize(
    "principal",
    [user(), user(is_authenticated=False), user(is_active=False), user(pk=None)],
)
def test_sensitive_queryset_denies_before_storage(scoped_export, principal):
    view, request, _, source, ordering, events = scoped_export
    request.user = principal
    with pytest.raises(PolicyPermissionDenied, match="not authorized"):
        view.authorized_export_queryset(request, include_sensitive=True)
    source.assert_not_called()
    ordering.assert_not_called()
    assert events == []


@pytest.mark.parametrize("sensitive", [False, True])
def test_export_queryset_restricts_actual_actor(scoped_export, sensitive):
    view, request, manager, source, ordering, events = scoped_export
    manager.filter.return_value.exists.return_value = True
    result = view.authorized_export_queryset(request, include_sensitive=sensitive)
    assert result.rows == (7, 9)
    assert events[0] == ("restrict", request.user, "view")
    source.assert_called_once_with(request)
    ordering.assert_called_once_with(result)
    if sensitive:
        assert view._export_object_ids == (7, 9)
    else:
        manager.filter.assert_not_called()


@pytest.mark.parametrize("sensitive", [False, True])
def test_export_selection_merges_get_post_and_deduplicates(scoped_export, sensitive):
    view, request, manager, _, ordering, _ = scoped_export
    manager.filter.return_value.exists.return_value = True
    request.GET = ExportParameters(id=["7", "7"])
    request.POST = ExportParameters(pk=["9", "7"])
    result = view.authorized_export_queryset(request, include_sensitive=sensitive)
    assert result.rows == (7, 9)
    ordering.assert_called_once_with(result)


@pytest.mark.parametrize("sensitive", [False, True])
@pytest.mark.parametrize("selected", [["7", "11"], ["11"], ["999"], ["-1"]])
def test_export_selection_never_silently_drops_invisible_ids(
    scoped_export, sensitive, selected
):
    view, request, manager, _, ordering, events = scoped_export
    manager.filter.return_value.exists.return_value = True
    request.POST = ExportParameters(pk=selected)
    view.filterset = Mock(
        side_effect=lambda parameters, queryset, *, request: SimpleNamespace(
            qs=queryset
        )
    )
    with pytest.raises(PolicyPermissionDenied, match="selection is not authorized"):
        view.authorized_export_queryset(request, include_sensitive=sensitive)
    assert events[0] == ("restrict", request.user, "view")
    ordering.assert_not_called()
    view.filterset.assert_not_called()
    if sensitive:
        assert view._export_object_ids == ((7,) if "7" in selected else ())


@pytest.mark.parametrize("location", ["GET", "POST"])
@pytest.mark.parametrize("field", ["id", "pk"])
@pytest.mark.parametrize("malformed", ["", "not-an-id", "7.5", None])
def test_export_selection_rejects_malformed_values(
    scoped_export, location, field, malformed
):
    view, request, manager, _, ordering, events = scoped_export
    manager.filter.return_value.exists.return_value = True
    setattr(request, location, ExportParameters({field: ["7", malformed]}))
    with pytest.raises(PolicyPermissionDenied, match="Invalid export selection"):
        view.authorized_export_queryset(request, include_sensitive=True)
    assert events == [("restrict", request.user, "view")]
    ordering.assert_not_called()


@pytest.mark.parametrize("sensitive", [False, True])
@pytest.mark.parametrize("filtered_ids", [(9,), ()])
def test_export_filters_narrow_visible_selection_and_preserve_request(
    scoped_export, sensitive, filtered_ids
):
    view, request, manager, _, ordering, _ = scoped_export
    manager.filter.return_value.exists.return_value = True
    request.POST = ExportParameters(pk=["7", "9"])
    request.GET = ExportParameters(name=["synthetic-filter"])

    def filterset(parameters, queryset, *, request):
        assert parameters is request.GET
        assert queryset.rows == (7, 9)
        return SimpleNamespace(qs=queryset.filter(pk__in=filtered_ids))

    view.filterset = Mock(side_effect=filterset)
    result = view.authorized_export_queryset(request, include_sensitive=sensitive)
    assert result.rows == filtered_ids
    view.filterset.assert_called_once()
    assert view.filterset.call_args.kwargs == {"request": request}
    ordering.assert_called_once_with(result)
    if sensitive:
        assert view._export_object_ids == filtered_ids
