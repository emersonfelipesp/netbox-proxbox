"""Fast source contracts for typed single-secret OpenBao owners."""

from __future__ import annotations

import ast
from pathlib import Path

from tests.contract_checks import (
    assert_digest_token_absent,
    assert_import_roots_allowed,
)


ROOT = Path(__file__).resolve().parents[1]
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
        "openbao_cloudinit_guards",
        "openbao_single",
        "openbao_single_pending",
        "openbao_single_transaction",
        "openbao_single_writer",
        "typing",
    }
)


def _source(relative: str) -> str:
    return (ROOT / relative).read_text()


def test_migration_adds_one_idempotent_uuid_reference_per_owner() -> None:
    source = _source(
        "netbox_proxbox/migrations/0101_single_secret_owner_openbao_references.py"
    )
    assert source.count("add_field_idempotent(") == 4
    for model, field in (
        ("fastapiendpoint", "openbao_token_credential_uuid"),
        ("pbsendpoint", "openbao_token_credential_uuid"),
        ("pdmendpoint", "openbao_token_credential_uuid"),
        ("firecrackerhost", "openbao_agent_token_credential_uuid"),
    ):
        assert f'"{model}"' in source
        assert f'"{field}"' in source
    assert 'dependencies = [("netbox_proxbox", "0100_' in source


def _single_secret_spec_calls() -> dict[str, ast.AST]:
    tree = ast.parse(_source("netbox_proxbox/integrations/openbao_single_pending.py"))
    specs = next(
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "SPECS"
    )
    if not isinstance(specs, ast.Dict):
        raise AssertionError("SPECS must remain a literal dictionary")
    return {
        ast.literal_eval(key): value
        for key, value in zip(specs.keys, specs.values, strict=True)
    }


def test_specs_pin_type_material_and_assignment_purposes() -> None:
    calls = _single_secret_spec_calls()
    assert set(calls) == {
        "fastapiendpoint",
        "pbsendpoint",
        "pdmendpoint",
        "firecrackerhost",
    }


def test_each_spec_pins_credential_type_and_purpose() -> None:
    expected = {
        "fastapiendpoint": ("api-token", "api"),
        "pbsendpoint": ("api-token", "api"),
        "pdmendpoint": ("api-token", "api"),
        "firecrackerhost": ("api-token", "agent"),
    }
    for name, call in _single_secret_spec_calls().items():
        assert isinstance(call, ast.Call)
        values = tuple(ast.literal_eval(value) for value in call.args[4:6])
        assert values == expected[name]


def test_models_route_reads_and_writes_through_selected_backend() -> None:
    for relative in (
        "netbox_proxbox/models/fastapi_endpoint.py",
        "netbox_proxbox/models/pbs_endpoint.py",
        "netbox_proxbox/models/pdm_endpoint.py",
        "netbox_proxbox/models/firecracker.py",
    ):
        source = _source(relative)
        assert "owner_uses_openbao_storage" in source
        assert "resolve_single_secret" in source
        assert "store_single_secret" in source
    firecracker = _source("netbox_proxbox/api/serializers/firecracker.py")
    assert "agent_token = serializers.CharField(" in firecracker
    assert "write_only=True" in firecracker


def test_openbao_primary_setters_branch_before_fernet_encryption() -> None:
    for relative, setter in (
        ("netbox_proxbox/models/fastapi_endpoint.py", "def token(self, value"),
        ("netbox_proxbox/models/pbs_endpoint.py", "def token_secret(self, value"),
        ("netbox_proxbox/models/pdm_endpoint.py", "def token_secret(self, value"),
    ):
        body = _source(relative).split(setter, 1)[1].split("    @property", 1)[0]
        assert body.index("if owner_uses_openbao_storage(self)") < body.index(
            "encrypt_primary_secret(value)"
        )


def test_rest_and_fastapi_ui_begin_outer_material_boundaries() -> None:
    api = _source("netbox_proxbox/api/views.py")
    assert "class _SingleSecretOwnerViewSetMixin:" in api
    for viewset in (
        "FirecrackerHostViewSet",
        "FastAPIEndpointViewSet",
        "PBSEndpointViewSet",
        "PDMEndpointViewSet",
    ):
        assert f"class {viewset}(_SingleSecretOwnerViewSetMixin" in api
    ui = _source("netbox_proxbox/views/endpoints/fastapi.py")
    assert ui.count("single_secret_mutation_boundary(") >= 3
    quick_edit = _source("netbox_proxbox/views/home_quick_edit.py")
    assert "single_secret_mutation_boundary(" in quick_edit
    assert quick_edit.index("single_secret_mutation_boundary(") < quick_edit.index(
        "form.is_valid()"
    )


def test_fastapi_export_carries_authenticated_material_user() -> None:
    view = _source("netbox_proxbox/views/endpoints/fastapi.py")
    serializer = _source("netbox_proxbox/views/endpoints/fastapi_export.py")
    assert "return user" in view
    assert "material_user=material_user" in view
    assert "user=material_user" in view
    assert "resolve_single_secret(endpoint, user=user)" in serializer


def test_assignment_metadata_is_secret_free_and_vendor_neutral() -> None:
    core = _source("netbox_proxbox/integrations/openbao_single.py")
    lookup_body = core.split("def credential_assignment_lookup", 1)[1].split(
        "def credential_assignment_readiness", 1
    )[0]
    assert "assigned_object_type" in lookup_body
    assert "assigned_object_id" in lookup_body
    assert "purpose" in lookup_body
    assert "material" not in lookup_body
    for relative in (
        "netbox_proxbox/api/serializers/endpoints.py",
        "netbox_proxbox/api/serializers/pbs_pdm.py",
        "netbox_proxbox/api/serializers/firecracker.py",
    ):
        source = _source(relative)
        assert "credential_assignment_ready" in source
        assert "credential_assignment_lookup" in source


def test_fail_closed_guards_cover_raw_bulk_cascade_and_downgrade_paths() -> None:
    guards = _source("netbox_proxbox/integrations/openbao_single_guards.py")
    for marker in (
        "guarded_update",
        "guarded_bulk_update",
        "guarded_bulk_create",
        "guarded_delete",
        "guarded_raw_delete",
        "_guard_parent_delete",
        "_guard_settings_downgrade",
        "_guard_settings_bulk",
    ):
        assert marker in guards
    writer = _source("netbox_proxbox/integrations/openbao_single_writer.py")
    assert "store_credential(" in writer
    assert "cas=credential.kv_version or 0" in writer
    assert "material_transaction" in _source(
        "netbox_proxbox/integrations/openbao_single_transaction.py"
    )
    assert "sensitive_variables" in writer


def test_no_private_or_dynamic_execution_dependency_is_introduced() -> None:
    modules = tuple(
        _source(f"netbox_proxbox/integrations/openbao_single{suffix}.py")
        for suffix in ("", "_pending", "_transaction", "_writer", "_request", "_guards")
    )
    sources = "\n".join(modules)
    assert_digest_token_absent(sources, _RETIRED_CONTRACT_DIGEST)
    for source in modules:
        assert_import_roots_allowed(source, _ALLOWED_IMPORT_ROOTS)
    assert "eval(" not in sources
    assert "exec(" not in sources
    assert "os.system" not in sources
