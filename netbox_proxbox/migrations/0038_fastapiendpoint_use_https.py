"""Add ``use_https`` to FastAPIEndpoint to decouple URL scheme from cert verification.

Issue #352: prior to this migration the ``verify_ssl`` flag controlled both the
URL scheme (``http`` vs ``https``) and the ``requests`` ``verify=`` kwarg, which
made HTTPS-with-self-signed-cert (e.g. the proxbox-api ``*-nginx`` image) impossible
to express. ``use_https`` now exclusively drives the URL scheme; ``verify_ssl``
controls only certificate verification.

Existing rows are backfilled so ``use_https = verify_ssl`` — preserving the
effective scheme each row was already using before the field existed.
"""

from django.db import migrations, models


TABLE = "netbox_proxbox_fastapiendpoint"


def _backfill_use_https(apps, schema_editor):
    FastAPIEndpoint = apps.get_model("netbox_proxbox", "FastAPIEndpoint")
    FastAPIEndpoint.objects.filter(verify_ssl=True).update(use_https=True)


def _reverse_backfill(apps, schema_editor):
    # No-op: dropping the column on reverse already removes the data.
    return


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0037_pluginsettings_runtime_tunables"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        f'ALTER TABLE "{TABLE}" '
                        'ADD COLUMN IF NOT EXISTS "use_https" boolean NOT NULL DEFAULT FALSE;'
                    ),
                    reverse_sql=(
                        f'ALTER TABLE "{TABLE}" DROP COLUMN IF EXISTS "use_https";'
                    ),
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="fastapiendpoint",
                    name="use_https",
                    field=models.BooleanField(
                        default=False,
                        verbose_name="Use HTTPS",
                        help_text=(
                            "Use the HTTPS scheme to reach the ProxBox backend. "
                            "Enable this when the backend is served over TLS, e.g. the "
                            "proxbox-api '*-nginx' image. Certificate verification is "
                            "controlled separately by 'Verify SSL'."
                        ),
                    ),
                ),
            ],
        ),
        migrations.RunPython(_backfill_use_https, _reverse_backfill),
    ]
