"""Source contracts for the ProxmoxEndpoint.environment field (#438).

These pin the operator-selected lifecycle stage that issue #438 added to
``ProxmoxEndpoint``. The field is manual classification only; sync paths must
never write it. The tests run via ``ast.parse`` so they do not require a live
Django/NetBox bootstrap.

Pinned wiring:
- The ``ProxmoxEndpointEnvironmentChoices`` choice set exists with the agreed
  slugs and is keyed for plugin admin override (``ProxmoxEndpoint.environment``).
- The ``environment`` model field is a nullable ``CharField`` with
  ``blank=True`` so the field is optional in forms and admin.
- A new ``0045_proxmoxendpoint_environment`` additive migration registers the
  column on top of ``0044_cloud_image_template``.
- The form, filterset, table, serializer, and template all surface the new
  field next to ``mode``.
- The plugin's sync paths never overwrite the field (regex grep over the
  ``netbox_proxbox/services`` and ``netbox_proxbox/proxmox_to_netbox``-style
  source trees).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "netbox_proxbox"

CHOICES_PATH = PLUGIN_ROOT / "choices.py"
MODEL_PATH = PLUGIN_ROOT / "models" / "proxmox_endpoint.py"
MIGRATION_PATH = PLUGIN_ROOT / "migrations" / "0045_proxmoxendpoint_environment.py"
FORM_PATH = PLUGIN_ROOT / "forms" / "proxmox.py"
FILTERSET_PATH = PLUGIN_ROOT / "filtersets.py"
TABLE_PATH = PLUGIN_ROOT / "tables" / "__init__.py"
SERIALIZER_PATH = PLUGIN_ROOT / "api" / "serializers" / "endpoints.py"
TEMPLATE_PATH = (
    PLUGIN_ROOT / "templates" / "netbox_proxbox" / "proxmoxendpoint.html"
)

EXPECTED_SLUGS = {
    "production",
    "staging",
    "development",
    "homologation",
    "testing",
    "lab",
}


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text())


def _find_class(module: ast.Module, name: str) -> ast.ClassDef:
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"Class {name!r} not found in {module}")


def _class_assign(cls: ast.ClassDef, name: str) -> ast.AST:
    for node in cls.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return node.value
    raise AssertionError(f"Assignment {name!r} not found in class {cls.name}")


def _meta_fields(cls: ast.ClassDef) -> str:
    for node in cls.body:
        if isinstance(node, ast.ClassDef) and node.name == "Meta":
            for stmt in node.body:
                if isinstance(stmt, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "fields" for t in stmt.targets
                ):
                    return ast.unparse(stmt.value)
    raise AssertionError(f"Meta.fields not found on class {cls.name}")


# ---------------------------------------------------------------------------
# Choice set
# ---------------------------------------------------------------------------


def test_environment_choice_set_exists_with_expected_slugs() -> None:
    """The choice set must enumerate the agreed lifecycle slugs.

    Slugs may be referenced through class-level constants (e.g. ``PRODUCTION``),
    so collect the string assignments on the class and compare the resulting
    set of slug values to the expected set.
    """
    cls = _find_class(_parse(CHOICES_PATH), "ProxmoxEndpointEnvironmentChoices")
    slug_constants: dict[str, str] = {}
    for node in cls.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)
                    and target.id != "key"
                ):
                    slug_constants[target.id] = node.value.value
    declared_slugs = set(slug_constants.values())
    assert EXPECTED_SLUGS.issubset(declared_slugs), (
        f"Choice set missing slugs: {EXPECTED_SLUGS - declared_slugs}"
    )


def test_environment_choice_set_uses_admin_override_key() -> None:
    """The choice set must declare the NetBox admin-override key."""
    cls = _find_class(_parse(CHOICES_PATH), "ProxmoxEndpointEnvironmentChoices")
    key = _class_assign(cls, "key")
    assert isinstance(key, ast.Constant) and key.value == "ProxmoxEndpoint.environment"


# ---------------------------------------------------------------------------
# Model field
# ---------------------------------------------------------------------------


def test_environment_field_is_optional_charfield() -> None:
    """``environment`` must be a nullable, blank=True CharField with choices."""
    src = MODEL_PATH.read_text()
    assert "environment = models.CharField(" in src
    block = src.split("environment = models.CharField(", 1)[1].split(")", 1)[0]
    assert "blank=True" in block
    assert "null=True" in block
    assert "choices=ProxmoxEndpointEnvironmentChoices" in block
    assert "max_length=32" in block


def test_environment_field_imported_in_model() -> None:
    """The model module must import the new choice class."""
    src = MODEL_PATH.read_text()
    assert "ProxmoxEndpointEnvironmentChoices" in src
    assert "from netbox_proxbox.choices import" in src


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


def test_migration_exists_and_chains_after_0044() -> None:
    """0045 must depend on 0044 and add the environment column additively."""
    assert MIGRATION_PATH.exists(), (
        "Migration 0045_proxmoxendpoint_environment.py is missing"
    )
    src = MIGRATION_PATH.read_text()
    assert '("netbox_proxbox", "0044_cloud_image_template")' in src
    assert "migrations.AddField(" in src
    assert 'name="environment"' in src
    assert "model_name=\"proxmoxendpoint\"" in src
    assert "blank=True" in src
    assert "null=True" in src


def test_migration_uses_plain_addfield_not_separate_state() -> None:
    """A brand-new column does not need SeparateDatabaseAndState gymnastics."""
    src = MIGRATION_PATH.read_text()
    assert "SeparateDatabaseAndState" not in src
    assert "RunSQL" not in src


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------


def test_environment_in_edit_form_meta_fields() -> None:
    """``ProxmoxEndpointForm.Meta.fields`` must include ``environment``."""
    cls = _find_class(_parse(FORM_PATH), "ProxmoxEndpointForm")
    assert "'environment'" in _meta_fields(cls) or '"environment"' in _meta_fields(cls)


def test_environment_filter_form_field_exists() -> None:
    """``ProxmoxEndpointFilterForm`` must expose ``environment`` as a multi-choice filter."""
    src = FORM_PATH.read_text()
    assert "environment = forms.MultipleChoiceField(" in src
    assert "ProxmoxEndpointEnvironmentChoices" in src


def test_environment_in_import_form_meta_fields() -> None:
    """``ProxmoxEndpointImportForm`` must accept ``environment`` from CSV."""
    cls = _find_class(_parse(FORM_PATH), "ProxmoxEndpointImportForm")
    assert "'environment'" in _meta_fields(cls) or '"environment"' in _meta_fields(cls)
    assert "environment = CSVChoiceField(" in FORM_PATH.read_text()


# ---------------------------------------------------------------------------
# Filterset
# ---------------------------------------------------------------------------


def test_environment_in_filterset_meta_fields() -> None:
    """``ProxmoxEndpointFilterSet.Meta.fields`` must include ``environment``."""
    cls = _find_class(_parse(FILTERSET_PATH), "ProxmoxEndpointFilterSet")
    rendered = _meta_fields(cls)
    assert "'environment'" in rendered or '"environment"' in rendered


# ---------------------------------------------------------------------------
# Table
# ---------------------------------------------------------------------------


def test_environment_column_and_default_columns() -> None:
    """``ProxmoxEndpointTable`` must declare an ``environment`` ChoiceFieldColumn
    and include it in both ``Meta.fields`` and ``Meta.default_columns``."""
    src = TABLE_PATH.read_text()
    assert "environment = ChoiceFieldColumn()" in src
    cls = _find_class(_parse(TABLE_PATH), "ProxmoxEndpointTable")
    for node in cls.body:
        if isinstance(node, ast.ClassDef) and node.name == "Meta":
            fields_seen = False
            defaults_seen = False
            for stmt in node.body:
                if not isinstance(stmt, ast.Assign):
                    continue
                target = stmt.targets[0]
                if not isinstance(target, ast.Name):
                    continue
                rendered = ast.unparse(stmt.value)
                if target.id == "fields":
                    assert "'environment'" in rendered or '"environment"' in rendered
                    fields_seen = True
                if target.id == "default_columns":
                    assert "'environment'" in rendered or '"environment"' in rendered
                    defaults_seen = True
            assert fields_seen and defaults_seen, (
                "ProxmoxEndpointTable Meta missing environment in fields or default_columns"
            )
            return
    raise AssertionError("ProxmoxEndpointTable.Meta not found")


# ---------------------------------------------------------------------------
# API serializer
# ---------------------------------------------------------------------------


def test_environment_in_api_serializer_meta_fields() -> None:
    """``ProxmoxEndpointSerializer.Meta.fields`` must include ``environment``
    and the field must accept blank/null on writes."""
    src = SERIALIZER_PATH.read_text()
    assert "environment = ChoiceField(" in src
    assert "ProxmoxEndpointEnvironmentChoices" in src
    cls = _find_class(_parse(SERIALIZER_PATH), "ProxmoxEndpointSerializer")
    rendered = _meta_fields(cls)
    assert "'environment'" in rendered or '"environment"' in rendered
    # Permissive on writes — operator may clear it back to blank.
    serializer_block = src.split("environment = ChoiceField(", 1)[1].split(")", 1)[0]
    assert "allow_null=True" in serializer_block
    assert "allow_blank=True" in serializer_block
    assert "required=False" in serializer_block


# ---------------------------------------------------------------------------
# Template
# ---------------------------------------------------------------------------


def test_environment_template_row_renders_under_mode() -> None:
    """The detail template must render an Environment row right after Mode."""
    src = TEMPLATE_PATH.read_text()
    assert "Environment" in src
    assert "object.environment" in src
    mode_idx = src.index('scope="row">Mode<')
    env_idx = src.index('scope="row">Environment<')
    assert env_idx > mode_idx, "Environment row must come after Mode row"


# ---------------------------------------------------------------------------
# Sync invariant — environment is operator-only, never written by sync
# ---------------------------------------------------------------------------


SYNC_DIRS = (
    PLUGIN_ROOT / "services",
    PLUGIN_ROOT / "schemas",
    PLUGIN_ROOT / "sync_stages.py",
    PLUGIN_ROOT / "sync_params.py",
    PLUGIN_ROOT / "sync_types.py",
    PLUGIN_ROOT / "jobs.py",
)
ASSIGNMENT_RE = re.compile(
    r"\.environment\s*=|environment\s*=\s*[^=]|['\"]environment['\"]\s*[:=]"
)


def _iter_sync_files() -> list[Path]:
    files: list[Path] = []
    for entry in SYNC_DIRS:
        if entry.is_file():
            files.append(entry)
        elif entry.is_dir():
            files.extend(p for p in entry.rglob("*.py"))
    return files


def test_sync_paths_never_write_environment() -> None:
    """Issue #438 contract: environment is manual-only.

    The sync-side modules must never assign or serialize it."""
    offenders: list[str] = []
    for path in _iter_sync_files():
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if ASSIGNMENT_RE.search(line):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Sync paths must never write ProxmoxEndpoint.environment:\n"
        + "\n".join(offenders)
    )
