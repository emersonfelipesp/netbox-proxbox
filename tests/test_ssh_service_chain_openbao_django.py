"""OpenBao-cell coverage for service-owned SSH credentials."""

from __future__ import annotations

import json
import os

import pytest

from tests.test_proxmox_endpoint_allowed_tenants import _require_harness


pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(
        os.environ.get("NETBOX_PROXBOX_TEST_OPENBAO") != "1",
        reason="requires the exact-source netbox-openbao companion cell",
    ),
]


@pytest.fixture
def service_openbao_estate(pytestconfig, transactional_db):
    _require_harness(pytestconfig)
    from django.contrib.auth import get_user_model
    from netbox_openbao import backends
    from netbox_openbao.backends.openbao import OpenBaoBackend
    from netbox_openbao.models import CredentialPolicy, SecretEngine
    from netbox_openbao.tests.fakes import FakeBackend
    from netbox_proxbox.models import ProxboxPluginSettings

    backends.BACKENDS["openbao"] = FakeBackend
    FakeBackend.reset()
    engine = SecretEngine.objects.create(
        name="Service SSH test",
        slug="service-ssh-test",
        api_url="https://bao.invalid:8200",
        kv_mount="secret",
        is_default=True,
    )
    policy = CredentialPolicy.objects.create(
        name="Service SSH",
        slug="service-ssh",
        engine=engine,
        openbao_policy="netbox-proxbox",
    )
    actor = get_user_model().objects.create_superuser(
        username="service-ssh-openbao",
        email="service-ssh-openbao@example.invalid",
        password=None,
    )
    settings = ProxboxPluginSettings.get_solo()
    settings.credential_storage_backend = "openbao"
    settings.openbao_policy_slug = policy.slug
    settings.openbao_service_username = actor.username
    settings.save()
    yield actor, policy, FakeBackend
    backends.BACKENDS["openbao"] = OpenBaoBackend


def _objects(actor, suffix=""):
    from ipam.models import IPAddress
    from netbox_proxbox.choices import ProxmoxAccessMethodChoices
    from netbox_proxbox.models import ProxmoxEndpoint

    host = "189" if suffix else "188"
    address = ".".join(("192", "0", "2", host))
    ip_address = IPAddress.objects.create(address=f"{address}/32")
    endpoint = ProxmoxEndpoint.objects.create(
        name=f"service-openbao{suffix}",
        domain=f"service-openbao{suffix}.example.invalid",
        ip_address=ip_address,
        username="root@pam",
        enabled=False,
        access_methods=ProxmoxAccessMethodChoices.API_SSH,
        credential_storage_backend="openbao",
    )
    endpoint._openbao_actor_user = actor
    return endpoint, ip_address


def _form(endpoint, ip_address, actor, **overrides):
    from netbox_proxbox.forms.proxmox import ProxmoxEndpointSSHSettingsForm
    from netbox_proxbox.models.ssh_credential import (
        AUTH_METHOD_PASSWORD,
        SSH_CRED_SOURCE_SERVICE,
    )

    data = {
        "ip_address": ip_address.pk,
        "ssh_credential_source": SSH_CRED_SOURCE_SERVICE,
        "ssh_service": "",
        "ssh_storage": "openbao_new",
        "ssh_username": "root",
        "ssh_port": 22,
        "ssh_auth_method": AUTH_METHOD_PASSWORD,
        "ssh_known_host_fingerprint": "SHA256:" + "A" * 43,
        "ssh_password": "service-openbao-password",
        "ssh_private_key": "",
    }
    data.update(overrides)
    return ProxmoxEndpointSSHSettingsForm(
        instance=endpoint, data=data, request_user=actor
    )


def test_endpoint_service_is_registered_as_openbao_assignable(
    service_openbao_estate,
) -> None:
    from netbox_openbao.registry import registered_assignable_models
    from netbox_proxbox.integrations.openbao import register_openbao_assignable_models

    register_openbao_assignable_models()

    assert "netbox_proxbox.proxmoxendpointservice" in registered_assignable_models()


def test_existing_openbao_credential_is_primary_on_service(
    service_openbao_estate,
) -> None:
    from django.contrib.contenttypes.models import ContentType
    from netbox_openbao.models import Credential, CredentialAssignment

    actor, policy, _backend = service_openbao_estate
    endpoint, ip_address = _objects(actor)
    credential = Credential.objects.create(
        name="Existing SSH password",
        credential_type="ssh-password",
        policy=policy,
        engine=policy.engine,
    )
    form = _form(
        endpoint,
        ip_address,
        actor,
        ssh_storage="openbao_existing",
        openbao_credential=credential.pk,
        ssh_password="",
    )

    assert form.is_valid(), form.errors.as_data()
    endpoint = form.save()
    endpoint.refresh_from_db()
    service_credential = endpoint.ssh_service.ssh_credential
    assert service_credential.openbao_password_credential_uuid == credential.uuid
    assert service_credential.password_enc == ""
    assignment = CredentialAssignment.objects.get(
        credential=credential,
        assigned_object_type=ContentType.objects.get_for_model(endpoint.ssh_service),
        assigned_object_id=endpoint.ssh_service_id,
        purpose="console",
    )
    assert assignment.is_primary is True


def test_new_openbao_material_is_created_and_resolves_from_service(
    service_openbao_estate,
) -> None:
    from django.contrib.contenttypes.models import ContentType
    from netbox_openbao.models import Credential, CredentialAssignment

    actor, _policy, backend = service_openbao_estate
    endpoint, ip_address = _objects(actor)
    form = _form(endpoint, ip_address, actor)

    assert form.is_valid(), form.errors.as_data()
    endpoint = form.save()
    endpoint.refresh_from_db()
    service_credential = endpoint.ssh_service.ssh_credential
    service_credential.refresh_from_db()
    reference = service_credential.openbao_password_credential_uuid
    assert reference is not None
    assert service_credential.password_enc == ""
    assert endpoint.get_ssh_password(key="") == "service-openbao-password"
    credential = Credential.objects.get(uuid=reference)
    assignment = CredentialAssignment.objects.get(
        credential=credential,
        assigned_object_type=ContentType.objects.get_for_model(endpoint.ssh_service),
        assigned_object_id=endpoint.ssh_service_id,
        purpose="console",
    )
    assert assignment.is_primary is True
    assert credential.path in backend.store


def test_blank_openbao_secret_input_preserves_existing_reference(
    service_openbao_estate,
) -> None:
    actor, _policy, _backend = service_openbao_estate
    endpoint, ip_address = _objects(actor)
    initial = _form(endpoint, ip_address, actor)
    assert initial.is_valid(), initial.errors.as_data()
    endpoint = initial.save()
    original = endpoint.ssh_service.ssh_credential.openbao_password_credential_uuid
    update = _form(
        endpoint,
        ip_address,
        actor,
        ssh_service=endpoint.ssh_service_id,
        ssh_password="",
    )

    assert update.is_valid(), update.errors.as_data()
    endpoint = update.save()
    endpoint.ssh_service.ssh_credential.refresh_from_db()

    assert (
        endpoint.ssh_service.ssh_credential.openbao_password_credential_uuid == original
    )


def test_openbao_service_refuses_implicit_legacy_transition(
    service_openbao_estate,
) -> None:
    actor, _policy, _backend = service_openbao_estate
    endpoint, ip_address = _objects(actor)
    initial = _form(endpoint, ip_address, actor)
    assert initial.is_valid(), initial.errors.as_data()
    endpoint = initial.save()
    update = _form(
        endpoint,
        ip_address,
        actor,
        ssh_service=endpoint.ssh_service_id,
        ssh_storage="legacy_encrypted",
        ssh_password="local-password",
    )

    assert not update.is_valid()
    assert "Remove the OpenBao service credential" in update.errors["ssh_storage"][0]


def test_service_secret_api_denies_credential_outside_reveal_scope(
    service_openbao_estate,
) -> None:
    from django.contrib.auth import get_user_model
    from netbox_proxbox.api.ssh_credentials import (
        ProxmoxEndpointSSHCredentialSecretsAPIView,
    )

    actor, _policy, _backend = service_openbao_estate
    endpoint, ip_address = _objects(actor)
    form = _form(endpoint, ip_address, actor)
    assert form.is_valid(), form.errors.as_data()
    endpoint = form.save()
    denied = get_user_model().objects.create_user(username="service-reveal-denied")
    endpoint._openbao_actor_user = denied

    response = (
        ProxmoxEndpointSSHCredentialSecretsAPIView._dedicated_credentials_response(
            endpoint
        )
    )

    assert response.status_code == 503
    assert "cannot be resolved" in response.data["detail"]


def test_service_secret_api_refuses_a_revoked_assignment(
    service_openbao_estate,
) -> None:
    from django.contrib.contenttypes.models import ContentType
    from netbox_openbao.models import CredentialAssignment
    from netbox_proxbox.api.ssh_credentials import (
        ProxmoxEndpointSSHCredentialSecretsAPIView,
    )

    actor, _policy, _backend = service_openbao_estate
    endpoint, ip_address = _objects(actor)
    form = _form(endpoint, ip_address, actor)
    assert form.is_valid(), form.errors.as_data()
    endpoint = form.save()
    CredentialAssignment.objects.filter(
        assigned_object_type=ContentType.objects.get_for_model(endpoint.ssh_service),
        assigned_object_id=endpoint.ssh_service_id,
        purpose="console",
    ).delete()

    response = (
        ProxmoxEndpointSSHCredentialSecretsAPIView._dedicated_credentials_response(
            endpoint
        )
    )

    assert response.status_code == 503
    assert "cannot be resolved" in response.data["detail"]


def test_provider_failure_rolls_back_the_complete_service_chain(
    service_openbao_estate, monkeypatch
) -> None:
    from django.core.exceptions import ValidationError
    from netbox_proxbox.integrations import openbao_service
    from netbox_proxbox.models import ProxmoxEndpointService

    actor, _policy, _backend = service_openbao_estate
    endpoint, ip_address = _objects(actor)
    form = _form(endpoint, ip_address, actor)
    assert form.is_valid(), form.errors.as_data()

    def fail_provider(*_args, **_kwargs):
        raise ValidationError("provider write failed")

    monkeypatch.setattr(openbao_service, "_create_credential", fail_provider)
    with pytest.raises(ValidationError, match="provider write failed"):
        form.save()

    endpoint.refresh_from_db()
    assert endpoint.ssh_service_id is None
    assert not ProxmoxEndpointService.objects.filter(endpoint=endpoint).exists()


def test_source_change_reuses_one_provider_transaction(service_openbao_estate) -> None:
    from netbox_proxbox.forms.proxmox import ProxmoxEndpointSSHSettingsForm
    from netbox_proxbox.models.ssh_credential import (
        AUTH_METHOD_PASSWORD,
        SSH_CRED_SOURCE_DEDICATED,
    )

    actor, _policy, _backend = service_openbao_estate
    endpoint, ip_address = _objects(actor)
    initial = _form(endpoint, ip_address, actor)
    assert initial.is_valid(), initial.errors.as_data()
    endpoint = initial.save()
    replacement = ProxmoxEndpointSSHSettingsForm(
        instance=endpoint,
        request_user=actor,
        data={
            "ip_address": ip_address.pk,
            "ssh_credential_source": SSH_CRED_SOURCE_DEDICATED,
            "ssh_service": "",
            "ssh_storage": "openbao_new",
            "ssh_username": "replacement",
            "ssh_port": 22,
            "ssh_auth_method": AUTH_METHOD_PASSWORD,
            "ssh_known_host_fingerprint": "SHA256:" + "B" * 43,
            "ssh_password": "replacement-password",
            "ssh_private_key": "",
        },
    )

    assert replacement.is_valid(), replacement.errors.as_data()
    endpoint = replacement.save()
    endpoint.refresh_from_db()
    assert endpoint.ssh_credential_source == SSH_CRED_SOURCE_DEDICATED
    assert endpoint.get_ssh_password(key="") == "replacement-password"


def test_main_edit_switches_api_storage_without_moving_local_service_ssh(
    service_openbao_estate, client
) -> None:
    from cryptography.fernet import Fernet
    from netbox_proxbox.models import ProxboxPluginSettings
    from netbox_proxbox.models.ssh_credential import (
        AUTH_METHOD_PASSWORD,
        SSH_CRED_SOURCE_SERVICE,
    )
    from django.urls import reverse

    actor, _policy, _backend = service_openbao_estate
    endpoint, ip_address = _objects(actor, "-local-service")
    endpoint.credential_storage_backend = "legacy_encrypted"
    endpoint.save(update_fields=("credential_storage_backend",))
    settings = ProxboxPluginSettings.get_solo()
    settings.encryption_key = Fernet.generate_key().decode()
    settings.save(update_fields=("encryption_key",))
    local = _form(
        endpoint,
        ip_address,
        actor,
        ssh_storage="legacy_encrypted",
        ssh_password="local-service-password",
    )
    assert local.is_valid(), local.errors.as_data()
    endpoint = local.save()
    service = endpoint.ssh_service
    client.force_login(actor)
    response = client.post(
        reverse("plugins:netbox_proxbox:proxmoxendpoint_edit", args=[endpoint.pk]),
        {
            "name": endpoint.name,
            "node_device_name_template": "",
            "ip_address": ip_address.pk,
            "domain": endpoint.domain,
            "port": endpoint.port,
            "username": endpoint.username,
            "password": "openbao-api-password",
            "token_name": "",
            "token_value": "",
            "credential_storage_backend": "openbao",
            "verify_ssl": "on",
            "enabled": "",
            "allow_writes": "",
            "allow_packer_template_builds": "",
            "access_methods": "api_ssh",
            "service_monitoring_enabled": "",
            "service_monitoring_interval_minutes": 5,
            "service_monitoring_units": [],
            "environment": "",
            "site": "",
            "tenant": "",
            "allowed_tenants": [],
            "tags": [],
            "ssh_credential_source": SSH_CRED_SOURCE_SERVICE,
            "ssh_service": service.pk,
            "ssh_storage": "legacy_encrypted",
            "ssh_username": "root",
            "ssh_port": 22,
            "ssh_auth_method": AUTH_METHOD_PASSWORD,
            "ssh_known_host_fingerprint": "SHA256:" + "A" * 43,
            "ssh_password": "",
            "ssh_private_key": "",
        },
    )

    errors = response.context["form"].errors if response.context else None
    assert response.status_code == 302, errors
    endpoint.refresh_from_db()
    service.ssh_credential.refresh_from_db()
    assert endpoint.credential_storage_backend == "openbao"
    assert endpoint.openbao_password_credential_uuid is not None
    assert service.ssh_credential.storage_backend == "legacy_encrypted"
    assert (
        service.ssh_credential.get_password(key=settings.encryption_key)
        == "local-service-password"
    )


def test_stale_service_material_intent_is_rejected(service_openbao_estate) -> None:
    from uuid import uuid4

    from django.core.exceptions import ValidationError
    from netbox_proxbox.integrations.openbao_service import assert_service_intent
    from netbox_proxbox.integrations.openbao_transaction import (
        endpoint_material_transaction,
    )
    from netbox_proxbox.models import ServiceSSHCredential

    actor, _policy, _backend = service_openbao_estate
    endpoint, ip_address = _objects(actor)
    form = _form(endpoint, ip_address, actor)
    assert form.is_valid(), form.errors.as_data()
    endpoint = form.save()
    owner = endpoint.ssh_service.ssh_credential
    expected = (
        owner.openbao_password_credential_uuid,
        owner.openbao_keypair_credential_uuid,
    )

    with endpoint_material_transaction([endpoint]):
        ServiceSSHCredential.objects.filter(pk=owner.pk).update(
            openbao_password_credential_uuid=uuid4()
        )
        with pytest.raises(ValidationError, match="changed before"):
            assert_service_intent(owner, expected)


def test_service_cleanup_preserves_shared_credentials(service_openbao_estate) -> None:
    from netbox_openbao.models import Credential, CredentialAssignment
    from netbox_proxbox.integrations.openbao_service import (
        cleanup_service_state,
        service_cleanup_boundary,
    )

    actor, _policy, _backend = service_openbao_estate
    endpoint, ip_address = _objects(actor)
    form = _form(endpoint, ip_address, actor)
    assert form.is_valid(), form.errors.as_data()
    endpoint = form.save()
    service = endpoint.ssh_service
    owner = service.ssh_credential
    credential_uuid = owner.openbao_password_credential_uuid

    with service_cleanup_boundary([service], actor=actor):
        cleanup_service_state(service, actor=actor)
        service.delete()

    assert Credential.objects.filter(uuid=credential_uuid).exists()
    assert not CredentialAssignment.objects.filter(
        assigned_object_id=service.pk, purpose="console"
    ).exists()


def test_service_credential_cleanup_removes_assignments_before_delete(
    service_openbao_estate,
) -> None:
    from netbox_openbao.models import Credential, CredentialAssignment
    from netbox_proxbox.integrations.openbao_service import (
        cleanup_service_credential,
        service_cleanup_boundary,
    )

    actor, _policy, _backend = service_openbao_estate
    endpoint, ip_address = _objects(actor)
    form = _form(endpoint, ip_address, actor)
    assert form.is_valid(), form.errors.as_data()
    endpoint = form.save()
    service = endpoint.ssh_service
    owner = service.ssh_credential
    credential_uuid = owner.openbao_password_credential_uuid

    with service_cleanup_boundary([service], actor=actor):
        cleanup_service_credential(owner, actor=actor)
        owner.delete()

    assert service.__class__.objects.filter(pk=service.pk).exists()
    assert Credential.objects.filter(uuid=credential_uuid).exists()
    assert not CredentialAssignment.objects.filter(
        assigned_object_id=service.pk, purpose="console"
    ).exists()


def test_endpoint_cascade_cleanup_preserves_provider_credential(
    service_openbao_estate,
) -> None:
    from netbox_openbao.models import Credential, CredentialAssignment
    from netbox_proxbox.integrations.openbao_service import (
        cleanup_endpoint_services,
        endpoint_service_cleanup_boundary,
    )

    actor, _policy, _backend = service_openbao_estate
    endpoint, ip_address = _objects(actor)
    form = _form(endpoint, ip_address, actor)
    assert form.is_valid(), form.errors.as_data()
    endpoint = form.save()
    service = endpoint.ssh_service
    credential_uuid = service.ssh_credential.openbao_password_credential_uuid

    with endpoint_service_cleanup_boundary([endpoint], actor=actor):
        cleanup_endpoint_services(endpoint, actor=actor)
        endpoint.delete()

    assert Credential.objects.filter(uuid=credential_uuid).exists()
    assert not CredentialAssignment.objects.filter(
        assigned_object_id=service.pk, purpose="console"
    ).exists()


def test_bulk_service_cleanup_clears_every_selected_assignment(
    service_openbao_estate,
) -> None:
    from netbox_openbao.models import CredentialAssignment
    from netbox_proxbox.integrations.openbao_service import (
        cleanup_service_state,
        service_cleanup_boundary,
    )

    actor, _policy, _backend = service_openbao_estate
    first_endpoint, first_ip = _objects(actor)
    second_endpoint, second_ip = _objects(actor, "-two")
    services = []
    for endpoint, ip_address in (
        (first_endpoint, first_ip),
        (second_endpoint, second_ip),
    ):
        form = _form(endpoint, ip_address, actor)
        assert form.is_valid(), form.errors.as_data()
        saved = form.save()
        services.append(saved.ssh_service)

    with service_cleanup_boundary(services, actor=actor):
        for service in services:
            cleanup_service_state(service, actor=actor)
        type(services[0]).objects.filter(
            pk__in=[service.pk for service in services]
        ).delete()

    assert not CredentialAssignment.objects.filter(
        assigned_object_id__in=[service.pk for service in services],
        purpose="console",
    ).exists()


def test_service_cleanup_requires_assignment_delete_authorization(
    service_openbao_estate,
) -> None:
    from django.contrib.auth import get_user_model
    from django.core.exceptions import PermissionDenied
    from netbox_openbao.models import CredentialAssignment
    from netbox_proxbox.integrations.openbao_service import (
        cleanup_service_state,
        service_cleanup_boundary,
    )

    actor, _policy, _backend = service_openbao_estate
    endpoint, ip_address = _objects(actor)
    form = _form(endpoint, ip_address, actor)
    assert form.is_valid(), form.errors.as_data()
    service = form.save().ssh_service
    denied = get_user_model().objects.create_user(username="service-cleanup-denied")

    with pytest.raises(PermissionDenied):
        with service_cleanup_boundary([service], actor=denied):
            cleanup_service_state(service, actor=denied)

    assert CredentialAssignment.objects.filter(
        assigned_object_id=service.pk, purpose="console"
    ).exists()


def _delete_graph(service_openbao_estate):
    actor, _policy, _backend = service_openbao_estate
    endpoint, ip_address = _objects(actor, f"-delete-{os.urandom(3).hex()}")
    form = _form(endpoint, ip_address, actor)
    assert form.is_valid(), form.errors.as_data()
    endpoint = form.save()
    service = endpoint.ssh_service
    owner = service.ssh_credential
    return actor, endpoint, service, owner


def _delete_url(target, *, bulk: bool) -> str:
    from django.urls import reverse

    model_name = target._meta.model_name
    action = f"{model_name}_bulk_delete" if bulk else f"{model_name}_delete"
    kwargs = {} if bulk else {"pk": target.pk}
    return reverse(f"plugins:netbox_proxbox:{action}", kwargs=kwargs)


def _assert_service_graph_intact(endpoint_pk, service_pk, owner_pk, reference) -> None:
    from netbox_openbao.models import CredentialAssignment
    from netbox_proxbox.models import (
        ProxmoxEndpoint,
        ProxmoxEndpointService,
        ServiceSSHCredential,
    )

    assert ProxmoxEndpoint.objects.filter(pk=endpoint_pk).exists()
    assert ProxmoxEndpointService.objects.filter(pk=service_pk).exists()
    assert ServiceSSHCredential.objects.filter(
        pk=owner_pk, openbao_password_credential_uuid=reference
    ).exists()
    assert CredentialAssignment.objects.filter(
        assigned_object_id=service_pk,
        purpose="console",
        credential__uuid=reference,
    ).exists()


def _api_delete_url(target) -> str:
    from django.urls import reverse
    from netbox_proxbox.models import ProxmoxEndpoint

    if isinstance(target, ProxmoxEndpoint):
        return reverse("plugins-api:netbox_proxbox-api:endpoints:proxmoxendpoint-list")
    return reverse("plugins-api:netbox_proxbox-api:proxmoxendpointservice-list")


def _service_assignment_exists(service_pk, reference) -> bool:
    from django.contrib.contenttypes.models import ContentType
    from netbox_openbao.models import CredentialAssignment
    from netbox_proxbox.models import ProxmoxEndpointService

    return CredentialAssignment.objects.filter(
        credential__uuid=reference,
        assigned_object_type=ContentType.objects.get_for_model(ProxmoxEndpointService),
        assigned_object_id=service_pk,
        purpose="console",
    ).exists()


@pytest.mark.parametrize("target_kind", ["endpoint", "service"])
def test_api_bulk_delete_missing_id_preserves_service_assignment(
    service_openbao_estate, client, target_kind
) -> None:
    actor, endpoint, service, owner = _delete_graph(service_openbao_estate)
    target = endpoint if target_kind == "endpoint" else service
    reference = owner.openbao_password_credential_uuid
    client.force_login(actor)

    response = client.delete(
        _api_delete_url(target),
        data=json.dumps([{"id": target.pk}, {"id": target.pk + 1000000}]),
        content_type="application/json",
    )

    assert response.status_code == 400, response.content
    assert type(target).objects.filter(pk=target.pk).exists()
    assert _service_assignment_exists(service.pk, reference)


@pytest.mark.parametrize("target_kind", ["endpoint", "service"])
def test_api_bulk_delete_protected_object_preserves_service_assignment(
    service_openbao_estate, client, target_kind
) -> None:
    from django.db.models import ProtectedError
    from django.db.models.signals import pre_delete

    actor, endpoint, service, owner = _delete_graph(service_openbao_estate)
    target = endpoint if target_kind == "endpoint" else service
    target_pk = target.pk
    reference = owner.openbao_password_credential_uuid
    client.force_login(actor)
    dispatch_uid = f"api_protected_service_chain_{target_kind}"

    def refuse_delete(sender, instance, **kwargs):
        del sender, kwargs
        if instance.pk == target_pk:
            raise ProtectedError("test protected delete", {instance})

    pre_delete.connect(
        refuse_delete,
        sender=type(target),
        weak=False,
        dispatch_uid=dispatch_uid,
    )
    try:
        response = client.delete(
            _api_delete_url(target),
            data=json.dumps([{"id": target_pk}]),
            content_type="application/json",
        )
    finally:
        pre_delete.disconnect(sender=type(target), dispatch_uid=dispatch_uid)

    assert response.status_code == 409, response.content
    assert type(target).objects.filter(pk=target_pk).exists()
    assert _service_assignment_exists(service.pk, reference)


@pytest.mark.parametrize("target_kind", ["endpoint", "service"])
def test_api_bulk_delete_success_cleans_service_assignment(
    service_openbao_estate, client, target_kind
) -> None:
    actor, endpoint, service, owner = _delete_graph(service_openbao_estate)
    target = endpoint if target_kind == "endpoint" else service
    target_pk = target.pk
    service_pk = service.pk
    reference = owner.openbao_password_credential_uuid
    client.force_login(actor)

    response = client.delete(
        _api_delete_url(target),
        data=json.dumps([{"id": target_pk}]),
        content_type="application/json",
    )

    assert response.status_code == 204, response.content
    assert not type(target).objects.filter(pk=target_pk).exists()
    assert not _service_assignment_exists(service_pk, reference)


@pytest.mark.parametrize("target_kind", ["endpoint", "service", "credential"])
@pytest.mark.parametrize("bulk", [False, True], ids=["single", "bulk"])
def test_unconfirmed_cancelled_and_invalid_deletes_leave_provider_state(
    service_openbao_estate, client, target_kind, bulk
) -> None:
    actor, endpoint, service, owner = _delete_graph(service_openbao_estate)
    reference = owner.openbao_password_credential_uuid
    targets = {"endpoint": endpoint, "service": service, "credential": owner}
    target = targets[target_kind]
    url = _delete_url(target, bulk=bulk)
    client.force_login(actor)
    if bulk:
        responses = [
            client.post(url, {"pk": [target.pk]}),
            client.post(url, {"pk": [target.pk], "cancel": "Cancel"}),
            client.post(
                url,
                {
                    "_confirm": "on",
                    "pk": [target.pk],
                    "confirm": "on",
                    "changelog_message": "x" * 201,
                },
            ),
        ]
    else:
        responses = [
            client.get(url),
            client.post(url, {"cancel": "Cancel"}),
            client.post(
                url,
                {"confirm": "on", "changelog_message": "x" * 201},
            ),
        ]

    assert all(response.status_code < 500 for response in responses)
    _assert_service_graph_intact(endpoint.pk, service.pk, owner.pk, reference)


@pytest.mark.parametrize("target_kind", ["endpoint", "service", "credential"])
@pytest.mark.parametrize("bulk", [False, True], ids=["single", "bulk"])
def test_protected_delete_rolls_back_provider_cleanup(
    service_openbao_estate, client, target_kind, bulk
) -> None:
    from django.db.models import ProtectedError
    from django.db.models.signals import pre_delete

    actor, endpoint, service, owner = _delete_graph(service_openbao_estate)
    reference = owner.openbao_password_credential_uuid
    targets = {"endpoint": endpoint, "service": service, "credential": owner}
    target = targets[target_kind]
    url = _delete_url(target, bulk=bulk)
    client.force_login(actor)
    dispatch_uid = f"test_protected_service_chain_{target_kind}_{bulk}"

    def refuse_delete(sender, instance, **kwargs):
        del sender, kwargs
        if instance.pk == target.pk:
            raise ProtectedError("test protected delete", {instance})

    pre_delete.connect(
        refuse_delete,
        sender=target.__class__,
        weak=False,
        dispatch_uid=dispatch_uid,
    )
    try:
        data = {"confirm": "on"}
        if bulk:
            data.update({"_confirm": "on", "pk": [target.pk]})
        response = client.post(url, data)
    finally:
        pre_delete.disconnect(sender=target.__class__, dispatch_uid=dispatch_uid)

    assert response.status_code < 500
    _assert_service_graph_intact(endpoint.pk, service.pk, owner.pk, reference)
