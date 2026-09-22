"""Real Django contracts for Proxbox-owned OpenBao assignments."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from tests.test_proxmox_endpoint_allowed_tenants import _require_harness

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(
        os.environ.get("NETBOX_PROXBOX_TEST_OPENBAO") != "1",
        reason="requires the exact-source netbox-openbao companion cell",
    ),
]


def _private_key() -> str:
    return (
        Ed25519PrivateKey.generate()
        .private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.OpenSSH,
            serialization.NoEncryption(),
        )
        .decode()
    )


@pytest.fixture
def openbao_estate(pytestconfig, transactional_db):
    _require_harness(pytestconfig)
    from django.contrib.auth import get_user_model
    from netbox_openbao import backends
    from netbox_openbao.backends.openbao import OpenBaoBackend
    from netbox_openbao.models import CredentialPolicy, SecretEngine
    from netbox_openbao.tests.fakes import FakeBackend
    from netbox_proxbox.models import ProxboxPluginSettings

    assert "netbox_openbao" in __import__("django.conf").conf.settings.PLUGINS
    backends.BACKENDS["openbao"] = FakeBackend
    FakeBackend.reset()
    engine = SecretEngine.objects.create(
        name="Proxbox test",
        slug="proxbox-test",
        api_url="https://bao.invalid:8200",
        kv_mount="secret",
        is_default=True,
    )
    policy = CredentialPolicy.objects.create(
        name="Proxbox",
        slug="proxbox",
        engine=engine,
        openbao_policy="netbox-proxbox",
    )
    actor = get_user_model().objects.create_superuser(
        username="proxbox-openbao-test",
        email="proxbox-openbao@example.invalid",
        password=None,
    )
    plugin_settings = ProxboxPluginSettings.get_solo()
    plugin_settings.credential_storage_backend = "openbao"
    plugin_settings.openbao_policy_slug = policy.slug
    plugin_settings.openbao_service_username = actor.username
    plugin_settings.save()
    yield actor, policy, FakeBackend
    backends.BACKENDS["openbao"] = OpenBaoBackend


def _endpoint(actor):
    from netbox_proxbox.models import ProxmoxEndpoint
    from netbox_proxbox.models.ssh_credential import (
        AUTH_METHOD_PASSWORD,
        SSH_CRED_SOURCE_DEDICATED,
    )

    endpoint = ProxmoxEndpoint.objects.create(
        name="OpenBao endpoint",
        enabled=False,
        credential_storage_backend="openbao",
        ssh_credential_source=SSH_CRED_SOURCE_DEDICATED,
        ssh_auth_method=AUTH_METHOD_PASSWORD,
    )
    endpoint._openbao_actor_user = actor
    return endpoint


def _assert_api_assignment_filter(endpoint, expected_uuid) -> None:
    from django.http import QueryDict
    from netbox_openbao.filtersets import CredentialFilterSet
    from netbox_openbao.models import Credential

    filters = QueryDict(mutable=True)
    filters["assigned_object_type"] = "netbox_proxbox.proxmoxendpoint"
    filters.setlist("assigned_object_id", [str(endpoint.pk)])
    filters.setlist("purpose", ["api"])
    assert list(
        CredentialFilterSet(filters, queryset=Credential.objects.all()).qs.values_list(
            "uuid", flat=True
        )
    ) == [expected_uuid]


def _assert_assignment_metadata(backend, endpoint) -> None:
    assert len(backend.store) == 4
    assert len(backend.metadata_calls) >= 4
    latest_metadata = {path: metadata for path, metadata in backend.metadata_calls}
    assert len(latest_metadata) == 4
    assert all(
        metadata["netbox_assignments"]
        == f"netbox_proxbox.proxmoxendpoint:{endpoint.pk}"
        for metadata in latest_metadata.values()
    )


def test_four_slots_persist_material_and_exact_assignments(openbao_estate) -> None:
    from django.contrib.contenttypes.models import ContentType
    from netbox_openbao.models import Credential, CredentialAssignment

    actor, policy, backend = openbao_estate
    endpoint = _endpoint(actor)
    endpoint.password = "api-password"
    endpoint.token_value = "api-token"
    endpoint.set_ssh_password("ssh-password", key="unused")
    endpoint.set_ssh_private_key(_private_key(), key="unused")
    endpoint.save()
    endpoint.refresh_from_db()

    expected = {
        endpoint.openbao_password_credential_uuid: ("password", "login", True),
        endpoint.openbao_token_credential_uuid: ("api-token", "api", True),
        endpoint.openbao_ssh_password_credential_uuid: (
            "ssh-password",
            "console",
            True,
        ),
        endpoint.openbao_ssh_keypair_credential_uuid: (
            "ssh-keypair",
            "console",
            False,
        ),
    }
    credentials = Credential.objects.in_bulk(expected, field_name="uuid")
    assert set(credentials) == set(expected)
    assert {row.policy_id for row in credentials.values()} == {policy.pk}
    content_type = ContentType.objects.get_for_model(type(endpoint))
    rows = CredentialAssignment.objects.filter(
        assigned_object_type=content_type,
        assigned_object_id=endpoint.pk,
    ).select_related("credential")
    observed = {
        row.credential.uuid: (
            row.credential.credential_type,
            row.purpose,
            row.is_primary,
        )
        for row in rows
    }
    assert observed == expected
    _assert_api_assignment_filter(endpoint, endpoint.openbao_token_credential_uuid)
    _assert_assignment_metadata(backend, endpoint)


def test_console_primary_switch_and_shared_clear_preserve_material(
    openbao_estate,
) -> None:
    from django.contrib.contenttypes.models import ContentType
    from netbox_openbao.models import Credential, CredentialAssignment
    from netbox_proxbox.models.ssh_credential import AUTH_METHOD_KEY

    actor, policy, backend = openbao_estate
    endpoint = _endpoint(actor)
    endpoint.set_ssh_password("ssh-password", key="unused")
    endpoint.set_ssh_private_key(_private_key(), key="unused")
    endpoint.save()
    password_uuid = endpoint.openbao_ssh_password_credential_uuid
    key_uuid = endpoint.openbao_ssh_keypair_credential_uuid

    endpoint.ssh_auth_method = AUTH_METHOD_KEY
    endpoint.save()
    primary = CredentialAssignment.objects.get(
        assigned_object_id=endpoint.pk,
        purpose="console",
        is_primary=True,
    )
    assert primary.credential.uuid == key_uuid

    shared = Credential.objects.get(uuid=password_uuid)
    other = _endpoint(actor)
    type(other).objects.filter(pk=other.pk).update(
        openbao_ssh_password_credential_uuid=shared.uuid
    )
    other.refresh_from_db()
    CredentialAssignment.objects.create(
        credential=shared,
        assigned_object_type=ContentType.objects.get_for_model(type(other)),
        assigned_object_id=other.pk,
        purpose="console",
        is_primary=True,
    )
    endpoint.set_ssh_password("", key="unused")
    endpoint.save()
    endpoint.refresh_from_db()

    assert endpoint.openbao_ssh_password_credential_uuid is None
    assert Credential.objects.filter(pk=shared.pk).exists()
    assert CredentialAssignment.objects.filter(
        credential=shared,
        assigned_object_id=other.pk,
        purpose="console",
    ).exists()
    assert shared.path in backend.store

    CredentialAssignment.objects.create(
        credential=shared,
        assigned_object_type=ContentType.objects.get_for_model(type(other)),
        assigned_object_id=other.pk,
        purpose="backup",
        is_primary=False,
    )
    other.delete()
    assert Credential.objects.filter(pk=shared.pk).exists()
    assert not CredentialAssignment.objects.filter(
        credential=shared,
        assigned_object_id=other.pk,
    ).exists()
    assert shared.path in backend.store


def test_assignment_permission_refusal_rolls_back_inventory_and_material(
    openbao_estate,
) -> None:
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Permission
    from django.core.exceptions import PermissionDenied
    from netbox_openbao.models import Credential, CredentialAssignment

    _actor, _policy, backend = openbao_estate
    unprivileged = get_user_model().objects.create_user(username="no-assignment")
    unprivileged.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="netbox_openbao",
            codename="add_credential",
        )
    )
    endpoint = _endpoint(unprivileged)
    endpoint.password = "must-roll-back"

    with pytest.raises(PermissionDenied, match="credential add permission"):
        endpoint.save()

    endpoint.refresh_from_db()
    assert endpoint.openbao_password_credential_uuid is None
    assert Credential.objects.count() == 0
    assert CredentialAssignment.objects.count() == 0
    assert backend.store == {}


def test_mixed_actors_are_rejected_before_material_write(openbao_estate) -> None:
    from django.contrib.auth import get_user_model
    from django.core.exceptions import PermissionDenied
    from netbox_openbao.models import Credential, CredentialAssignment
    from netbox_proxbox.integrations.openbao import (
        store_endpoint_api_token,
        store_endpoint_password,
    )

    actor, policy, backend = openbao_estate
    other = get_user_model().objects.create_superuser(
        username="proxbox-openbao-other",
        email="proxbox-openbao-other@example.invalid",
        password=None,
    )
    endpoint = _endpoint(actor)
    store_endpoint_password(endpoint, "first-actor", user=actor)
    store_endpoint_api_token(endpoint, "second-actor", user=other)

    with pytest.raises(PermissionDenied, match="same actor"):
        endpoint.save()

    endpoint.refresh_from_db()
    assert endpoint.openbao_password_credential_uuid is None
    assert endpoint.openbao_token_credential_uuid is None
    assert Credential.objects.count() == 0
    assert CredentialAssignment.objects.count() == 0
    assert backend.store == {}


def test_partial_save_cannot_desynchronize_ssh_primary(openbao_estate) -> None:
    from django.core.exceptions import ValidationError
    from netbox_proxbox.models.ssh_credential import AUTH_METHOD_KEY

    actor, _policy, backend = openbao_estate
    endpoint = _endpoint(actor)
    endpoint.set_ssh_password("first", key="unused")
    endpoint.set_ssh_private_key(_private_key(), key="unused")
    endpoint.save()
    stored = {path: list(versions) for path, versions in backend.store.items()}
    endpoint.ssh_auth_method = AUTH_METHOD_KEY
    endpoint.set_ssh_password("second", key="unused")

    with pytest.raises(ValidationError, match="outside update_fields"):
        endpoint.save(update_fields=["name"])

    endpoint.refresh_from_db()
    assert endpoint.ssh_auth_method != AUTH_METHOD_KEY
    assert backend.store == stored


@pytest.mark.parametrize("partial", [False, True])
def test_direct_uuid_rebinding_is_rejected(openbao_estate, partial: bool) -> None:
    from django.core.exceptions import ValidationError

    actor, _policy, backend = openbao_estate
    endpoint = _endpoint(actor)
    endpoint.openbao_password_credential_uuid = uuid4()
    kwargs = {"update_fields": ["openbao_password_credential_uuid"]} if partial else {}

    with pytest.raises(ValidationError, match="references changed"):
        endpoint.save(**kwargs)

    endpoint.refresh_from_db()
    assert endpoint.openbao_password_credential_uuid is None
    assert backend.store == {}


def test_api_selector_update_uses_request_actor_before_save(openbao_estate) -> None:
    from django.core.exceptions import PermissionDenied
    from netbox_proxbox.api.serializers.endpoints import ProxmoxEndpointSerializer
    from netbox_proxbox.models.ssh_credential import AUTH_METHOD_KEY

    actor, _policy, _backend = openbao_estate
    endpoint = _endpoint(actor)
    endpoint.set_ssh_password("password", key="unused")
    endpoint.set_ssh_private_key(_private_key(), key="unused")
    endpoint.save()
    endpoint.domain = "pve.example.invalid"
    endpoint.save(update_fields=["domain"])
    actor.is_active = False
    actor.save(update_fields=["is_active"])
    serializer = ProxmoxEndpointSerializer(
        endpoint,
        data={"ssh_auth_method": AUTH_METHOD_KEY},
        partial=True,
        context={"request": SimpleNamespace(user=actor)},
    )
    assert serializer.is_valid(), serializer.errors

    with pytest.raises(PermissionDenied, match="active OpenBao credential actor"):
        serializer.save()

    endpoint.refresh_from_db()
    assert endpoint.ssh_auth_method != AUTH_METHOD_KEY


def test_concurrent_rotations_serialize_versions(openbao_estate) -> None:
    from django.db import close_old_connections
    from netbox_openbao.models import Credential
    from netbox_proxbox.models import ProxmoxEndpoint

    actor, _policy, backend = openbao_estate
    endpoint = _endpoint(actor)
    endpoint.password = "version-one"
    endpoint.save()
    credential_uuid = endpoint.openbao_password_credential_uuid
    ready = Barrier(2)

    def rotate(value: str) -> None:
        close_old_connections()
        try:
            worker = ProxmoxEndpoint.objects.get(pk=endpoint.pk)
            worker._openbao_actor_user = type(actor).objects.get(pk=actor.pk)
            worker.password = value
            ready.wait(timeout=10)
            worker.save()
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(rotate, value) for value in ("version-two", "version-three")
        ]
        for future in futures:
            future.result(timeout=30)

    credential = Credential.objects.get(uuid=credential_uuid)
    assert credential.kv_version == 3
    assert len(backend.store[credential.path]) == 3


def test_competing_primary_updates_leave_one_matching_primary(openbao_estate) -> None:
    from django.db import close_old_connections
    from netbox_openbao.models import CredentialAssignment
    from netbox_proxbox.models import ProxmoxEndpoint
    from netbox_proxbox.models.ssh_credential import (
        AUTH_METHOD_KEY,
        AUTH_METHOD_PASSWORD,
        SSH_CRED_SOURCE_DEDICATED,
        SSH_CRED_SOURCE_REUSE,
    )

    actor, _policy, _backend = openbao_estate
    endpoint = _endpoint(actor)
    endpoint.set_ssh_password("password", key="unused")
    endpoint.set_ssh_private_key(_private_key(), key="unused")
    endpoint.save()
    ProxmoxEndpoint.objects.filter(pk=endpoint.pk).update(
        ssh_credential_source=SSH_CRED_SOURCE_REUSE
    )
    ready = Barrier(2)

    def select(method: str) -> None:
        close_old_connections()
        try:
            worker = ProxmoxEndpoint.objects.get(pk=endpoint.pk)
            worker._openbao_actor_user = type(actor).objects.get(pk=actor.pk)
            worker.ssh_credential_source = SSH_CRED_SOURCE_DEDICATED
            worker.ssh_auth_method = method
            ready.wait(timeout=10)
            worker.save()
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(select, method)
            for method in (AUTH_METHOD_PASSWORD, AUTH_METHOD_KEY)
        ]
        for future in futures:
            future.result(timeout=30)

    endpoint.refresh_from_db()
    primary = CredentialAssignment.objects.get(
        assigned_object_id=endpoint.pk,
        purpose="console",
        is_primary=True,
    )
    expected = {
        AUTH_METHOD_PASSWORD: endpoint.openbao_ssh_password_credential_uuid,
        AUTH_METHOD_KEY: endpoint.openbao_ssh_keypair_credential_uuid,
    }
    assert primary.credential.uuid == expected[endpoint.ssh_auth_method]


def test_provider_write_failure_rolls_back_owner_graph(openbao_estate) -> None:
    from netbox_openbao.backends.exceptions import OpenBaoConflict
    from netbox_openbao.models import Credential, CredentialAssignment

    actor, _policy, backend = openbao_estate
    endpoint = _endpoint(actor)
    endpoint.password = "must-not-persist"
    backend.fail_on_write = True

    with pytest.raises(OpenBaoConflict):
        endpoint.save()

    endpoint.refresh_from_db()
    assert endpoint.openbao_password_credential_uuid is None
    assert Credential.objects.count() == 0
    assert CredentialAssignment.objects.count() == 0
    assert backend.store == {}


def test_object_constraints_deny_rotate_and_assignment_delete(
    openbao_estate,
) -> None:
    from core.models import ObjectType
    from django.contrib.auth import get_user_model
    from django.core.exceptions import PermissionDenied
    from netbox_openbao.models import Credential, CredentialAssignment
    from users.models import ObjectPermission

    actor, _policy, backend = openbao_estate
    endpoint = _endpoint(actor)
    endpoint.password = "version-one"
    endpoint.save()
    credential = Credential.objects.get(uuid=endpoint.openbao_password_credential_uuid)
    constrained = get_user_model().objects.create_user(username="constrained")
    for model, action in (
        (Credential, "rotate"),
        (CredentialAssignment, "delete"),
    ):
        permission = ObjectPermission.objects.create(
            name=f"deny endpoint {action}",
            actions=[action],
            constraints={"pk": -1},
        )
        permission.users.add(constrained)
        permission.object_types.add(ObjectType.objects.get_for_model(model))

    endpoint._openbao_actor_user = constrained
    endpoint.password = "version-two"
    with pytest.raises(PermissionDenied, match="object permission"):
        endpoint.save()
    credential.refresh_from_db()
    assert credential.kv_version == 1
    assert len(backend.store[credential.path]) == 1

    endpoint.refresh_from_db()
    endpoint._openbao_actor_user = constrained
    endpoint.password = ""
    with pytest.raises(PermissionDenied, match="object permission"):
        endpoint.save()
    assert CredentialAssignment.objects.filter(credential=credential).exists()


def test_assignment_drift_compensates_written_version(openbao_estate) -> None:
    from django.core.exceptions import ValidationError
    from netbox_openbao.models import Credential, CredentialAssignment

    actor, policy, backend = openbao_estate
    endpoint = _endpoint(actor)
    endpoint.password = "version-one"
    endpoint.save()
    credential = Credential.objects.get(uuid=endpoint.openbao_password_credential_uuid)
    assignment = CredentialAssignment.objects.get(credential=credential)
    assignment.enabled = False
    assignment.save(update_fields=["enabled"])
    endpoint.password = "version-two"

    with pytest.raises(ValidationError, match="disabled credential assignment"):
        endpoint.save()

    credential.refresh_from_db()
    assert credential.kv_version == 1
    assert backend(policy.engine).read(credential.path) == {"password": "version-one"}
    assert backend.delete_calls[-1] == (credential.path, (2,))


def test_stale_reference_fails_before_material_access(openbao_estate) -> None:
    from django.core.exceptions import ValidationError
    from netbox_proxbox.models import ProxmoxEndpoint

    actor, _policy, backend = openbao_estate
    endpoint = _endpoint(actor)
    stale = uuid4()
    ProxmoxEndpoint.objects.filter(pk=endpoint.pk).update(
        openbao_password_credential_uuid=stale
    )
    endpoint.refresh_from_db()
    endpoint.password = "must-not-write"

    with pytest.raises(ValidationError, match="cannot be resolved"):
        endpoint.save()

    assert backend.store == {}


def test_metadata_projection_failure_does_not_rollback_commit(
    openbao_estate,
) -> None:
    from netbox_openbao.models import Credential, CredentialAssignment

    actor, policy, backend = openbao_estate
    endpoint = _endpoint(actor)
    endpoint.password = "committed-material"
    backend.fail_on_metadata = True

    endpoint.save()

    endpoint.refresh_from_db()
    credential = Credential.objects.get(uuid=endpoint.openbao_password_credential_uuid)
    assert CredentialAssignment.objects.filter(credential=credential).exists()
    assert backend(policy.engine).read(credential.path) == {
        "password": "committed-material"
    }


def test_credential_delete_cascades_assignment_and_exposes_stale_reference(
    openbao_estate,
) -> None:
    from django.core.exceptions import ValidationError
    from netbox_openbao.models import Credential, CredentialAssignment

    actor, _policy, _backend = openbao_estate
    endpoint = _endpoint(actor)
    endpoint.password = "delete-cascade"
    endpoint.save()
    credential = Credential.objects.get(uuid=endpoint.openbao_password_credential_uuid)

    credential_id = credential.pk
    credential.delete()

    assert not CredentialAssignment.objects.filter(credential_id=credential_id).exists()
    endpoint.password = "must-not-recreate"
    with pytest.raises(ValidationError, match="cannot be resolved"):
        endpoint.save()


def test_policy_slug_migration_round_trip(pytestconfig, transactional_db) -> None:
    _require_harness(pytestconfig)
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    before = ("netbox_proxbox", "0098_proxmoxendpoint_iana_timezone")
    after = ("netbox_proxbox", "0099_proxboxpluginsettings_openbao_policy_slug")
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate([before])
        old_model = executor.loader.project_state([before]).apps.get_model(
            "netbox_proxbox", "ProxboxPluginSettings"
        )
        assert "openbao_policy_slug" not in {
            field.name for field in old_model._meta.get_fields()
        }

        executor = MigrationExecutor(connection)
        executor.migrate([after])
        new_model = executor.loader.project_state([after]).apps.get_model(
            "netbox_proxbox", "ProxboxPluginSettings"
        )
        assert new_model._meta.get_field("openbao_policy_slug").default == "proxbox"
        row = new_model.objects.create(singleton_key="default")
        assert row.openbao_policy_slug == "proxbox"

        executor = MigrationExecutor(connection)
        executor.migrate([before])
        reversed_model = executor.loader.project_state([before]).apps.get_model(
            "netbox_proxbox", "ProxboxPluginSettings"
        )
        assert "openbao_policy_slug" not in {
            field.name for field in reversed_model._meta.get_fields()
        }
    finally:
        MigrationExecutor(connection).migrate(latest)
