"""Scrub unsafe InfluxDB metadata and constrain token reference columns.

``ProxmoxMetricsInfluxDB.query_token_secret_ref`` and
``writer_token_secret_ref`` are documented to hold a netbox-nms
``ObservabilitySecret`` *reference*, never a credential. Until now that was
enforced only by ``RegexValidator`` and ``Model.clean()``, neither of which runs
on ``objects.create()``, ``bulk_create()``, ``queryset.update()``, a loaded
fixture, or raw SQL -- so a plaintext InfluxDB token could be persisted and then
rendered verbatim on the detail page.

Forwards runs in three steps:

1. **Scrub and quarantine.** Any token that is not an exact reference and any
   InfluxDB URL that is not a credential-free HTTP(S) URL is blanked, with the
   affected primary keys logged. A row missing a safe URL or required query
   reference is also disabled and receives a persistent remediation marker in
   its comments.
2. **Sanitize audit history.** Matching fields in existing ``ObjectChange``
   pre/post snapshots are replaced through the same fail-closed masking rules.
3. **Constrain.** Two ``CheckConstraint``\\ s pin both columns to
   ``'' OR <reference>``. The empty branch keeps required-ness a form concern
   while the database guarantees that whatever *is* stored is a reference.

The scrub, quarantine, marker, and audit sanitization are deliberately **not**
reversed -- the discarded text was, by definition, a value that should never
have been persisted, and re-writing a credential on rollback would recreate the
bug. Reversing this migration therefore drops the constraints only.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
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
_INFLUX_URL_VALIDATOR = URLValidator(schemes=("http", "https"))
_MASKED_VALUE = "********"
_QUARANTINE_MARKER = (
    "[Security quarantine] This mapping was disabled during upgrade after unsafe "
    "or missing InfluxDB URL/query-token metadata was removed. Enter a "
    "credential-free HTTP(S) base URL and an exact nms-secret:<uuid> query-token "
    "reference, then explicitly re-enable the mapping."
)
_CHANGELOG_BATCH_SIZE = 500


def _is_safe_influx_url(value: str | None) -> bool:
    """Return whether ``value`` is a credential-free HTTP(S) base URL."""
    if not isinstance(value, str) or not value:
        return False
    try:
        _INFLUX_URL_VALIDATOR(value)
        parsed_url = urlsplit(value)
    except (ValidationError, ValueError):
        return False
    return not ("@" in parsed_url.netloc or parsed_url.query or parsed_url.fragment)


def _masked_secret_ref(value: object, pattern: re.Pattern[str]) -> object:
    """Return safe references/blanks and mask every other stored value."""
    if value is None or value == "":
        return ""
    if isinstance(value, str) and pattern.fullmatch(value):
        return value
    return _MASKED_VALUE


def _masked_influx_url(value: object) -> object:
    """Return credential-free HTTP(S) URLs and mask every other value."""
    if isinstance(value, str) and _is_safe_influx_url(value):
        return value
    return _MASKED_VALUE


def _sanitize_snapshot(
    snapshot: object,
    pattern: re.Pattern[str],
) -> tuple[object, bool]:
    """Mask metrics metadata in one historical ObjectChange snapshot."""
    if not isinstance(snapshot, dict):
        return snapshot, False

    sanitized = snapshot.copy()
    if "influx_url" in sanitized:
        sanitized["influx_url"] = _masked_influx_url(sanitized["influx_url"])
    for field_name in _TOKEN_FIELDS:
        if field_name in sanitized:
            sanitized[field_name] = _masked_secret_ref(sanitized[field_name], pattern)
    return sanitized, sanitized != snapshot


def _sanitize_objectchange_snapshots(apps, schema_editor) -> None:
    """Remove unsafe metrics metadata from historical audit snapshots."""
    content_type_model = apps.get_model("contenttypes", "ContentType")
    object_change_model = apps.get_model("core", "ObjectChange")
    alias = schema_editor.connection.alias
    content_type = (
        content_type_model.objects.using(alias)
        .filter(
            app_label="netbox_proxbox",
            model="proxmoxmetricsinfluxdb",
        )
        .first()
    )
    if content_type is None:
        return

    pattern = re.compile(_NMS_SECRET_REF_RE)
    manager = object_change_model.objects.using(alias)
    pending = []
    sanitized_count = 0
    queryset = manager.filter(changed_object_type_id=content_type.pk).only(
        "pk",
        "prechange_data",
        "postchange_data",
    )
    for change in queryset.iterator(chunk_size=_CHANGELOG_BATCH_SIZE):
        prechange_data, prechange_changed = _sanitize_snapshot(
            change.prechange_data,
            pattern,
        )
        postchange_data, postchange_changed = _sanitize_snapshot(
            change.postchange_data,
            pattern,
        )
        if not (prechange_changed or postchange_changed):
            continue
        change.prechange_data = prechange_data
        change.postchange_data = postchange_data
        pending.append(change)
        sanitized_count += 1
        if len(pending) >= _CHANGELOG_BATCH_SIZE:
            manager.bulk_update(
                pending,
                ("prechange_data", "postchange_data"),
                batch_size=_CHANGELOG_BATCH_SIZE,
            )
            pending.clear()
    if pending:
        manager.bulk_update(
            pending,
            ("prechange_data", "postchange_data"),
            batch_size=_CHANGELOG_BATCH_SIZE,
        )

    if sanitized_count:
        logger.warning(
            "netbox-proxbox: masked unsafe InfluxDB metadata in %s historical "
            "ObjectChange row(s).",
            sanitized_count,
        )


def _scrub_non_conforming_values(apps, schema_editor) -> None:
    """Blank unsafe values and quarantine mappings that cannot be queried."""
    model = apps.get_model("netbox_proxbox", "ProxmoxMetricsInfluxDB")
    pattern = re.compile(_NMS_SECRET_REF_RE)
    manager = model.objects.using(schema_editor.connection.alias)

    for row in manager.only("pk", "influx_url", *_TOKEN_FIELDS, "enabled", "comments"):
        query_ref = getattr(row, "query_token_secret_ref", "") or ""
        unsafe_url = not _is_safe_influx_url(getattr(row, "influx_url", ""))
        unsafe_query_ref = not pattern.fullmatch(query_ref)
        updates = {
            field_name: ""
            for field_name in _TOKEN_FIELDS
            if (getattr(row, field_name) or "")
            and not pattern.fullmatch(getattr(row, field_name))
        }
        affected_fields = set(updates)
        if unsafe_query_ref:
            affected_fields.add("query_token_secret_ref")
        if unsafe_url:
            updates["influx_url"] = ""
            affected_fields.add("influx_url")

        if unsafe_url or unsafe_query_ref:
            updates["enabled"] = False
            comments = getattr(row, "comments", "") or ""
            if _QUARANTINE_MARKER not in comments:
                separator = "\n\n" if comments else ""
                updates["comments"] = f"{comments}{separator}{_QUARANTINE_MARKER}"
        if not updates:
            continue
        manager.filter(pk=row.pk).update(**updates)
        # The discarded value is never logged -- it may be the credential this
        # migration exists to remove.
        logger.warning(
            "netbox-proxbox: cleared or detected non-conforming value(s) in %s "
            "on ProxmoxMetricsInfluxDB pk=%s%s; re-enter valid InfluxDB "
            "metadata for that row.",
            ", ".join(sorted(affected_fields)),
            row.pk,
            " and disabled the mapping" if unsafe_url or unsafe_query_ref else "",
        )

    _sanitize_objectchange_snapshots(apps, schema_editor)


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0078_sync_state_last_synced_role"),
    ]

    operations = [
        migrations.RunPython(
            _scrub_non_conforming_values,
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
