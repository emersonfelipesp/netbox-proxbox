"""Populate empty FastAPIEndpoint tokens and register with backend.

This migration ensures existing FastAPIEndpoint objects have tokens generated
and attempts to register them with the proxbox-api backend. Failures are logged
but do not block migration.
"""

import logging
import secrets

from django.db import migrations

logger = logging.getLogger(__name__)


def populate_fastapi_tokens(apps, schema_editor):
    """Generate tokens for FastAPIEndpoint objects with empty tokens.

    Backend registration via signal handlers and runtime paths to avoid
    network I/O during migrations.
    """
    FastAPIEndpoint = apps.get_model("netbox_proxbox", "FastAPIEndpoint")

    for endpoint in FastAPIEndpoint.objects.filter(token=""):
        logger.info("Generating token for FastAPIEndpoint %s", endpoint.pk)
        endpoint.token = secrets.token_urlsafe(48)
        endpoint.save()
        logger.info(
            "FastAPIEndpoint %s token generated (registration will be retried on save signal)",
            endpoint.pk,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0021_backuproutine_tags_replication_tags_and_more"),
    ]

    operations = [
        migrations.RunPython(populate_fastapi_tokens),
    ]
