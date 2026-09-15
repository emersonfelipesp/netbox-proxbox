"""Real model, Fernet, form, and migration contracts for optional OpenBao storage."""

from __future__ import annotations

from unittest.mock import patch
from types import SimpleNamespace

from cryptography.fernet import Fernet
import pytest

from tests.test_proxmox_endpoint_allowed_tenants import _require_harness

pytestmark = pytest.mark.django_db


@pytest.fixture
def optionality_models(pytestconfig, request):
    _require_harness(pytestconfig)
    request.getfixturevalue("db")
    from netbox_proxbox.models import ProxboxPluginSettings, ProxmoxEndpoint

    return ProxboxPluginSettings, ProxmoxEndpoint


def test_fresh_settings_and_all_four_credentials_use_real_fernet(
    optionality_models, settings
):
    Settings, Endpoint = optionality_models
    settings.PLUGINS = ["netbox_proxbox"]
    Settings.objects.all().delete()
    configuration = Settings.get_solo()
    assert configuration.credential_storage_backend == ""
    key = Fernet.generate_key().decode("ascii")
    configuration.encryption_key = key
    configuration.save()
    endpoint = Endpoint(name="credential-test", username="root@pam", enabled=False)
    endpoint.password = "api-password"
    endpoint.token_value = "api-token"
    endpoint.set_ssh_password("ssh-password", key=key)
    endpoint.set_ssh_private_key("ssh-private-key", key=key)
    endpoint.save()
    endpoint.refresh_from_db()
    for field, plaintext in (
        ("password_enc", "api-password"),
        ("token_value_enc", "api-token"),
        ("ssh_password_enc", "ssh-password"),
        ("ssh_private_key_enc", "ssh-private-key"),
    ):
        ciphertext = getattr(endpoint, field)
        assert ciphertext != plaintext
        assert Fernet(key.encode()).decrypt(ciphertext.encode()).decode() == plaintext
    assert endpoint.password == "api-password"
    assert endpoint.token_value == "api-token"
    assert endpoint.get_ssh_password(key=key) == "ssh-password"
    assert endpoint.get_ssh_private_key(key=key) == "ssh-private-key"
    assert endpoint.openbao_password_credential_uuid is None
    assert endpoint.openbao_token_credential_uuid is None
    assert endpoint.openbao_ssh_password_credential_uuid is None
    assert endpoint.openbao_ssh_keypair_credential_uuid is None


@pytest.mark.parametrize(
    "kind", ["password", "token_value", "ssh_password", "ssh_private_key"]
)
def test_explicit_openbao_writes_fail_closed_without_plugin(
    optionality_models, settings, kind
):
    from django.core.exceptions import ValidationError

    _, Endpoint = optionality_models
    settings.PLUGINS = ["netbox_proxbox"]
    endpoint = Endpoint(
        name="explicit-openbao", enabled=False, credential_storage_backend="openbao"
    )
    with pytest.raises(ValidationError, match="netbox-openbao"):
        if kind.startswith("ssh_"):
            getattr(endpoint, f"set_{kind}")(
                "must-not-store", key=Fernet.generate_key().decode()
            )
        else:
            setattr(endpoint, kind, "must-not-store")
    for field in (
        "password_enc",
        "token_value_enc",
        "ssh_password_enc",
        "ssh_private_key_enc",
    ):
        assert getattr(endpoint, field) == ""


def test_automatic_settings_form_and_serializer_accept_blank(optionality_models):
    from netbox_proxbox.forms.settings import ProxboxPluginSettingsForm
    from netbox_proxbox.api.serializers.settings import ProxboxPluginSettingsSerializer

    field = ProxboxPluginSettingsForm.base_fields["credential_storage_backend"]
    assert field.clean("") == ""
    assert list(field.choices)[0] == ("", "Automatic (enabled plugins)")
    serializer = ProxboxPluginSettingsSerializer()
    assert serializer.fields["credential_storage_backend"].run_validation("") == ""


@pytest.mark.parametrize("saved", ["openbao", "legacy_encrypted"])
@pytest.mark.django_db(transaction=True)
def test_forward_migration_preserves_explicit_storage_choices(pytestconfig, saved):
    _require_harness(pytestconfig)
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    from netbox_proxbox.choices import CredentialStorageBackendChoices

    before = ("netbox_proxbox", "0093_proxmox_metrics_source_mode")
    after = ("netbox_proxbox", "0094_automatic_credential_storage_default")
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate([before])
        old_settings = executor.loader.project_state([before]).apps.get_model(
            "netbox_proxbox", "ProxboxPluginSettings"
        )
        row = old_settings.objects.first() or old_settings.objects.create()
        row.credential_storage_backend = saved
        row.save(update_fields=["credential_storage_backend"])
        executor = MigrationExecutor(connection)
        executor.migrate([after])
        new_settings = executor.loader.project_state([after]).apps.get_model(
            "netbox_proxbox", "ProxboxPluginSettings"
        )
        assert new_settings.objects.get(pk=row.pk).credential_storage_backend == saved
        assert new_settings._meta.get_field("credential_storage_backend").default == ""
        fresh_state = executor.loader.project_state(
            [("netbox_proxbox", "0083_openbao_credential_storage")]
        )
        fresh_settings = fresh_state.apps.get_model(
            "netbox_proxbox", "ProxboxPluginSettings"
        )
        assert (
            fresh_settings._meta.get_field("credential_storage_backend").default
            == CredentialStorageBackendChoices.OPENBAO
        )
    finally:
        MigrationExecutor(connection).migrate(latest)


@pytest.mark.parametrize("token_selected", [False, True])
def test_backend_and_export_support_single_openbao_auth_method(
    optionality_models, token_selected
):
    from netbox_proxbox.integrations import openbao
    from netbox_proxbox.views.backend_sync import _proxmox_backend_payload
    from netbox_proxbox.views.endpoints.proxmox_export import (
        _serialize_proxmox_endpoint,
    )

    _, Endpoint = optionality_models
    endpoint = Endpoint(
        name="single-auth", enabled=False, credential_storage_backend="openbao"
    )
    endpoint.token_name = "token-name" if token_selected else ""
    endpoint.openbao_password_credential_uuid = (
        None if token_selected else "11111111-1111-4111-8111-111111111111"
    )
    endpoint.openbao_token_credential_uuid = (
        "22222222-2222-4222-8222-222222222222" if token_selected else None
    )
    endpoint.save()
    payload = (
        {"token": "token-secret"} if token_selected else {"password": "password-secret"}
    )
    with (
        patch.object(openbao, "_credential_for_uuid", return_value=object()),
        patch.object(openbao, "reveal_credential_material", return_value=payload),
    ):
        backend = _proxmox_backend_payload(endpoint)
        exported = _serialize_proxmox_endpoint(endpoint, include_sensitive=True)
    assert backend["password"] == (None if token_selected else "password-secret")
    assert backend["token_value"] == ("token-secret" if token_selected else None)
    assert exported["password"] == ("" if token_selected else "password-secret")
    assert exported["token_value"] == ("token-secret" if token_selected else "")


@pytest.mark.parametrize("token_selected", [False, True])
def test_edit_form_preserves_single_openbao_auth_method(
    optionality_models, token_selected
):
    from netbox_proxbox.forms.proxmox import ProxmoxEndpointForm
    from netbox_proxbox.integrations import openbao

    _, Endpoint = optionality_models
    endpoint = Endpoint(
        name="single-auth-edit",
        domain="pve.example.test",
        port=8006,
        username="root@pam",
        enabled=False,
        credential_storage_backend="openbao",
        token_name="api-token" if token_selected else "",
        openbao_password_credential_uuid=None
        if token_selected
        else "11111111-1111-4111-8111-111111111111",
        openbao_token_credential_uuid="22222222-2222-4222-8222-222222222222"
        if token_selected
        else None,
    )
    endpoint.save()
    form = ProxmoxEndpointForm(
        instance=endpoint,
        data={
            "name": endpoint.name,
            "domain": endpoint.domain,
            "port": 8006,
            "username": "root@pam",
            "token_name": endpoint.token_name,
            "credential_storage_backend": "openbao",
            "mode": "undefined",
            "ssh_credential_source": "dedicated",
            "ssh_port": 22,
            "ssh_auth_method": "password",
            "access_methods": "api",
            "service_monitoring_interval_minutes": 5,
        },
    )
    material = (
        {"token": "token-secret"} if token_selected else {"password": "password-secret"}
    )
    with (
        patch.object(openbao, "_credential_for_uuid", return_value=object()),
        patch.object(openbao, "reveal_credential_material", return_value=material),
        patch.object(openbao, "openbao_prerequisites_errors", return_value=[]),
    ):
        assert form.is_valid(), form.errors.as_data()
    assert form.cleaned_data["password"] == (
        "" if token_selected else "password-secret"
    )
    assert form.cleaned_data["token_value"] == (
        "token-secret" if token_selected else ""
    )


def _saved_openbao_endpoint(Endpoint, name="optionality", **overrides):
    values = {
        "name": name,
        "domain": "pve.example.test",
        "port": 8006,
        "username": "root@pam",
        "enabled": False,
        "credential_storage_backend": "openbao",
    }
    values.update(overrides)
    endpoint = Endpoint(**values)
    endpoint.save()
    return endpoint


def _edit_data(endpoint, **overrides):
    values = {
        "name": endpoint.name,
        "domain": endpoint.domain,
        "port": 8006,
        "username": "root@pam",
        "token_name": endpoint.token_name,
        "credential_storage_backend": endpoint.credential_storage_backend,
        "mode": "undefined",
        "ssh_credential_source": "dedicated",
        "ssh_port": 22,
        "ssh_auth_method": "password",
        "access_methods": "api",
        "service_monitoring_interval_minutes": 5,
    }
    values.update(overrides)
    return values


@pytest.mark.parametrize("existing_reference", [False, True])
def test_edit_form_repairs_missing_auth_but_rejects_stale_counterpart(
    optionality_models, existing_reference
):
    from netbox_proxbox.forms.proxmox import ProxmoxEndpointForm
    from netbox_proxbox.integrations import openbao

    _, Endpoint = optionality_models
    endpoint = _saved_openbao_endpoint(
        Endpoint,
        openbao_password_credential_uuid="11111111-1111-4111-8111-111111111111"
        if existing_reference
        else None,
    )
    form = ProxmoxEndpointForm(
        instance=endpoint,
        data=_edit_data(endpoint, token_name="replacement", token_value="new-token"),
    )
    with (
        patch.object(openbao, "_credential_for_uuid", return_value=None),
        patch.object(openbao, "openbao_prerequisites_errors", return_value=[]),
    ):
        assert form.is_valid() is not existing_reference, form.errors.as_data()
    if existing_reference:
        assert "password" in form.errors
    else:
        assert form.cleaned_data["password"] == ""
        assert form.cleaned_data["token_value"] == "new-token"


@pytest.mark.parametrize("clear", ["clear_password", "clear_token"])
def test_edit_form_clears_before_selection_and_preserves_original_store(
    optionality_models, clear
):
    from netbox_proxbox.forms.proxmox import ProxmoxEndpointForm
    from netbox_proxbox.integrations import openbao

    _, Endpoint = optionality_models
    endpoint = _saved_openbao_endpoint(
        Endpoint,
        token_name="existing-token",
        openbao_password_credential_uuid="11111111-1111-4111-8111-111111111111",
        openbao_token_credential_uuid="22222222-2222-4222-8222-222222222222",
    )
    actor = object()
    form = ProxmoxEndpointForm(
        instance=endpoint,
        request_user=actor,
        data=_edit_data(
            endpoint, **{clear: True, "credential_storage_backend": "legacy_encrypted"}
        ),
    )
    with (
        patch.object(openbao, "_credential_for_uuid", return_value=object()),
        patch.object(
            openbao,
            "reveal_credential_material",
            return_value={"password": "kept-password", "token": "kept-token"},
        ) as reveal,
        patch.object(openbao, "openbao_prerequisites_errors", return_value=[]),
    ):
        assert form.is_valid(), form.errors.as_data()
    reveal.assert_called_once()
    assert form._request_user is actor
    assert endpoint._openbao_actor_user is actor
    assert form.cleaned_data["password"] == (
        "" if clear == "clear_password" else "kept-password"
    )
    assert form.cleaned_data["token_value"] == (
        "kept-token" if clear == "clear_password" else ""
    )
    assert form.cleaned_data["token_name"] == (
        "existing-token" if clear == "clear_password" else ""
    )


def test_edit_form_reports_missing_address_after_preservation(optionality_models):
    from netbox_proxbox.forms.proxmox import ProxmoxEndpointForm
    from netbox_proxbox.integrations import openbao

    _, Endpoint = optionality_models
    endpoint = _saved_openbao_endpoint(Endpoint)
    form = ProxmoxEndpointForm(
        instance=endpoint,
        data=_edit_data(
            endpoint, domain="", token_name="new-token", token_value="value"
        ),
    )
    with patch.object(openbao, "openbao_prerequisites_errors", return_value=[]):
        assert not form.is_valid()
    assert "domain" in form.errors
    assert "ip_address" in form.errors


@pytest.mark.parametrize("failure", ["missing", "deleted", "denied"])
def test_endpoint_list_serializes_failed_openbao_ssh_readiness(
    optionality_models, failure
):
    from netbox_proxbox.api.serializers.endpoints import ProxmoxEndpointSerializer
    from netbox_proxbox.integrations import openbao

    _, Endpoint = optionality_models
    endpoint = _saved_openbao_endpoint(
        Endpoint,
        ssh_credential_source="reuse_endpoint",
        access_methods="api_ssh",
        ssh_known_host_fingerprint="SHA256:test",
        openbao_password_credential_uuid=None
        if failure == "missing"
        else "11111111-1111-4111-8111-111111111111",
    )
    endpoint.allow_writes = True
    with (
        patch.object(
            openbao,
            "_credential_for_uuid",
            return_value=None if failure == "deleted" else object(),
        ),
        patch.object(
            openbao,
            "reveal_credential_material",
            side_effect=PermissionError("secret-canary"),
        ),
        patch.object(Endpoint, "effective_rpc_enabled", return_value=True),
    ):
        assert endpoint.has_ssh_terminal_credentials is False
        assert endpoint.service_monitoring_eligible is False
        data = ProxmoxEndpointSerializer(
            [endpoint], many=True, context={"request": None}
        ).data
    assert data[0]["has_ssh_terminal_credentials"] is False
    assert data[0]["service_monitoring_eligible"] is False
    assert "secret-canary" not in str(data)


@pytest.mark.parametrize("eligibility_raises", [False, True])
def test_monitoring_failure_does_not_skip_next_healthy_endpoint(
    optionality_models, eligibility_raises
):
    from django.core.exceptions import ValidationError
    from netbox_proxbox import jobs
    from netbox_proxbox.integrations import openbao, rpc

    _, Endpoint = optionality_models
    broken = _saved_openbao_endpoint(
        Endpoint, "a-broken", ssh_credential_source="reuse_endpoint"
    )
    healthy = _saved_openbao_endpoint(
        Endpoint,
        "b-healthy",
        ssh_credential_source="dedicated",
        ssh_username="root",
        ssh_auth_method="password",
        openbao_ssh_password_credential_uuid="22222222-2222-4222-8222-222222222222",
    )
    Endpoint.objects.filter(pk__in=[broken.pk, healthy.pk]).update(
        enabled=True,
        allow_writes=True,
        access_methods="api_ssh",
        service_monitoring_enabled=True,
        ssh_known_host_fingerprint="SHA256:test",
    )
    original = Endpoint.service_monitoring_eligible.fget

    def eligibility(endpoint):
        if eligibility_raises and endpoint.pk == broken.pk:
            raise ValidationError("Credential readiness failed.")
        return original(endpoint)

    job = jobs.ProxmoxServiceMonitoringJob.__new__(jobs.ProxmoxServiceMonitoringJob)
    job.job = SimpleNamespace(user=None)
    with (
        patch.object(Endpoint, "service_monitoring_eligible", property(eligibility)),
        patch.object(Endpoint, "effective_rpc_enabled", return_value=True),
        patch.object(openbao, "_credential_for_uuid", return_value=None),
        patch.object(rpc, "project_completed_collections", return_value=0),
        patch.object(rpc, "collect_systemctl_services") as collect,
    ):
        job.run()
    assert [call.args[0].pk for call in collect.call_args_list] == [healthy.pk]
    broken.refresh_from_db()
    assert broken.service_monitoring_last_status == "failed"
    assert broken.service_monitoring_last_error


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("missing", 503),
        ("token", 422),
        ("denied", 503),
        ("healthy", 200),
        ("unpinned", 404),
    ],
)
def test_ssh_reuse_response_contains_expected_openbao_failure(
    optionality_models, mode, expected
):
    from netbox_proxbox.api import ssh_credentials
    from netbox_proxbox.integrations import openbao
    from tests.django_support import make_user

    _, Endpoint = optionality_models
    endpoint = _saved_openbao_endpoint(
        Endpoint,
        ssh_credential_source="reuse_endpoint",
        access_methods="api_ssh",
        token_name="api-token" if mode == "token" else "",
        openbao_password_credential_uuid="11111111-1111-4111-8111-111111111111"
        if mode in {"denied", "healthy", "unpinned"}
        else None,
        ssh_known_host_fingerprint="SHA256:" + "A" * 43 if mode == "healthy" else "",
    )
    user = make_user("ssh-reader", is_staff=True, is_superuser=True)
    request = SimpleNamespace(user=user, is_secure=lambda: True)
    with (
        patch.object(
            openbao,
            "_credential_for_uuid",
            return_value=None if mode == "missing" else object(),
        ),
        patch.object(
            openbao,
            "reveal_credential_material",
            side_effect=PermissionError("secret-canary") if mode == "denied" else None,
            return_value={"password": "usable-password"},
        ) as reveal,
    ):
        response = ssh_credentials.ProxmoxEndpointSSHCredentialSecretsAPIView().get(
            request, endpoint.pk
        )
    assert response.status_code == expected
    if mode == "healthy":
        assert response.data["password"] == "usable-password"
        assert response.data["private_key"] == ""
    else:
        assert "password" not in response.data
    assert bool(reveal.call_count) is (mode in {"denied", "healthy", "unpinned"})
    assert "secret-canary" not in str(response.data)


def test_reuse_form_contains_failed_preservation_in_all_readiness_checks(
    optionality_models,
):
    from django.core.exceptions import ValidationError
    from netbox_proxbox.forms.proxmox import ProxmoxEndpointForm
    from netbox_proxbox.integrations import openbao

    _, Endpoint = optionality_models
    endpoint = _saved_openbao_endpoint(
        Endpoint,
        ssh_credential_source="reuse_endpoint",
        ssh_known_host_fingerprint="SHA256:" + "A" * 43,
        openbao_password_credential_uuid="11111111-1111-4111-8111-111111111111",
    )
    form = ProxmoxEndpointForm(
        instance=endpoint,
        data=_edit_data(
            endpoint,
            token_name="new-token",
            token_value="new-value",
            allow_writes=True,
            access_methods="api_ssh",
            ssh_credential_source="reuse_endpoint",
            ssh_known_host_fingerprint=endpoint.ssh_known_host_fingerprint,
            service_monitoring_enabled=True,
        ),
    )
    with (
        patch.object(openbao, "_credential_for_uuid", return_value=None),
        patch.object(openbao, "openbao_prerequisites_errors", return_value=[]),
        patch.object(Endpoint, "effective_rpc_enabled", return_value=True),
    ):
        assert not form.is_valid()
        assert "password" in form.errors
        assert "ssh_credential_source" in form.errors
        assert "service_monitoring_enabled" in form.errors
        endpoint.service_monitoring_enabled = False
        with pytest.raises(ValidationError) as raised:
            endpoint.clean()
    assert "ssh_credential_source" in raised.value.message_dict
