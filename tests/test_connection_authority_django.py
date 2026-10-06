"""Native, database-free connection approval boundaries and migration state."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

# This import owns the native harness bootstrap and its mocked-suite skip.
from tests.test_changelog_secret_redaction_django import apps

from django.db.migrations.loader import MigrationLoader
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from netbox.api.authentication import TokenPermissions
from users.models import Token

from netbox_proxbox.api.serializers.endpoints import (
    NetBoxEndpointSerializer,
    ProxmoxEndpointSerializer,
)
from netbox_proxbox.api.views import NetBoxEndpointViewSet, ProxmoxEndpointViewSet
from netbox_proxbox.services.connection_authority import ConnectionAuthorityError
from netbox_proxbox.views import backend_sync


@pytest.mark.parametrize("kind", ["proxmox", "netbox"])
def test_native_unapproved_endpoint_denies_before_material_resolution(
    monkeypatch, kind
) -> None:
    model = apps.get_model(
        "netbox_proxbox", "ProxmoxEndpoint" if kind == "proxmox" else "NetBoxEndpoint"
    )
    endpoint = model(pk=101, domain="endpoint.example.test", enabled=True)
    assert endpoint.approved_connection_target_fingerprint == ""
    resolver = Mock(
        side_effect=AssertionError("unapproved target must not resolve material")
    )
    monkeypatch.setattr(
        "netbox_proxbox.integrations.openbao.resolve_endpoint_api_credentials", resolver
    )
    builder = (
        backend_sync._proxmox_backend_payload
        if kind == "proxmox"
        else backend_sync._netbox_endpoint_backend_payload
    )
    with pytest.raises(ConnectionAuthorityError):
        builder(endpoint)
    resolver.assert_not_called()


@pytest.mark.parametrize("viewset", [NetBoxEndpointViewSet, ProxmoxEndpointViewSet])
def test_native_authority_action_retains_write_token_permissions(viewset) -> None:
    action = next(
        action
        for action in viewset.get_extra_actions()
        if action.__name__ == "connection_authority"
    )
    assert set(action.mapping) == {"get", "put"}
    view = viewset()
    permissions = view.get_permissions()
    token_permissions = [
        permission
        for permission in permissions
        if isinstance(permission, TokenPermissions)
    ]
    assert token_permissions
    request = SimpleNamespace(
        method="PUT",
        auth=Token(write_enabled=False),
        user=SimpleNamespace(is_authenticated=True),
    )
    assert all(
        not permission.has_permission(request, view) for permission in token_permissions
    )


@pytest.mark.parametrize("viewset", [NetBoxEndpointViewSet, ProxmoxEndpointViewSet])
def test_native_authority_denial_precedes_object_resolution(viewset) -> None:
    view = viewset()
    view.get_object = Mock(side_effect=AssertionError("must deny before lookup"))
    request = SimpleNamespace(method="PUT", user=AnonymousUser(), data={})
    with pytest.raises(PermissionDenied):
        view.connection_authority(request)
    view.get_object.assert_not_called()


@pytest.mark.parametrize(
    "serializer", [NetBoxEndpointSerializer, ProxmoxEndpointSerializer]
)
def test_native_ordinary_serializers_cannot_write_approval(serializer) -> None:
    assert "approved_connection_target_fingerprint" not in serializer().fields


def test_native_migration_state_adds_unapproved_internal_fields() -> None:
    loader = MigrationLoader(None)
    before = loader.project_state(
        [("netbox_proxbox", "0103_custom_fields_request_delay_help_text")]
    )
    after = loader.project_state([("netbox_proxbox", "0104_security_hardening")])
    for name in ("NetBoxEndpoint", "ProxmoxEndpoint"):
        assert "approved_connection_target_fingerprint" not in {
            field.name
            for field in before.apps.get_model(
                "netbox_proxbox", name
            )._meta.get_fields()
        }
        field = after.apps.get_model("netbox_proxbox", name)._meta.get_field(
            "approved_connection_target_fingerprint"
        )
        assert field.default == ""
        assert field.editable is False
        assert field.max_length == 64


@pytest.mark.parametrize("kind", ["proxmox", "netbox"])
@pytest.mark.parametrize(
    "enabled,can_change", [(True, True), (False, True), (True, False)]
)
def test_native_review_panel_routes_and_initial_approval_state(
    kind, enabled, can_change
):
    """Render native template routes without giving a browser implicit approval."""
    from django.template.loader import render_to_string
    from django.urls import reverse

    url = reverse(
        f"plugins-api:netbox_proxbox-api:endpoints:{kind}endpoint-connection-authority",
        kwargs={"pk": 101},
    )
    assert url == f"/api/plugins/proxbox/endpoints/{kind}/101/connection-authority/"
    html = render_to_string(
        "netbox_proxbox/inc/connection_authority.html",
        {
            "authority_url": url,
            "object": SimpleNamespace(enabled=enabled),
            "can_change": can_change,
            "csrf_token": "native-panel-test",
        },
    )
    assert f'data-authority-url="{url}"' in html
    assert f'data-endpoint-enabled="{str(enabled).lower()}"' in html
    assert f'data-can-change="{str(can_change).lower()}"' in html
    assert 'name="csrfmiddlewaretoken"' in html
    assert "connection-authority.js" in html
    assert "data-proxbox-connection-authority-approve\n                disabled" in html


@pytest.mark.parametrize("valid_csrf", [True, False])
def test_native_session_approval_requires_csrf(valid_csrf):
    """The session authentication used by the approval panel enforces real CSRF."""
    from django.conf import settings
    from django.middleware.csrf import get_token
    from django.test import RequestFactory
    from rest_framework.authentication import SessionAuthentication
    from rest_framework.exceptions import PermissionDenied as RESTPermissionDenied

    factory = RequestFactory()
    seed = factory.get("/plugins/proxbox/")
    token = get_token(seed)
    request = factory.put(
        "/api/plugins/proxbox/endpoints/proxmox/101/connection-authority/",
        data={"target_fingerprint": "a" * 64},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token if valid_csrf else "invalid",
    )
    request.COOKIES[settings.CSRF_COOKIE_NAME] = seed.META["CSRF_COOKIE"]
    if valid_csrf:
        SessionAuthentication().enforce_csrf(request)
    else:
        with pytest.raises(RESTPermissionDenied, match="CSRF"):
            SessionAuthentication().enforce_csrf(request)
