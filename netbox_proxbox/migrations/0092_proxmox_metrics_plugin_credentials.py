"""Move Proxmox metrics credentials into plugin-owned encrypted fields.

The previous schema stored references resolved by an external observability
service. Those references cannot be resolved by this plugin, so the upgrade
clears them, disables affected mappings, and requires operators to enter the
credentials again through the plugin. Non-secret endpoint metadata is retained
when it remains valid. Historical audit snapshots are masked before the legacy
columns are removed.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import migrations, models
from django.db.migrations.exceptions import IrreversibleError


logger = logging.getLogger("netbox_proxbox.migrations")
_URL_RE = r"^[Hh][Tt][Tt][Pp][Ss]://[^/?#@\s]+(?:/[^?#\s]*)?$"
_URL_VALIDATOR = URLValidator(schemes=("https",))
_MASKED = "********"
_MARKER = (
    "[Credential quarantine] This mapping was disabled during upgrade because "
    "its external token reference could not be imported into plugin-owned "
    "encrypted storage. Enter a new query token and explicitly re-enable it."
)


def _safe_url(value: object) -> bool:
    """Return whether a stored URL can remain as non-secret metadata."""
    if not isinstance(value, str) or not re.fullmatch(_URL_RE, value):
        return False
    try:
        _URL_VALIDATOR(value)
        parsed = urlsplit(value)
    except (ValidationError, ValueError):
        return False
    return not ("@" in parsed.netloc or parsed.query or parsed.fragment)


def _sanitize_snapshot(snapshot: object) -> tuple[object, bool]:
    """Mask legacy token values and unsafe URLs in one ObjectChange payload."""
    if not isinstance(snapshot, dict):
        return snapshot, False
    sanitized = dict(snapshot)
    changed = False
    if "influx_url" in sanitized and not _safe_url(sanitized["influx_url"]):
        sanitized["influx_url"] = _MASKED
        changed = True
    for field_name in ("query_token_secret_ref", "writer_token_secret_ref"):
        if sanitized.get(field_name):
            sanitized[field_name] = _MASKED
            changed = True
    return sanitized, changed


def _sanitize_object_changes(apps, schema_editor) -> None:
    """Remove legacy credential material from metrics audit snapshots."""
    content_type = (
        apps.get_model("contenttypes", "ContentType")
        .objects.using(schema_editor.connection.alias)
        .filter(app_label="netbox_proxbox", model="proxmoxmetricsinfluxdb")
        .first()
    )
    if content_type is None:
        return
    object_change = apps.get_model("core", "ObjectChange")
    manager = object_change.objects.using(schema_editor.connection.alias)
    for change in manager.filter(changed_object_type_id=content_type.pk).iterator():
        prechange, pre_changed = _sanitize_snapshot(change.prechange_data)
        postchange, post_changed = _sanitize_snapshot(change.postchange_data)
        if not (pre_changed or post_changed):
            continue
        change.prechange_data = prechange
        change.postchange_data = postchange
        manager.filter(pk=change.pk).update(
            prechange_data=prechange,
            postchange_data=postchange,
        )


def _quarantine_legacy_credentials(apps, schema_editor) -> None:
    """Clear every legacy token reference and disable rows requiring re-entry."""
    model = apps.get_model("netbox_proxbox", "ProxmoxMetricsInfluxDB")
    manager = model.objects.using(schema_editor.connection.alias)
    for row in manager.only(
        "pk",
        "influx_url",
        "query_token_secret_ref",
        "writer_token_secret_ref",
        "enabled",
        "comments",
    ).iterator():
        updates = {
            "query_token_enc": "",
            "query_token_secret_ref": "",
            "writer_token_secret_ref": "",
        }
        if not _safe_url(row.influx_url):
            updates["influx_url"] = ""
        comments = row.comments or ""
        if _MARKER not in comments:
            updates["comments"] = f"{comments}\n\n{_MARKER}" if comments else _MARKER
        updates["enabled"] = False
        manager.filter(pk=row.pk).update(**updates)
    _sanitize_object_changes(apps, schema_editor)
    logger.warning("netbox-proxbox: quarantined legacy Proxmox metrics credentials")


def _reverse_quarantine(*_args: object) -> None:
    raise IrreversibleError(
        "Proxmox metrics credential quarantine is irreversible; restore from a backup."
    )


class Migration(migrations.Migration):
    dependencies = [("netbox_proxbox", "0091_remove_branch_intent_custom_fields")]

    operations = [
        migrations.AddField(
            model_name="proxmoxmetricsinfluxdb",
            name="query_token_enc",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.RunPython(_quarantine_legacy_credentials, _reverse_quarantine),
        migrations.RemoveConstraint(
            model_name="proxmoxmetricsinfluxdb",
            name="netbox_proxbox_metrics_influxdb_query_token_is_ref",
        ),
        migrations.RemoveConstraint(
            model_name="proxmoxmetricsinfluxdb",
            name="netbox_proxbox_metrics_influxdb_writer_token_is_ref",
        ),
        migrations.RemoveConstraint(
            model_name="proxmoxmetricsinfluxdb",
            name="netbox_proxbox_metrics_influxdb_url_is_safe",
        ),
        migrations.RemoveField(
            model_name="proxmoxmetricsinfluxdb",
            name="query_token_secret_ref",
        ),
        migrations.RemoveField(
            model_name="proxmoxmetricsinfluxdb",
            name="writer_token_secret_ref",
        ),
        migrations.AddConstraint(
            model_name="proxmoxmetricsinfluxdb",
            constraint=models.CheckConstraint(
                condition=models.Q(query_token_enc__gt="") | models.Q(enabled=False),
                name="netbox_proxbox_metrics_influxdb_query_token_configured",
            ),
        ),
        migrations.AddConstraint(
            model_name="proxmoxmetricsinfluxdb",
            constraint=models.CheckConstraint(
                condition=models.Q(enabled=False) | models.Q(influx_url__regex=_URL_RE),
                name="netbox_proxbox_metrics_influxdb_url_is_safe",
            ),
        ),
    ]
