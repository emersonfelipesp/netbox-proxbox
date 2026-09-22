"""Real-provider behavior for FastAPI, PBS, PDM, and Firecracker tokens."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Barrier
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from cryptography.fernet import Fernet
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
def openbao_single_estate(pytestconfig, transactional_db):
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
        name="Proxbox single-secret test",
        slug="proxbox-single-secret-test",
        api_url="https://bao.invalid:8200",
        kv_mount="secret",
        is_default=True,
    )
    policy = CredentialPolicy.objects.create(
        name="Proxbox single-secret owners",
        slug="proxbox",
        engine=engine,
        openbao_policy="netbox-proxbox",
    )
    actor = get_user_model().objects.create_superuser(
        username="proxbox-single-secret-test",
        email="proxbox-single-secret@example.invalid",
        password=None,
    )
    settings = ProxboxPluginSettings.get_solo()
    settings.encryption_key = Fernet.generate_key().decode()
    settings.credential_storage_backend = "openbao"
    settings.openbao_policy_slug = policy.slug
    settings.openbao_service_username = actor.username
    settings.save()
    yield actor, policy, FakeBackend
    backends.BACKENDS["openbao"] = OpenBaoBackend


def _owner(kind: str, actor: Any) -> Any:
    from netbox_proxbox.models import (
        FastAPIEndpoint,
        FirecrackerHost,
        FirecrackerHostPool,
        PBSEndpoint,
        PDMEndpoint,
    )

    if kind == "fastapi":
        owner = FastAPIEndpoint(
            name="single-fastapi",
            domain="backend.example.invalid",
            enabled=True,
            use_https=True,
        )
    elif kind == "pbs":
        owner = PBSEndpoint(name="single-pbs", token_id="root@pam!sync")
    elif kind == "pdm":
        owner = PDMEndpoint(name="single-pdm", token_id="root@pam!sync")
    else:
        pool = FirecrackerHostPool.objects.create(
            name="single-pool", slug="single-pool"
        )
        owner = FirecrackerHost(
            pool=pool,
            name="single-firecracker",
            agent_base_url="https://127.0.0.1:9443",
        )
    owner._openbao_actor_user = actor
    return owner


def _set_material(owner, kind: str, value: str) -> None:
    if kind == "fastapi":
        owner.token = value
    elif kind in {"pbs", "pdm"}:
        owner.token_secret = value
    else:
        owner.set_agent_token(value, key="unused")


def _patch_fastapi_adoption(monkeypatch: pytest.MonkeyPatch) -> None:
    from netbox_proxbox.services import backend_key_adoption

    monkeypatch.setattr(
        backend_key_adoption,
        "adopt_rotated_backend_key",
        lambda endpoint, candidate, **kwargs: SimpleNamespace(
            target_fingerprint=backend_key_adoption.backend_key_target_fingerprint(
                endpoint
            )
        ),
    )


def _fastapi_owner(actor: Any, name: str, *, enabled: bool = True) -> Any:
    from netbox_proxbox.models import FastAPIEndpoint

    owner = FastAPIEndpoint(
        name=name,
        domain=f"{name}.example.invalid",
        enabled=enabled,
        use_https=True,
    )
    owner._openbao_actor_user = actor
    return owner


def _get_material(owner, kind: str) -> str:
    if kind == "fastapi":
        return owner.token
    if kind in {"pbs", "pdm"}:
        return owner.token_secret
    return owner.get_agent_token(key="unused")


def _reference(owner: Any, kind: str) -> tuple[str, Any]:
    field = (
        "openbao_agent_token_credential_uuid"
        if kind == "firecracker"
        else "openbao_token_credential_uuid"
    )
    return field, getattr(owner, field)


def _assert_created_owner(
    owner: Any,
    credential: Any,
    assignment: Any,
    policy: Any,
    purpose: str,
    encrypted_field: str,
) -> None:
    assert credential.policy_id == policy.pk
    assert credential.credential_type == "api-token"
    assert assignment.assigned_object_type.model == owner._meta.model_name
    assert assignment.assigned_object_id == owner.pk
    assert assignment.purpose == purpose
    assert assignment.is_primary is True
    assert getattr(owner, encrypted_field) == ""


@pytest.mark.parametrize(
    ("kind", "purpose", "encrypted_field"),
    [
        ("fastapi", "api", "token_enc"),
        ("pbs", "api", "token_secret_enc"),
        ("pdm", "api", "token_secret_enc"),
        ("firecracker", "agent", "agent_token_enc"),
    ],
)
def test_create_rotate_resolve_and_assign(
    openbao_single_estate,
    monkeypatch,
    kind: str,
    purpose: str,
    encrypted_field: str,
) -> None:
    from netbox_openbao.models import Credential, CredentialAssignment
    from netbox_proxbox.services import backend_key_adoption

    actor, policy, backend = openbao_single_estate
    monkeypatch.setattr(
        backend_key_adoption,
        "adopt_rotated_backend_key",
        lambda endpoint, candidate, **kwargs: SimpleNamespace(
            target_fingerprint=backend_key_adoption.backend_key_target_fingerprint(
                endpoint
            )
        ),
    )
    owner = _owner(kind, actor)
    _set_material(owner, kind, f"{kind}-first")
    owner.save()
    reference_field, credential_uuid = _reference(owner, kind)
    credential = Credential.objects.get(uuid=credential_uuid)
    assignment = CredentialAssignment.objects.get(credential=credential)

    _assert_created_owner(
        owner, credential, assignment, policy, purpose, encrypted_field
    )
    assert _get_material(owner, kind) == f"{kind}-first"
    assert backend(policy.engine).read(credential.path) == {"token": f"{kind}-first"}

    _set_material(owner, kind, f"{kind}-second")
    owner.save()
    owner.refresh_from_db()
    assert getattr(owner, reference_field) == credential_uuid
    credential.refresh_from_db()
    assert credential.kv_version == 2
    assert _get_material(owner, kind) == f"{kind}-second"


def test_openbao_missing_reference_never_falls_back_to_fernet(
    openbao_single_estate,
) -> None:
    from django.core.exceptions import ValidationError
    from netbox_proxbox.models import PBSEndpoint, ProxboxPluginSettings
    from netbox_proxbox.models.primary_secrets import encrypt_primary_secret

    _actor, _policy, _backend = openbao_single_estate
    settings = ProxboxPluginSettings.get_solo()
    owner = PBSEndpoint.objects.create(
        name="missing-reference",
        token_id="root@pam!missing",
        token_secret_enc=encrypt_primary_secret("must-not-return"),
    )
    assert settings.credential_storage_backend == "openbao"

    with pytest.raises(ValidationError, match="not configured") as error:
        _ = owner.token_secret

    assert "must-not-return" not in str(error.value)


def test_delete_keeps_shared_provider_material(openbao_single_estate) -> None:
    from netbox_openbao.models import Credential, CredentialAssignment

    actor, policy, backend = openbao_single_estate
    owner = _owner("pbs", actor)
    _set_material(owner, "pbs", "retained-provider-token")
    owner.save()
    credential = Credential.objects.get(uuid=owner.openbao_token_credential_uuid)
    path = credential.path
    owner.delete()

    assert not CredentialAssignment.objects.filter(credential=credential).exists()
    assert Credential.objects.filter(pk=credential.pk).exists()
    assert backend(policy.engine).read(path) == {"token": "retained-provider-token"}


def test_openbao_to_legacy_switch_requires_explicit_cleanup(
    openbao_single_estate,
) -> None:
    from django.core.exceptions import ValidationError
    from netbox_proxbox.models import ProxboxPluginSettings

    actor, _policy, _backend = openbao_single_estate
    owner = _owner("pdm", actor)
    _set_material(owner, "pdm", "downgrade-blocked")
    owner.save()
    settings = ProxboxPluginSettings.get_solo()
    settings.credential_storage_backend = "legacy_encrypted"

    with pytest.raises(ValidationError, match="cleanup path"):
        settings.save()


@pytest.mark.parametrize(
    ("operation", "assignment_only"),
    [
        ("bulk_update", False),
        ("upsert", True),
        ("expression", False),
    ],
)
def test_settings_bulk_downgrade_refuses_remaining_single_secret_state(
    openbao_single_estate,
    operation: str,
    assignment_only: bool,
) -> None:
    from django.core.exceptions import ValidationError
    from django.db.models import F
    from netbox_openbao.models import CredentialAssignment
    from netbox_proxbox.models import ProxboxPluginSettings
    from tests.django_support import raw_update_fields

    actor, _policy, _backend = openbao_single_estate
    owner = _owner("pbs", actor)
    _set_material(owner, "pbs", "bulk-downgrade-token")
    owner.save()
    if assignment_only:
        raw_update_fields(
            type(owner),
            owner.pk,
            openbao_token_credential_uuid=None,
        )
    settings = ProxboxPluginSettings.get_solo()

    with pytest.raises(ValidationError, match="cleanup path"):
        if operation == "bulk_update":
            settings.credential_storage_backend = "legacy_encrypted"
            ProxboxPluginSettings.objects.bulk_update(
                [settings], ["credential_storage_backend"]
            )
        elif operation == "upsert":
            candidate = ProxboxPluginSettings(
                singleton_key="default",
                credential_storage_backend="legacy_encrypted",
            )
            ProxboxPluginSettings.objects.bulk_create(
                [candidate],
                update_conflicts=True,
                update_fields=["credential_storage_backend"],
                unique_fields=["singleton_key"],
            )
        else:
            settings.credential_storage_backend = F("credential_storage_backend")
            ProxboxPluginSettings.objects.bulk_update(
                [settings], ["credential_storage_backend"]
            )

    settings.refresh_from_db()
    assert settings.credential_storage_backend == "openbao"
    assert CredentialAssignment.objects.filter(
        assigned_object_id=owner.pk,
        assigned_object_type__model="pbsendpoint",
        purpose="api",
    ).exists()


def test_legacy_to_openbao_waits_for_explicit_material_write(
    openbao_single_estate,
) -> None:
    from django.core.exceptions import ValidationError
    from netbox_proxbox.models import PBSEndpoint, ProxboxPluginSettings

    actor, _policy, _backend = openbao_single_estate
    settings = ProxboxPluginSettings.get_solo()
    settings.credential_storage_backend = "legacy_encrypted"
    settings.save()
    owner = PBSEndpoint(name="legacy-first", token_id="root@pam!legacy")
    owner.token_secret = "retained-legacy-token"
    owner.save()
    ciphertext = owner.token_secret_enc

    settings.credential_storage_backend = "openbao"
    settings.save()
    owner.refresh_from_db()
    assert owner.openbao_token_credential_uuid is None
    assert owner.token_secret_enc == ciphertext
    with pytest.raises(ValidationError, match="not configured"):
        _ = owner.token_secret

    owner._openbao_actor_user = actor
    owner.token_secret = "explicit-openbao-token"
    owner.save()
    owner.refresh_from_db()
    assert owner.openbao_token_credential_uuid is not None
    assert owner.token_secret_enc == ""
    assert owner.token_secret == "explicit-openbao-token"


def test_direct_reference_rebind_is_rejected_without_provider_change(
    openbao_single_estate,
) -> None:
    from django.core.exceptions import ValidationError
    from netbox_openbao.models import Credential

    actor, _policy, backend = openbao_single_estate
    owner = _owner("pbs", actor)
    _set_material(owner, "pbs", "original-token")
    owner.save()
    original_uuid = owner.openbao_token_credential_uuid
    credential = Credential.objects.get(uuid=original_uuid)
    stored = {path: list(versions) for path, versions in backend.store.items()}
    owner.openbao_token_credential_uuid = uuid4()

    with pytest.raises(ValidationError, match="changed|cannot be rebound"):
        owner.save(update_fields=["openbao_token_credential_uuid"])

    owner.refresh_from_db()
    assert owner.openbao_token_credential_uuid == original_uuid
    credential.refresh_from_db()
    assert credential.kv_version == 1
    assert backend.store == stored


def test_provider_cas_failure_rolls_back_new_owner_graph(
    openbao_single_estate,
) -> None:
    from netbox_openbao.backends.exceptions import OpenBaoConflict
    from netbox_openbao.models import Credential, CredentialAssignment
    from netbox_proxbox.models import PBSEndpoint

    actor, _policy, backend = openbao_single_estate
    owner = _owner("pbs", actor)
    _set_material(owner, "pbs", "must-not-persist")
    backend.fail_on_write = True

    with pytest.raises(OpenBaoConflict):
        owner.save()

    assert not PBSEndpoint.objects.filter(name="single-pbs").exists()
    assert Credential.objects.count() == 0
    assert CredentialAssignment.objects.count() == 0
    assert backend.store == {}


def test_concurrent_rotations_serialize_provider_versions(
    openbao_single_estate,
) -> None:
    from django.db import close_old_connections
    from netbox_openbao.models import Credential
    from netbox_proxbox.models import PBSEndpoint

    actor, _policy, backend = openbao_single_estate
    owner = _owner("pbs", actor)
    _set_material(owner, "pbs", "version-one")
    owner.save()
    credential_uuid = owner.openbao_token_credential_uuid
    ready = Barrier(2)

    def rotate(value: str) -> None:
        close_old_connections()
        try:
            worker = PBSEndpoint.objects.get(pk=owner.pk)
            worker._openbao_actor_user = type(actor).objects.get(pk=actor.pk)
            worker.token_secret = value
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


@pytest.mark.parametrize("kind", ["fastapi", "pbs", "pdm"])
def test_openbao_primary_setters_do_not_create_fernet_key(
    openbao_single_estate,
    monkeypatch,
    kind: str,
) -> None:
    from netbox_proxbox.models import ProxboxPluginSettings

    actor, _policy, _backend = openbao_single_estate
    settings = ProxboxPluginSettings.get_solo()
    settings.encryption_key = ""
    settings.save(update_fields=["encryption_key"])
    _patch_fastapi_adoption(monkeypatch)
    owner = _owner(kind, actor)
    _set_material(owner, kind, f"{kind}-provider-only")
    owner.save()

    settings.refresh_from_db()
    owner.refresh_from_db()
    assert settings.encryption_key == ""
    assert _reference(owner, kind)[1] is not None
    assert getattr(owner, "token_enc", getattr(owner, "token_secret_enc", "")) == ""


def test_fastapi_openbao_disabled_explicit_and_enabled_blank_branches(
    openbao_single_estate,
    monkeypatch,
) -> None:
    from django.core.exceptions import ValidationError
    from netbox_proxbox.models import FastAPIEndpoint, ProxboxPluginSettings

    actor, _policy, _backend = openbao_single_estate
    settings = ProxboxPluginSettings.get_solo()
    settings.encryption_key = ""
    settings.save(update_fields=["encryption_key"])
    _patch_fastapi_adoption(monkeypatch)
    monkeypatch.setattr(
        "netbox_proxbox.services.endpoint_autoconfiguration.autoconfigure_fastapi_endpoint",
        lambda: SimpleNamespace(state="pending", endpoint_id=None),
    )

    disabled = _fastapi_owner(actor, "disabled-explicit", enabled=False)
    disabled.token = "must-not-stage"
    with pytest.raises(ValidationError, match="disabled new endpoint"):
        disabled.save()
    assert not FastAPIEndpoint.objects.filter(name="disabled-explicit").exists()

    pending = _fastapi_owner(actor, "enabled-blank")
    pending.save()
    pending.refresh_from_db()
    settings.refresh_from_db()
    assert pending.openbao_token_credential_uuid is not None
    assert pending.token_enc == ""
    assert pending.backend_key_target_fingerprint == ""
    assert pending.token
    assert settings.encryption_key == ""


def test_fastapi_openbao_retains_material_and_revalidates_unchanged_token(
    openbao_single_estate,
    monkeypatch,
) -> None:
    from netbox_openbao.models import Credential

    actor, _policy, _backend = openbao_single_estate
    _patch_fastapi_adoption(monkeypatch)
    owner = _fastapi_owner(actor, "retained-fastapi")
    owner.token = "retained-fastapi-token"
    owner.save()
    credential = Credential.objects.get(uuid=owner.openbao_token_credential_uuid)
    original_uuid = owner.openbao_token_credential_uuid
    original_fingerprint = owner.backend_key_target_fingerprint

    owner.refresh_from_db()
    owner.name = "retained-fastapi-renamed"
    owner.save(update_fields=["name"])
    credential.refresh_from_db()
    assert credential.kv_version == 1
    assert owner.openbao_token_credential_uuid == original_uuid
    assert owner.token == "retained-fastapi-token"

    owner.domain = "retained-fastapi-moved.example.invalid"
    owner.token = "retained-fastapi-token"
    owner.save()
    credential.refresh_from_db()
    assert credential.kv_version == 1
    assert owner.openbao_token_credential_uuid == original_uuid
    assert owner.backend_key_target_fingerprint != original_fingerprint
    assert owner.token == "retained-fastapi-token"


def test_fastapi_openbao_replaces_failed_legacy_ciphertext_and_partial_rotates(
    openbao_single_estate,
    monkeypatch,
) -> None:
    from netbox_openbao.models import Credential
    from netbox_proxbox.models import ProxboxPluginSettings
    from tests.django_support import raw_update_fields

    _actor, _policy, _backend = openbao_single_estate
    settings = ProxboxPluginSettings.get_solo()
    settings.credential_storage_backend = "legacy_encrypted"
    settings.encryption_key = ""
    settings.save()
    owner = _fastapi_owner(_actor, "failed-legacy-fastapi", enabled=False)
    owner.save()
    raw_update_fields(type(owner), owner.pk, token_enc="invalid-fernet-ciphertext")
    settings.credential_storage_backend = "openbao"
    settings.save(update_fields=["credential_storage_backend"])
    _patch_fastapi_adoption(monkeypatch)

    owner.refresh_from_db()
    owner.enabled = True
    owner.token = "replacement-provider-token"
    owner.save()
    credential = Credential.objects.get(uuid=owner.openbao_token_credential_uuid)
    credential_uuid = credential.uuid
    assert owner.token_enc == ""
    assert owner.token == "replacement-provider-token"

    owner.refresh_from_db()
    owner.token = "partially-rotated-provider-token"
    owner.save(update_fields=["token_enc"])
    credential.refresh_from_db()
    settings.refresh_from_db()
    assert owner.openbao_token_credential_uuid == credential_uuid
    assert owner.token == "partially-rotated-provider-token"
    assert credential.kv_version == 2
    assert settings.encryption_key == ""


def test_fastapi_openbao_outer_rollback_retains_intent_for_retry(
    openbao_single_estate,
    monkeypatch,
) -> None:
    from netbox_openbao.backends.exceptions import OpenBaoConflict
    from netbox_proxbox.models import FastAPIEndpoint, ProxboxPluginSettings

    actor, _policy, backend = openbao_single_estate
    settings = ProxboxPluginSettings.get_solo()
    settings.encryption_key = ""
    settings.save(update_fields=["encryption_key"])
    _patch_fastapi_adoption(monkeypatch)
    owner = _fastapi_owner(actor, "retry-fastapi")
    owner.token = "retry-provider-token"
    backend.fail_on_write = True

    with pytest.raises(OpenBaoConflict):
        owner.save()
    assert not FastAPIEndpoint.objects.filter(name="retry-fastapi").exists()
    assert owner.pk is None

    backend.fail_on_write = False
    owner.save()
    settings.refresh_from_db()
    assert owner.openbao_token_credential_uuid is not None
    assert owner.token == "retry-provider-token"
    assert settings.encryption_key == ""


@pytest.mark.parametrize("operation", ["update", "bulk_update", "delete", "raw_delete"])
def test_raw_owner_writes_refuse_openbao_state(
    openbao_single_estate,
    operation: str,
) -> None:
    from django.core.exceptions import ValidationError

    actor, _policy, _backend = openbao_single_estate
    owner = _owner("pdm", actor)
    _set_material(owner, "pdm", "guarded-token")
    owner.save()
    queryset = type(owner).objects.filter(pk=owner.pk)

    with pytest.raises(ValidationError, match="cleanup path"):
        if operation == "update":
            queryset.update(name="bypass")
        elif operation == "bulk_update":
            owner.name = "bypass"
            type(owner).objects.bulk_update([owner], ["name"])
        elif operation == "delete":
            queryset.delete()
        else:
            queryset._raw_delete("default")


def test_bulk_create_and_pool_cascade_refuse_openbao_state(
    openbao_single_estate,
) -> None:
    from django.core.exceptions import ValidationError
    from netbox_proxbox.models import FirecrackerHost, FirecrackerHostPool

    actor, _policy, _backend = openbao_single_estate
    injected = FirecrackerHost(
        pool=FirecrackerHostPool.objects.create(name="injected", slug="injected"),
        name="injected-host",
        agent_base_url="https://injected.invalid",
        openbao_agent_token_credential_uuid=uuid4(),
    )
    with pytest.raises(ValidationError, match="cleanup path"):
        FirecrackerHost.objects.bulk_create([injected])

    owner = _owner("firecracker", actor)
    _set_material(owner, "firecracker", "cascade-token")
    owner.save()
    with pytest.raises(ValidationError, match="cleanup path"):
        owner.pool.delete()


def test_shared_credential_assignment_survives_owner_delete(
    openbao_single_estate,
) -> None:
    from django.contrib.contenttypes.models import ContentType
    from netbox_openbao.models import Credential, CredentialAssignment

    actor, _policy, _backend = openbao_single_estate
    owner = _owner("pbs", actor)
    _set_material(owner, "pbs", "shared-token")
    owner.save()
    survivor = _owner("pdm", actor)
    survivor.save()
    credential = Credential.objects.get(uuid=owner.openbao_token_credential_uuid)
    shared = CredentialAssignment.objects.create(
        credential=credential,
        assigned_object_type=ContentType.objects.get_for_model(type(survivor)),
        assigned_object_id=survivor.pk,
        purpose="api",
        is_primary=True,
    )

    owner.delete()

    shared.refresh_from_db()
    assert shared.credential_id == credential.pk
    assert Credential.objects.filter(pk=credential.pk).exists()


def test_readiness_lookup_and_serialization_are_secret_free(
    openbao_single_estate,
) -> None:
    from netbox_proxbox.api.serializers.pbs_pdm import PBSEndpointSerializer
    from netbox_proxbox.integrations.openbao import (
        credential_assignment_lookup,
        credential_assignment_readiness,
    )

    actor, _policy, _backend = openbao_single_estate
    secret = "never-serialize-this-token"
    owner = _owner("pbs", actor)
    _set_material(owner, "pbs", secret)
    owner.save()
    lookup = credential_assignment_lookup(owner)
    data = PBSEndpointSerializer(owner, context={"request": None}).data

    assert lookup == {
        "assigned_object_type": "netbox_proxbox.pbsendpoint",
        "assigned_object_id": str(owner.pk),
        "purpose": "api",
    }
    assert credential_assignment_readiness(owner)[0] is True
    assert data["credential_assignment_lookup"] == lookup
    assert "token_secret" not in data
    assert "openbao_token_credential_uuid" not in data
    assert secret not in repr(data)


def _observe_provider_entry(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    from django.db import connection
    from netbox_openbao import material_transactions
    from netbox_openbao.backends.exceptions import OpenBaoError

    entered_inside_atomic: list[bool] = []
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


def test_fastapi_sensitive_export_uses_authenticated_token_user_authority(
    openbao_single_estate,
    monkeypatch,
) -> None:
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Permission
    from django.core.exceptions import PermissionDenied
    from django.http import HttpResponse
    from django.test import RequestFactory
    from netbox.api.authentication import TokenAuthentication
    from netbox_proxbox.views.endpoints.fastapi import FastAPIEndpointExportView
    from netbox_proxbox.views.endpoints.fastapi_export import (
        _serialize_fastapi_endpoint,
    )
    from tests.django_support import grant_user_permissions

    actor, _policy, _backend = openbao_single_estate
    _patch_fastapi_adoption(monkeypatch)
    owner = _fastapi_owner(actor, "export-fastapi")
    owner.token = "export-provider-token"
    owner.save()
    group_model = actor._meta.get_field("groups").remote_field.model
    permitted_group = group_model.objects.create(name="export-provider-permitted")
    _policy.groups.add(permitted_group)
    denied = get_user_model().objects.create_user(username="export-provider-denied")
    grant_user_permissions(
        denied,
        [
            Permission.objects.get(
                content_type__app_label="netbox_proxbox",
                codename="view_fastapiendpoint",
            )
        ],
    )

    allowed_row = _serialize_fastapi_endpoint(owner, True, user=actor)
    assert allowed_row["token"] == "export-provider-token"
    with pytest.raises(PermissionDenied):
        _serialize_fastapi_endpoint(owner, True, user=denied)
    denied.has_perm = lambda permission: True

    monkeypatch.setattr(
        TokenAuthentication,
        "authenticate",
        lambda self, request: (denied, object()),
    )
    request = RequestFactory().post(
        "/plugins/proxbox/endpoints/fastapi/export/",
        {
            "include_sensitive": "true",
            "token_version": "v2",
            "token_key": "nbt_export",
            "token_secret": "proof",
        },
    )
    request.user = actor
    captured: dict[str, Any] = {}
    view = FastAPIEndpointExportView()

    def capture_export(*args: Any, **kwargs: Any) -> HttpResponse:
        captured.update(kwargs)
        return HttpResponse("captured")

    monkeypatch.setattr(view, "_export_response", capture_export)
    response = view.post(request)
    assert response.status_code == 200
    assert captured["material_user"] == denied


def test_authenticated_fastapi_ui_create_starts_provider_before_netbox_atomic(
    openbao_single_estate,
    monkeypatch,
) -> None:
    from django.test import Client
    from django.urls import reverse
    from netbox_proxbox.models import FastAPIEndpoint
    from netbox_proxbox.services import backend_key_adoption

    actor, _policy, _backend = openbao_single_estate
    monkeypatch.setattr(
        backend_key_adoption,
        "adopt_rotated_backend_key",
        lambda endpoint, candidate, **kwargs: SimpleNamespace(
            target_fingerprint=backend_key_adoption.backend_key_target_fingerprint(
                endpoint
            )
        ),
    )
    entered_inside_atomic = _observe_provider_entry(monkeypatch)
    client = Client()
    client.force_login(actor)
    secret = "fastapi-ui-token"
    response = client.post(
        reverse("plugins:netbox_proxbox:fastapiendpoint_add"),
        {
            "name": "ui-fastapi",
            "domain": "ui-fastapi.example.invalid",
            "port": 8800,
            "use_https": "on",
            "enabled": "on",
            "token": secret,
        },
    )

    assert response.status_code == 302, response.content
    endpoint = FastAPIEndpoint.objects.get(name="ui-fastapi")
    assert endpoint.openbao_token_credential_uuid is not None
    assert endpoint.token_enc == ""
    assert endpoint.token == secret
    assert entered_inside_atomic == [False]


def test_invalid_fastapi_home_quick_edit_does_not_create_legacy_key(
    openbao_single_estate,
) -> None:
    from django.test import Client
    from django.urls import reverse
    from netbox_proxbox.models import ProxboxPluginSettings

    actor, _policy, _backend = openbao_single_estate
    settings = ProxboxPluginSettings.get_solo()
    settings.credential_storage_backend = "legacy_encrypted"
    settings.encryption_key = ""
    settings.save()
    owner = _fastapi_owner(actor, "invalid-quick-edit", enabled=False)
    owner.save()
    client = Client()
    client.force_login(actor)

    response = client.post(
        reverse(
            "plugins:netbox_proxbox:home_quick_edit",
            args=["fastapi", owner.pk],
        ),
        {
            "name": owner.name,
            "domain": owner.domain,
            "port": 0,
            "token": "must-not-persist-or-create-key",
        },
    )

    assert response.status_code == 422
    settings.refresh_from_db()
    owner.refresh_from_db()
    assert settings.encryption_key == ""
    assert owner.token_enc == ""


@pytest.mark.parametrize(
    ("kind", "route_name", "model_name", "port"),
    [
        ("pbs", "pbsendpoint", "PBSEndpoint", 8007),
        ("pdm", "pdmendpoint", "PDMEndpoint", 8443),
    ],
)
def test_authenticated_pbs_pdm_api_create_and_update_use_request_boundary(
    openbao_single_estate,
    monkeypatch,
    kind: str,
    route_name: str,
    model_name: str,
    port: int,
) -> None:
    from django.test import Client
    from django.urls import reverse
    from netbox_proxbox import models

    actor, _policy, _backend = openbao_single_estate
    entered_inside_atomic = _observe_provider_entry(monkeypatch)
    client = Client()
    client.force_login(actor)
    first_secret = f"{kind}-api-first"
    create = client.post(
        reverse(f"plugins-api:netbox_proxbox-api:endpoints:{route_name}-list"),
        {
            "name": f"api-{kind}",
            "domain": f"api-{kind}.example.invalid",
            "port": port,
            "token_id": "root@pam!api",
            "token_secret": first_secret,
            "enabled": True,
        },
        content_type="application/json",
    )

    assert create.status_code == 201, create.content
    owner = getattr(models, model_name).objects.get(name=f"api-{kind}")
    credential_uuid = owner.openbao_token_credential_uuid
    assert credential_uuid is not None
    assert first_secret not in create.content.decode()

    second_secret = f"{kind}-api-second"
    update = client.patch(
        reverse(
            f"plugins-api:netbox_proxbox-api:endpoints:{route_name}-detail",
            args=[owner.pk],
        ),
        {"token_secret": second_secret},
        content_type="application/json",
    )

    assert update.status_code == 200, update.content
    owner.refresh_from_db()
    assert owner.openbao_token_credential_uuid == credential_uuid
    assert owner.token_secret == second_secret
    assert second_secret not in update.content.decode()
    assert entered_inside_atomic == [False, False]


def test_authenticated_firecracker_api_stores_effective_backend_and_hides_token(
    openbao_single_estate,
    monkeypatch,
) -> None:
    from django.test import Client
    from django.urls import reverse
    from netbox_proxbox.models import FirecrackerHost, FirecrackerHostPool

    actor, _policy, _backend = openbao_single_estate
    pool = FirecrackerHostPool.objects.create(name="api-pool", slug="api-pool")
    entered_inside_atomic = _observe_provider_entry(monkeypatch)
    client = Client()
    client.force_login(actor)
    secret = "firecracker-discovery-token"
    response = client.post(
        reverse("plugins-api:netbox_proxbox-api:firecrackerhost-list"),
        {
            "pool": {"id": pool.pk},
            "name": "api-host",
            "agent_base_url": "https://agent.example.invalid",
            "agent_token": secret,
            "status": "offline",
        },
        content_type="application/json",
    )

    assert response.status_code == 201, response.content
    host = FirecrackerHost.objects.get(name="api-host")
    assert host.openbao_agent_token_credential_uuid is not None
    assert host.agent_token_enc == ""
    assert secret not in response.content.decode()
    assert "openbao_agent_token_credential_uuid" not in response.content.decode()
    assert entered_inside_atomic == [False]


def test_provider_removal_and_traceback_fail_closed_without_secret(
    openbao_single_estate,
    monkeypatch,
) -> None:
    import builtins

    from django.test import RequestFactory
    from django.views.debug import ExceptionReporter
    from netbox_openbao import services
    from netbox_proxbox.integrations.openbao_single_request import (
        single_secret_mutation_boundary,
    )
    from netbox_proxbox.integrations.openbao_single_writer import (
        _has_owned_assignments,
    )

    actor, _policy, _backend = openbao_single_estate
    owner = _owner("pbs", actor)
    _set_material(owner, "pbs", "provider-removal-token")
    owner.save()
    original_import = builtins.__import__

    def missing_provider(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "netbox_openbao.models":
            raise ImportError("simulated removed provider")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing_provider)
    with pytest.raises(Exception, match="Restore the provider") as error:
        _has_owned_assignments(owner)
    assert "provider-removal-token" not in str(error.value)
    monkeypatch.setattr(builtins, "__import__", original_import)

    secret = "traceback-must-never-contain-this-token"
    request = RequestFactory().post(
        "/api/plugins/proxbox/endpoints/pbs/", {"token_secret": secret}
    )
    request.user = actor

    def fail_store(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("simulated provider failure")

    monkeypatch.setattr(services, "store_credential", fail_store)
    failing = _owner("pbs", actor)
    try:
        with single_secret_mutation_boundary(
            [],
            [request.POST],
            model=type(failing),
            material_field="token_secret",
            actor=actor,
            request=request,
            allow_new=True,
        ):
            _set_material(failing, "pbs", secret)
            failing.save()
    except RuntimeError as exc:
        report = ExceptionReporter(
            request, type(exc), exc, exc.__traceback__
        ).get_traceback_text()
    else:  # pragma: no cover
        raise AssertionError("The injected provider failure did not escape.")

    assert secret not in report
