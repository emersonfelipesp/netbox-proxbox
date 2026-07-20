"""Add retry-safe sync-state storage and bridge FK staging columns."""

from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import add_field_idempotent


APP_LABEL = "netbox_proxbox"


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
                cursor,
                table,
            )
        }


def _bind_field(apps, model, field_name: str, field):
    bound_field = field.clone()
    bound_field.set_attributes_from_name(field_name)
    bound_field.model = model
    remote_field = getattr(bound_field, "remote_field", None)
    remote_model = getattr(remote_field, "model", None)
    if isinstance(remote_model, str):
        app_label, model_name = remote_model.split(".", 1)
        remote_field.model = apps.get_model(app_label, model_name)
    return bound_field


def _add_staging_field_if_missing(model_name: str, field_name: str, field):
    def forwards(apps, schema_editor):
        model = apps.get_model(APP_LABEL, model_name)
        bound_field = _bind_field(apps, model, field_name, field)
        if not _table_exists(schema_editor, model._meta.db_table):
            return
        if _column_exists(schema_editor, model._meta.db_table, bound_field.column):
            return
        schema_editor.add_field(model, bound_field)

    return forwards


def _remove_staging_field_if_present(model_name: str, field_name: str, field):
    def reverse(apps, schema_editor):
        model = apps.get_model(APP_LABEL, model_name)
        bound_field = _bind_field(apps, model, field_name, field)
        if not _table_exists(schema_editor, model._meta.db_table):
            return
        if not _column_exists(schema_editor, model._meta.db_table, bound_field.column):
            return
        schema_editor.remove_field(model, bound_field)

    return reverse


def add_staging_field_idempotent(model_name: str, field_name: str, field):
    """Add a temporary field not present on the final live model."""
    return migrations.SeparateDatabaseAndState(
        database_operations=[
            migrations.RunPython(
                _add_staging_field_if_missing(model_name, field_name, field),
                reverse_code=_remove_staging_field_if_present(
                    model_name,
                    field_name,
                    field,
                ),
            ),
        ],
        state_operations=[
            migrations.AddField(
                model_name=model_name,
                name=field_name,
                field=field.clone(),
            ),
        ],
    )


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0066_backfill_proxbox_sync_state"),
    ]

    operations = [
        add_staging_field_idempotent(
            model_name="proxboxvirtualdisksyncstate",
            field_name="proxbox_storage_fk",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="virtual_disk_sync_states",
                to="netbox_proxbox.proxmoxstorage",
            ),
        ),
        add_field_idempotent(
            model_name="proxboxvirtualdisksyncstate",
            field_name="proxbox_storage_raw_id",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        add_field_idempotent(
            model_name="proxboxvirtualdisksyncstate",
            field_name="proxbox_storage_raw_value",
            field=models.TextField(blank=True, default=""),
        ),
        add_staging_field_idempotent(
            model_name="proxboxvminterfacesyncstate",
            field_name="proxbox_bridge_fk",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="proxbox_vm_interface_sync_states",
                to="dcim.interface",
            ),
        ),
        add_field_idempotent(
            model_name="proxboxvminterfacesyncstate",
            field_name="proxbox_bridge_raw_id",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        add_field_idempotent(
            model_name="proxboxvminterfacesyncstate",
            field_name="proxbox_bridge_raw_value",
            field=models.TextField(blank=True, default=""),
        ),
    ]
