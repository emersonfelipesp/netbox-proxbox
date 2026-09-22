"""Real-provider contracts for OpenBao-backed node SSH credentials."""

from __future__ import annotations

import os
from contextlib import contextmanager
from uuid import uuid4

from cryptography.fernet import Fernet
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

FINGERPRINT = "SHA256:" + "A" * 43


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
def openbao_node_estate(pytestconfig, transactional_db):
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
        name="Proxbox node test",
        slug="proxbox-node-test",
        api_url="https://bao.invalid:8200",
        kv_mount="secret",
        is_default=True,
    )
    policy = CredentialPolicy.objects.create(
        name="Proxbox nodes",
        slug="proxbox",
        engine=engine,
        openbao_policy="netbox-proxbox",
    )
    actor = get_user_model().objects.create_superuser(
        username="proxbox-node-openbao-test",
        email="proxbox-node-openbao@example.invalid",
        password=None,
    )
    plugin_settings = ProxboxPluginSettings.get_solo()
    plugin_settings.credential_storage_backend = "openbao"
    plugin_settings.openbao_policy_slug = policy.slug
    plugin_settings.openbao_service_username = actor.username
    plugin_settings.save()
    yield actor, policy, FakeBackend
    backends.BACKENDS["openbao"] = OpenBaoBackend


def _device(name: str):
    from utilities.testing import create_test_device

    return create_test_device(name)


def _node(*, device=None, name: str = "OpenBao node"):
    from netbox_proxbox.models import ProxmoxEndpoint, ProxmoxNode

    endpoint = ProxmoxEndpoint.objects.create(
        name=f"{name} endpoint",
        enabled=False,
        credential_storage_backend="openbao",
    )
    return ProxmoxNode.objects.create(
        endpoint=endpoint,
        netbox_device=device,
        name=name,
        ip_address="127.0.0.1",
    )


def _owner(node, actor, auth_method: str):
    from netbox_proxbox.models import NodeSSHCredential

    owner = NodeSSHCredential(
        node=node,
        username="proxbox-discovery",
        auth_method=auth_method,
        known_host_fingerprint=FINGERPRINT,
    )
    owner._openbao_actor_user = actor
    return owner


def _set_selected(owner, method: str, value: str, actor) -> None:
    from netbox_proxbox.models.ssh_credential import AUTH_METHOD_PASSWORD

    if method == AUTH_METHOD_PASSWORD:
        owner.set_password(value, key="unused", user=actor)
    else:
        owner.set_private_key(value, key="unused", user=actor)


def _selected_case(method: str) -> tuple[str, str, str, str]:
    from netbox_proxbox.models.ssh_credential import AUTH_METHOD_PASSWORD

    if method == AUTH_METHOD_PASSWORD:
        return (
            "openbao_password_credential_uuid",
            "ssh-password",
            "password",
            "password",
        )
    return (
        "openbao_keypair_credential_uuid",
        "ssh-keypair",
        "private_key",
        "keypair",
    )


def _material_value(auth_method: str, label: str) -> str:
    return f"selected-{label}" if auth_method == "password" else _private_key()


def _assert_device_assignment(assignment, device, credential, device_type) -> None:
    assert assignment.credential_id == credential.pk
    assert assignment.assigned_object_type == device_type
    assert assignment.assigned_object_id == device.pk
    assert assignment.purpose == "login"
    assert assignment.is_primary is True
    assert assignment.enabled is True


@pytest.mark.parametrize("auth_method", ["password", "key"])
def test_selected_material_create_rotate_and_exact_device_primary(
    openbao_node_estate,
    auth_method: str,
) -> None:
    from django.contrib.contenttypes.models import ContentType
    from dcim.models import Device
    from netbox_openbao.models import Credential, CredentialAssignment

    actor, policy, backend = openbao_node_estate
    reference_field, credential_type, material_field, label = _selected_case(
        auth_method
    )
    first = _material_value(auth_method, f"first-{label}")
    second = _material_value(auth_method, f"second-{label}")
    device = _device(f"selected-{label}-device")
    owner = _owner(_node(device=device, name=f"selected-{label}"), actor, auth_method)
    _set_selected(owner, auth_method, first, actor)
    owner.save()

    credential_uuid = getattr(owner, reference_field)
    credential = Credential.objects.get(uuid=credential_uuid)
    assignment = CredentialAssignment.objects.get(credential=credential)
    assert credential.policy_id == policy.pk
    assert credential.credential_type == credential_type
    _assert_device_assignment(
        assignment,
        device,
        credential,
        ContentType.objects.get_for_model(Device),
    )
    assert backend(policy.engine).read(credential.path) == {material_field: first}

    _set_selected(owner, auth_method, second, actor)
    owner.save()
    credential.refresh_from_db()
    assert getattr(owner, reference_field) == credential_uuid
    assert credential.kv_version == 2
    assert backend(policy.engine).read(credential.path) == {material_field: second}
    assert CredentialAssignment.objects.filter(credential=credential).count() == 1


def test_unlinked_owner_defers_then_link_relink_and_unlink_reconcile(
    openbao_node_estate,
) -> None:
    from dcim.models import Device
    from django.contrib.contenttypes.models import ContentType
    from netbox_openbao.models import Credential, CredentialAssignment
    from netbox_proxbox.models.ssh_credential import AUTH_METHOD_PASSWORD

    actor, _policy, _backend = openbao_node_estate
    first_device = _device("node-first-device")
    second_device = _device("node-second-device")
    node = _node(name="deferred-node")
    owner = _owner(node, actor, AUTH_METHOD_PASSWORD)
    owner.set_password("deferred-password", key="unused", user=actor)
    owner.save()
    credential = Credential.objects.get(uuid=owner.openbao_password_credential_uuid)
    assert not CredentialAssignment.objects.filter(credential=credential).exists()

    device_type = ContentType.objects.get_for_model(Device)
    node.netbox_device = first_device
    node.save(update_fields=["netbox_device"])
    assignment = CredentialAssignment.objects.get(credential=credential)
    assert assignment.assigned_object_type == device_type
    assert assignment.assigned_object_id == first_device.pk
    assert assignment.purpose == "login"
    assert assignment.is_primary is True

    node.netbox_device = second_device
    node.save(update_fields=["netbox_device"])
    assignment = CredentialAssignment.objects.get(credential=credential)
    assert assignment.assigned_object_id == second_device.pk
    assert CredentialAssignment.objects.filter(credential=credential).count() == 1

    node.netbox_device = None
    node.save(update_fields=["netbox_device"])
    assert not CredentialAssignment.objects.filter(credential=credential).exists()


def test_foreign_device_primary_conflict_rolls_back_owner_and_material(
    openbao_node_estate,
) -> None:
    from django.contrib.contenttypes.models import ContentType
    from django.core.exceptions import ValidationError
    from dcim.models import Device
    from netbox_openbao.models import Credential, CredentialAssignment
    from netbox_proxbox.models import NodeSSHCredential
    from netbox_proxbox.models.ssh_credential import AUTH_METHOD_PASSWORD

    actor, policy, backend = openbao_node_estate
    device = _device("foreign-primary-device")
    foreign = Credential.objects.create(
        name="Foreign primary",
        credential_type="ssh-password",
        policy=policy,
        engine=policy.engine,
    )
    foreign_assignment = CredentialAssignment.objects.create(
        credential=foreign,
        assigned_object_type=ContentType.objects.get_for_model(Device),
        assigned_object_id=device.pk,
        purpose="login",
        is_primary=True,
    )
    owner = _owner(
        _node(device=device, name="conflicted-node"), actor, AUTH_METHOD_PASSWORD
    )
    owner.set_password("must-roll-back", key="unused", user=actor)

    with pytest.raises(ValidationError, match="already primary"):
        owner.save()

    assert not NodeSSHCredential.objects.filter(node=owner.node).exists()
    assert Credential.objects.count() == 1
    assert CredentialAssignment.objects.filter(pk=foreign_assignment.pk).exists()
    assert backend.store == {}


def test_direct_uuid_rebind_is_rejected_without_provider_change(
    openbao_node_estate,
) -> None:
    from django.core.exceptions import ValidationError
    from netbox_openbao.models import Credential
    from netbox_proxbox.models.ssh_credential import AUTH_METHOD_PASSWORD

    actor, _policy, backend = openbao_node_estate
    owner = _owner(_node(name="rebind-node"), actor, AUTH_METHOD_PASSWORD)
    owner.set_password("original", key="unused", user=actor)
    owner.save()
    original_uuid = owner.openbao_password_credential_uuid
    credential = Credential.objects.get(uuid=original_uuid)
    stored = {path: list(versions) for path, versions in backend.store.items()}
    owner.openbao_password_credential_uuid = uuid4()

    with pytest.raises(ValidationError, match="references changed|cannot be rebound"):
        owner.save(update_fields=["openbao_password_credential_uuid"])

    owner.refresh_from_db()
    assert owner.openbao_password_credential_uuid == original_uuid
    assert credential.kv_version == 1
    assert backend.store == stored


def test_missing_assignment_permission_rolls_back_inventory_and_material(
    openbao_node_estate,
) -> None:
    from django.contrib.auth import get_user_model
    from django.core.exceptions import PermissionDenied
    from netbox_openbao.models import Credential, CredentialAssignment
    from netbox_proxbox.models import NodeSSHCredential
    from netbox_proxbox.models.ssh_credential import AUTH_METHOD_PASSWORD

    actor, _policy, backend = openbao_node_estate
    limited = get_user_model().objects.create_user(username="node-limited")
    node = _node(name="limited-node")
    owner = _owner(node, actor, AUTH_METHOD_PASSWORD)
    owner.set_password("retained-material", key="unused", user=actor)
    owner.save()
    credential = Credential.objects.get(uuid=owner.openbao_password_credential_uuid)
    stored = {path: list(versions) for path, versions in backend.store.items()}
    node._openbao_actor_user = limited
    node.netbox_device = _device("limited-device")

    with pytest.raises(PermissionDenied, match="assignment requires add permission"):
        node.save(update_fields=["netbox_device"])

    node.refresh_from_db()
    assert node.netbox_device_id is None
    assert NodeSSHCredential.objects.filter(pk=owner.pk).exists()
    assert Credential.objects.filter(pk=credential.pk).exists()
    assert CredentialAssignment.objects.count() == 0
    assert backend.store == stored


def test_inactive_actor_cannot_rotate_selected_material(openbao_node_estate) -> None:
    from django.core.exceptions import PermissionDenied
    from netbox_openbao.models import Credential
    from netbox_proxbox.models.ssh_credential import AUTH_METHOD_PASSWORD

    actor, _policy, backend = openbao_node_estate
    owner = _owner(_node(name="inactive-actor-node"), actor, AUTH_METHOD_PASSWORD)
    owner.set_password("version-one", key="unused", user=actor)
    owner.save()
    credential = Credential.objects.get(uuid=owner.openbao_password_credential_uuid)
    stored = {path: list(versions) for path, versions in backend.store.items()}
    actor.is_active = False
    actor.save(update_fields=["is_active"])
    owner.set_password("version-two", key="unused", user=actor)

    with pytest.raises(PermissionDenied, match="active OpenBao credential actor"):
        owner.save()

    credential.refresh_from_db()
    assert credential.kv_version == 1
    assert backend.store == stored


def test_provider_failure_rolls_back_new_owner_graph(openbao_node_estate) -> None:
    from netbox_openbao.backends.exceptions import OpenBaoConflict
    from netbox_openbao.models import Credential, CredentialAssignment
    from netbox_proxbox.models import NodeSSHCredential
    from netbox_proxbox.models.ssh_credential import AUTH_METHOD_PASSWORD

    actor, _policy, backend = openbao_node_estate
    owner = _owner(
        _node(device=_device("provider-failure-device"), name="provider-failure-node"),
        actor,
        AUTH_METHOD_PASSWORD,
    )
    owner.set_password("must-not-persist", key="unused", user=actor)
    backend.fail_on_write = True

    with pytest.raises(OpenBaoConflict):
        owner.save()

    assert not NodeSSHCredential.objects.filter(node=owner.node).exists()
    assert Credential.objects.count() == 0
    assert CredentialAssignment.objects.count() == 0
    assert backend.store == {}


@pytest.mark.parametrize("stale_reference", [False, True])
def test_selected_openbao_missing_or_stale_reference_never_falls_back_to_fernet(
    openbao_node_estate,
    stale_reference: bool,
) -> None:
    from django.core.exceptions import ValidationError
    from netbox_proxbox.models import NodeSSHCredential, ProxboxPluginSettings
    from netbox_proxbox.models.ssh_credential import AUTH_METHOD_PASSWORD
    from netbox_proxbox.utils import encryption as enc_helpers

    _actor, _policy, backend = openbao_node_estate
    key = Fernet.generate_key().decode()
    marker = "legacy-fernet-must-not-return"
    plugin_settings = ProxboxPluginSettings.get_solo()
    plugin_settings.encryption_key = key
    plugin_settings.save(update_fields=["encryption_key"])
    owner = NodeSSHCredential.objects.create(
        node=_node(name=f"missing-reference-{stale_reference}"),
        username="proxbox-discovery",
        auth_method=AUTH_METHOD_PASSWORD,
        known_host_fingerprint=FINGERPRINT,
        password_enc=enc_helpers.encrypt(marker, key=key),
    )
    if stale_reference:
        from tests.django_support import raw_update_fields

        raw_update_fields(
            NodeSSHCredential,
            owner.pk,
            openbao_password_credential_uuid=uuid4(),
        )
        owner.refresh_from_db()

    with pytest.raises(ValidationError, match="cannot resolve OpenBao") as error:
        owner.get_password(key=key)

    assert marker not in str(error.value)
    assert backend.store == {}


def test_owner_deletion_removes_only_its_device_assignment(
    openbao_node_estate,
) -> None:
    from netbox_openbao.models import Credential, CredentialAssignment
    from netbox_proxbox.models import NodeSSHCredential
    from netbox_proxbox.models.ssh_credential import AUTH_METHOD_PASSWORD

    actor, policy, backend = openbao_node_estate
    owner = _owner(
        _node(device=_device("owner-delete-device"), name="owner-delete-node"),
        actor,
        AUTH_METHOD_PASSWORD,
    )
    owner.set_password("retained-provider-material", key="unused", user=actor)
    owner.save()
    credential = Credential.objects.get(uuid=owner.openbao_password_credential_uuid)
    credential_path = credential.path
    owner_pk = owner.pk
    owner.delete()

    assert not NodeSSHCredential.objects.filter(pk=owner_pk).exists()
    assert not CredentialAssignment.objects.filter(credential=credential).exists()
    assert Credential.objects.filter(pk=credential.pk).exists()
    assert backend(policy.engine).read(credential_path) == {
        "password": "retained-provider-material"
    }


def _observe_provider_entry(monkeypatch):
    from django.db import connection
    from netbox_openbao import material_transactions
    from netbox_openbao.backends.exceptions import OpenBaoError

    entered_inside_atomic = []
    original = material_transactions.material_transaction

    @contextmanager
    def observed():
        try:
            material_transactions.current_material_transaction()
        except OpenBaoError:
            entered_inside_atomic.append(connection.in_atomic_block)
        with original() as transaction_context:
            yield transaction_context

    monkeypatch.setattr(material_transactions, "material_transaction", observed)
    return entered_inside_atomic


def _observe_actor(monkeypatch):
    from netbox_proxbox.integrations import openbao_assignments

    actors = []
    original = openbao_assignments.fresh_material_actor

    def observed(user=None):
        actors.append(user)
        return original(user)

    monkeypatch.setattr(openbao_assignments, "fresh_material_actor", observed)
    return actors


def _credential_form_payload(node, password: str) -> dict[str, object]:
    return {
        "node": node.pk,
        "username": "proxbox-discovery",
        "port": 22,
        "auth_method": "password",
        "known_host_fingerprint": FINGERPRINT,
        "sudo_required": True,
        "password": password,
        "private_key": "",
    }


def test_authenticated_ui_create_starts_provider_before_netbox_atomic(
    openbao_node_estate,
    monkeypatch,
) -> None:
    from django.test import Client
    from django.urls import reverse
    from netbox_proxbox.models import NodeSSHCredential

    actor, _policy, _backend = openbao_node_estate
    node = _node(device=_device("ui-boundary-device"), name="ui-boundary-node")
    entered_inside_atomic = _observe_provider_entry(monkeypatch)
    client = Client()
    client.force_login(actor)

    response = client.post(
        reverse("plugins:netbox_proxbox:nodesshcredential_add"),
        _credential_form_payload(node, "ui-boundary-password"),
    )

    assert response.status_code == 302
    assert NodeSSHCredential.objects.filter(node=node).exists()
    assert entered_inside_atomic == [False]


def test_authenticated_api_create_starts_provider_before_netbox_atomic(
    openbao_node_estate,
    monkeypatch,
) -> None:
    from django.test import Client
    from django.urls import reverse
    from netbox_proxbox.models import NodeSSHCredential

    actor, _policy, _backend = openbao_node_estate
    node = _node(device=_device("api-boundary-device"), name="api-boundary-node")
    entered_inside_atomic = _observe_provider_entry(monkeypatch)
    client = Client()
    client.force_login(actor)

    response = client.post(
        reverse("plugins-api:netbox_proxbox-api:nodesshcredential-list"),
        _credential_form_payload(node, "api-boundary-password"),
        content_type="application/json",
    )

    assert response.status_code == 201, response.content
    assert NodeSSHCredential.objects.filter(node=node).exists()
    assert entered_inside_atomic == [False]


def test_authenticated_ui_edit_delete_and_bulk_use_request_boundary(
    openbao_node_estate,
    monkeypatch,
) -> None:
    from django.test import Client
    from django.urls import reverse
    from netbox_proxbox.models.ssh_credential import AUTH_METHOD_PASSWORD

    actor, _policy, _backend = openbao_node_estate
    owners = []
    for index in range(4):
        owner = _owner(
            _node(
                device=_device(f"ui-mutation-device-{index}"),
                name=f"ui-mutation-node-{index}",
            ),
            actor,
            AUTH_METHOD_PASSWORD,
        )
        owner.set_password(f"ui-initial-{index}", key="unused", user=actor)
        owner.save()
        owners.append(owner)
    entered_inside_atomic = _observe_provider_entry(monkeypatch)
    observed_actors = _observe_actor(monkeypatch)
    client = Client()
    client.force_login(actor)

    edit = client.post(
        reverse(
            "plugins:netbox_proxbox:nodesshcredential_edit",
            args=[owners[0].pk],
        ),
        _credential_form_payload(owners[0].node, "ui-rotated-password"),
    )
    deleted = client.post(
        reverse(
            "plugins:netbox_proxbox:nodesshcredential_delete",
            args=[owners[1].pk],
        ),
        {"confirm": "on"},
    )
    bulk_deleted = client.post(
        reverse("plugins:netbox_proxbox:nodesshcredential_bulk_delete"),
        {
            "pk": [str(owners[2].pk), str(owners[3].pk)],
            "confirm": "on",
            "_confirm": "on",
        },
    )

    assert edit.status_code == 302
    assert deleted.status_code == 302
    assert bulk_deleted.status_code == 302
    assert entered_inside_atomic == [False, False, False]
    assert observed_actors
    assert {user.pk for user in observed_actors} == {actor.pk}


def test_authenticated_rest_update_link_delete_and_bulk_use_request_boundary(
    openbao_node_estate,
    monkeypatch,
) -> None:
    from django.test import Client
    from django.urls import reverse
    from netbox_proxbox.models.ssh_credential import AUTH_METHOD_PASSWORD

    actor, _policy, _backend = openbao_node_estate
    owners = []
    for index in range(5):
        owner = _owner(
            _node(
                device=_device(f"api-mutation-device-{index}"),
                name=f"api-mutation-node-{index}",
            ),
            actor,
            AUTH_METHOD_PASSWORD,
        )
        owner.set_password(f"api-initial-{index}", key="unused", user=actor)
        owner.save()
        owners.append(owner)
    entered_inside_atomic = _observe_provider_entry(monkeypatch)
    observed_actors = _observe_actor(monkeypatch)
    client = Client()
    client.force_login(actor)
    credential_list = reverse("plugins-api:netbox_proxbox-api:nodesshcredential-list")

    updated = client.patch(
        reverse(
            "plugins-api:netbox_proxbox-api:nodesshcredential-detail",
            args=[owners[0].pk],
        ),
        {"password": "api-rotated-password"},
        content_type="application/json",
    )
    linked_device = _device("api-linked-device")
    linked = client.patch(
        reverse(
            "plugins-api:netbox_proxbox-api:proxmoxnode-detail",
            args=[owners[0].node_id],
        ),
        {"netbox_device": {"id": linked_device.pk}},
        content_type="application/json",
    )
    deleted = client.delete(
        reverse(
            "plugins-api:netbox_proxbox-api:nodesshcredential-detail",
            args=[owners[1].pk],
        )
    )
    bulk_updated = client.patch(
        credential_list,
        [
            {"id": owners[2].pk, "password": "api-bulk-rotated-2"},
            {"id": owners[3].pk, "password": "api-bulk-rotated-3"},
        ],
        content_type="application/json",
    )
    bulk_deleted = client.delete(
        credential_list,
        [{"id": owners[2].pk}, {"id": owners[3].pk}, {"id": owners[4].pk}],
        content_type="application/json",
    )

    assert updated.status_code == 200, updated.content
    assert linked.status_code == 200, linked.content
    assert deleted.status_code == 204, deleted.content
    assert bulk_updated.status_code == 200, bulk_updated.content
    assert bulk_deleted.status_code == 204, bulk_deleted.content
    assert entered_inside_atomic == [False, False, False, False, False]
    assert observed_actors
    assert {user.pk for user in observed_actors} == {actor.pk}


def test_shared_credential_assignment_on_unrelated_device_is_preserved(
    openbao_node_estate,
) -> None:
    from django.contrib.contenttypes.models import ContentType
    from dcim.models import Device
    from netbox_openbao.models import Credential, CredentialAssignment
    from netbox_proxbox.models.ssh_credential import AUTH_METHOD_PASSWORD

    actor, _policy, _backend = openbao_node_estate
    old_device = _device("shared-old-device")
    new_device = _device("shared-new-device")
    unrelated_device = _device("shared-unrelated-device")
    node = _node(device=old_device, name="shared-assignment-node")
    owner = _owner(node, actor, AUTH_METHOD_PASSWORD)
    owner.set_password("shared-assignment-password", key="unused", user=actor)
    owner.save()
    credential = Credential.objects.get(uuid=owner.openbao_password_credential_uuid)
    unrelated = CredentialAssignment.objects.create(
        credential=credential,
        assigned_object_type=ContentType.objects.get_for_model(Device),
        assigned_object_id=unrelated_device.pk,
        purpose="login",
        is_primary=True,
    )

    node.netbox_device = new_device
    node._openbao_actor_user = actor
    node.save(update_fields=["netbox_device"])

    unrelated.refresh_from_db()
    assert unrelated.assigned_object_id == unrelated_device.pk
    targets = set(
        CredentialAssignment.objects.filter(credential=credential).values_list(
            "assigned_object_id", flat=True
        )
    )
    assert targets == {new_device.pk, unrelated_device.pk}


def _share_selected_password(owner, node, actor):
    """Seed an existing shared reference without invoking the guarded mutation API."""
    from netbox_proxbox.models import NodeSSHCredential
    from netbox_proxbox.models.ssh_credential import AUTH_METHOD_PASSWORD

    shared = NodeSSHCredential(
        node=node,
        username="proxbox-shared",
        auth_method=AUTH_METHOD_PASSWORD,
        known_host_fingerprint=FINGERPRINT,
        openbao_password_credential_uuid=owner.openbao_password_credential_uuid,
    )
    shared._openbao_actor_user = actor
    NodeSSHCredential.save.__wrapped__(shared)
    return shared


@pytest.mark.parametrize("operation", ["save", "relink", "unlink", "delete"])
def test_same_device_shared_selected_assignment_survives_owner_lifecycle(
    openbao_node_estate,
    operation: str,
) -> None:
    from netbox_openbao.models import Credential, CredentialAssignment
    from netbox_proxbox.models.ssh_credential import AUTH_METHOD_PASSWORD

    actor, _policy, _backend = openbao_node_estate
    shared_device = _device(f"same-device-{operation}")
    first_node = _node(device=shared_device, name=f"first-shared-{operation}")
    owner = _owner(first_node, actor, AUTH_METHOD_PASSWORD)
    owner.set_password("shared-password", key="unused", user=actor)
    owner.save()
    credential = Credential.objects.get(uuid=owner.openbao_password_credential_uuid)
    survivor = _share_selected_password(
        owner,
        _node(device=shared_device, name=f"survivor-shared-{operation}"),
        actor,
    )

    if operation == "save":
        owner.username = "updated-owner"
        owner.save(update_fields=["username"])
    elif operation == "relink":
        first_node.netbox_device = _device("relinked-owner-device")
        first_node._openbao_actor_user = actor
        first_node.save(update_fields=["netbox_device"])
    elif operation == "unlink":
        first_node.netbox_device = None
        first_node._openbao_actor_user = actor
        first_node.save(update_fields=["netbox_device"])
    else:
        owner.delete()

    survivor.refresh_from_db()
    assert survivor.openbao_password_credential_uuid == credential.uuid
    targets = set(
        CredentialAssignment.objects.filter(credential=credential).values_list(
            "assigned_object_id", flat=True
        )
    )
    expected = {shared_device.pk}
    if operation == "relink":
        expected.add(first_node.netbox_device_id)
    assert targets == expected


def test_shared_selected_credential_on_different_devices_keeps_isolated_cleanup(
    openbao_node_estate,
) -> None:
    from netbox_openbao.models import Credential, CredentialAssignment
    from netbox_proxbox.models.ssh_credential import AUTH_METHOD_PASSWORD

    actor, _policy, _backend = openbao_node_estate
    first_device = _device("different-device-first")
    second_device = _device("different-device-second")
    owner = _owner(
        _node(device=first_device, name="different-device-owner"),
        actor,
        AUTH_METHOD_PASSWORD,
    )
    owner.set_password("shared-different-device", key="unused", user=actor)
    owner.save()
    credential = Credential.objects.get(uuid=owner.openbao_password_credential_uuid)
    survivor = _share_selected_password(
        owner,
        _node(device=second_device, name="different-device-survivor"),
        actor,
    )
    CredentialAssignment.objects.create(
        credential=credential,
        assigned_object_type=CredentialAssignment.objects.get(
            credential=credential,
            assigned_object_id=first_device.pk,
        ).assigned_object_type,
        assigned_object_id=second_device.pk,
        purpose="login",
        is_primary=True,
    )

    owner.delete()

    survivor.refresh_from_db()
    assert set(
        CredentialAssignment.objects.filter(credential=credential).values_list(
            "assigned_object_id", flat=True
        )
    ) == {second_device.pk}


def test_assignment_readiness_and_ansible_lookup_are_secret_free(
    openbao_node_estate,
) -> None:
    from django.http import QueryDict
    from netbox_openbao.filtersets import CredentialFilterSet
    from netbox_openbao.models import Credential
    from netbox_proxbox.integrations.openbao import (
        node_openbao_assignment_lookup,
        node_openbao_assignment_readiness,
    )
    from netbox_proxbox.models.ssh_credential import AUTH_METHOD_PASSWORD

    actor, _policy, _backend = openbao_node_estate
    device = _device("ansible-lookup-device")
    owner = _owner(
        _node(device=device, name="ansible-lookup-node"), actor, AUTH_METHOD_PASSWORD
    )
    owner.set_password("never-return-this-material", key="unused", user=actor)
    owner.save()

    lookup = node_openbao_assignment_lookup(owner)
    assert lookup == {
        "assigned_object_type": "dcim.device",
        "assigned_object_id": str(device.pk),
        "purpose": "login",
    }
    assert node_openbao_assignment_readiness(owner)[0] is True
    filters = QueryDict(mutable=True)
    for name, value in lookup.items():
        filters[name] = value
    matches = CredentialFilterSet(
        filters, queryset=Credential.objects.all()
    ).qs.values_list("uuid", flat=True)
    assert list(matches) == [owner.openbao_password_credential_uuid]
    assert "never-return-this-material" not in repr(lookup)


@pytest.mark.parametrize("operation", ["update", "bulk_update", "delete", "raw_delete"])
def test_raw_owner_writes_refuse_openbao_state(
    openbao_node_estate,
    operation: str,
) -> None:
    from django.core.exceptions import ValidationError
    from netbox_proxbox.models.ssh_credential import AUTH_METHOD_PASSWORD

    actor, _policy, _backend = openbao_node_estate
    owner = _owner(_node(name=f"raw-{operation}-node"), actor, AUTH_METHOD_PASSWORD)
    owner.set_password("raw-guard-password", key="unused", user=actor)
    owner.save()
    queryset = type(owner).objects.filter(pk=owner.pk)

    with pytest.raises(ValidationError, match="cleanup path"):
        if operation == "update":
            queryset.update(username="bypass")
        elif operation == "bulk_update":
            owner.username = "bypass"
            type(owner).objects.bulk_update([owner], ["username"])
        elif operation == "delete":
            queryset.delete()
        else:
            queryset._raw_delete("default")


@pytest.mark.parametrize("parent", ["device", "node", "endpoint"])
def test_parent_deletion_refuses_implicit_openbao_cleanup(
    openbao_node_estate,
    parent: str,
) -> None:
    from django.core.exceptions import ValidationError
    from netbox_proxbox.models.ssh_credential import AUTH_METHOD_PASSWORD

    actor, _policy, _backend = openbao_node_estate
    device = _device(f"parent-{parent}-device")
    node = _node(device=device, name=f"parent-{parent}-node")
    owner = _owner(node, actor, AUTH_METHOD_PASSWORD)
    owner.set_password("parent-guard-password", key="unused", user=actor)
    owner.save()
    target = {"device": device, "node": node, "endpoint": node.endpoint}[parent]

    with pytest.raises(ValidationError, match="cleanup path"):
        target.delete()

    assert type(owner).objects.filter(pk=owner.pk).exists()


def test_openbao_to_legacy_switch_refuses_remaining_node_state(
    openbao_node_estate,
) -> None:
    from django.core.exceptions import ValidationError
    from netbox_proxbox.models.ssh_credential import AUTH_METHOD_PASSWORD

    actor, _policy, _backend = openbao_node_estate
    owner = _owner(_node(name="downgrade-guard-node"), actor, AUTH_METHOD_PASSWORD)
    owner.set_password("downgrade-guard-password", key="unused", user=actor)
    owner.save()
    endpoint = owner.node.endpoint
    endpoint.credential_storage_backend = "legacy_encrypted"

    with pytest.raises(ValidationError, match="cleanup path"):
        endpoint.save(update_fields=["credential_storage_backend"])

    with pytest.raises(ValidationError, match="cleanup path"):
        type(endpoint).objects.filter(pk=endpoint.pk).update(
            credential_storage_backend="legacy_encrypted"
        )

    endpoint.credential_storage_backend = "legacy_encrypted"
    with pytest.raises(ValidationError, match="cleanup path"):
        type(endpoint).objects.bulk_update([endpoint], ["credential_storage_backend"])


@pytest.mark.parametrize("operation", ["update", "bulk_update"])
def test_raw_node_link_writes_refuse_openbao_state(
    openbao_node_estate,
    operation: str,
) -> None:
    from django.core.exceptions import ValidationError
    from netbox_proxbox.models.ssh_credential import AUTH_METHOD_PASSWORD

    actor, _policy, _backend = openbao_node_estate
    node = _node(device=_device("raw-link-original"), name=f"raw-link-{operation}")
    owner = _owner(node, actor, AUTH_METHOD_PASSWORD)
    owner.set_password("raw-link-password", key="unused", user=actor)
    owner.save()
    replacement = _device("raw-link-replacement")

    with pytest.raises(ValidationError, match="cleanup path"):
        if operation == "update":
            type(node).objects.filter(pk=node.pk).update(netbox_device=replacement)
        else:
            node.netbox_device = replacement
            type(node).objects.bulk_update([node], ["netbox_device"])


def test_global_openbao_downgrade_refuses_inherited_node_state(
    openbao_node_estate,
) -> None:
    from django.core.exceptions import ValidationError
    from netbox_proxbox.models import (
        ProxmoxEndpoint,
        ProxmoxNode,
        ProxboxPluginSettings,
    )
    from netbox_proxbox.models.ssh_credential import AUTH_METHOD_PASSWORD

    actor, _policy, _backend = openbao_node_estate
    endpoint = ProxmoxEndpoint.objects.create(
        name="inherited-openbao-endpoint",
        enabled=False,
        credential_storage_backend="",
    )
    node = ProxmoxNode.objects.create(
        endpoint=endpoint,
        name="inherited-openbao-node",
        ip_address="127.0.0.1",
    )
    owner = _owner(node, actor, AUTH_METHOD_PASSWORD)
    owner.set_password("inherited-openbao-password", key="unused", user=actor)
    owner.save()
    settings = ProxboxPluginSettings.get_solo()
    settings.credential_storage_backend = "legacy_encrypted"

    with pytest.raises(ValidationError, match="cleanup path"):
        settings.save(update_fields=["credential_storage_backend"])
    with pytest.raises(ValidationError, match="cleanup path"):
        ProxboxPluginSettings.objects.filter(pk=settings.pk).update(
            credential_storage_backend="legacy_encrypted"
        )


def test_provider_removal_error_requires_explicit_secret_safe_cleanup(
    openbao_node_estate,
    monkeypatch,
) -> None:
    import builtins

    from django.core.exceptions import ValidationError
    from netbox_proxbox.integrations.openbao_node_writer import (
        _has_owned_assignments,
    )
    from netbox_proxbox.models.ssh_credential import AUTH_METHOD_PASSWORD

    actor, _policy, _backend = openbao_node_estate
    owner = _owner(_node(name="provider-removal-node"), actor, AUTH_METHOD_PASSWORD)
    owner.set_password("provider-removal-password", key="unused", user=actor)
    owner.save()
    original_import = builtins.__import__

    def missing_provider(name, *args, **kwargs):
        if name == "netbox_openbao.models":
            raise ImportError("simulated removed provider")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing_provider)
    with pytest.raises(ValidationError, match="Restore the provider") as error:
        _has_owned_assignments(owner)

    assert "provider-removal-password" not in str(error.value)


def test_node_relation_name_in_update_fields_reconciles_assignment(
    openbao_node_estate,
) -> None:
    from netbox_openbao.models import CredentialAssignment
    from netbox_proxbox.models.ssh_credential import AUTH_METHOD_PASSWORD

    actor, _policy, _backend = openbao_node_estate
    first = _node(device=_device("relation-first-device"), name="relation-first")
    second = _node(device=_device("relation-second-device"), name="relation-second")
    owner = _owner(first, actor, AUTH_METHOD_PASSWORD)
    owner.set_password("relation-selector-password", key="unused", user=actor)
    owner.save()

    owner.node = second
    owner._openbao_actor_user = actor
    owner.save(update_fields=["node"])

    assignment = CredentialAssignment.objects.get(
        credential__uuid=owner.openbao_password_credential_uuid
    )
    assert assignment.assigned_object_id == second.netbox_device_id


def test_bulk_create_refuses_injected_openbao_reference(
    openbao_node_estate,
) -> None:
    from django.core.exceptions import ValidationError
    from netbox_proxbox.models import NodeSSHCredential
    from netbox_proxbox.models.ssh_credential import AUTH_METHOD_PASSWORD

    actor, _policy, _backend = openbao_node_estate
    owner = _owner(_node(name="bulk-create-guard-node"), actor, AUTH_METHOD_PASSWORD)
    owner.openbao_password_credential_uuid = uuid4()

    with pytest.raises(ValidationError, match="cleanup path"):
        NodeSSHCredential.objects.bulk_create([owner])


def test_hardware_consumer_api_resolves_fake_material_with_real_token(
    openbao_node_estate,
    monkeypatch,
) -> None:
    from django.test import Client
    from django.urls import reverse
    from users.models import Token

    from netbox_proxbox.models.ssh_credential import AUTH_METHOD_PASSWORD

    actor, _policy, _backend = openbao_node_estate
    node = _node(device=_device("hardware-api-device"), name="hardware-api-node")
    node.endpoint.access_methods = "api_ssh"
    node.endpoint.save(update_fields=["access_methods"])
    owner = _owner(
        node,
        actor,
        AUTH_METHOD_PASSWORD,
    )
    owner.set_password("stored-fake-material", key="unused", user=actor)
    owner.save()
    fake_material = "api-only-fake-material"
    monkeypatch.setattr(
        "netbox_proxbox.integrations.openbao.reveal_credential_material",
        lambda *_args, **_kwargs: {"password": fake_material},
    )
    token = Token.objects.create(version=1, user=actor)
    client = Client()

    response = client.get(
        reverse(
            "plugins-api:netbox_proxbox-api:api-ssh-credential-secrets",
            args=[owner.node_id],
        ),
        HTTP_AUTHORIZATION=f"Token {token.token}",
        secure=True,
    )

    assert response.status_code == 200, response.content
    assert response.json()["password"] == fake_material
    assert "stored-fake-material" not in response.content.decode()


def test_unexpected_material_failure_redacts_every_plaintext_frame(
    openbao_node_estate,
    monkeypatch,
) -> None:
    from django.test import RequestFactory
    from django.views.debug import ExceptionReporter
    from netbox_openbao import services
    from netbox_proxbox.integrations.openbao_node_request import (
        node_credential_request_boundary,
    )
    from netbox_proxbox.models.ssh_credential import AUTH_METHOD_PASSWORD

    actor, _policy, _backend = openbao_node_estate
    secret = "traceback-must-never-contain-this-password"
    node = _node(device=_device("traceback-device"), name="traceback-node")
    request = RequestFactory().post(
        "/plugins/proxbox/ssh-credentials/add/",
        {
            "node": node.pk,
            "password": secret,
        },
    )
    request.user = actor

    def fail_store(*_args, **_kwargs):
        raise RuntimeError("simulated post-input provider failure")

    monkeypatch.setattr(services, "store_credential", fail_store)
    owner = _owner(node, actor, AUTH_METHOD_PASSWORD)
    try:
        with node_credential_request_boundary(
            [], [request.POST], actor=actor, request=request, allow_new=True
        ):
            owner.set_password(secret, key="unused", user=actor, request=request)
            owner.save()
    except RuntimeError as exc:
        report = ExceptionReporter(
            request, type(exc), exc, exc.__traceback__
        ).get_traceback_text()
    else:  # pragma: no cover - the injected failure must escape
        raise AssertionError("The injected provider failure did not escape.")

    assert secret not in report


def test_node_reference_migration_state_and_round_trip(
    pytestconfig,
    transactional_db,
) -> None:
    _require_harness(pytestconfig)
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    before = ("netbox_proxbox", "0099_proxboxpluginsettings_openbao_policy_slug")
    after = ("netbox_proxbox", "0100_nodesshcredential_openbao_references")
    password_uuid = uuid4()
    keypair_uuid = uuid4()
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate([before])
        old_apps = executor.loader.project_state([before]).apps
        OldEndpoint = old_apps.get_model("netbox_proxbox", "ProxmoxEndpoint")
        OldNode = old_apps.get_model("netbox_proxbox", "ProxmoxNode")
        OldOwner = old_apps.get_model("netbox_proxbox", "NodeSSHCredential")
        assert "openbao_password_credential_uuid" not in {
            field.name for field in OldOwner._meta.get_fields()
        }
        endpoint = OldEndpoint.objects.create(name="migration-node-endpoint")
        node = OldNode.objects.create(
            endpoint_id=endpoint.pk,
            name="migration-node",
            ip_address="127.0.0.1",
        )
        owner = OldOwner.objects.create(
            node_id=node.pk,
            username="migration-user",
            known_host_fingerprint=FINGERPRINT,
        )

        executor = MigrationExecutor(connection)
        executor.migrate([after])
        NewOwner = executor.loader.project_state([after]).apps.get_model(
            "netbox_proxbox", "NodeSSHCredential"
        )
        migrated = NewOwner.objects.get(pk=owner.pk)
        assert migrated.openbao_password_credential_uuid is None
        assert migrated.openbao_keypair_credential_uuid is None
        NewOwner.objects.filter(pk=owner.pk).update(
            openbao_password_credential_uuid=password_uuid,
            openbao_keypair_credential_uuid=keypair_uuid,
        )

        executor = MigrationExecutor(connection)
        executor.migrate([before])
        ReversedOwner = executor.loader.project_state([before]).apps.get_model(
            "netbox_proxbox", "NodeSSHCredential"
        )
        assert not {
            "openbao_password_credential_uuid",
            "openbao_keypair_credential_uuid",
        }.intersection(field.name for field in ReversedOwner._meta.get_fields())

        executor = MigrationExecutor(connection)
        executor.migrate([after])
        RoundTripOwner = executor.loader.project_state([after]).apps.get_model(
            "netbox_proxbox", "NodeSSHCredential"
        )
        round_trip = RoundTripOwner.objects.get(pk=owner.pk)
        assert round_trip.openbao_password_credential_uuid == password_uuid
        assert round_trip.openbao_keypair_credential_uuid == keypair_uuid
    finally:
        MigrationExecutor(connection).migrate(latest)
