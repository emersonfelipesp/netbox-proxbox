"""Change VMBackup.encrypted from BooleanField to CharField.

Proxmox returns 'encrypted' as a string: an encryption fingerprint hash (PBS)
or the literal string "1" for encrypted backups. BooleanField loses this data.
Empty string means not encrypted; a non-empty value holds the fingerprint or "1".
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("netbox_proxbox", "0025_proxmoxstorage_new_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="vmbackup",
            name="encrypted",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                help_text="Encryption fingerprint or flag from Proxmox (empty = not encrypted).",
            ),
        ),
        migrations.RunSQL(
            sql="UPDATE netbox_proxbox_vmbackup SET encrypted = '1' WHERE encrypted = 'True';",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="UPDATE netbox_proxbox_vmbackup SET encrypted = '' WHERE encrypted = 'False';",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
