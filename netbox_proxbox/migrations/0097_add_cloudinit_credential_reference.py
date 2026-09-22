"""Add the generic cloud-init credential reference without dropping old data.

Fresh installations already receive the generic field from migration 0064.
For an existing database, this migration discovers the single historical
credential-reference column by structure, creates the generic column, copies
populated values, and deliberately leaves the historical column untouched so
an older application can still be restored during a downgrade.
"""

from django.db import migrations


TARGET_COLUMN = "credential_reference_id"
HISTORICAL_SUFFIX = "_credential_id"


def _column_names(schema_editor, table: str) -> set[str]:
    with schema_editor.connection.cursor() as cursor:
        return {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(
                cursor, table
            )
        }


def _historical_columns(columns: set[str]) -> list[str]:
    return sorted(
        column
        for column in columns
        if column.endswith(HISTORICAL_SUFFIX) and column != TARGET_COLUMN
    )


def add_and_copy_credential_reference(apps, schema_editor) -> None:
    """Create the generic field and copy the sole structural predecessor."""
    model = apps.get_model("netbox_proxbox", "ProxmoxVMCloudInit")
    table = model._meta.db_table
    columns = _column_names(schema_editor, table)
    historical_columns = _historical_columns(columns)
    if len(historical_columns) > 1:
        raise RuntimeError(
            "Credential-reference migration is ambiguous: expected no more than "
            "one historical *_credential_id column"
        )

    field = model._meta.get_field(TARGET_COLUMN)
    if TARGET_COLUMN not in columns:
        schema_editor.add_field(model, field)

    if not historical_columns:
        return

    historical_column = historical_columns[0]
    quote_name = schema_editor.quote_name
    quoted_table = quote_name(table)
    quoted_target = quote_name(TARGET_COLUMN)
    quoted_historical = quote_name(historical_column)
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            f"SELECT COUNT(*) FROM {quoted_table} "  # nosec B608 -- quoted identifiers
            f"WHERE {quoted_target} IS NOT NULL "
            f"AND {quoted_historical} IS NOT NULL "
            f"AND {quoted_target} <> {quoted_historical}"
        )
        conflict_count = cursor.fetchone()[0]
        if conflict_count:
            raise RuntimeError(
                "Credential-reference migration found conflicting populated values"
            )
        cursor.execute(
            f"UPDATE {quoted_table} SET {quoted_target} = {quoted_historical} "  # nosec B608 -- quoted identifiers
            f"WHERE {quoted_target} IS NULL AND {quoted_historical} IS NOT NULL"
        )


def preserve_generic_credential_reference(apps, schema_editor) -> None:
    """Preserve the field owned by migration 0064 when reversing this repair.

    Migration 0097 repairs databases whose legacy lineage omitted the physical
    column, but it does not add the field to Django's state: migration 0064
    already did that. Dropping the column while reverting to 0096 therefore
    leaves the historical state claiming a field that no longer exists.
    """
    return


class Migration(migrations.Migration):
    dependencies = [("netbox_proxbox", "0096_overwrite_vm_platform")]

    operations = [
        migrations.RunPython(
            add_and_copy_credential_reference,
            preserve_generic_credential_reference,
        )
    ]
