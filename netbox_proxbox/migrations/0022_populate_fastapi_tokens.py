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
    """Generate tokens for FastAPIEndpoint objects with empty tokens and register with backend."""
    import requests

    FastAPIEndpoint = apps.get_model("netbox_proxbox", "FastAPIEndpoint")

    for endpoint in FastAPIEndpoint.objects.filter(token=""):
        logger.info("Generating token for FastAPIEndpoint %s", endpoint.pk)

        endpoint.token = secrets.token_urlsafe(48)

        host = None
        if endpoint.domain:
            host = endpoint.domain
        elif endpoint.ip_address:
            host = str(endpoint.ip_address.address).split("/")[0]

        if not host:
            logger.warning(
                "FastAPIEndpoint %s has no domain or IP address, saving token without registration",
                endpoint.pk,
            )
            endpoint.save()
            continue

        scheme = "https" if endpoint.verify_ssl else "http"
        base_url = f"{scheme}://{host}:{endpoint.port}"

        registered = False
        try:
            status_resp = requests.get(
                f"{base_url}/auth/bootstrap-status",
                verify=endpoint.verify_ssl,
                timeout=5,
            )
            if status_resp.status_code == 200:
                status_data = status_resp.json()
                if status_data.get("needs_bootstrap", False):
                    try:
                        register_resp = requests.post(
                            f"{base_url}/auth/register-key",
                            json={
                                "api_key": endpoint.token,
                                "label": f"netbox-migration-{endpoint.pk}",
                            },
                            verify=endpoint.verify_ssl,
                            timeout=10,
                        )
                        if register_resp.status_code in (201, 409):
                            logger.info(
                                "Registered API key for FastAPIEndpoint %s with backend during migration",
                                endpoint.pk,
                            )
                            registered = True
                        else:
                            logger.warning(
                                "Failed to register API key for FastAPIEndpoint %s: HTTP %s",
                                endpoint.pk,
                                register_resp.status_code,
                            )
                    except requests.exceptions.RequestException as exc:
                        logger.warning(
                            "Could not register API key for FastAPIEndpoint %s: %s",
                            endpoint.pk,
                            exc,
                        )
                else:
                    logger.debug(
                        "FastAPIEndpoint %s: backend already has API key registered",
                        endpoint.pk,
                    )
                    registered = True
            else:
                logger.warning(
                    "Bootstrap status check failed for FastAPIEndpoint %s: HTTP %s",
                    endpoint.pk,
                    status_resp.status_code,
                )
        except requests.exceptions.RequestException as exc:
            logger.warning(
                "Could not check bootstrap status for FastAPIEndpoint %s: %s",
                endpoint.pk,
                exc,
            )

        endpoint.save()

        if registered:
            logger.info("FastAPIEndpoint %s token saved and registered", endpoint.pk)
        else:
            logger.info(
                "FastAPIEndpoint %s token saved (registration will be retried on save signal)",
                endpoint.pk,
            )


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0021_backuproutine_tags_replication_tags_and_more"),
    ]

    operations = [
        migrations.RunPython(populate_fastapi_tokens),
    ]
