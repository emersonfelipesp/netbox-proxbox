"""Repair databases that applied the old post-0036 migration lineage.

Some live installs advanced from ``0036_add_overwrite_vm_type`` through a
now-replaced set of 0037..0046 migration files.  Their schema contains many
of the same columns as the current consolidated v0.0.15/v0.0.16 migration
chain, but not all of them.  This migration is intentionally database-only:
operators first fake-apply the current source-tree 0037..0046 migrations, then
run this migration to create only the tables/columns/data still missing from
the live database.
"""

from __future__ import annotations

from django.db import migrations

from netbox_proxbox.migrations._v0_0_15_release_data import (
    register_hardware_discovery_cfs,
)
from netbox_proxbox.migrations._v0_0_16_release_data import (
    register_intent_custom_fields,
)


APP_LABEL = "netbox_proxbox"

MISSING_MODEL_TABLES = (
    "NodeSSHCredential",
    "ProxmoxVMCloudInit",
    "ProxmoxApplyJob",
    "DeletionRequest",
    "CloudImageTemplate",
)

MISSING_MODEL_FIELDS = {
    "ProxboxPluginSettings": (
        "ensure_netbox_objects",
        "delete_orphans",
        "parse_description_metadata",
        "embed_description_metadata",
        "overwrite_vm_proxmox_tags",
        "overwrite_vm_cloudinit",
        "intent_warn_plaintext_password",
        "intent_apply_authorization_self_approve_allowed",
        "intent_deletion_request_ttl_days",
        "hardware_discovery_enabled",
    ),
    "ProxmoxEndpoint": (
        "environment",
        "overwrite_vm_proxmox_tags",
        "overwrite_vm_cloudinit",
    ),
}


def _existing_tables(schema_editor) -> set[str]:
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        return set(connection.introspection.table_names(cursor))


def _existing_columns(schema_editor, table_name: str) -> set[str]:
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        return {
            column.name
            for column in connection.introspection.get_table_description(
                cursor,
                table_name,
            )
        }


def _create_model_and_auto_m2m_tables(apps, schema_editor, model_name: str) -> None:
    model = apps.get_model(APP_LABEL, model_name)
    tables = _existing_tables(schema_editor)

    if model._meta.db_table not in tables:
        schema_editor.create_model(model)
        tables = _existing_tables(schema_editor)

    for field in model._meta.local_many_to_many:
        through = field.remote_field.through
        through_table = through._meta.db_table
        if (
            through._meta.auto_created
            and through_table.startswith("netbox_proxbox_")
            and through_table not in tables
        ):
            schema_editor.create_model(through)
            tables.add(through_table)


def _add_missing_model_fields(apps, schema_editor) -> None:
    for model_name, field_names in MISSING_MODEL_FIELDS.items():
        model = apps.get_model(APP_LABEL, model_name)
        columns = _existing_columns(schema_editor, model._meta.db_table)

        for field_name in field_names:
            field = model._meta.get_field(field_name)
            if field.column in columns:
                continue
            schema_editor.add_field(model, field)
            columns.add(field.column)


def repair_legacy_lineage_schema(apps, schema_editor) -> None:
    for model_name in MISSING_MODEL_TABLES:
        _create_model_and_auto_m2m_tables(apps, schema_editor, model_name)

    _add_missing_model_fields(apps, schema_editor)

    register_hardware_discovery_cfs(apps, schema_editor)
    register_intent_custom_fields(apps, schema_editor)


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0046_pluginsettings_embed_description_metadata"),
    ]

    operations = [
        migrations.RunPython(
            repair_legacy_lineage_schema,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
