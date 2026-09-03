"""Execute branch custom-field removal and restoration migration."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from tests.test_hardware_remainder_migration import (
    _Apps,
    _CF,
    _Obj,
    _ObjManager,
    _Schema,
    _install_stub,
)


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "netbox_proxbox"
    / "migrations"
    / "0091_remove_branch_intent_custom_fields.py"
)
PRODUCTION_FIELDS = {
    "apply_to_proxmox": (
        "boolean",
        "yes",
        "Apply this branch to Proxmox",
        (
            "Set to True on a netbox-branching branch to opt that branch into "
            "the NetBox→Proxmox intent pipeline. Default False; merging a branch "
            "with this flag off triggers no Proxmox-side mutation."
        ),
    ),
    "apply_destroy_confirmed": (
        "boolean",
        "yes",
        "Apply destroys allowed for this branch",
        (
            "Set on a netbox-branching branch so DELETE diffs produce "
            "DeletionRequest rows for separate authorization. Default False; "
            "without this flag, DELETE diffs short-circuit at plan time."
        ),
    ),
}


@pytest.fixture
def migration():
    _install_stub()
    spec = importlib.util.spec_from_file_location(
        "migration_0091_branch_intent", MIGRATION_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed():
    apps = _Apps()
    branch_ct = apps.ct_manager.get(app_label="netbox_branching", model="branch")
    for name, (
        field_type,
        ui_editable,
        label,
        description,
    ) in PRODUCTION_FIELDS.items():
        field = _CF(
            name,
            type=field_type,
            ui_editable=ui_editable,
            label=label,
            description=description,
        )
        field.object_types.members.append(branch_ct)
        apps.store[name] = field
    branch = _Obj(
        1,
        {
            "apply_to_proxmox": None,
            "cf_apply_destroy_confirmed": "",
            "keep": "operator-owned",
        },
    )
    apps.obj_managers[("netbox_branching", "Branch")] = _ObjManager([branch])
    return apps, branch


def test_forward_removes_empty_definitions_and_stale_keys(migration):
    apps, branch = _seed()

    migration.remove_branch_intent_custom_fields(apps, _Schema())

    assert apps.store == {}
    assert branch.custom_field_data == {"keep": "operator-owned"}
    manager = apps.obj_managers[("netbox_branching", "Branch")]
    assert manager.select_for_update_calls >= 2
    assert apps.cf_model.objects.last_queryset.locked is True
    assert manager.calls[:3] == ["only", "iterator", "select_for_update"]
    assert manager.calls[-4:] == [
        "select_for_update",
        "only",
        "iterator",
        "bulk_update",
    ]


@pytest.mark.parametrize("value", [False, True, [], {}, [1], {"x": 1}])
def test_any_non_null_non_blank_value_preserves_the_whole_field(migration, value):
    apps, branch = _seed()
    branch.custom_field_data["apply_to_proxmox"] = value

    migration.remove_branch_intent_custom_fields(apps, _Schema())

    assert "apply_to_proxmox" in apps.store
    assert apps.store["apply_to_proxmox"].object_types.removed == []
    assert branch.custom_field_data["apply_to_proxmox"] == value
    assert "apply_destroy_confirmed" not in apps.store


@pytest.mark.parametrize(
    ("attribute", "replacement"),
    [("type", "text"), ("ui_editable", "hidden")],
)
def test_shape_mismatch_preserves_definition_binding_and_key(
    migration,
    attribute,
    replacement,
):
    apps, branch = _seed()
    field = apps.store["apply_to_proxmox"]
    setattr(field, attribute, replacement)

    migration.remove_branch_intent_custom_fields(apps, _Schema())

    assert apps.store["apply_to_proxmox"] is field
    assert field.object_types.removed == []
    assert branch.custom_field_data["apply_to_proxmox"] is None


@pytest.mark.parametrize("value", [False, [], {}])
def test_strip_retests_each_key_and_preserves_late_data(migration, value):
    apps, branch = _seed()
    branch.custom_field_data = {"apply_to_proxmox": value}
    model = apps.get_model("netbox_branching", "Branch")

    migration._strip_values(model, "default", {"apply_to_proxmox"})

    assert branch.custom_field_data == {"apply_to_proxmox": value}
    assert model.objects.bulk_updated == []


def test_reverse_restores_exact_production_definitions_and_binding(migration):
    apps, _branch = _seed()
    migration.remove_branch_intent_custom_fields(apps, _Schema())

    migration.restore_branch_intent_custom_fields(apps, _Schema())

    assert set(apps.store) == set(PRODUCTION_FIELDS)
    for name, (
        field_type,
        ui_editable,
        label,
        description,
    ) in PRODUCTION_FIELDS.items():
        field = apps.store[name]
        assert (field.type, field.ui_editable, field.label, field.description) == (
            field_type,
            ui_editable,
            label,
            description,
        )
        assert field.ui_visible == "always"
        assert field.weight == 100
        assert field.filter_logic == "loose"
        assert field.required is False
        assert field.search_weight == 0
        assert field.group_name == ""
        assert [
            f"{content_type.app_label}.{content_type.model}"
            for content_type in field.object_types.added
        ] == ["netbox_branching.branch"]


def test_forward_and_reverse_are_noops_without_branch_content_type(migration):
    apps, branch = _seed()
    snapshot = dict(apps.store)

    real_get = apps.ct_manager.get

    def missing_branch_content_type(**kwargs):
        if kwargs == {"app_label": "netbox_branching", "model": "branch"}:
            raise apps.ct_model.DoesNotExist
        return real_get(**kwargs)

    apps.ct_manager.get = missing_branch_content_type

    migration.remove_branch_intent_custom_fields(apps, _Schema())
    migration.restore_branch_intent_custom_fields(apps, _Schema())

    assert apps.store == snapshot
    assert branch.custom_field_data == {
        "apply_to_proxmox": None,
        "cf_apply_destroy_confirmed": "",
        "keep": "operator-owned",
    }
