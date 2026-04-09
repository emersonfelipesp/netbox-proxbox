"""Change VMTaskHistory.pstart from DateTimeField to BigIntegerField.

Proxmox 'pstart' is a kernel-internal process start counter (opaque integer),
NOT a UNIX timestamp. Storing it as DateTimeField produced garbage datetime
values. BigIntegerField preserves the original value for UPID parsing and
task deduplication purposes.

Existing pstart values are nulled because they were incorrectly derived
from treating the integer as a timestamp and are not recoverable.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("netbox_proxbox", "0026_vmbackup_encrypted_to_charfield"),
    ]

    operations = [
        migrations.RunSQL(
            sql="UPDATE netbox_proxbox_vmtaskhistory SET pstart = NULL;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AlterField(
            model_name="vmtaskhistory",
            name="pstart",
            field=models.BigIntegerField(
                null=True,
                blank=True,
                help_text="Process start value from Proxmox (kernel-internal counter, not a timestamp).",
            ),
        ),
    ]
