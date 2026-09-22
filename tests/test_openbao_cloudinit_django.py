"""Exact-provider behavior for VM cloud-init OpenBao login credentials."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from typing import Any
from uuid import uuid4

import pytest

from tests.test_openbao_single_secret_django import (
    _observe_provider_entry,
    openbao_single_estate as openbao_single_estate_fixture,
)
from tests.test_proxmox_endpoint_allowed_tenants import _require_harness


pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(
        os.environ.get("NETBOX_PROXBOX_TEST_OPENBAO") != "1",
        reason="requires the exact-source netbox-openbao companion cell",
    ),
]


@pytest.fixture
def cloudinit_owner(
    pytestconfig,
    transactional_db,
    openbao_single_estate_fixture,  # noqa: F811 - pytest fixture injection
):
    _require_harness(pytestconfig)
    from netbox_proxbox.models import ProxmoxVMCloudInit
    from utilities.testing import create_test_virtualmachine

    actor, policy, backend = openbao_single_estate_fixture
    vm = create_test_virtualmachine("cloudinit-openbao-vm")
    owner = ProxmoxVMCloudInit(virtual_machine=vm, is_intent=True)
    owner._openbao_actor_user = actor
    return owner, actor, policy, backend


def _private_key() -> str:
    from netbox_openbao.secrets.generators import generate_ssh_keypair

    return str(generate_ssh_keypair("ed25519")["private_key"])


def _login_assignments(owner: Any) -> Any:
    from netbox_openbao.models import CredentialAssignment

    return CredentialAssignment.objects.filter(
        assigned_object_type__app_label="virtualization",
        assigned_object_type__model="virtualmachine",
        assigned_object_id=owner.virtual_machine_id,
        purpose="login",
    )


def _assert_credential_metadata(password: Any, keypair: Any, policy: Any) -> None:
    assert password.credential_type == "password"
    assert keypair.credential_type == "ssh-keypair"
    assert password.policy_id == policy.pk
    assert keypair.policy_id == policy.pk


def _assert_assignment_shape(assignments: Any, password: Any, keypair: Any) -> None:
    assert assignments.count() == 2
    assert assignments.get(credential=password).is_primary is True
    assert assignments.get(credential=keypair).is_primary is False


def _assert_material_round_trip(
    owner: Any,
    actor: Any,
    policy: Any,
    backend: Any,
    private_key: str,
    password: Any,
    keypair: Any,
) -> None:
    assert owner.get_password(user=actor) == "cloudinit-password"
    assert owner.get_private_key(user=actor) == private_key
    assert backend(policy.engine).read(password.path) == {
        "password": "cloudinit-password"
    }
    assert backend(policy.engine).read(keypair.path)["private_key"] == private_key


def _assert_assignment_metadata(owner: Any) -> None:
    from netbox_proxbox.integrations.openbao_cloudinit import (
        cloudinit_assignment_lookup,
        cloudinit_assignment_readiness,
    )

    assert cloudinit_assignment_readiness(owner)[0] is True
    assert cloudinit_assignment_lookup(owner) == {
        "assigned_object_type": "virtualization.virtualmachine",
        "assigned_object_id": str(owner.virtual_machine_id),
        "purpose": "login",
    }


def test_create_resolve_assign_and_select_password_primary(cloudinit_owner) -> None:
    from netbox_openbao.models import Credential

    owner, actor, policy, backend = cloudinit_owner
    private_key = _private_key()
    owner.ssh_pwauth = True
    owner.set_password("cloudinit-password", user=actor)
    owner.set_private_key(private_key, user=actor)
    owner.save()
    owner.refresh_from_db()

    password = Credential.objects.get(uuid=owner.openbao_password_credential_uuid)
    keypair = Credential.objects.get(uuid=owner.openbao_keypair_credential_uuid)
    assignments = _login_assignments(owner)

    _assert_credential_metadata(password, keypair, policy)
    _assert_assignment_shape(assignments, password, keypair)
    _assert_material_round_trip(
        owner, actor, policy, backend, private_key, password, keypair
    )
    _assert_assignment_metadata(owner)


def test_ssh_pwauth_false_selects_keypair_primary(cloudinit_owner) -> None:
    from netbox_openbao.models import CredentialAssignment

    owner, actor, _policy, _backend = cloudinit_owner
    owner.ssh_pwauth = False
    owner.set_password("secondary-password", user=actor)
    owner.set_private_key(_private_key(), user=actor)
    owner.save()

    primary = CredentialAssignment.objects.get(
        assigned_object_id=owner.virtual_machine_id,
        purpose="login",
        is_primary=True,
    )
    assert str(primary.credential.uuid) == str(owner.openbao_keypair_credential_uuid)


def test_rotation_uses_cas_and_keeps_uuid(cloudinit_owner) -> None:
    from netbox_openbao.models import Credential

    owner, actor, _policy, _backend = cloudinit_owner
    owner.set_password("first-password", user=actor)
    owner.save()
    original_uuid = owner.openbao_password_credential_uuid

    owner.set_password("second-password", user=actor)
    owner.save()
    owner.refresh_from_db()
    credential = Credential.objects.get(uuid=original_uuid)

    assert owner.openbao_password_credential_uuid == original_uuid
    assert credential.kv_version == 2
    assert owner.get_password(user=actor) == "second-password"


def test_concurrent_rotations_serialize_provider_versions(cloudinit_owner) -> None:
    from django.db import close_old_connections
    from netbox_openbao.models import Credential
    from netbox_proxbox.models import ProxmoxVMCloudInit

    owner, actor, _policy, backend = cloudinit_owner
    owner.set_password("version-one", user=actor)
    owner.save()
    credential_uuid = owner.openbao_password_credential_uuid
    ready = Barrier(2)

    def rotate(value: str) -> None:
        close_old_connections()
        try:
            worker = ProxmoxVMCloudInit.objects.get(pk=owner.pk)
            worker_actor = type(actor).objects.get(pk=actor.pk)
            worker.set_password(value, user=worker_actor)
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


def test_concurrent_clear_rejects_stale_rotation_without_resurrection(
    cloudinit_owner,
) -> None:
    from django.core.exceptions import ValidationError
    from django.db import close_old_connections
    from netbox_openbao.models import Credential, CredentialAssignment
    from netbox_proxbox.models import ProxmoxVMCloudInit

    owner, actor, _policy, backend = cloudinit_owner
    owner.set_password("clear-wins-version", user=actor)
    owner.save()
    credential = Credential.objects.get(uuid=owner.openbao_password_credential_uuid)
    ready = Barrier(2)
    cleared = Event()

    def clear_password() -> None:
        close_old_connections()
        try:
            worker = ProxmoxVMCloudInit.objects.get(pk=owner.pk)
            worker_actor = type(actor).objects.get(pk=actor.pk)
            worker.set_password("", user=worker_actor)
            ready.wait(timeout=10)
            worker.save()
            cleared.set()
        finally:
            close_old_connections()

    def rotate_stale_password() -> str:
        close_old_connections()
        try:
            worker = ProxmoxVMCloudInit.objects.get(pk=owner.pk)
            worker_actor = type(actor).objects.get(pk=actor.pk)
            worker.set_password("must-not-resurrect", user=worker_actor)
            ready.wait(timeout=10)
            if not cleared.wait(timeout=10):
                raise AssertionError("The clearing transaction did not finish.")
            try:
                worker.save()
            except ValidationError as exc:
                return str(exc)
            raise AssertionError("A stale rotation unexpectedly succeeded.")
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        clear_future = pool.submit(clear_password)
        rotate_future = pool.submit(rotate_stale_password)
        clear_future.result(timeout=30)
        error = rotate_future.result(timeout=30)

    owner.refresh_from_db()
    assert "changed before ownership" in error
    assert owner.openbao_password_credential_uuid is None
    assert not CredentialAssignment.objects.filter(
        credential=credential,
        assigned_object_id=owner.virtual_machine_id,
        purpose="login",
    ).exists()
    assert backend.store[credential.path] == [{"password": "clear-wins-version"}]


def test_concurrent_primary_change_rejects_stale_owner_snapshot(
    cloudinit_owner,
) -> None:
    from django.core.exceptions import ValidationError
    from django.db import close_old_connections
    from netbox_openbao.models import CredentialAssignment
    from netbox_proxbox.integrations.openbao_cloudinit import (
        cloudinit_mutation_boundary,
    )
    from netbox_proxbox.models import ProxmoxVMCloudInit

    owner, actor, _policy, backend = cloudinit_owner
    owner.ssh_pwauth = True
    owner.set_password("primary-cas-password", user=actor)
    owner.set_private_key(_private_key(), user=actor)
    owner.save()
    password_uuid = owner.openbao_password_credential_uuid
    keypair_uuid = owner.openbao_keypair_credential_uuid
    before_store = {path: list(versions) for path, versions in backend.store.items()}
    stale_loaded = Event()
    selection_committed = Event()

    def save_stale_owner() -> str:
        close_old_connections()
        try:
            worker = ProxmoxVMCloudInit.objects.get(pk=owner.pk)
            stale_loaded.set()
            if not selection_committed.wait(timeout=10):
                raise AssertionError(
                    "The primary-selection transaction did not finish."
                )
            worker.ciuser = "must-not-persist"
            try:
                worker.save()
            except ValidationError as exc:
                return str(exc)
            raise AssertionError(
                "A stale primary-selection snapshot unexpectedly saved."
            )
        finally:
            close_old_connections()

    def select_keypair_primary() -> None:
        close_old_connections()
        try:
            if not stale_loaded.wait(timeout=10):
                raise AssertionError("The stale owner was not loaded.")
            worker = ProxmoxVMCloudInit.objects.get(pk=owner.pk)
            worker_actor = type(actor).objects.get(pk=actor.pk)
            with cloudinit_mutation_boundary(
                [worker], [{"ssh_pwauth": False}], actor=worker_actor
            ):
                worker.ssh_pwauth = False
                worker.save()
        finally:
            selection_committed.set()
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        stale_future = pool.submit(save_stale_owner)
        selection_future = pool.submit(select_keypair_primary)
        selection_future.result(timeout=30)
        error = stale_future.result(timeout=30)

    owner.refresh_from_db()
    assignments = CredentialAssignment.objects.filter(
        assigned_object_id=owner.virtual_machine_id,
        purpose="login",
    )
    assert "changed before ownership" in error
    assert owner.ssh_pwauth is False
    assert owner.ciuser == ""
    assert assignments.get(credential__uuid=password_uuid).is_primary is False
    assert assignments.get(credential__uuid=keypair_uuid).is_primary is True
    assert backend.store == before_store


def test_provider_failure_rolls_back_and_retains_intent(cloudinit_owner) -> None:
    from netbox_openbao.backends.exceptions import OpenBaoConflict
    from netbox_openbao.models import Credential, CredentialAssignment
    from netbox_proxbox.models import ProxmoxVMCloudInit

    owner, actor, _policy, backend = cloudinit_owner
    owner.set_password("retry-cloudinit-password", user=actor)
    backend.fail_on_write = True

    with pytest.raises(OpenBaoConflict):
        owner.save()
    assert owner.pk is None
    assert not ProxmoxVMCloudInit.objects.filter(
        virtual_machine=owner.virtual_machine
    ).exists()
    assert Credential.objects.count() == 0
    assert CredentialAssignment.objects.count() == 0
    assert backend.store == {}

    backend.fail_on_write = False
    owner.save()
    assert owner.openbao_password_credential_uuid is not None
    assert owner.get_password(user=actor) == "retry-cloudinit-password"


def test_material_write_requires_authenticated_object_permissions(
    cloudinit_owner,
) -> None:
    from django.contrib.auth import get_user_model
    from django.core.exceptions import PermissionDenied
    from netbox_openbao.models import Credential, CredentialAssignment

    owner, _actor, _policy, _backend = cloudinit_owner
    limited = get_user_model().objects.create_user(username="cloudinit-limited")
    owner.set_password("permission-denied-password", user=limited)

    with pytest.raises(PermissionDenied, match="add permission"):
        owner.save()
    assert owner.pk is None
    assert Credential.objects.count() == 0
    assert CredentialAssignment.objects.count() == 0


def test_openbao_never_falls_back_to_external_reference(cloudinit_owner) -> None:
    from django.core.exceptions import ValidationError

    owner, actor, _policy, _backend = cloudinit_owner
    owner.credential_reference_id = 901
    owner.save()

    with pytest.raises(ValidationError, match="not configured"):
        owner.get_password(user=actor)


def test_legacy_preserves_external_reference_and_rejects_material(
    cloudinit_owner,
) -> None:
    from django.core.exceptions import ValidationError
    from netbox_proxbox.models import ProxboxPluginSettings

    owner, actor, _policy, _backend = cloudinit_owner
    settings = ProxboxPluginSettings.get_solo()
    settings.credential_storage_backend = "legacy_encrypted"
    settings.save()
    owner.credential_reference_id = 901
    owner.save()
    owner.refresh_from_db()
    assert owner.credential_reference_id == 901

    with pytest.raises(ValidationError, match="require OpenBao"):
        owner.set_password("must-not-store", user=actor)


def test_delete_removes_only_owned_assignments_and_keeps_material(
    cloudinit_owner,
) -> None:
    from netbox_openbao.models import Credential, CredentialAssignment

    owner, actor, policy, backend = cloudinit_owner
    owner.set_password("retained-password", user=actor)
    owner.save()
    credential = Credential.objects.get(uuid=owner.openbao_password_credential_uuid)
    path = credential.path
    owner.delete()

    assert not CredentialAssignment.objects.filter(credential=credential).exists()
    assert Credential.objects.filter(pk=credential.pk).exists()
    assert backend(policy.engine).read(path) == {"password": "retained-password"}


def test_delete_failure_rolls_back_and_restores_reference(cloudinit_owner) -> None:
    from django.db.models.signals import pre_delete
    from netbox_openbao.models import CredentialAssignment
    from netbox_proxbox.models import ProxmoxVMCloudInit

    owner, actor, _policy, _backend = cloudinit_owner
    owner.set_password("delete-rollback-password", user=actor)
    owner.save()
    reference = owner.openbao_password_credential_uuid
    dispatch_uid = "proxbox_cloudinit_delete_rollback_test"

    def fail_delete(sender: type, instance: Any, **_kwargs: Any) -> None:
        if sender is ProxmoxVMCloudInit and instance.pk == owner.pk:
            raise RuntimeError("simulated post-cleanup delete failure")

    pre_delete.connect(
        fail_delete,
        sender=ProxmoxVMCloudInit,
        weak=False,
        dispatch_uid=dispatch_uid,
    )
    try:
        with pytest.raises(RuntimeError, match="post-cleanup delete failure"):
            owner.delete()
    finally:
        pre_delete.disconnect(
            sender=ProxmoxVMCloudInit,
            dispatch_uid=dispatch_uid,
        )

    assert owner.openbao_password_credential_uuid == reference
    owner.refresh_from_db()
    assert owner.openbao_password_credential_uuid == reference
    assert CredentialAssignment.objects.filter(
        credential__uuid=reference,
        assigned_object_id=owner.virtual_machine_id,
        purpose="login",
    ).exists()


def test_shared_assignment_on_another_vm_survives_delete(cloudinit_owner) -> None:
    from django.contrib.contenttypes.models import ContentType
    from netbox_openbao.models import Credential, CredentialAssignment
    from utilities.testing import create_test_virtualmachine
    from virtualization.models import VirtualMachine

    owner, actor, _policy, _backend = cloudinit_owner
    owner.set_password("shared-cloudinit-password", user=actor)
    owner.save()
    credential = Credential.objects.get(uuid=owner.openbao_password_credential_uuid)
    survivor_vm = create_test_virtualmachine("cloudinit-shared-survivor")
    shared = CredentialAssignment.objects.create(
        credential=credential,
        assigned_object_type=ContentType.objects.get_for_model(VirtualMachine),
        assigned_object_id=survivor_vm.pk,
        purpose="login",
        is_primary=True,
    )

    owner.delete()

    shared.refresh_from_db()
    assert shared.credential_id == credential.pk
    assert Credential.objects.filter(pk=credential.pk).exists()


def test_parent_vm_change_moves_only_owned_assignments(cloudinit_owner) -> None:
    from netbox_openbao.models import CredentialAssignment
    from netbox_proxbox.integrations.openbao_cloudinit import (
        cloudinit_mutation_boundary,
    )
    from utilities.testing import create_test_virtualmachine

    owner, actor, _policy, _backend = cloudinit_owner
    owner.set_password("moved-cloudinit-password", user=actor)
    owner.save()
    old_vm_id = owner.virtual_machine_id
    new_vm = create_test_virtualmachine("cloudinit-moved-parent")

    with cloudinit_mutation_boundary(
        [owner],
        [{"virtual_machine": new_vm.pk}],
        actor=actor,
    ):
        owner.virtual_machine = new_vm
        owner.save()

    assert not CredentialAssignment.objects.filter(
        assigned_object_id=old_vm_id,
        purpose="login",
    ).exists()
    assert CredentialAssignment.objects.filter(
        assigned_object_id=new_vm.pk,
        purpose="login",
        credential__uuid=owner.openbao_password_credential_uuid,
        is_primary=True,
    ).exists()


def test_raw_bulk_cascade_and_downgrade_guards(cloudinit_owner) -> None:
    from django.core.exceptions import ValidationError
    from netbox_proxbox.models import ProxmoxVMCloudInit, ProxboxPluginSettings

    owner, actor, _policy, _backend = cloudinit_owner
    owner.set_password("guarded-password", user=actor)
    owner.save()

    with pytest.raises(ValidationError, match="cleanup path"):
        ProxmoxVMCloudInit.objects.filter(pk=owner.pk).update(ciuser="blocked")
    with pytest.raises(ValidationError, match="cleanup path"):
        ProxmoxVMCloudInit.objects.filter(pk=owner.pk).delete()
    with pytest.raises(ValidationError, match="cleanup path"):
        owner.virtual_machine.delete()
    settings = ProxboxPluginSettings.get_solo()
    settings.credential_storage_backend = "legacy_encrypted"
    with pytest.raises(ValidationError, match="cleanup path"):
        settings.save()


@pytest.mark.parametrize("operation", ["bulk_update", "raw_delete"])
def test_additional_bulk_and_raw_guards(cloudinit_owner, operation: str) -> None:
    from django.core.exceptions import ValidationError
    from netbox_proxbox.models import ProxmoxVMCloudInit

    owner, actor, _policy, _backend = cloudinit_owner
    owner.set_password("bulk-guard-password", user=actor)
    owner.save()
    owner.ciuser = "blocked"

    with pytest.raises(ValidationError, match="cleanup path"):
        if operation == "bulk_update":
            ProxmoxVMCloudInit.objects.bulk_update([owner], ["ciuser"])
        else:
            ProxmoxVMCloudInit.objects.filter(pk=owner.pk)._raw_delete("default")


def test_bulk_create_rejects_injected_openbao_reference(cloudinit_owner) -> None:
    from django.core.exceptions import ValidationError
    from netbox_proxbox.models import ProxmoxVMCloudInit
    from utilities.testing import create_test_virtualmachine

    vm = create_test_virtualmachine("cloudinit-bulk-create")
    injected = ProxmoxVMCloudInit(
        virtual_machine=vm,
        is_intent=True,
        openbao_password_credential_uuid=uuid4(),
    )
    with pytest.raises(ValidationError, match="cleanup path"):
        ProxmoxVMCloudInit.objects.bulk_create([injected])


def test_provider_absence_and_traceback_fail_closed_without_secret(
    cloudinit_owner,
    monkeypatch,
) -> None:
    import builtins

    from django.test import RequestFactory
    from django.views.debug import ExceptionReporter
    from netbox_openbao import services
    from netbox_proxbox.integrations.openbao_cloudinit import (
        _has_owned_assignments,
        cloudinit_mutation_boundary,
    )
    from netbox_proxbox.models import ProxmoxVMCloudInit
    from utilities.testing import create_test_virtualmachine

    owner, actor, _policy, _backend = cloudinit_owner
    owner.set_password("provider-absence-password", user=actor)
    owner.save()
    original_import = builtins.__import__

    def missing_provider(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "netbox_openbao.models":
            raise ImportError("simulated removed provider")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing_provider)
    with pytest.raises(Exception, match="Restore the provider") as error:
        _has_owned_assignments(owner)
    assert "provider-absence-password" not in str(error.value)
    monkeypatch.setattr(builtins, "__import__", original_import)

    secret = "traceback-must-never-contain-this-cloudinit-password"
    failing_vm = create_test_virtualmachine("cloudinit-traceback")
    request = RequestFactory().post(
        "/api/plugins/proxbox/vm-cloudinit/",
        {"virtual_machine": failing_vm.pk, "password": secret},
    )
    request.user = actor

    def fail_store(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("simulated provider failure")

    monkeypatch.setattr(services, "store_credential", fail_store)
    failing = ProxmoxVMCloudInit(
        virtual_machine=failing_vm,
        is_intent=True,
    )
    try:
        with cloudinit_mutation_boundary(
            [],
            [request.POST],
            actor=actor,
            request=request,
            allow_new=True,
        ):
            failing.set_password(secret, user=actor, request=request)
            failing.save()
    except RuntimeError as exc:
        report = ExceptionReporter(
            request, type(exc), exc, exc.__traceback__
        ).get_traceback_text()
    else:  # pragma: no cover - injected failure must escape
        raise AssertionError("The injected provider failure did not escape.")

    assert secret not in report


def test_backend_validation_traceback_redacts_password(
    cloudinit_owner,
    monkeypatch,
) -> None:
    from django.test import RequestFactory
    from django.views.debug import ExceptionReporter
    from netbox_proxbox.integrations.openbao_single_request import (
        mark_single_secret_request_sensitive,
    )

    owner, actor, _policy, _backend = cloudinit_owner
    secret = "backend-validation-must-not-leak-password"
    request = RequestFactory().post("/cloud-init/", {"password": secret})
    request.user = actor
    mark_single_secret_request_sensitive(request)

    def fail_validation(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("simulated backend validation failure")

    monkeypatch.setattr(
        "netbox_proxbox.integrations.openbao.validate_openbao_storage_available",
        fail_validation,
    )
    try:
        owner.set_password(secret, user=actor, request=request)
    except RuntimeError as exc:
        report = ExceptionReporter(
            request, type(exc), exc, exc.__traceback__
        ).get_traceback_text()
    else:  # pragma: no cover - injected failure must escape
        raise AssertionError("The injected validation failure did not escape.")

    assert secret not in report


def test_second_setter_traceback_redacts_both_materials(
    cloudinit_owner,
    monkeypatch,
) -> None:
    from django.test import RequestFactory
    from django.views.debug import ExceptionReporter
    from netbox_proxbox.api.serializers.vm_cloudinit import (
        ProxmoxVMCloudInitSerializer,
    )
    from netbox_proxbox.integrations.openbao_single_request import (
        mark_single_secret_request_sensitive,
    )

    owner, actor, _policy, _backend = cloudinit_owner
    password = "first-setter-must-not-leak-password"
    private_key = "second-setter-must-not-leak-private-key"
    request = RequestFactory().post(
        "/cloud-init/", {"password": password, "private_key": private_key}
    )
    request.user = actor
    mark_single_secret_request_sensitive(request)
    calls = 0

    def fail_second_validation(*_args: Any, **_kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated second setter failure")

    monkeypatch.setattr(
        "netbox_proxbox.integrations.openbao.validate_openbao_storage_available",
        fail_second_validation,
    )
    serializer = ProxmoxVMCloudInitSerializer(context={"request": request})
    try:
        serializer._queue_material(
            owner, {"password": password, "private_key": private_key}
        )
    except RuntimeError as exc:
        report = ExceptionReporter(
            request, type(exc), exc, exc.__traceback__
        ).get_traceback_text()
    else:  # pragma: no cover - injected failure must escape
        raise AssertionError("The injected second setter failure did not escape.")

    assert password not in report
    assert private_key not in report


def test_api_write_is_secret_free_and_enters_provider_before_atomic(
    cloudinit_owner,
    monkeypatch,
) -> None:
    from django.contrib.contenttypes.models import ContentType
    from django.test import Client
    from django.urls import reverse
    from netbox_proxbox.models import ProxmoxVMCloudInit
    from tests.django_support import make_api_token
    from users.models import ObjectPermission

    owner, actor, _policy, _backend = cloudinit_owner
    permission = ObjectPermission.objects.create(
        name="cloudinit-openbao-api",
        actions=["view", "add", "change", "delete"],
    )
    permission.object_types.add(ContentType.objects.get_for_model(ProxmoxVMCloudInit))
    permission.users.add(actor)
    _token, headers = make_api_token(actor)
    entered_inside_atomic = _observe_provider_entry(monkeypatch)
    secret = "api-cloudinit-password"
    response = Client().post(
        reverse("plugins-api:netbox_proxbox-api:proxmoxvmcloudinit-list"),
        data=json.dumps(
            {
                "virtual_machine": owner.virtual_machine_id,
                "is_intent": True,
                "ssh_pwauth": True,
                "password": secret,
            }
        ),
        content_type="application/json",
        **headers,
    )

    assert response.status_code == 201, response.content
    body = response.json()
    assert "password" not in body
    assert "private_key" not in body
    assert "openbao_password_credential_uuid" not in body
    assert secret not in response.content.decode()
    assert body["password_configured"] is True
    assert body["credential_assignment_lookup"]["purpose"] == "login"
    assert entered_inside_atomic == [False]


def test_authenticated_bulk_update_and_delete_use_outer_boundary(
    cloudinit_owner,
    monkeypatch,
) -> None:
    from django.test import Client
    from django.urls import reverse
    from netbox_openbao.models import CredentialAssignment
    from netbox_proxbox.models import ProxmoxVMCloudInit
    from utilities.testing import create_test_virtualmachine

    first, actor, _policy, _backend = cloudinit_owner
    owners = [first]
    for index in range(1, 3):
        owners.append(
            ProxmoxVMCloudInit(
                virtual_machine=create_test_virtualmachine(
                    f"cloudinit-api-bulk-{index}"
                ),
                is_intent=True,
            )
        )
    for index, owner in enumerate(owners):
        owner.set_password(f"bulk-initial-{index}", user=actor)
        owner.save()
    entered_inside_atomic = _observe_provider_entry(monkeypatch)
    client = Client()
    client.force_login(actor)
    list_url = reverse("plugins-api:netbox_proxbox-api:proxmoxvmcloudinit-list")

    updated = client.patch(
        list_url,
        [
            {"id": owners[0].pk, "password": "bulk-rotated-0"},
            {"id": owners[1].pk, "password": "bulk-rotated-1"},
        ],
        content_type="application/json",
    )
    deleted = client.delete(
        list_url,
        [{"id": owners[0].pk}, {"id": owners[1].pk}],
        content_type="application/json",
    )

    assert updated.status_code == 200, updated.content
    assert deleted.status_code == 204, deleted.content
    assert not ProxmoxVMCloudInit.objects.filter(
        pk__in=[owners[0].pk, owners[1].pk]
    ).exists()
    assert not CredentialAssignment.objects.filter(
        assigned_object_id__in=[
            owners[0].virtual_machine_id,
            owners[1].virtual_machine_id,
        ],
        purpose="login",
    ).exists()
    assert entered_inside_atomic == [False, False]


def _bulk_delete_owner(
    name: str, ciuser: str, secret: str, actor: Any
) -> tuple[Any, Any, str]:
    from netbox_openbao.models import Credential
    from netbox_proxbox.models import ProxmoxVMCloudInit
    from utilities.testing import create_test_virtualmachine

    owner = ProxmoxVMCloudInit(
        virtual_machine=create_test_virtualmachine(name),
        ciuser=ciuser,
        is_intent=True,
    )
    owner.set_password(secret, user=actor)
    owner.save()
    credential = Credential.objects.get(uuid=owner.openbao_password_credential_uuid)
    return owner, credential, secret


def _assert_filtered_bulk_cleanup(
    targets: tuple[tuple[Any, Any, str], ...],
    kept: tuple[Any, Any, str],
    shared: Any,
    policy: Any,
    backend: Any,
) -> None:
    from netbox_openbao.models import Credential, CredentialAssignment
    from netbox_proxbox.models import ProxmoxVMCloudInit

    target_ids = [owner.pk for owner, _credential, _secret in targets]
    target_vm_ids = [
        owner.virtual_machine_id for owner, _credential, _secret in targets
    ]
    assert not ProxmoxVMCloudInit.objects.filter(pk__in=target_ids).exists()
    assert not CredentialAssignment.objects.filter(
        assigned_object_id__in=target_vm_ids, purpose="login"
    ).exists()
    kept[0].refresh_from_db()
    assert kept[0].openbao_password_credential_uuid == kept[1].uuid
    assert CredentialAssignment.objects.filter(credential=kept[1]).exists()
    shared.refresh_from_db()
    assert Credential.objects.filter(pk=shared.credential_id).exists()
    for _owner, credential, secret in targets:
        assert backend(policy.engine).read(credential.path) == {"password": secret}


def test_authenticated_ui_all_bulk_delete_uses_filtered_outer_boundary(
    cloudinit_owner,
    monkeypatch,
) -> None:
    from django.contrib.contenttypes.models import ContentType
    from django.test import Client
    from django.urls import reverse
    from netbox_openbao.models import CredentialAssignment
    from utilities.testing import create_test_virtualmachine
    from virtualization.models import VirtualMachine

    _owner, actor, policy, backend = cloudinit_owner
    targets = (
        _bulk_delete_owner(
            "cloudinit-ui-all-first", "round3-delete", "round3-first", actor
        ),
        _bulk_delete_owner(
            "cloudinit-ui-all-second", "round3-delete", "round3-second", actor
        ),
    )
    kept = _bulk_delete_owner(
        "cloudinit-ui-all-kept", "round3-keep", "round3-kept", actor
    )
    survivor = create_test_virtualmachine("cloudinit-ui-all-shared-survivor")
    shared = CredentialAssignment.objects.create(
        credential=targets[0][1],
        assigned_object_type=ContentType.objects.get_for_model(VirtualMachine),
        assigned_object_id=survivor.pk,
        purpose="login",
        is_primary=True,
    )
    entered_inside_atomic = _observe_provider_entry(monkeypatch)
    client = Client()
    client.force_login(actor)
    url = reverse("plugins:netbox_proxbox:proxmoxvmcloudinit_bulk_delete")

    response = client.post(
        f"{url}?ciuser=round3-delete",
        {
            "_all": "1",
            "_confirm": "on",
            "confirm": "on",
            "pk": [str(targets[0][0].pk)],
        },
    )

    assert response.status_code == 302, response.content
    assert entered_inside_atomic == [False]
    _assert_filtered_bulk_cleanup(targets, kept, shared, policy, backend)


def test_cloudinit_reference_migration_round_trip(
    pytestconfig,
    transactional_db,
) -> None:
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    from utilities.testing import create_test_virtualmachine

    _require_harness(pytestconfig)
    before = ("netbox_proxbox", "0101_single_secret_owner_openbao_references")
    after = ("netbox_proxbox", "0102_vm_cloudinit_openbao_references")
    password_uuid = uuid4()
    keypair_uuid = uuid4()
    vm = create_test_virtualmachine("cloudinit-reference-migration")
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    try:
        executor.migrate([before])
        old_apps = executor.loader.project_state([before]).apps
        OldOwner = old_apps.get_model("netbox_proxbox", "ProxmoxVMCloudInit")
        assert not {
            "openbao_password_credential_uuid",
            "openbao_keypair_credential_uuid",
        }.intersection(field.name for field in OldOwner._meta.get_fields())
        owner = OldOwner.objects.create(
            virtual_machine_id=vm.pk,
            credential_reference_id=901,
            is_intent=True,
        )

        executor = MigrationExecutor(connection)
        executor.migrate([after])
        NewOwner = executor.loader.project_state([after]).apps.get_model(
            "netbox_proxbox", "ProxmoxVMCloudInit"
        )
        migrated = NewOwner.objects.get(pk=owner.pk)
        assert migrated.credential_reference_id == 901
        assert migrated.openbao_password_credential_uuid is None
        assert migrated.openbao_keypair_credential_uuid is None
        NewOwner.objects.filter(pk=owner.pk).update(
            openbao_password_credential_uuid=password_uuid,
            openbao_keypair_credential_uuid=keypair_uuid,
        )

        executor = MigrationExecutor(connection)
        executor.migrate([before])
        ReversedOwner = executor.loader.project_state([before]).apps.get_model(
            "netbox_proxbox", "ProxmoxVMCloudInit"
        )
        assert not {
            "openbao_password_credential_uuid",
            "openbao_keypair_credential_uuid",
        }.intersection(field.name for field in ReversedOwner._meta.get_fields())

        executor = MigrationExecutor(connection)
        executor.migrate([after])
        RoundTripOwner = executor.loader.project_state([after]).apps.get_model(
            "netbox_proxbox", "ProxmoxVMCloudInit"
        )
        round_trip = RoundTripOwner.objects.get(pk=owner.pk)
        assert round_trip.credential_reference_id == 901
        assert round_trip.openbao_password_credential_uuid == password_uuid
        assert round_trip.openbao_keypair_credential_uuid == keypair_uuid
    finally:
        MigrationExecutor(connection).migrate(latest)
