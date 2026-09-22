"""Real-Django setup, idempotence, and assignment-only safety tests."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from threading import Barrier

import pytest

from tests.test_proxmox_endpoint_allowed_tenants import _require_harness

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(
        os.environ.get("NETBOX_PROXBOX_TEST_OPENBAO") != "1",
        reason="requires the exact-source netbox-openbao companion cell",
    ),
]


def _counts() -> tuple[int, int, int, int, int]:
    from django.contrib.auth import get_user_model
    from netbox_openbao.models import (
        Credential,
        CredentialAssignment,
        CredentialPolicy,
        SecretEngine,
    )

    return (
        SecretEngine.objects.count(),
        CredentialPolicy.objects.count(),
        Credential.objects.count(),
        CredentialAssignment.objects.count(),
        get_user_model().objects.count(),
    )


def _configure_service_user(username: str = "openbao-setup") -> None:
    from django.contrib.auth import get_user_model
    from netbox_proxbox.models import ProxboxPluginSettings

    actor = get_user_model().objects.create_user(username=username, is_active=True)
    settings = ProxboxPluginSettings.get_solo()
    settings.openbao_service_username = actor.username
    settings.openbao_policy_slug = "proxbox"
    settings.save()


def _assert_writable_failure_rolls_back(*args: str) -> None:
    from django.core.management import call_command
    from django.core.management.base import CommandError

    before = _counts()
    with pytest.raises(CommandError):
        call_command(
            "proxbox_openbao_setup", *args, stdout=StringIO(), stderr=StringIO()
        )
    assert _counts() == before


def test_check_leaves_database_unchanged(pytestconfig, transactional_db) -> None:
    _require_harness(pytestconfig)
    from django.core.management import call_command
    from django.core.management.base import CommandError

    before = _counts()
    with pytest.raises(CommandError):
        call_command(
            "proxbox_openbao_setup", "--check", stdout=StringIO(), stderr=StringIO()
        )
    assert _counts() == before


def test_setup_is_idempotent_and_never_creates_users_or_credentials(
    pytestconfig, transactional_db
) -> None:
    _require_harness(pytestconfig)
    from django.core.management import call_command

    _configure_service_user()
    call_command(
        "proxbox_openbao_setup",
        "--api-url",
        "https://bao.invalid:8200",
        stdout=StringIO(),
    )
    first = _counts()
    call_command("proxbox_openbao_setup", stdout=StringIO())
    assert _counts() == first
    assert first[2] == 0


def test_writable_setup_rolls_back_when_service_user_is_missing(
    pytestconfig, transactional_db
) -> None:
    _require_harness(pytestconfig)
    _assert_writable_failure_rolls_back("--api-url", "https://bao.invalid:8200")


def test_writable_setup_rolls_back_when_rpc_is_missing(
    pytestconfig, transactional_db
) -> None:
    _require_harness(pytestconfig)
    from django.conf import settings
    from django.test import override_settings

    _configure_service_user("missing-rpc-service")
    plugins = [name for name in settings.PLUGINS if name != "netbox_rpc"]
    with override_settings(PLUGINS=plugins):
        _assert_writable_failure_rolls_back("--api-url", "https://bao.invalid:8200")


def test_writable_setup_rolls_back_on_provider_diagnostic(
    pytestconfig, transactional_db, monkeypatch
) -> None:
    _require_harness(pytestconfig)
    from netbox_proxbox.management.commands import proxbox_openbao_setup
    from netbox_proxbox.services.openbao_readiness import (
        OpenBaoReadiness,
        OpenBaoReadinessItem,
    )

    _configure_service_user("provider-diagnostic-service")
    diagnostic = OpenBaoReadiness(
        (
            OpenBaoReadinessItem(
                "provider_diagnostic",
                "Provider diagnostic",
                False,
                "The provider model API is unavailable (diagnostic).",
                "Repair the provider installation.",
            ),
        )
    )
    monkeypatch.setattr(proxbox_openbao_setup, "openbao_readiness", lambda: diagnostic)
    _assert_writable_failure_rolls_back("--api-url", "https://bao.invalid:8200")


def test_writable_setup_without_api_url_writes_nothing(
    pytestconfig, transactional_db
) -> None:
    _require_harness(pytestconfig)
    _configure_service_user("missing-url-service")
    _assert_writable_failure_rolls_back()


def test_backfill_adds_only_missing_relation_and_is_idempotent(
    pytestconfig, transactional_db
) -> None:
    _require_harness(pytestconfig)
    from django.contrib.auth import get_user_model
    from django.core.management import call_command
    from django.db import connection
    from netbox_openbao.models import (
        Credential,
        CredentialAssignment,
        CredentialPolicy,
        SecretEngine,
    )
    from netbox_proxbox.models import ProxmoxEndpoint, ProxboxPluginSettings

    engine = SecretEngine.objects.create(
        name="Backfill",
        slug="backfill",
        api_url="https://bao.invalid:8200",
        is_default=True,
    )
    policy = CredentialPolicy.objects.create(
        name="Proxbox", slug="proxbox", engine=engine, openbao_policy="proxbox"
    )
    credential = Credential.objects.create(
        name="Existing token", credential_type="api-token", policy=policy, engine=engine
    )
    endpoint = ProxmoxEndpoint.objects.create(name="Backfill endpoint", enabled=False)
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE netbox_proxbox_proxmoxendpoint "
            "SET openbao_token_credential_uuid = %s WHERE id = %s",
            [str(credential.uuid), endpoint.pk],
        )
    actor = get_user_model().objects.create_user(
        username="backfill-service", is_active=True
    )
    settings = ProxboxPluginSettings.get_solo()
    settings.openbao_service_username = actor.username
    settings.openbao_policy_slug = policy.slug
    settings.save()
    snapshot = (credential.path, credential.kv_version, credential.live_kv_version)
    call_command("proxbox_openbao_setup", "--backfill-assignments", stdout=StringIO())
    assignment = CredentialAssignment.objects.get()
    assignment.description = "operator-owned annotation"
    assignment.save(update_fields=["description"])
    assignment_pk = assignment.pk
    call_command("proxbox_openbao_setup", "--backfill-assignments", stdout=StringIO())
    credential.refresh_from_db()
    assignment.refresh_from_db()
    assert CredentialAssignment.objects.count() == 1
    assert assignment.pk == assignment_pk
    assert assignment.enabled is True
    assert assignment.is_primary is True
    assert assignment.description == "operator-owned annotation"
    assert (
        credential.path,
        credential.kv_version,
        credential.live_kv_version,
    ) == snapshot


def _endpoint_assignment_case(*, credential_type: str = "api-token"):
    from django.contrib.contenttypes.models import ContentType
    from django.db import connection
    from netbox_openbao.models import Credential, CredentialPolicy, SecretEngine
    from netbox_proxbox.models import ProxmoxEndpoint

    engine = SecretEngine.objects.create(
        name="Assignment invariant",
        slug="assignment-invariant",
        api_url="https://bao.invalid:8200",
        is_default=True,
    )
    policy = CredentialPolicy.objects.create(
        name="Proxbox", slug="proxbox", engine=engine, openbao_policy="proxbox"
    )
    credential = Credential.objects.create(
        name="Referenced credential",
        credential_type=credential_type,
        policy=policy,
        engine=engine,
    )
    endpoint = ProxmoxEndpoint.objects.create(name="Invariant endpoint", enabled=False)
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE netbox_proxbox_proxmoxendpoint "
            "SET openbao_token_credential_uuid = %s WHERE id = %s",
            [str(credential.uuid), endpoint.pk],
        )
    _configure_service_user("assignment-invariant-service")
    content_type = ContentType.objects.get_for_model(endpoint)
    return credential, endpoint, content_type, policy


def test_backfill_refuses_exact_non_primary_and_foreign_primary(
    pytestconfig, transactional_db
) -> None:
    _require_harness(pytestconfig)
    from django.core.management import call_command
    from django.core.management.base import CommandError
    from netbox_openbao.models import Credential, CredentialAssignment

    credential, endpoint, content_type, policy = _endpoint_assignment_case()
    exact = CredentialAssignment.objects.create(
        credential=credential,
        assigned_object_type=content_type,
        assigned_object_id=endpoint.pk,
        purpose="api",
        is_primary=False,
    )
    foreign = Credential.objects.create(
        name="Foreign primary",
        credential_type="api-token",
        policy=policy,
        engine=policy.engine,
    )
    CredentialAssignment.objects.create(
        credential=foreign,
        assigned_object_type=content_type,
        assigned_object_id=endpoint.pk,
        purpose="api",
        is_primary=True,
    )
    with pytest.raises(CommandError) as excinfo:
        call_command(
            "proxbox_openbao_setup",
            "--backfill-assignments",
            stdout=StringIO(),
            stderr=StringIO(),
        )
    assert "must be primary" in str(excinfo.value)
    assert str(credential.uuid) not in str(excinfo.value)
    exact.refresh_from_db()
    assert exact.is_primary is False
    assert CredentialAssignment.objects.count() == 2


def test_backfill_refuses_disabled_exact_assignment(
    pytestconfig, transactional_db
) -> None:
    _require_harness(pytestconfig)
    from django.core.management import call_command
    from django.core.management.base import CommandError
    from netbox_openbao.models import CredentialAssignment

    credential, endpoint, content_type, _policy = _endpoint_assignment_case()
    exact = CredentialAssignment.objects.create(
        credential=credential,
        assigned_object_type=content_type,
        assigned_object_id=endpoint.pk,
        purpose="api",
        is_primary=True,
        enabled=False,
    )
    with pytest.raises(CommandError) as excinfo:
        call_command(
            "proxbox_openbao_setup",
            "--backfill-assignments",
            stdout=StringIO(),
            stderr=StringIO(),
        )
    assert "is disabled" in str(excinfo.value)
    assert str(credential.uuid) not in str(excinfo.value)
    exact.refresh_from_db()
    assert exact.enabled is False


def test_backfill_refuses_endpoint_credential_type_mismatch(
    pytestconfig, transactional_db
) -> None:
    _require_harness(pytestconfig)
    from django.core.management import call_command
    from django.core.management.base import CommandError
    from netbox_openbao.models import CredentialAssignment

    credential, _endpoint, _content_type, _policy = _endpoint_assignment_case(
        credential_type="password"
    )
    with pytest.raises(CommandError) as excinfo:
        call_command(
            "proxbox_openbao_setup",
            "--backfill-assignments",
            stdout=StringIO(),
            stderr=StringIO(),
        )
    assert "incompatible type" in str(excinfo.value)
    assert str(credential.uuid) not in str(excinfo.value)
    assert CredentialAssignment.objects.count() == 0


def test_final_readiness_failure_rolls_back_backfill_rows(
    pytestconfig, transactional_db
) -> None:
    _require_harness(pytestconfig)
    from django.conf import settings
    from django.core.management import call_command
    from django.core.management.base import CommandError
    from django.db import connection
    from django.test import override_settings
    from netbox_openbao.models import (
        Credential,
        CredentialAssignment,
        CredentialPolicy,
        SecretEngine,
    )
    from netbox_proxbox.models import ProxmoxEndpoint

    engine = SecretEngine.objects.create(
        name="Rollback backfill",
        slug="rollback-backfill",
        api_url="https://bao.invalid:8200",
        is_default=True,
    )
    policy = CredentialPolicy.objects.create(
        name="Proxbox", slug="proxbox", engine=engine, openbao_policy="proxbox"
    )
    credential = Credential.objects.create(
        name="Rollback token",
        credential_type="api-token",
        policy=policy,
        engine=engine,
    )
    endpoint = ProxmoxEndpoint.objects.create(name="Rollback endpoint", enabled=False)
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE netbox_proxbox_proxmoxendpoint "
            "SET openbao_token_credential_uuid = %s WHERE id = %s",
            [str(credential.uuid), endpoint.pk],
        )
    _configure_service_user("rollback-backfill-service")
    plugins = [name for name in settings.PLUGINS if name != "netbox_rpc"]
    with override_settings(PLUGINS=plugins), pytest.raises(CommandError):
        call_command(
            "proxbox_openbao_setup",
            "--backfill-assignments",
            stdout=StringIO(),
            stderr=StringIO(),
        )
    assert CredentialAssignment.objects.count() == 0


def _node_backfill_case(
    *,
    linked: bool,
    selected_reference: bool,
    credential_type: str | None = None,
):
    from django.db import connection
    from netbox_openbao.models import Credential, CredentialPolicy, SecretEngine
    from netbox_proxbox.models import (
        NodeSSHCredential,
        ProxmoxEndpoint,
        ProxmoxNode,
    )
    from netbox_proxbox.models.ssh_credential import AUTH_METHOD_PASSWORD

    engine = SecretEngine.objects.create(
        name="Node backfill",
        slug="node-backfill",
        api_url="https://bao.invalid:8200",
        is_default=True,
    )
    policy = CredentialPolicy.objects.create(
        name="Proxbox", slug="proxbox", engine=engine, openbao_policy="proxbox"
    )
    selected_type = credential_type or (
        "ssh-password" if selected_reference else "ssh-keypair"
    )
    credential = Credential.objects.create(
        name="Existing node credential",
        credential_type=selected_type,
        policy=policy,
        engine=engine,
    )
    device = None
    if linked:
        from utilities.testing import create_test_device

        device = create_test_device("OpenBao setup node")
    endpoint = ProxmoxEndpoint.objects.create(name="Node endpoint", enabled=False)
    node = ProxmoxNode.objects.create(
        endpoint=endpoint,
        netbox_device=device,
        name="Node backfill",
        ip_address="127.0.0.1",
    )
    owner = NodeSSHCredential.objects.create(
        node=node,
        username="proxbox-discovery",
        auth_method=AUTH_METHOD_PASSWORD,
        known_host_fingerprint="SHA256:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    )
    with connection.cursor() as cursor:
        if selected_reference:
            cursor.execute(
                "UPDATE netbox_proxbox_nodesshcredential "
                "SET openbao_password_credential_uuid = %s WHERE id = %s",
                [str(credential.uuid), owner.pk],
            )
        else:
            cursor.execute(
                "UPDATE netbox_proxbox_nodesshcredential "
                "SET openbao_keypair_credential_uuid = %s WHERE id = %s",
                [str(credential.uuid), owner.pk],
            )
    _configure_service_user("node-backfill-service")
    return credential


@pytest.mark.parametrize(
    ("linked", "selected_reference", "expected"),
    [
        (False, True, "no linked NetBox device"),
        (True, False, "selected authentication reference is missing"),
    ],
)
def test_node_backfill_refuses_incomplete_ownership_without_material_details(
    pytestconfig,
    transactional_db,
    linked,
    selected_reference,
    expected,
) -> None:
    _require_harness(pytestconfig)
    from django.core.management import call_command
    from django.core.management.base import CommandError
    from netbox_openbao.models import CredentialAssignment

    credential = _node_backfill_case(
        linked=linked,
        selected_reference=selected_reference,
    )
    with pytest.raises(CommandError) as excinfo:
        call_command(
            "proxbox_openbao_setup",
            "--backfill-assignments",
            stdout=StringIO(),
            stderr=StringIO(),
        )
    message = str(excinfo.value)
    assert expected in message
    assert str(credential.uuid) not in message
    assert CredentialAssignment.objects.count() == 0


def test_node_backfill_refuses_selected_credential_type_mismatch(
    pytestconfig, transactional_db
) -> None:
    _require_harness(pytestconfig)
    from django.core.management import call_command
    from django.core.management.base import CommandError
    from netbox_openbao.models import CredentialAssignment

    credential = _node_backfill_case(
        linked=True,
        selected_reference=True,
        credential_type="ssh-keypair",
    )
    with pytest.raises(CommandError) as excinfo:
        call_command(
            "proxbox_openbao_setup",
            "--backfill-assignments",
            stdout=StringIO(),
            stderr=StringIO(),
        )
    assert "incompatible type" in str(excinfo.value)
    assert str(credential.uuid) not in str(excinfo.value)
    assert CredentialAssignment.objects.count() == 0


def test_concurrent_backfill_creates_one_assignment(
    pytestconfig, transactional_db, monkeypatch
) -> None:
    _require_harness(pytestconfig)
    from django.db import close_old_connections, connection
    from netbox_openbao.models import (
        Credential,
        CredentialAssignment,
        CredentialPolicy,
        SecretEngine,
    )
    from netbox_proxbox.models import ProxmoxEndpoint
    from netbox_proxbox.services import openbao_assignment_backfill as service

    engine = SecretEngine.objects.create(
        name="Concurrent backfill",
        slug="concurrent-backfill",
        api_url="https://bao.invalid:8200",
        is_default=True,
    )
    policy = CredentialPolicy.objects.create(
        name="Proxbox", slug="proxbox", engine=engine, openbao_policy="proxbox"
    )
    credential = Credential.objects.create(
        name="Concurrent token",
        credential_type="api-token",
        policy=policy,
        engine=engine,
    )
    endpoint = ProxmoxEndpoint.objects.create(name="Concurrent endpoint", enabled=False)
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE netbox_proxbox_proxmoxendpoint "
            "SET openbao_token_credential_uuid = %s WHERE id = %s",
            [str(credential.uuid), endpoint.pk],
        )

    original = service.assignment_proposals
    barrier = Barrier(2)

    def synchronized_proposals():
        proposals = original()
        barrier.wait(timeout=10)
        return proposals

    monkeypatch.setattr(service, "assignment_proposals", synchronized_proposals)

    def run_backfill() -> int:
        close_old_connections()
        try:
            return service.backfill_assignments().created
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = sorted(executor.map(lambda _index: run_backfill(), range(2)))
    assert results == [0, 1]
    assert CredentialAssignment.objects.count() == 1
