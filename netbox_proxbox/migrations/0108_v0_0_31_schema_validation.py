"""Validate the immutable 0.0.30 schema in the next release boundary."""

from django.db import migrations

from ._release_0107_schema import finalize_release_schema


class Migration(migrations.Migration):
    atomic = True

    dependencies = [("netbox_proxbox", "0107_v0_0_30_release")]

    operations = [
        migrations.RunPython(finalize_release_schema, migrations.RunPython.noop),
    ]
