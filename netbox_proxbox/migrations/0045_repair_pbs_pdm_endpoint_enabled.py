"""Repair missing enabled columns on PBS/PDM endpoint tables.

The v0.0.18 release added ``EndpointBase.enabled`` but its released
``0040_endpoint_enabled`` migration covered only ProxmoxEndpoint,
NetBoxEndpoint, and FastAPIEndpoint. Databases that installed that release
can therefore have PBSEndpoint/PDMEndpoint tables without the physical
``enabled`` column even though the Django model state expects it.

The consolidated develop migration already carries the corrected state and
fresh-install database operation. This migration is intentionally database-only:
it repairs already-installed databases without adding duplicate state ops.
"""

from __future__ import annotations

from django.db import migrations

APP_LABEL = "netbox_proxbox"
MODEL_NAMES = ("PBSEndpoint", "PDMEndpoint")


def _table_exists(schema_editor, table: str) -> bool:
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        return table in set(connection.introspection.table_names(cursor))


def _column_exists(schema_editor, table: str, column: str) -> bool:
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        return column in {
            description.name
            for description in connection.introspection.get_table_description(
                cursor, table
            )
        }


def repair_endpoint_enabled_columns(apps, schema_editor) -> None:
    """Add ``enabled`` to existing PBS/PDM endpoint tables when missing."""
    for model_name in MODEL_NAMES:
        model = apps.get_model(APP_LABEL, model_name)
        table = model._meta.db_table
        if not _table_exists(schema_editor, table):
            continue
        field = model._meta.get_field("enabled")
        if _column_exists(schema_editor, table, field.column):
            continue
        schema_editor.add_field(model, field)


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0044_merge_reconciliation_engine_settings"),
    ]

    operations = [
        migrations.RunPython(
            repair_endpoint_enabled_columns,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
