"""Real-NetBox authorization for endpoint exports and sensitive-access grants."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from cryptography.fernet import Fernet
import pytest

from tests.test_proxmox_endpoint_allowed_tenants import _require_harness


@pytest.mark.parametrize("superuser", [False, True])
@pytest.mark.parametrize("active", [False, True])
def test_grant_api_permission_with_real_user_without_database(
    pytestconfig, superuser, active
):
    """Exercise DRF's real permission dispatch before any grant queryset evaluation."""
    _require_harness(pytestconfig)
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIRequestFactory, force_authenticate
    from netbox_proxbox.api.sensitive_data_access import SensitiveDataAccessViewSet

    principal = get_user_model()(
        username="unsaved-policy-probe", is_superuser=superuser, is_active=active
    )
    request = APIRequestFactory().post(
        "/api/plugins/proxbox/sensitive-data-access/", {}, format="json"
    )
    force_authenticate(request, user=principal)
    view = SensitiveDataAccessViewSet()
    view.action_map = {"post": "create"}
    view.request = view.initialize_request(request)
    permission = view.get_permissions()[0]
    assert permission.has_permission(view.request, view) is (superuser and active)


def test_readiness_superuser_uses_no_database(pytestconfig):
    _require_harness(pytestconfig)
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIRequestFactory, force_authenticate
    from netbox_proxbox.api.sensitive_data_access import SensitiveDataReadinessView

    principal = get_user_model()(
        username="unsaved-superuser-probe", is_superuser=True, is_active=True
    )
    request = APIRequestFactory().get("/api/plugins/proxbox/sensitive-data-readiness/")
    force_authenticate(request, user=principal)
    response = SensitiveDataReadinessView.as_view()(request)
    assert response.status_code == 200
    assert response.data == {"schema_version": 1, "can_access_sensitive_data": True}
    assert response["Cache-Control"] == "no-store"


@pytest.mark.parametrize(
    "method", ["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"]
)
@pytest.mark.parametrize("write_enabled", [False, True])
@pytest.mark.parametrize("token_version", [1, 2])
def test_grant_api_preserves_token_write_boundary_without_database(
    pytestconfig, method, write_enabled, token_version
):
    """Run the actual permission chain with only queryset evaluation omitted."""
    _require_harness(pytestconfig)
    from django.contrib.auth import get_user_model
    from rest_framework.exceptions import PermissionDenied
    from rest_framework.test import APIRequestFactory, force_authenticate
    from users.models import Token
    from netbox_proxbox.api.sensitive_data_access import SensitiveDataAccessViewSet

    token_kwargs = {}
    if "version" in {field.name for field in Token._meta.fields}:
        token_kwargs["version"] = token_version
    elif token_version == 2:
        pytest.skip("This NetBox version has no v2 token contract.")
    principal = get_user_model()(username="unsaved-token-owner", is_superuser=True)
    token = Token(user=principal, write_enabled=write_enabled, **token_kwargs)
    request = APIRequestFactory().generic(method, "/synthetic-grants/")
    force_authenticate(request, user=principal, token=token)
    view = SensitiveDataAccessViewSet()
    view.action_map = {
        method.lower(): "list" if method in {"GET", "HEAD"} else "create"
    }
    view.request = view.initialize_request(request)
    # DjangoObjectPermissions needs model metadata, not any rows, for this check.
    view.get_queryset = Mock(return_value=view.queryset)
    allowed = write_enabled or method in {"GET", "HEAD", "OPTIONS"}
    if allowed:
        view.check_permissions(view.request)
    else:
        with pytest.raises(PermissionDenied):
            view.check_permissions(view.request)


def test_netbox_secret_widget_never_echoes_values_without_database(pytestconfig):
    _require_harness(pytestconfig)
    from netbox_proxbox.forms.netbox import NetBoxEndpointForm

    widget = NetBoxEndpointForm.base_fields["token_secret"].widget
    assert widget.render_value is False
    for secret in ("stored-secret-sentinel", "submitted-secret-sentinel"):
        html = widget.render("token_secret", secret)
        assert secret not in html
        assert 'value="' not in html


@pytest.mark.parametrize(
    "change",
    [None, "new", "version", "token_key", "domain", "ip_address", "port", "verify_ssl"],
)
def test_netbox_blank_secret_preservation_binds_identity_without_database(
    pytestconfig, change
):
    _require_harness(pytestconfig)
    from netbox_proxbox.choices import NetBoxTokenVersionChoices
    from netbox_proxbox.forms.netbox import NetBoxEndpointForm
    from netbox_proxbox.models import NetBoxEndpoint

    instance = NetBoxEndpoint(
        pk=7,
        token_version=NetBoxTokenVersionChoices.V2,
        token_key="nbt_existing",
        token_secret="stored-secret-sentinel",
        domain="netbox.example.test",
        port=443,
        verify_ssl=True,
    )
    data = dict(
        domain="netbox.example.test", port=443, verify_ssl=True, ip_address=None
    )
    token_key = "nbt_existing"
    if change == "new":
        instance.pk = None
    elif change == "version":
        instance.token_version = NetBoxTokenVersionChoices.V1
    elif change == "token_key":
        token_key = "nbt_other"
    elif change == "domain":
        data["domain"] = "other.example.test"
    elif change == "ip_address":
        data["ip_address"] = SimpleNamespace(pk=9)
    elif change == "port":
        data["port"] = 8443
    elif change == "verify_ssl":
        data["verify_ssl"] = False
    # The full ModelForm constructor reads custom fields; this test targets the identity helper.
    form = object.__new__(NetBoxEndpointForm)
    form.instance = instance
    expected = "stored-secret-sentinel" if change is None else ""
    assert form._preserved_v2_secret(data, token_key=token_key) == expected


@pytest.mark.parametrize("flag", [False, True])
@pytest.mark.parametrize("visible", [False, True])
def test_runtime_key_requires_independent_settings_visibility_without_database(
    pytestconfig: pytest.Config,
    monkeypatch: pytest.MonkeyPatch,
    flag: bool,
    visible: bool,
) -> None:
    """Run the actual disclosure policy with only grant/object storage replaced."""
    _require_harness(pytestconfig)
    from django.contrib.auth import get_user_model
    from netbox_proxbox.api.views import _user_can_read_runtime_secret
    from netbox_proxbox.models import ProxboxPluginSettings, ProxboxSensitiveDataAccess

    principal = get_user_model()(pk=17, username="unsaved-runtime-caller")
    grant_query = Mock()
    grant_query.exists.return_value = flag
    grant_lookup = Mock(return_value=grant_query)
    monkeypatch.setattr(ProxboxSensitiveDataAccess.objects, "filter", grant_lookup)
    visible_query = Mock()
    visible_query.filter.return_value.exists.return_value = visible
    restrict = Mock(return_value=visible_query)
    monkeypatch.setattr(ProxboxPluginSettings.objects, "restrict", restrict)

    assert _user_can_read_runtime_secret(principal, settings_pk=1) is (flag and visible)
    grant_lookup.assert_called_once_with(user_id=17, can_access_sensitive_data=True)
    if flag:
        restrict.assert_called_once_with(principal, "view")
        visible_query.filter.assert_called_once_with(pk=1)
    else:
        restrict.assert_not_called()


@pytest.mark.parametrize("failure", ["missing-row", "database", "deleted-row"])
def test_runtime_key_visibility_lookup_fails_closed_without_database(
    pytestconfig: pytest.Config, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    _require_harness(pytestconfig)
    from django.contrib.auth import get_user_model
    from django.core.exceptions import ObjectDoesNotExist
    from django.db import DatabaseError
    from netbox_proxbox.api.views import _user_can_read_runtime_secret
    from netbox_proxbox.models import ProxboxPluginSettings, ProxboxSensitiveDataAccess

    principal = get_user_model()(pk=17, username="unsaved-runtime-failure")
    grant_query = Mock()
    grant_query.exists.return_value = True
    monkeypatch.setattr(
        ProxboxSensitiveDataAccess.objects, "filter", Mock(return_value=grant_query)
    )
    restrict = Mock()
    restrict.side_effect = (
        DatabaseError("synthetic-storage-failure")
        if failure == "database"
        else ObjectDoesNotExist("synthetic-deleted-row")
    )
    monkeypatch.setattr(ProxboxPluginSettings.objects, "restrict", restrict)
    settings_pk = None if failure == "missing-row" else 1
    assert _user_can_read_runtime_secret(principal, settings_pk=settings_pk) is False
    if failure == "missing-row":
        restrict.assert_not_called()
    else:
        restrict.assert_called_once_with(principal, "view")


@pytest.mark.parametrize("kind", ["proxmox", "netbox", "fastapi"])
@pytest.mark.parametrize("failure_kind", ["denied", "unavailable", "success"])
def test_native_export_failure_boundary_without_database(
    pytestconfig, kind, failure_kind, caplog
):
    """Exercise actual endpoint POST routing with real Django responses and errors."""
    _require_harness(pytestconfig)
    import logging
    from uuid import UUID

    from django.contrib.auth import get_user_model
    from django.core.exceptions import PermissionDenied
    from django.http import HttpResponse
    from django.test import RequestFactory
    from netbox_proxbox.views.endpoints import (
        FastAPIEndpointExportView,
        NetBoxEndpointExportView,
        ProxmoxEndpointExportView,
    )

    view = {
        "proxmox": ProxmoxEndpointExportView,
        "netbox": NetBoxEndpointExportView,
        "fastapi": FastAPIEndpointExportView,
    }[kind]()
    request = RequestFactory().post(
        "/synthetic-export/",
        {"include_sensitive": "true", "format": "json", "token": "input-sentinel"},
    )
    request.user = get_user_model()(username="unsaved-export", is_superuser=True)
    failure = {
        "denied": PermissionDenied("provider-secret-sentinel"),
        "unavailable": RuntimeError("decryption-secret-sentinel"),
        "success": None,
    }[failure_kind]
    view._export_response = Mock(
        side_effect=failure, return_value=HttpResponse("export-secret-sentinel")
    )
    with caplog.at_level(logging.INFO, logger="netbox_proxbox.sensitive_export"):
        response = view.post(request)
    assert (
        response.status_code
        == {"denied": 403, "unavailable": 503, "success": 200}[failure_kind]
    )
    assert response["Cache-Control"] == "no-store"
    UUID(response["X-Export-Correlation-ID"])
    assert "sentinel" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)
    if failure_kind != "success":
        assert "sentinel" not in response.content.decode()
    if kind == "fastapi":
        assert view._export_response.call_args.kwargs["material_user"] is request.user


@pytest.mark.parametrize("kind", ["proxmox", "netbox", "fastapi"])
def test_native_list_refuses_raw_object_exports_without_database(pytestconfig, kind):
    _require_harness(pytestconfig)
    from django.core.exceptions import PermissionDenied
    from django.test import RequestFactory
    from netbox_proxbox.views.endpoints import (
        FastAPIEndpointListView,
        NetBoxEndpointListView,
        ProxmoxEndpointListView,
    )

    view = {
        "proxmox": ProxmoxEndpointListView,
        "netbox": NetBoxEndpointListView,
        "fastapi": FastAPIEndpointListView,
    }[kind]()
    template = Mock()
    template.render_to_response.side_effect = AssertionError("secret-template-sentinel")
    response = view.export_template(template, RequestFactory().get("/synthetic-list/"))
    assert response.status_code == 403
    assert response["Cache-Control"] == "no-store"
    assert "sentinel" not in response.content.decode()
    template.render_to_response.assert_not_called()
    with pytest.raises(PermissionDenied, match="safe YAML"):
        view.export_yaml()


def test_nested_token_and_table_are_secret_free_without_database(pytestconfig):
    _require_harness(pytestconfig)
    from django.test import RequestFactory
    from users.models import Token
    from netbox_proxbox.api.serializers.endpoints import NestedTokenSerializer
    from netbox_proxbox.tables import NetBoxEndpointTable

    class PoisonToken:
        pk = 17
        id = 17
        _meta = Token._meta

        @property
        def key(self):
            raise AssertionError("token-key-sentinel was read")

        def __str__(self):
            raise AssertionError("token-display-sentinel was read")

    request = RequestFactory().get("/synthetic-endpoint/")
    serializer = NestedTokenSerializer(context={"request": request})
    payload = serializer.to_representation(PoisonToken())
    assert set(payload) == {"id", "url", "display"}
    assert payload["display"] == "Token 17"
    assert "sentinel" not in repr(payload)
    assert str(NetBoxEndpointTable.base_columns["token"].accessor) == "token__pk"
    # Exercise the renderer without NetBox's unrelated custom-field database lookup.
    table = object.__new__(NetBoxEndpointTable)
    assert table.render_token(17) == "Token 17"
    assert table.value_token(17) == "Token 17"


@pytest.fixture
def sensitive_estate(pytestconfig, request):
    """Create synthetic disabled endpoints in the explicitly selected native lane."""
    _require_harness(pytestconfig)
    request.getfixturevalue("db")
    settings = request.getfixturevalue("settings")
    from django.contrib.contenttypes.models import ContentType
    from django.urls import reverse
    from users.models import ObjectPermission, Token

    from netbox_proxbox.models import (
        FastAPIEndpoint,
        NetBoxEndpoint,
        ProxmoxEndpoint,
        ProxboxPluginSettings,
        ProxboxSensitiveDataAccess,
    )
    from tests.django_support import make_user

    settings.PLUGINS = ["netbox_proxbox"]
    configuration = ProxboxPluginSettings.get_solo()
    configuration.credential_storage_backend = "legacy_encrypted"
    configuration.encryption_key = Fernet.generate_key().decode("ascii")
    configuration.save(update_fields=("credential_storage_backend", "encryption_key"))
    users = {
        "viewer": make_user("sensitive-viewer", is_staff=True),
        "flagged": make_user("sensitive-flagged"),
        "superuser": make_user("sensitive-superuser", is_superuser=True),
    }
    ProxboxSensitiveDataAccess.objects.create(
        user=users["flagged"], can_access_sensitive_data=True
    )
    token_fields = {field.name for field in Token._meta.fields}
    token_kwargs = {"user": users["superuser"]}
    if "version" in token_fields:
        token_kwargs["version"] = 1
    core_token = Token.objects.create(**token_kwargs)
    core_value = getattr(core_token, "plaintext", None) or core_token.key
    model_by_kind = {
        "proxmox": ProxmoxEndpoint,
        "netbox": NetBoxEndpoint,
        "fastapi": FastAPIEndpoint,
    }
    visible = {}
    hidden = {}
    for kind, model in model_by_kind.items():
        common = dict(
            domain=f"{kind}.example.test",
            enabled=False,
            port=8006,
            verify_ssl=True,
            credential_storage_backend="legacy_encrypted",
        )
        if kind == "proxmox":
            common.update(
                username="root@pam",
                password="pve-password-sentinel",
                token_name="export",
                token_value="pve-token-sentinel",
            )
        elif kind == "fastapi":
            common.pop("credential_storage_backend")
            common.update(use_https=True)
        else:
            common.pop("credential_storage_backend")
            common.update(
                token=core_token,
                token_version="v1",
                token_key="nbt_v2_identifier",
                token_secret="v2-secret-sentinel",
            )
        visible[kind] = model.objects.create(name=f"visible-{kind}", **common)
        hidden[kind] = model.objects.create(name=f"hidden-{kind}", **common)
        if kind == "fastapi":
            from netbox_proxbox.services.encryption_recovery import (
                _locked_encrypted_queryset_update,
            )
            from netbox_proxbox.utils.encryption import encrypt

            token_enc = encrypt(
                "backend-token-sentinel", key=configuration.encryption_key
            )
            for endpoint in (visible[kind], hidden[kind]):
                _locked_encrypted_queryset_update(
                    model.objects.filter(pk=endpoint.pk), token_enc=token_enc
                )
                endpoint.refresh_from_db()
        permission = ObjectPermission.objects.create(
            name=f"View only visible {kind}",
            actions=["view"],
            constraints={"pk": visible[kind].pk},
        )
        permission.object_types.add(ContentType.objects.get_for_model(model))
        permission.users.add(users["viewer"], users["flagged"])
    grant_permission = ObjectPermission.objects.create(
        name="Ordinary grant CRUD must not confer flag administration",
        actions=["view", "add", "change", "delete"],
    )
    grant_permission.object_types.add(
        ContentType.objects.get_for_model(ProxboxSensitiveDataAccess)
    )
    grant_permission.users.add(users["viewer"], users["flagged"])
    export_urls = {
        kind: reverse(f"plugins:netbox_proxbox:{kind}endpoint_export")
        for kind in model_by_kind
    }
    return SimpleNamespace(
        users=users,
        visible=visible,
        hidden=hidden,
        urls=export_urls,
        grant_model=ProxboxSensitiveDataAccess,
        configuration=configuration,
        secrets=(
            "pve-password-sentinel",
            "pve-token-sentinel",
            "backend-token-sentinel",
            core_value,
            "v2-secret-sentinel",
        ),
    )


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["proxmox", "netbox", "fastapi"])
@pytest.mark.parametrize("data_format", ["csv", "json", "yaml"])
def test_safe_export_obeys_real_object_permissions(sensitive_estate, kind, data_format):
    from django.test import Client

    client = Client()
    client.force_login(sensitive_estate.users["viewer"])
    response = client.get(sensitive_estate.urls[kind], {"format": data_format})
    assert response.status_code == 200
    content = response.content.decode()
    assert f"visible-{kind}" in content
    assert f"hidden-{kind}" not in content
    for secret in sensitive_estate.secrets:
        assert secret not in content


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["proxmox", "netbox", "fastapi"])
@pytest.mark.parametrize("data_format", ["csv", "json", "yaml"])
@pytest.mark.parametrize("role", ["flagged", "superuser"])
def test_sensitive_export_has_explicit_authority(
    sensitive_estate, kind, data_format, role
):
    from django.test import Client

    client = Client()
    client.force_login(sensitive_estate.users[role])
    response = client.post(
        sensitive_estate.urls[kind],
        {
            "include_sensitive": "true",
            "format": data_format,
        },
    )
    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    content = response.content.decode()
    expected = {
        "proxmox": "pve-password-sentinel",
        "fastapi": "backend-token-sentinel",
        "netbox": "v2-secret-sentinel",
    }[kind]
    assert expected in content
    assert f"visible-{kind}" in content
    assert (f"hidden-{kind}" in content) is (role == "superuser")


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["proxmox", "netbox", "fastapi"])
@pytest.mark.parametrize(
    "proof",
    [
        {"token_version": "v1", "v1_manual_token": "self-issued-v1-sentinel"},
        {"token_version": "v2", "token_key": "nbt_self", "token_secret": "self-secret"},
        {"netbox_token": "other-actor-token-sentinel"},
        {},
    ],
)
def test_ordinary_viewer_cannot_forge_sensitive_export(sensitive_estate, kind, proof):
    from django.test import Client

    client = Client()
    client.force_login(sensitive_estate.users["viewer"])
    response = client.post(
        sensitive_estate.urls[kind], {"include_sensitive": "true", **proof}
    )
    assert response.status_code == 403
    for secret in sensitive_estate.secrets:
        assert secret.encode() not in response.content


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["proxmox", "netbox", "fastapi"])
def test_mixed_selection_fails_before_serializer(sensitive_estate, kind, monkeypatch):
    from django.test import Client
    from netbox_proxbox.views.endpoints import fastapi, netbox, proxmox

    modules = {"proxmox": proxmox, "netbox": netbox, "fastapi": fastapi}
    serializer = Mock(
        side_effect=AssertionError("An unauthorized selection reached serialization.")
    )
    monkeypatch.setattr(modules[kind], f"_serialize_{kind}_endpoint", serializer)
    client = Client()
    client.force_login(sensitive_estate.users["flagged"])
    response = client.post(
        sensitive_estate.urls[kind],
        {
            "include_sensitive": "true",
            "pk": [sensitive_estate.visible[kind].pk, sensitive_estate.hidden[kind].pk],
        },
    )
    assert response.status_code == 403
    serializer.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["proxmox", "netbox", "fastapi"])
def test_revocation_blocks_next_export(sensitive_estate, kind):
    from django.test import Client

    user = sensitive_estate.users["flagged"]
    client = Client()
    client.force_login(user)
    data = {"include_sensitive": "true"}
    assert client.post(sensitive_estate.urls[kind], data).status_code == 200
    sensitive_estate.grant_model.objects.filter(user=user).update(
        can_access_sensitive_data=False
    )
    assert client.post(sensitive_estate.urls[kind], data).status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["proxmox", "netbox", "fastapi"])
def test_sensitive_post_requires_csrf(sensitive_estate, kind):
    from django.test import Client

    client = Client(enforce_csrf_checks=True)
    client.force_login(sensitive_estate.users["superuser"])
    response = client.post(sensitive_estate.urls[kind], {"include_sensitive": "true"})
    assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["viewer", "flagged"])
@pytest.mark.parametrize("method", ["get", "post", "patch", "delete"])
def test_only_superusers_can_administer_grants(sensitive_estate, role, method):
    from django.urls import reverse
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(sensitive_estate.users[role])
    grant = sensitive_estate.grant_model.objects.get(
        user=sensitive_estate.users["flagged"]
    )
    route = (
        "proxboxsensitivedataaccess-list"
        if method in ("get", "post")
        else "proxboxsensitivedataaccess-detail"
    )
    kwargs = {} if method in ("get", "post") else {"pk": grant.pk}
    url = reverse(f"plugins-api:netbox_proxbox-api:{route}", kwargs=kwargs)
    response = getattr(client, method)(
        url,
        {
            "user": sensitive_estate.users[role].pk,
            "can_access_sensitive_data": True,
        },
        format="json",
    )
    assert response.status_code == 403
    grant.refresh_from_db()
    assert grant.can_access_sensitive_data is True
    assert not sensitive_estate.grant_model.objects.filter(
        user=sensitive_estate.users["viewer"]
    ).exists()


@pytest.mark.django_db
def test_default_off_grant_and_fresh_readiness(sensitive_estate):
    from django.urls import reverse
    from rest_framework.test import APIClient

    user = sensitive_estate.users["viewer"]
    grant = sensitive_estate.grant_model.objects.create(user=user)
    assert grant.can_access_sensitive_data is False
    client = APIClient()
    client.force_authenticate(user)
    url = reverse("plugins-api:netbox_proxbox-api:sensitive-data-readiness")
    response = client.get(url)
    assert response.status_code == 200
    assert response.data == {"schema_version": 1, "can_access_sensitive_data": False}
    assert response["Cache-Control"] == "no-store"
    grant.can_access_sensitive_data = True
    grant.save(update_fields=("can_access_sensitive_data",))
    assert client.get(url).data["can_access_sensitive_data"] is True
    grant.can_access_sensitive_data = False
    grant.save(update_fields=("can_access_sensitive_data",))
    assert client.get(url).data["can_access_sensitive_data"] is False


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["viewer", "flagged", "superuser"])
@pytest.mark.parametrize("settings_scope", ["absent", "mismatched", "matching"])
def test_runtime_settings_disclose_key_only_with_sensitive_authority(
    sensitive_estate, role, settings_scope
):
    from django.contrib.contenttypes.models import ContentType
    from django.urls import reverse
    from rest_framework.test import APIClient
    from users.models import ObjectPermission

    if settings_scope != "absent":
        configuration = sensitive_estate.configuration
        permission = ObjectPermission.objects.create(
            name=f"Runtime settings visibility {settings_scope}",
            actions=["view"],
            constraints={
                "pk": configuration.pk
                if settings_scope == "matching"
                else configuration.pk + 1
            },
        )
        permission.object_types.add(
            ContentType.objects.get_for_model(type(configuration))
        )
        permission.users.add(sensitive_estate.users[role])

    client = APIClient()
    client.force_authenticate(sensitive_estate.users[role])
    url = reverse("plugins-api:netbox_proxbox-api:proxboxpluginsettings-runtime")
    response = client.get(url)
    expected_status = (
        200
        if role == "superuser" or settings_scope == "matching"
        else 403
        if settings_scope == "absent"
        else 404
    )
    assert response.status_code == expected_status
    if expected_status != 200:
        return
    assert response["Cache-Control"] == "no-store"
    assert response.data["encryption_key_configured"] is True
    permitted = role == "superuser" or (
        role == "flagged" and settings_scope == "matching"
    )
    expected = sensitive_estate.configuration.encryption_key if permitted else ""
    assert response.data["encryption_key"] == expected
    if role == "flagged":
        sensitive_estate.grant_model.objects.filter(
            user=sensitive_estate.users[role]
        ).update(can_access_sensitive_data=False)
        assert client.get(url).data["encryption_key"] == ""


@pytest.mark.django_db
def test_superuser_grant_and_revoke_with_real_netbox_token(sensitive_estate):
    from django.urls import reverse
    from rest_framework.test import APIClient
    from tests.django_support import make_api_token

    _, headers = make_api_token(sensitive_estate.users["superuser"])
    client = APIClient()
    client.credentials(**headers)
    list_url = reverse("plugins-api:netbox_proxbox-api:proxboxsensitivedataaccess-list")
    response = client.post(
        list_url,
        {
            "user": sensitive_estate.users["viewer"].pk,
            "can_access_sensitive_data": True,
        },
        format="json",
    )
    assert response.status_code == 201
    detail_url = reverse(
        "plugins-api:netbox_proxbox-api:proxboxsensitivedataaccess-detail",
        kwargs={"pk": response.data["id"]},
    )
    response = client.patch(
        detail_url, {"can_access_sensitive_data": False}, format="json"
    )
    assert response.status_code == 200
    assert response.data["can_access_sensitive_data"] is False


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["viewer", "flagged", "superuser"])
@pytest.mark.parametrize("kind", ["proxmox", "netbox", "fastapi"])
def test_html_sensitive_controls_follow_authority(sensitive_estate, role, kind):
    from django.test import Client
    from django.urls import reverse

    client = Client()
    client.force_login(sensitive_estate.users[role])
    url = reverse(f"plugins:netbox_proxbox:{kind}endpoint_list")
    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode()
    assert ("Export with secrets" in content) is (role != "viewer")
    assert 'name="netbox_token"' not in content
    assert 'name="token_secret"' not in content
    for secret in sensitive_estate.secrets:
        assert secret not in content


def test_bulk_import_still_strips_export_ids(pytestconfig, monkeypatch):
    _require_harness(pytestconfig)
    from netbox.views.generic import BulkImportView
    from netbox_proxbox.views.endpoints.proxmox import ProxmoxEndpointBulkImportView

    captured = []

    def capture(parent, form, request):
        captured.extend(form.cleaned_data["data"])
        return []

    monkeypatch.setattr(BulkImportView, "create_and_update_objects", capture)
    records = [{"id": "1", "name": "imported-one"}, {"name": "imported-two"}]
    ProxmoxEndpointBulkImportView().create_and_update_objects(
        SimpleNamespace(cleaned_data={"data": records}),
        request=None,
    )
    assert captured == [{"name": "imported-one"}, {"name": "imported-two"}]
