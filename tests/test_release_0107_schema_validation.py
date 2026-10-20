"""Dependency-light catalog and deferred-DDL contracts for release 0107."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, Mock, call

import pytest


@pytest.fixture
def validator() -> ModuleType:
    source = (
        Path(__file__).parents[1] / "netbox_proxbox/migrations/_release_0107_schema.py"
    )
    spec = importlib.util.spec_from_file_location("release_schema_under_test", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def index() -> dict:
    return dict(
        oid=1,
        columns=["netbox_cluster_id"],
        unique=True,
        valid=True,
        ready=True,
        live=True,
        unconditional=True,
        simple=True,
        nulls_distinct=True,
        references=["netbox_cluster_id"],
        whole_row=False,
    )


@pytest.mark.parametrize(
    "change",
    [
        {"unique": False},
        {"valid": False},
        {"ready": False},
        {"live": False},
        {"unconditional": False},
        {"simple": False},
        {"nulls_distinct": False},
        {"columns": ["netbox_cluster_id", "id"]},
        {"columns": [None]},
    ],
)
def test_incompatible_index_cannot_establish_ownership(
    validator, index, change
) -> None:
    index.update(change)
    with pytest.raises(validator.ReleaseSchemaError, match="enforcing index"):
        validator._require_index(
            {"indexes": [index]}, "endpoint", ("netbox_cluster_id",), unique=True
        )


def test_valid_unique_index_establishes_ownership(validator, index) -> None:
    validator._require_index(
        {"indexes": [index]}, "endpoint", ("netbox_cluster_id",), unique=True
    )


@pytest.mark.parametrize("version, count", [(140000, 3), (150000, 4)])
def test_catalog_never_parses_new_column_on_postgresql_14(
    validator, monkeypatch, version, count
) -> None:
    cursor = Mock()
    cursor.db.pg_version = version
    rows = Mock(return_value=[])
    monkeypatch.setattr(validator, "_rows", rows)
    validator._catalog(cursor, "endpoint")
    queries = [call.args[1] for call in rows.call_args_list]
    assert len(queries) == count
    assert any("indnullsnotdistinct" in sql for sql in queries) == (version >= 150000)


@pytest.fixture
def foreign_key() -> dict:
    return dict(
        kind="f",
        columns=["netbox_cluster_id"],
        target=42,
        target_columns=["id"],
        validated=True,
        deferrable=True,
        deferred=True,
        triggers=True,
        delete_action="a",
        update_action="a",
        match="s",
    )


def _target_field() -> SimpleNamespace:
    return SimpleNamespace(
        column="netbox_cluster_id",
        target_field=SimpleNamespace(
            column="id",
            model=SimpleNamespace(
                _meta=SimpleNamespace(db_table="virtualization_cluster")
            ),
        ),
    )


@pytest.mark.parametrize(
    "change",
    [
        {"target": 99},
        {"target_columns": ["other"]},
        {"validated": False},
        {"triggers": False},
        {"deferrable": False},
        {"deferred": False},
        {"delete_action": "c"},
        {"columns": ["netbox_cluster_id", "id"]},
    ],
)
def test_wrong_or_unvalidated_foreign_key_is_refused(
    validator, foreign_key, change
) -> None:
    foreign_key.update(change)
    cursor = Mock()
    cursor.fetchone.return_value = (42,)
    with pytest.raises(validator.ReleaseSchemaError, match="incompatible foreign key"):
        validator._require_foreign_key(
            cursor, {"constraints": [foreign_key]}, "endpoint", _target_field()
        )


def test_valid_foreign_key_is_accepted(validator, foreign_key) -> None:
    cursor = Mock()
    cursor.fetchone.return_value = (42,)
    validator._require_foreign_key(
        cursor, {"constraints": [foreign_key]}, "endpoint", _target_field()
    )


def test_missing_foreign_key_is_refused(validator) -> None:
    cursor = Mock()
    cursor.fetchone.return_value = (42,)
    with pytest.raises(validator.ReleaseSchemaError, match="missing foreign key"):
        validator._require_foreign_key(
            cursor, {"constraints": []}, "endpoint", _target_field()
        )


def _editor() -> SimpleNamespace:
    return SimpleNamespace(
        connection=SimpleNamespace(vendor="postgresql", in_atomic_block=True),
        atomic_migration=True,
        deferred_sql=["first", "second"],
        execute=Mock(),
    )


@pytest.fixture
def isolated_lock(validator, monkeypatch) -> SimpleNamespace:
    lock = Mock(return_value="0")
    restore = Mock()
    monkeypatch.setattr(validator, "_lock_release_tables", lock)
    monkeypatch.setattr(validator, "_restore_lock_timeout", restore)
    return SimpleNamespace(lock=lock, restore=restore)


def test_finalizer_drains_queue_before_validation_and_emits_pending_commit_receipt(
    validator, monkeypatch, capsys, isolated_lock
) -> None:
    editor = _editor()
    validate = Mock()
    events = Mock()
    events.attach_mock(editor.execute, "ddl")
    events.attach_mock(validate, "validate")
    events.attach_mock(isolated_lock.lock, "lock")
    events.attach_mock(isolated_lock.restore, "restore")
    monkeypatch.setattr(validator, "validate_release_schema", validate)
    validator.finalize_release_schema(None, editor)
    assert events.mock_calls == [
        call.lock(None, editor),
        call.ddl("first", None),
        call.ddl("second", None),
        call.validate(None, editor),
        call.restore(editor, "0"),
    ]
    assert not editor.deferred_sql
    validate.assert_called_once_with(None, editor)
    assert validator.RECEIPT in capsys.readouterr().out


def test_deferred_sql_failure_prevents_validation_and_receipt(
    validator, monkeypatch, capsys, isolated_lock
) -> None:
    editor = _editor()
    editor.execute.side_effect = RuntimeError("injected DDL failure")
    validate = Mock()
    monkeypatch.setattr(validator, "validate_release_schema", validate)
    with pytest.raises(RuntimeError, match="injected DDL failure"):
        validator.finalize_release_schema(None, editor)
    validate.assert_not_called()
    assert capsys.readouterr().out == ""


def test_postcondition_failure_never_emits_success(
    validator, monkeypatch, capsys, isolated_lock
) -> None:
    editor = _editor()
    monkeypatch.setattr(
        validator,
        "validate_release_schema",
        Mock(side_effect=validator.ReleaseSchemaError("malformed")),
    )
    with pytest.raises(validator.ReleaseSchemaError, match="malformed"):
        validator.finalize_release_schema(None, editor)
    assert capsys.readouterr().out == ""


def test_newly_queued_ddl_is_never_discarded(
    validator, monkeypatch, capsys, isolated_lock
) -> None:
    editor = _editor()

    def append_unchecked(*_args: object) -> None:
        editor.deferred_sql.append("unexpected")

    editor.execute.side_effect = append_unchecked
    validate = Mock()
    monkeypatch.setattr(validator, "validate_release_schema", validate)
    with pytest.raises(validator.ReleaseSchemaError, match="unchecked SQL"):
        validator.finalize_release_schema(None, editor)
    validate.assert_not_called()
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "change", [{"type": "integer"}, {"nullable": False}, {"generated": "s"}]
)
def test_incompatible_column_is_refused(validator, change) -> None:
    field = Mock(column="netbox_cluster_id", null=True)
    field.db_type.return_value = "bigint"
    field.db_parameters.return_value = {}
    actual = dict(
        type="bigint",
        nullable=True,
        generated="",
        default=None,
        identity="",
        sequence=None,
    )
    actual.update(change)
    with pytest.raises(validator.ReleaseSchemaError):
        validator._require_column(
            {"columns": {field.column: actual}}, "endpoint", field, Mock()
        )


def test_plain_integer_primary_key_without_generation_is_refused(validator) -> None:
    field = Mock(column="id")
    field.get_internal_type.return_value = "BigAutoField"
    with pytest.raises(validator.ReleaseSchemaError, match="generated ID"):
        validator._require_default(
            dict(identity="", sequence=None, default=None), "service", field
        )


def test_wrong_declared_constraint_cannot_borrow_an_unrelated_index(
    validator, index
) -> None:
    catalog = dict(
        indexes=[index],
        constraints=[
            dict(
                kind="u",
                columns=["netbox_cluster_id"],
                validated=True,
                name="expected",
                index=99,
            )
        ],
    )
    with pytest.raises(validator.ReleaseSchemaError, match="enforcing index"):
        validator._require_key(
            catalog, "endpoint", ("netbox_cluster_id",), name="expected"
        )


@pytest.mark.parametrize(
    "change",
    [{"atomic_migration": False}, {"in_atomic_block": False}, {"vendor": "sqlite"}],
)
def test_finalizer_refuses_unsupported_transaction(validator, change) -> None:
    editor = _editor()
    if "atomic_migration" in change:
        editor.atomic_migration = change["atomic_migration"]
    else:
        for name, value in change.items():
            setattr(editor.connection, name, value)
    with pytest.raises(validator.ReleaseSchemaError):
        validator.finalize_release_schema(None, editor)
    editor.execute.assert_not_called()


def _enforcement_model() -> tuple[SimpleNamespace, list[SimpleNamespace]]:
    ownership = SimpleNamespace(
        column="netbox_cluster_id",
        unique=True,
        primary_key=False,
        is_relation=True,
        db_constraint=True,
    )
    username = SimpleNamespace(
        column="username", unique=False, primary_key=False, is_relation=False
    )
    model = SimpleNamespace(
        _meta=SimpleNamespace(db_table="endpoint", unique_together=(), constraints=[])
    )
    return model, [ownership, username]


@pytest.mark.parametrize(
    "change",
    [
        {"nulls_distinct": False},
        {"columns": ["username"], "references": ["username"]},
        {"columns": [None], "references": ["netbox_cluster_id"], "simple": False},
        {
            "columns": ["username"],
            "references": ["netbox_cluster_id"],
            "unconditional": False,
        },
    ],
)
def test_good_unique_never_masks_conflicting_additional_enforcement(
    validator, index, change
) -> None:
    model, fields = _enforcement_model()
    extra = {**index, **change, "oid": 2}
    with pytest.raises(validator.ReleaseSchemaError, match="additional unique"):
        validator._reject_extra_unique_indexes(
            dict(indexes=[index, extra]), model, fields, whole_table=True
        )


@pytest.mark.parametrize("kind", ["c", "x"])
def test_extra_constraint_on_owned_field_is_refused(validator, kind) -> None:
    model, fields = _enforcement_model()
    row = dict(kind=kind, columns=["netbox_cluster_id"], references=[], whole_row=False)
    with pytest.raises(
        validator.ReleaseSchemaError, match="additional check or exclusion"
    ):
        validator._reject_extra_constraints(
            dict(constraints=[row]), model, fields, whole_table=False
        )


def test_unrelated_endpoint_constraints_remain_allowed(validator, index) -> None:
    model, fields = _enforcement_model()
    owned = fields[:1]
    other = {**index, "columns": ["username"], "references": ["username"]}
    catalog = dict(
        indexes=[other],
        constraints=[
            dict(kind="c", columns=["username"], references=[], whole_row=False)
        ],
    )
    validator._reject_extra_unique_indexes(catalog, model, owned, whole_table=False)
    validator._reject_extra_constraints(catalog, model, owned, whole_table=False)


@pytest.mark.parametrize(
    "current, expected", [(0, "5000ms"), (100, "100ms"), (10000, "5000ms")]
)
def test_schema_lock_is_deterministic_bounded_and_transaction_local(
    validator, monkeypatch, current, expected
) -> None:
    models = [
        SimpleNamespace(_meta=SimpleNamespace(db_table=name))
        for name in ("through", "endpoint", "service", "credential")
    ]
    monkeypatch.setattr(validator, "_release_models", Mock(return_value=models))
    cursor = Mock()
    cursor.fetchone.return_value = (f"{current}ms", current)
    editor = MagicMock()
    editor.connection.cursor.return_value.__enter__.return_value = cursor
    editor.quote_name.side_effect = [
        '"credential"',
        '"endpoint"',
        '"service"',
        '"through"',
    ]
    original = validator._lock_release_tables(None, editor)
    assert original == f"{current}ms"
    assert cursor.execute.call_args_list[1] == call(
        "SELECT set_config('lock_timeout', %s, true)", [expected]
    )
    assert cursor.execute.call_args_list[2] == call(
        'LOCK TABLE "credential", "endpoint", "service", "through" IN SHARE UPDATE EXCLUSIVE MODE'
    )


@pytest.mark.parametrize(
    "tree, expected",
    [
        (None, False),
        ("{CONST :constisnull true}", False),
        ("{VAR :varattno 0 :varattnosyn 4}", True),
        ("({FUNCEXPR :args ({VAR :varattno\t0\n:varattnosyn 4})})", True),
        ("{VAR :varattno 12 :varattnosyn 0}", False),
        ("{VAR :varattno -1 :varattnosyn 0}", False),
    ],
)
def test_whole_row_node_is_distinct_from_scalar_and_syntactic_slots(
    validator, tree, expected
) -> None:
    assert validator._node_has_whole_row(tree) is expected


@pytest.mark.parametrize(
    "value", [1, "", "not a node", "{VAR :unknown_slot 0}", "{VAR :varattno invalid}"]
)
def test_unknown_node_representation_fails_closed(validator, value) -> None:
    with pytest.raises(validator.ReleaseSchemaError):
        validator._node_has_whole_row(value)


def test_node_text_has_a_fixed_size_bound(validator, monkeypatch) -> None:
    monkeypatch.setattr(validator, "_MAX_NODE_TEXT", 16)
    with pytest.raises(validator.ReleaseSchemaError, match="uninspectable"):
        validator._node_has_whole_row("{CONST :value " + "x" * 20 + "}")


@pytest.mark.parametrize(
    "kind, numbers, tree, expected",
    [
        ("c", [0], None, True),
        ("c", [4], None, False),
        ("x", [0], "{VAR :varattno 4 :varattnosyn 0}", False),
        ("x", [0], "{VAR :varattno 0 :varattnosyn 4}", True),
    ],
)
def test_check_zero_and_exclusion_expression_slots_keep_their_meaning(
    validator, kind, numbers, tree, expected
) -> None:
    row = dict(kind=kind, attribute_numbers=numbers, expressions=tree)
    assert validator._whole_row_reference(row) is expected


def test_catalog_retains_whole_row_check_and_index_identity(
    validator, monkeypatch
) -> None:
    cursor = Mock()
    cursor.db.pg_version = 140000
    index_row = dict(oid=1, expressions="{VAR :varattno 0}")
    check_row = dict(kind="c", attribute_numbers=[0])
    monkeypatch.setattr(
        validator, "_rows", Mock(side_effect=[[], [index_row], [check_row]])
    )
    catalog = validator._catalog(cursor, "endpoint")
    assert catalog["indexes"][0]["whole_row"]
    assert catalog["constraints"][0]["whole_row"]


@pytest.mark.parametrize("kind", ["c", "x"])
def test_whole_row_enforcement_touches_owned_fields_without_named_dependencies(
    validator, kind
) -> None:
    model, fields = _enforcement_model()
    row = dict(kind=kind, columns=[], references=[], whole_row=True)
    with pytest.raises(
        validator.ReleaseSchemaError, match="additional check or exclusion"
    ):
        validator._reject_extra_constraints(
            dict(constraints=[row]), model, fields, whole_table=False
        )


@pytest.mark.parametrize("slot", ["expressions", "predicate", "check_expression"])
def test_every_catalog_expression_slot_preserves_whole_row_reference(
    validator, slot
) -> None:
    assert validator._whole_row_reference({slot: "{VAR :varattno 0}"})


@pytest.mark.parametrize(
    "tree",
    ["{VAR :varattno 1 :varnullingrels (b 0)}", "{VAR :varattno 1 :varattnosyn 0}"],
)
def test_unrelated_zero_slots_do_not_imply_whole_row(validator, tree) -> None:
    assert not validator._node_has_whole_row(tree)
