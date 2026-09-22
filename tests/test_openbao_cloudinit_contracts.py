"""Source contracts for VM cloud-init OpenBao login credentials."""

from __future__ import annotations

import ast
from pathlib import Path

from tests.contract_checks import (
    assert_digest_token_absent,
    assert_import_roots_allowed,
)


ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "netbox_proxbox/models/vm_cloudinit.py"
SERIALIZER = ROOT / "netbox_proxbox/api/serializers/vm_cloudinit.py"
VIEWS = ROOT / "netbox_proxbox/api/views.py"
INTEGRATION = ROOT / "netbox_proxbox/integrations/openbao_cloudinit.py"
GUARDS = ROOT / "netbox_proxbox/integrations/openbao_cloudinit_guards.py"
MIGRATION = ROOT / "netbox_proxbox/migrations/0102_vm_cloudinit_openbao_references.py"
_RETIRED_CONTRACT_DIGEST = (
    "9851abb282006b6aa941f4689303c5a5dc0920ff197d59c9ac62b68261a494b0"
)
_ALLOWED_IMPORT_ROOTS = frozenset(
    {
        "__future__",
        "collections",
        "contextlib",
        "contextvars",
        "dataclasses",
        "django",
        "functools",
        "netbox_openbao",
        "netbox_proxbox",
        "openbao",
        "openbao_cloudinit",
        "openbao_node_request",
        "openbao_single_request",
        "openbao_single_transaction",
        "openbao_single_writer",
        "typing",
        "virtualization",
    }
)


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _class(tree: ast.Module, name: str) -> ast.ClassDef:
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == name
    )


def _meta_fields() -> tuple[str, ...]:
    tree = ast.parse(_source(SERIALIZER))
    serializer = _class(tree, "ProxmoxVMCloudInitSerializer")
    meta = next(
        node
        for node in serializer.body
        if isinstance(node, ast.ClassDef) and node.name == "Meta"
    )
    assignment = next(
        node
        for node in meta.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "fields"
            for target in node.targets
        )
    )
    return ast.literal_eval(assignment.value)


def test_migration_0102_is_additive_idempotent_and_follows_0101() -> None:
    source = _source(MIGRATION)
    tree = ast.parse(source)

    assert '("netbox_proxbox", "0101_single_secret_owner_openbao_references")' in source
    assert source.count("add_field_idempotent(") == 2
    assert '"openbao_password_credential_uuid"' in source
    assert '"openbao_keypair_credential_uuid"' in source
    assert source.count("models.UUIDField(") == 2
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "RunPython"
        for node in ast.walk(tree)
    )


def test_model_has_only_opaque_provider_references_and_explicit_setters() -> None:
    source = _source(MODEL)

    assert "openbao_password_credential_uuid = models.UUIDField(" in source
    assert "openbao_keypair_credential_uuid = models.UUIDField(" in source
    assert "def set_password(" in source
    assert "def set_private_key(" in source
    assert "def get_password(" in source
    assert "def get_private_key(" in source
    assert "password = models." not in source
    assert "private_key = models." not in source


def test_serializer_inputs_are_write_only_and_uuid_references_are_absent() -> None:
    source = _source(SERIALIZER)
    fields = _meta_fields()

    assert "password = serializers.CharField(\n        write_only=True" in source
    assert "private_key = serializers.CharField(\n        write_only=True" in source
    assert "openbao_password_credential_uuid" not in fields
    assert "openbao_keypair_credential_uuid" not in fields
    assert "password_configured" in fields
    assert "private_key_configured" in fields
    assert "credential_assignment_ready" in fields
    assert "credential_assignment_lookup" in fields


def test_public_ssh_key_fields_never_enter_provider_payloads() -> None:
    source = _source(INTEGRATION)

    assert '"password": CloudInitSecretSpec(' in source
    assert '"private_key": CloudInitSecretSpec(' in source
    assert "sshkeys" not in source
    assert "sshkeys_enc" not in source


def test_assignment_contract_targets_vm_login_and_selects_primary_from_ssh_pwauth() -> (
    None
):
    source = _source(INTEGRATION)

    assert '"assigned_object_type": "virtualization.virtualmachine"' in source
    assert '"purpose": "login"' in source
    assert "owner.ssh_pwauth is True" in source
    assert 'references["password"]' in source
    assert 'references["private_key"]' in source
    assert "A foreign primary login assignment already exists" in source


def test_api_owns_outer_create_update_delete_and_bulk_boundaries() -> None:
    source = _source(VIEWS)
    tree = ast.parse(source)
    mixin = _class(tree, "_CloudInitSecretOwnerViewSetMixin")
    methods = {
        node.name
        for node in mixin.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert {"create", "update", "destroy", "bulk_update", "bulk_destroy"} <= methods
    assert "cloudinit_mutation_boundary" in source
    assert "actor=request.user" in source


def test_guards_cover_raw_bulk_cascade_and_storage_downgrade() -> None:
    guard_source = _source(GUARDS)
    shared_source = _source(
        ROOT / "netbox_proxbox/integrations/openbao_single_guards.py"
    )

    assert "guard_cloudinit_update" in guard_source
    assert "guard_cloudinit_bulk" in guard_source
    assert "guard_cloudinit_delete" in guard_source
    assert "sender is VirtualMachine" in guard_source
    assert "any_cloudinit_openbao_state" in shared_source


def test_integration_has_no_private_control_plane_dependency() -> None:
    sources = (_source(INTEGRATION), _source(GUARDS))
    combined = "\n".join(sources)
    assert_digest_token_absent(combined, _RETIRED_CONTRACT_DIGEST)
    for source in sources:
        assert_import_roots_allowed(source, _ALLOWED_IMPORT_ROOTS)
    assert "requests" not in combined
