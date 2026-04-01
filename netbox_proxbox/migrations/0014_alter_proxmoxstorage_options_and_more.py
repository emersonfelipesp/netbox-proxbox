from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0013_proxmoxstorage_cluster_foreignkey"),
        ("virtualization", "0052_gfk_indexes"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="proxmoxstorage",
            options={"ordering": ("cluster__name", "name")},
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        ALTER TABLE netbox_proxbox_proxmoxstorage
                        DROP CONSTRAINT IF EXISTS
                            netbox_proxbox_proxmoxstorage_unique_cluster_name;
                        CREATE UNIQUE INDEX IF NOT EXISTS
                            netbox_proxbox_proxmoxstorage_cluster_id_name_uniq
                        ON netbox_proxbox_proxmoxstorage (cluster_id, name);
                    """,
                    reverse_sql="""
                        DROP INDEX IF EXISTS
                            netbox_proxbox_proxmoxstorage_cluster_id_name_uniq;
                    """,
                ),
            ],
            state_operations=[
                migrations.AlterUniqueTogether(
                    name="proxmoxstorage",
                    unique_together={("cluster", "name")},
                ),
            ],
        ),
    ]
