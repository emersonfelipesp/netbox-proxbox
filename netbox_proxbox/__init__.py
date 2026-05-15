"""Register the ProxBox NetBox plugin and declare its compatibility metadata."""

from importlib import util as importlib_util
import logging
import os
import sys
import threading

# Netbox plugin related import
from netbox.plugins import PluginConfig


logger = logging.getLogger(__name__)


_SERVER_MANAGEMENT_COMMANDS = frozenset(
    {
        "runserver",
        "runserver_plus",
        "rqworker",
    }
)


def _is_server_process() -> bool:
    """Return True only when Django is being launched as a long-running server.

    The startup push is only meaningful while NetBox is actually serving HTTP
    (gunicorn / uvicorn / ``runserver``) or running an RQ worker. For
    one-shot management commands such as ``createsuperuser``, ``migrate``,
    ``shell``, ``test``, etc., it must stay silent so its log output does
    not bleed into interactive prompts.
    """
    argv0 = os.path.basename(sys.argv[0]) if sys.argv else ""
    is_manage_entrypoint = argv0 in {"manage.py", "django-admin", "django-admin.py"}
    if not is_manage_entrypoint:
        return True
    subcommand = sys.argv[1] if len(sys.argv) > 1 else ""
    return subcommand in _SERVER_MANAGEMENT_COMMANDS


def _deferred_startup_push() -> None:
    """Push existing NetBox endpoint data to the proxbox-api backend after a short delay.

    Runs in a daemon thread to avoid blocking Django app initialization.
    Best-effort: logs warnings on failure but never raises.  This covers
    the common scenario where the backend starts fresh (empty SQLite) while
    the plugin already has a configured ``NetBoxEndpoint``.
    """
    import time

    time.sleep(10)  # Give the backend time to start before the first push.

    try:
        from netbox_proxbox.models import NetBoxEndpoint  # noqa: PLC0415
        from netbox_proxbox.services.backend_auth import (  # noqa: PLC0415
            ensure_backend_key_registered,
        )
        from netbox_proxbox.services.backend_context import (  # noqa: PLC0415
            get_fastapi_request_context,
        )
        from netbox_proxbox.views.backend_sync import (  # noqa: PLC0415
            sync_netbox_endpoint_to_backend as _push,
        )

        # Ensure the API key is registered with the backend before pushing
        # endpoints.  Without this, authenticated requests would be rejected
        # with 401 if the backend restarted with an empty database.
        key_ok, key_msg = ensure_backend_key_registered()
        if key_ok:
            logger.info("Startup push: API key verified — %s", key_msg)
        else:
            logger.warning("Startup push: API key registration failed — %s", key_msg)

        context = get_fastapi_request_context()
        if context is None or not context.http_url:
            logger.debug(
                "Startup push: no FastAPIEndpoint configured, skipping NetBox endpoint push"
            )
            return

        base_url = context.http_url.rstrip("/")
        auth_headers = dict(context.headers or {})
        backend_verify_ssl = bool(context.verify_ssl)

        pushed = 0
        for nb_ep in NetBoxEndpoint.objects.all():
            ok, err, _ = _push(
                nb_ep,
                base_url=base_url,
                auth_headers=auth_headers,
                backend_verify_ssl=backend_verify_ssl,
            )
            if ok:
                pushed += 1
                logger.info(
                    "Startup push: synced NetBox endpoint '%s' to proxbox-api backend",
                    getattr(nb_ep, "name", nb_ep.pk),
                )
            else:
                logger.warning(
                    "Startup push: could not sync NetBox endpoint '%s' to proxbox-api: %s",
                    getattr(nb_ep, "name", nb_ep.pk),
                    err,
                )

        if pushed == 0:
            logger.debug("Startup push: no NetBoxEndpoint records found to push")

    except Exception as exc:  # noqa: BLE001
        from django.db import OperationalError, ProgrammingError  # noqa: PLC0415

        if isinstance(exc, (ProgrammingError, OperationalError)):
            # Database tables not yet created (migrations still running on first
            # start).  This is expected and harmless — the push will be retried
            # on the next restart once migrations have completed.
            logger.debug(
                "Startup push: database not ready yet (migrations pending), skipping: %s",
                exc,
            )
        else:
            logger.warning(
                "Startup push: failed to push NetBox endpoints to proxbox-api backend",
                exc_info=True,
            )


def _runtime_dependencies_available() -> bool:
    """Return True when the Pydantic-backed runtime modules can be imported."""
    return all(
        importlib_util.find_spec(module_name) is not None
        for module_name in ("pydantic", "pydantic_core")
    )


class ProxboxConfig(PluginConfig):
    """Django app config for the Proxbox NetBox plugin (URLs, queues, job registration).

    Proxbox sync work is enqueued as core NetBox Jobs (see ``jobs.ProxboxSyncJob``) on
    ``netbox.constants.RQ_QUEUE_DEFAULT`` (``jobs.PROXBOX_SYNC_QUEUE_NAME``), so the stock
    ``manage.py rqworker`` without extra queue flags picks them up. We intentionally do not
    register a dedicated plugin RQ queue here (``queues`` empty); legacy jobs may still show
    ``queue_name`` ``netbox_proxbox.sync`` from older releases.
    """

    name = "netbox_proxbox"
    verbose_name = "Proxbox"
    description = "Integrates Proxmox and Netbox"
    version = "0.0.15rc4"
    author = "Emerson Felipe (@emersonfelipesp)"
    author_email = "emersonfelipe.2003@gmail.com"
    min_version = "4.5.8"
    max_version = "4.6.99"
    base_url = "proxbox"
    required_settings = []
    queues = []

    def ready(self) -> None:
        """Register models, then import job modules so runners and core Job views hook in."""
        super().ready()
        if not _runtime_dependencies_available():
            logger.warning(
                "Skipping ProxBox job and view registration because Pydantic is not installed."
            )
            return
        from . import jobs  # noqa: F401 — registers ProxboxSyncJob with the NetBox job system
        from .views import job_cancel, job_run  # noqa: F401 — core Job: proxbox-run / proxbox-cancel
        from . import signals  # noqa: F401 — ensures token auto-generation and backend registration
        from . import signal_receivers  # noqa: F401 — owns the post_merge receiver chain

        # Push any existing NetBox endpoint data to the proxbox-api backend shortly
        # after startup.  This ensures the backend always has the endpoint record even
        # after a fresh start or database wipe, without blocking Django initialization.
        # Only run for long-lived server processes — one-shot management commands
        # like ``createsuperuser`` must not have these warnings leak into stdout.
        if _is_server_process():
            thread = threading.Thread(
                target=_deferred_startup_push,
                daemon=True,
                name="proxbox-startup-endpoint-push",
            )
            thread.start()
        else:
            logger.debug(
                "Skipping proxbox startup push: not a server process (argv=%r)",
                sys.argv,
            )


config = ProxboxConfig
