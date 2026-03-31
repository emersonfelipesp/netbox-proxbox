"""Add missing ProxmoxStorage, ProxmoxStorageVirtualDisk, and proxmox_storage fields.

This migration fixes the case where migration 0010 was marked as applied
but the actual database tables/columns were not created.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0010_squashed_plugin_settings_and_storage"),
        ("virtualization", "0052_gfk_indexes"),
    ]
    replaces = [
        ("netbox_proxbox", "0011_fix_missing_storage_tables"),
    ]

    operations = [
        # Create ProxmoxStorage if table doesn't exist
        migrations.RunSQL(
            sql="""
                CREATE TABLE IF NOT EXISTS netbox_proxbox_proxmoxstorage (
                    id bigint NOT NULL PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
                    created timestamp with time zone NULL,
                    last_updated timestamp with time zone NULL,
                    custom_field_data jsonb NOT NULL,
                    cluster varchar(255) NOT NULL,
                    name varchar(255) NOT NULL,
                    storage_type varchar(100) NULL,
                    content varchar(255) NULL,
                    path varchar(255) NULL,
                    nodes varchar(255) NULL,
                    shared boolean NOT NULL DEFAULT false,
                    enabled boolean NOT NULL DEFAULT true,
                    CONSTRAINT netbox_proxbox_proxmoxstorage_unique_cluster_name UNIQUE (cluster, name)
                );
            """,
            reverse_sql="DROP TABLE IF EXISTS netbox_proxbox_proxmoxstorage CASCADE;",
        ),
        # Create ProxmoxStorageVirtualDisk if table doesn't exist
        migrations.RunSQL(
            sql="""
                CREATE TABLE IF NOT EXISTS netbox_proxbox_proxmoxstoragevirtualdisk (
                    id bigint NOT NULL PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
                    proxmox_storage_id bigint NOT NULL REFERENCES netbox_proxbox_proxmoxstorage(id) DEFERRABLE INITIALLY DEFERRED,
                    virtual_disk_id bigint NOT NULL REFERENCES virtualization_virtualdisk(id) DEFERRABLE INITIALLY DEFERRED,
                    CONSTRAINT netbox_proxbox_proxmoxstoragevirtualdisk_unique_proxmox_storage_virtual_disk UNIQUE (proxmox_storage_id, virtual_disk_id)
                );
            """,
            reverse_sql="DROP TABLE IF EXISTS netbox_proxbox_proxmoxstoragevirtualdisk CASCADE;",
        ),
        # Add proxmox_storage_id to VMBackup if column doesn't exist
        migrations.RunSQL(
            sql="""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'netbox_proxbox_vmbackup'
                        AND column_name = 'proxmox_storage_id'
                    ) THEN
                        ALTER TABLE netbox_proxbox_vmbackup
                        ADD COLUMN proxmox_storage_id bigint NULL
                        REFERENCES netbox_proxbox_proxmoxstorage(id) DEFERRABLE INITIALLY DEFERRED;
                    END IF;
                END $$;
            """,
            reverse_sql="ALTER TABLE netbox_proxbox_vmbackup DROP COLUMN IF EXISTS proxmox_storage_id;",
        ),
        # Add proxmox_storage_id to VMSnapshot if column doesn't exist
        migrations.RunSQL(
            sql="""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'netbox_proxbox_vmsnapshot'
                        AND column_name = 'proxmox_storage_id'
                    ) THEN
                        ALTER TABLE netbox_proxbox_vmsnapshot
                        ADD COLUMN proxmox_storage_id bigint NULL
                        REFERENCES netbox_proxbox_proxmoxstorage(id) DEFERRABLE INITIALLY DEFERRED;
                    END IF;
                END $$;
            """,
            reverse_sql="ALTER TABLE netbox_proxbox_vmsnapshot DROP COLUMN IF EXISTS proxmox_storage_id;",
        ),
        # Create VMTaskHistory if table doesn't exist
        migrations.RunSQL(
            sql="""
                CREATE TABLE IF NOT EXISTS netbox_proxbox_vmtaskhistory (
                    id bigint NOT NULL PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
                    created timestamp with time zone NULL,
                    last_updated timestamp with time zone NULL,
                    custom_field_data jsonb NOT NULL DEFAULT '{}',
                    vm_type varchar(16) NOT NULL DEFAULT 'unknown',
                    upid varchar(255) NOT NULL UNIQUE,
                    node varchar(255) NOT NULL,
                    pid integer NULL,
                    pstart integer NULL,
                    task_id varchar(255) NULL,
                    task_type varchar(255) NOT NULL,
                    username varchar(255) NOT NULL,
                    start_time timestamp with time zone NOT NULL,
                    end_time timestamp with time zone NULL,
                    description text NOT NULL,
                    status varchar(255) NOT NULL,
                    task_state varchar(255) NULL,
                    exitstatus varchar(255) NULL,
                    virtual_machine_id bigint NOT NULL REFERENCES virtualization_virtualmachine(id) DEFERRABLE INITIALLY DEFERRED
                );
            """,
            reverse_sql="DROP TABLE IF EXISTS netbox_proxbox_vmtaskhistory CASCADE;",
        ),
    ]
