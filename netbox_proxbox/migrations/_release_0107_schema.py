"""Fail-closed physical postconditions for the unpublished 0.0.30 release."""

from __future__ import annotations

import re
from typing import Any

RECEIPT = "PROXBOX_RELEASE_0107_SCHEMA_VALIDATED_V1 (transaction commit pending)"
ENDPOINT_FIELDS = (
    "netbox_cluster",
    "ssh_service",
    "cloud_image_ssh_target_node",
    "cloud_image_ssh_identity_file",
    "cloud_image_ssh_binding_fingerprint",
)
_VAR_NODE = re.compile(r"\{VAR(?=\s|})")
_VAR_ATTRIBUTE = re.compile(r":varattno\s+(-?\d+)(?=\s|})")
_MAX_NODE_TEXT = 1_000_000


class ReleaseSchemaError(RuntimeError):
    """Refuse an existing schema whose release invariant cannot be proved."""


def _require(condition: bool, table: str, detail: str) -> None:
    if not condition:
        raise ReleaseSchemaError(f"Release 0107 schema mismatch: {table}: {detail}")


def _rows(cursor: Any, sql: str, table: str) -> list[dict[str, Any]]:
    cursor.execute(sql, [table])
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def _catalog(cursor: Any, table: str) -> dict[str, Any]:
    columns = _rows(
        cursor,
        """SELECT attname AS name, format_type(atttypid, atttypmod) AS type,
                  NOT a.attnotnull AS nullable, a.attgenerated AS generated,
                  a.attidentity AS identity,
                  pg_get_expr(d.adbin, d.adrelid) AS default,
                  pg_get_serial_sequence(a.attrelid::regclass::text, a.attname)
                    AS sequence,
                  'nextval(' || quote_literal(pg_get_serial_sequence(
                    a.attrelid::regclass::text, a.attname)::regclass::text)
                    || '::regclass)' AS expected_serial_default
           FROM pg_attribute a LEFT JOIN pg_attrdef d
             ON d.adrelid = a.attrelid AND d.adnum = a.attnum
           WHERE a.attrelid = to_regclass(%s)
             AND a.attnum > 0 AND NOT a.attisdropped""",
        table,
    )
    indexes = _rows(
        cursor,
        """SELECT i.indexrelid AS oid, i.indisunique AS unique,
                  i.indisprimary AS primary, i.indisvalid AS valid,
                  i.indisready AS ready, i.indislive AS live,
                  i.indpred IS NULL AS unconditional,
                  i.indexprs IS NULL AS simple,
                  i.indexprs::text AS expressions, i.indpred::text AS predicate,
                  ARRAY(SELECT DISTINCT a.attname FROM pg_depend d
                        JOIN pg_attribute a ON a.attrelid = d.refobjid
                          AND a.attnum = d.refobjsubid
                        WHERE d.classid = 'pg_class'::regclass
                          AND d.objid = i.indexrelid
                          AND d.refobjid = i.indrelid AND d.refobjsubid > 0)
                    AS references,
                  ARRAY(SELECT a.attname FROM unnest(i.indkey::smallint[])
                        WITH ORDINALITY AS k(num, position)
                        LEFT JOIN pg_attribute a
                          ON a.attrelid = i.indrelid AND a.attnum = k.num
                        WHERE k.position <= i.indnkeyatts
                        ORDER BY k.position) AS columns
           FROM pg_index i WHERE i.indrelid = to_regclass(%s)""",
        table,
    )
    nulls_not_distinct = set()
    if cursor.db.pg_version >= 150000:
        # PostgreSQL 14 lacks this catalog column and always distinguishes NULLs.
        nulls_not_distinct = {
            row["oid"]
            for row in _rows(
                cursor,
                "SELECT indexrelid AS oid FROM pg_index "
                "WHERE indrelid = to_regclass(%s) AND indnullsnotdistinct",
                table,
            )
        }
    for index in indexes:
        index["nulls_distinct"] = index["oid"] not in nulls_not_distinct
    constraints = _rows(
        cursor,
        """SELECT c.conname AS name, c.contype AS kind,
                  c.convalidated AS validated, c.conindid AS index,
                  c.confrelid AS target, c.confdeltype AS delete_action,
                  c.confupdtype AS update_action, c.confmatchtype AS match,
                  c.condeferrable AS deferrable, c.condeferred AS deferred,
                  c.conkey AS attribute_numbers, c.conbin::text AS check_expression,
                  owned_index.indexprs::text AS expressions,
                  owned_index.indpred::text AS predicate,
                  ARRAY(SELECT DISTINCT a.attname FROM pg_depend d
                        JOIN pg_attribute a ON a.attrelid = d.refobjid
                          AND a.attnum = d.refobjsubid
                        WHERE d.classid = 'pg_constraint'::regclass
                          AND d.objid = c.oid
                          AND d.refobjid = c.conrelid AND d.refobjsubid > 0)
                    AS references,
                  ARRAY(SELECT a.attname FROM unnest(c.conkey)
                        WITH ORDINALITY AS k(num, position)
                        JOIN pg_attribute a
                          ON a.attrelid = c.conrelid AND a.attnum = k.num
                        ORDER BY k.position) AS columns,
                  ARRAY(SELECT a.attname FROM unnest(c.confkey)
                        WITH ORDINALITY AS k(num, position)
                        JOIN pg_attribute a
                          ON a.attrelid = c.confrelid AND a.attnum = k.num
                        ORDER BY k.position) AS target_columns,
                  (SELECT count(*) >= 4 AND bool_and(tgenabled IN ('O', 'A'))
                   FROM pg_trigger WHERE tgconstraint = c.oid) AS triggers
           FROM pg_constraint c LEFT JOIN pg_index owned_index
             ON owned_index.indexrelid = c.conindid
              AND owned_index.indrelid = c.conrelid
           WHERE c.conrelid = to_regclass(%s)""",
        table,
    )
    for row in indexes + constraints:
        row["whole_row"] = _whole_row_reference(row)
    return {
        "columns": {row["name"]: row for row in columns},
        "indexes": indexes,
        "constraints": constraints,
    }


def _usable_index(index: dict[str, Any], columns: tuple[str, ...]) -> bool:
    return tuple(index["columns"]) == columns and all(
        index[key]
        for key in (
            "valid",
            "ready",
            "live",
            "unconditional",
            "simple",
            "nulls_distinct",
        )
    )


def _require_index(
    catalog: dict[str, Any],
    table: str,
    columns: tuple[str, ...],
    *,
    unique: bool = False,
    oid: int | None = None,
) -> None:
    matches = [index for index in catalog["indexes"] if _usable_index(index, columns)]
    if unique:
        matches = [index for index in matches if index["unique"]]
    if oid is not None:
        matches = [index for index in matches if index["oid"] == oid]
    _require(bool(matches), table, f"missing enforcing index for {columns}")


def _require_key(
    catalog: dict[str, Any],
    table: str,
    columns: tuple[str, ...],
    *,
    name: str | None = None,
    primary: bool = False,
) -> None:
    kind = "p" if primary else "u"
    matches = [
        row
        for row in catalog["constraints"]
        if row["kind"] == kind and tuple(row["columns"]) == columns and row["validated"]
    ]
    if name is not None:
        matches = [row for row in matches if row["name"] == name]
    _require(bool(matches), table, f"missing validated {kind} constraint for {columns}")
    for row in matches:
        _require_index(catalog, table, columns, unique=True, oid=row["index"])


def _require_foreign_key(
    cursor: Any,
    catalog: dict[str, Any],
    table: str,
    field: Any,
) -> None:
    column = (field.column,)
    foreign = [
        row
        for row in catalog["constraints"]
        if row["kind"] == "f" and field.column in row["columns"]
    ]
    cursor.execute(
        "SELECT to_regclass(%s)::oid", [field.target_field.model._meta.db_table]
    )
    target = cursor.fetchone()[0]
    _require(bool(foreign), table, f"missing foreign key for {column}")
    for row in foreign:
        valid = (
            tuple(row["columns"]) == column
            and row["target"] == target
            and tuple(row["target_columns"]) == (field.target_field.column,)
            and all(
                row[key] for key in ("validated", "deferrable", "deferred", "triggers")
            )
            and (row["delete_action"], row["update_action"], row["match"])
            == ("a", "a", "s")
        )
        _require(valid, table, f"incompatible foreign key for {column}")


def _require_column(
    catalog: dict[str, Any], table: str, field: Any, connection: Any
) -> None:
    actual = catalog["columns"].get(field.column)
    _require(actual is not None, table, f"missing column {field.column}")
    expected = field.db_type(connection)
    actual_type = actual["type"].replace("character varying", "varchar")
    _require(actual_type == expected, table, f"incompatible type for {field.column}")
    _require(
        actual["nullable"] == field.null,
        table,
        f"incompatible nullability for {field.column}",
    )
    _require(
        not actual["generated"], table, f"unexpected generated column {field.column}"
    )
    _require(
        not field.db_parameters(connection).get("check"),
        table,
        f"unsupported release check declaration for {field.column}",
    )
    _require_default(actual, table, field)


def _require_default(actual: dict[str, Any], table: str, field: Any) -> None:
    if field.get_internal_type() in ("AutoField", "BigAutoField", "SmallAutoField"):
        generated = bool(actual["sequence"]) and (
            actual["identity"] in ("a", "d")
            or actual["default"] == actual["expected_serial_default"]
        )
        _require(generated, table, f"missing generated ID for {field.column}")
    elif field.has_db_default():
        _require(
            field.db_default == "", table, "unsupported release default declaration"
        )
        _require(
            actual["default"] in ("''", "''::character varying", "''::text"),
            table,
            f"incompatible database default for {field.column}",
        )
    else:
        _require(
            actual["default"] is None and not actual["identity"],
            table,
            f"unexpected database default for {field.column}",
        )


def _validate_field(
    cursor: Any, catalog: dict[str, Any], model: Any, field: Any, connection: Any
) -> None:
    table = model._meta.db_table
    _require_column(catalog, table, field, connection)
    if field.primary_key:
        _require_key(catalog, table, (field.column,), primary=True)
    elif field.unique:
        _require_index(catalog, table, (field.column,), unique=True)
    elif field.db_index:
        _require_index(catalog, table, (field.column,))
    if field.is_relation and field.db_constraint:
        _require_foreign_key(cursor, catalog, table, field)


def _validate_declared_constraints(catalog: dict[str, Any], model: Any) -> None:
    table = model._meta.db_table
    expected_columns = {field.column for field in model._meta.local_concrete_fields}
    _require(
        set(catalog["columns"]) == expected_columns, table, "unexpected service columns"
    )
    _require(
        not any(row["kind"] == "c" for row in catalog["constraints"]),
        table,
        "unexpected release check constraint",
    )
    _require(not model._meta.indexes, table, "unsupported release index declaration")
    for names in model._meta.unique_together:
        columns = tuple(model._meta.get_field(name).column for name in names)
        _require_key(catalog, table, columns)
    for constraint in model._meta.constraints:
        supported = (
            type(constraint).__name__ == "UniqueConstraint"
            and bool(constraint.fields)
            and constraint.condition is None
            and not constraint.expressions
        )
        _require(supported, table, "unsupported release constraint declaration")
        columns = tuple(
            model._meta.get_field(name).column for name in constraint.fields
        )
        _require_key(catalog, table, columns, name=constraint.name)


def _expected_unique_keys(model: Any, fields: list[Any]) -> set[tuple[str, ...]]:
    keys = {(field.column,) for field in fields if field.unique or field.primary_key}
    for names in model._meta.unique_together:
        keys.add(tuple(model._meta.get_field(name).column for name in names))
    for constraint in model._meta.constraints:
        if type(constraint).__name__ == "UniqueConstraint":
            keys.add(
                tuple(model._meta.get_field(name).column for name in constraint.fields)
            )
    return keys


def _node_has_whole_row(value: Any) -> bool:
    """Inspect bounded catalog tokens without running the stored expression."""
    if value is None:
        return False
    supported = isinstance(value, str) and 0 < len(value) <= _MAX_NODE_TEXT
    _require(supported, "catalog", "uninspectable expression representation")
    _require(value.startswith(("{", "(")), "catalog", "unknown node envelope")
    attributes = _VAR_ATTRIBUTE.findall(value)
    _require(
        len(_VAR_NODE.findall(value)) == len(attributes),
        "catalog",
        "unknown VAR representation",
    )
    return any(int(attribute) == 0 for attribute in attributes)


def _whole_row_reference(row: dict[str, Any]) -> bool:
    if row.get("kind") == "c" and 0 in (row.get("attribute_numbers") or ()):
        return True
    return any(
        _node_has_whole_row(row.get(name))
        for name in ("expressions", "predicate", "check_expression")
    )


def _touches_fields(row: dict[str, Any], columns: set[str]) -> bool:
    references = set(row["columns"]) | set(row["references"])
    return row["whole_row"] or bool(references & columns)


def _reject_extra_unique_indexes(
    catalog: dict[str, Any], model: Any, fields: list[Any], *, whole_table: bool
) -> None:
    columns = {field.column for field in fields}
    expected = _expected_unique_keys(model, fields)
    for index in catalog["indexes"]:
        if not index["unique"]:
            continue
        if not whole_table and not _touches_fields(index, columns):
            continue
        key = tuple(index["columns"])
        compatible = key in expected and _usable_index(index, key)
        _require(
            compatible,
            model._meta.db_table,
            "conflicting additional unique enforcement",
        )


def _reject_extra_constraints(
    catalog: dict[str, Any], model: Any, fields: list[Any], *, whole_table: bool
) -> None:
    columns = {field.column for field in fields}
    foreign_columns = {
        (field.column,) for field in fields if field.is_relation and field.db_constraint
    }
    for constraint in catalog["constraints"]:
        if not whole_table and not _touches_fields(constraint, columns):
            continue
        _require(
            constraint["kind"] not in ("c", "x"),
            model._meta.db_table,
            "conflicting additional check or exclusion enforcement",
        )
        if constraint["kind"] == "f":
            _require(
                tuple(constraint["columns"]) in foreign_columns,
                model._meta.db_table,
                "unexpected additional foreign key",
            )


def _release_models(apps: Any) -> tuple[Any, Any, Any, Any]:
    endpoint = apps.get_model("netbox_proxbox", "ProxmoxEndpoint")
    service = apps.get_model("netbox_proxbox", "ProxmoxEndpointService")
    credential = apps.get_model("netbox_proxbox", "ServiceSSHCredential")
    through = service._meta.get_field("ipaddresses").remote_field.through
    return endpoint, service, credential, through


def _lock_release_tables(apps: Any, schema_editor: Any) -> str:
    """Retain bounded locks that block ordinary and concurrent index DDL."""
    tables = sorted(model._meta.db_table for model in _release_models(apps))
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_setting('lock_timeout'), setting::bigint "
            "FROM pg_settings WHERE name = 'lock_timeout'"
        )
        original, milliseconds = cursor.fetchone()
        timeout = f"{min(milliseconds or 5000, 5000)}ms"
        cursor.execute("SELECT set_config('lock_timeout', %s, true)", [timeout])
        quoted = ", ".join(schema_editor.quote_name(table) for table in tables)
        cursor.execute(f"LOCK TABLE {quoted} IN SHARE UPDATE EXCLUSIVE MODE")
    return original


def _restore_lock_timeout(schema_editor: Any, value: str) -> None:
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT set_config('lock_timeout', %s, true)", [value])


def validate_release_schema(apps: Any, schema_editor: Any) -> None:
    """Check historical release fields and every new service/M2M concrete field."""
    connection = schema_editor.connection
    endpoint, service, credential, through = _release_models(apps)
    with connection.cursor() as cursor:
        catalog = _catalog(cursor, endpoint._meta.db_table)
        fields = [endpoint._meta.get_field(name) for name in ENDPOINT_FIELDS]
        for field in fields:
            _validate_field(cursor, catalog, endpoint, field, connection)
        _reject_extra_unique_indexes(catalog, endpoint, fields, whole_table=False)
        _reject_extra_constraints(catalog, endpoint, fields, whole_table=False)
        for model in (service, credential, through):
            catalog = _catalog(cursor, model._meta.db_table)
            for field in model._meta.local_concrete_fields:
                _validate_field(cursor, catalog, model, field, connection)
            _validate_declared_constraints(catalog, model)
            fields = list(model._meta.local_concrete_fields)
            _reject_extra_unique_indexes(catalog, model, fields, whole_table=True)
            _reject_extra_constraints(catalog, model, fields, whole_table=True)


def finalize_release_schema(apps: Any, schema_editor: Any) -> None:
    """Drain deferred DDL and check the final invariant before the atomic commit."""
    connection = schema_editor.connection
    _require(connection.vendor == "postgresql", "release", "PostgreSQL is required")
    _require(
        schema_editor.atomic_migration and connection.in_atomic_block,
        "release",
        "an atomic schema editor is required",
    )
    lock_timeout = _lock_release_tables(apps, schema_editor)
    pending = list(schema_editor.deferred_sql)
    schema_editor.deferred_sql.clear()
    for statement in pending:
        schema_editor.execute(statement, None)
    _require(not schema_editor.deferred_sql, "release", "DDL queued unchecked SQL")
    validate_release_schema(apps, schema_editor)
    _require(
        not schema_editor.deferred_sql, "release", "unchecked deferred SQL remains"
    )
    _restore_lock_timeout(schema_editor, lock_timeout)
    print(RECEIPT)
