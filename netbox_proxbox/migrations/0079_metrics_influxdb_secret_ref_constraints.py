"""Constrain InfluxDB metrics token columns to ``nms-secret:<uuid>`` references.

``ProxmoxMetricsInfluxDB.query_token_secret_ref`` and
``writer_token_secret_ref`` are documented to hold a netbox-nms
``ObservabilitySecret`` *reference*, never a credential. Until now that was
enforced only by ``RegexValidator`` and ``Model.clean()``, neither of which runs
on ``objects.create()``, ``bulk_create()``, ``queryset.update()``, a loaded
fixture, or raw SQL -- so a plaintext InfluxDB token could be persisted and then
rendered verbatim on the detail page.

Forwards runs in two steps:

1. **Scrub.** Any stored value that is not an exact reference is blanked, with
   the affected primary keys logged. This has to happen first: ``AddConstraint``
   validates existing rows, so a single non-conforming row would abort the whole
   upgrade.
2. **Constrain.** Two ``CheckConstraint``\\ s pin both columns to
   ``'' OR <reference>``. The empty branch keeps required-ness a form concern
   while the database guarantees that whatever *is* stored is a reference.

The scrub is deliberately **not** reversed -- the discarded text was, by
definition, a value that should never have been in the column, and re-writing a
credential back into the database on a rollback would be the bug rather than the
fix. Reversing this migration therefore drops the constraints only.
"""

from __future__ import annotations

import logging
import re

from django.db import migrations, models


logger = logging.getLogger("netbox_proxbox.migrations")

# Frozen copy of ``netbox_proxbox.models.proxmox_metrics.NMS_SECRET_REF_RE``.
# Migrations must not import from the live model module: a later grammar change
# there would silently rewrite what this already-applied migration did.
_NMS_SECRET_REF_RE = (
    r"^nms-secret:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

_TOKEN_FIELDS = ("query_token_secret_ref", "writer_token_secret_ref")


def _scrub_non_reference_token_values(apps, schema_editor) -> None:
    """Blank any token column that does not hold an exact reference."""
    model = apps.get_model("netbox_proxbox", "ProxmoxMetricsInfluxDB")
    pattern = re.compile(_NMS_SECRET_REF_RE)

    for row in model.objects.using(schema_editor.connection.alias).only(
        "pk", *_TOKEN_FIELDS
    ):
        updates = {
            field_name: ""
            for field_name in _TOKEN_FIELDS
            if (getattr(row, field_name) or "")
            and not pattern.fullmatch(getattr(row, field_name))
        }
        if not updates:
            continue
        model.objects.using(schema_editor.connection.alias).filter(pk=row.pk).update(
            **updates
        )
        # The discarded value is never logged -- it may be the credential this
        # migration exists to remove.
        logger.warning(
            "netbox-proxbox: cleared non-reference value(s) in %s on "
            "ProxmoxMetricsInfluxDB pk=%s; re-enter the netbox-nms "
            "nms-secret:<uuid> reference for that row.",
            ", ".join(sorted(updates)),
            row.pk,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0078_sync_state_last_synced_role"),
    ]

    operations = [
        migrations.RunPython(
            _scrub_non_reference_token_values,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="proxmoxmetricsinfluxdb",
            constraint=models.CheckConstraint(
                condition=models.Q(query_token_secret_ref__regex=_NMS_SECRET_REF_RE)
                | models.Q(query_token_secret_ref=""),
                name="netbox_proxbox_metrics_influxdb_query_token_is_ref",
            ),
        ),
        migrations.AddConstraint(
            model_name="proxmoxmetricsinfluxdb",
            constraint=models.CheckConstraint(
                condition=models.Q(writer_token_secret_ref__regex=_NMS_SECRET_REF_RE)
                | models.Q(writer_token_secret_ref=""),
                name="netbox_proxbox_metrics_influxdb_writer_token_is_ref",
            ),
        ),
    ]
