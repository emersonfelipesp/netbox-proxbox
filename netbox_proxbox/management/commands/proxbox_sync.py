"""Django management command to enqueue a full Proxmox→NetBox sync.

Usage:
    python manage.py proxbox_sync [--user USERNAME] [--wait] [--timeout SECONDS]
                                  [--poll-interval SECONDS] [--worker-grace SECONDS]
                                  [--enqueue-once]

This is the headless equivalent of clicking "Full Update" in the plugin UI:
it enqueues the same ``ProxboxSyncJob`` (on NetBox's default RQ queue) with
``sync_types=[SyncTypeChoices.ALL]`` and all configured Proxmox endpoint IDs.

``--enqueue-once`` is the integration hook for the ``proxbox-scheduler``
container (issue #372): it routes through ``JobRunner.enqueue_once()``,
which uses an advisory-locked dedup keyed on the job class + instance, so
the command no-ops when a pending recurring schedule already exists.

Exit codes:
    0  job enqueued (and, with --wait, completed successfully)
    non-zero  proxbox-api unreachable, misconfiguration, or the job ended in
              a non-completed terminal state
"""

from __future__ import annotations

import logging
import time
from argparse import ArgumentParser

from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_WORKER_GRACE = 30.0
TERMINAL_JOB_STATUSES = {"completed", "errored", "failed"}
SUCCESS_JOB_STATUSES = {"completed"}


class Command(BaseCommand):
    """Command implementation."""

    help = (
        "Enqueue a full Proxmox→NetBox sync, equivalent to the plugin UI's "
        '"Full Update" button. Suitable for cron, systemd timers, and CI.'
    )

    def add_arguments(self, parser: ArgumentParser) -> None:
        """Handle add arguments."""
        parser.add_argument(
            "--user",
            dest="username",
            default=None,
            help=(
                "Username to attribute the enqueued job to. "
                "Defaults to the oldest active superuser."
            ),
        )
        parser.add_argument(
            "--wait",
            action="store_true",
            help="Block until the job reaches a terminal state and mirror its exit code.",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=None,
            help=(
                "Maximum seconds to wait when --wait is set. "
                "Defaults to PROXBOX_SYNC_JOB_TIMEOUT (7200)."
            ),
        )
        parser.add_argument(
            "--poll-interval",
            type=float,
            default=DEFAULT_POLL_INTERVAL,
            help=f"Seconds between job-status polls when --wait is set (default: {DEFAULT_POLL_INTERVAL}).",
        )
        parser.add_argument(
            "--worker-grace",
            type=float,
            default=DEFAULT_WORKER_GRACE,
            help=(
                "When --wait is set, fast-fail if the job stays pending for this many "
                f"seconds with no RQ worker on the default queue (default: {DEFAULT_WORKER_GRACE})."
            ),
        )
        parser.add_argument(
            "--enqueue-once",
            action="store_true",
            help=(
                "Dedup against any pending recurring schedule via "
                "JobRunner.enqueue_once(). If a pending ProxboxSyncJob already "
                "exists (e.g. created by the NetBox-side Schedule Sync form), "
                "reuse it instead of enqueuing a duplicate. Intended for the "
                "proxbox-scheduler container (issue #372)."
            ),
        )

    def handle(self, *args: object, **options: object) -> None:
        """Handle handle."""
        from netbox_proxbox.choices import SyncTypeChoices
        from netbox_proxbox.jobs import (
            PROXBOX_SYNC_JOB_TIMEOUT,
            PROXBOX_SYNC_QUEUE_NAME,
            ProxboxSyncJob,
        )
        from netbox_proxbox.models import ProxmoxEndpoint
        from netbox_proxbox.services.backend_auth import wait_for_backend_ready
        from netbox_proxbox.services.backend_context import (
            get_fastapi_request_context,
        )

        username = options.get("username")
        wait = bool(options.get("wait"))
        timeout = options.get("timeout")
        if timeout is None:
            timeout = PROXBOX_SYNC_JOB_TIMEOUT
        poll_interval_raw = options.get("poll_interval")
        poll_interval = (
            DEFAULT_POLL_INTERVAL
            if poll_interval_raw is None
            else float(poll_interval_raw)
        )
        worker_grace_raw = options.get("worker_grace")
        worker_grace = (
            DEFAULT_WORKER_GRACE
            if worker_grace_raw is None
            else float(worker_grace_raw)
        )
        enqueue_once = bool(options.get("enqueue_once"))

        user = self._resolve_user(username)

        context = get_fastapi_request_context()
        if context is None or not context.http_url:
            raise CommandError(
                "No FastAPIEndpoint configured. Create one under "
                "Plugins > ProxBox > Endpoints > FastAPI before running proxbox_sync."
            )

        # Snappy pre-flight: 5 retries is enough for a CLI. The job itself will
        # use the standard reachability helpers internally.
        ok, msg = wait_for_backend_ready(context, max_retries=5)
        if not ok:
            raise CommandError(
                f"proxbox-api backend not reachable at {context.http_url}: {msg}"
            )

        proxmox_endpoint_ids = list(
            ProxmoxEndpoint.objects.values_list("pk", flat=True)
        )
        if not proxmox_endpoint_ids:
            self.stdout.write(
                self.style.WARNING(
                    "No ProxmoxEndpoint records configured; nothing to sync."
                )
            )
            return

        enqueue_kwargs = dict(
            instance=None,
            user=user,
            queue_name=PROXBOX_SYNC_QUEUE_NAME,
            name="Proxbox Sync: Full update (CLI)",
            sync_types=[SyncTypeChoices.ALL],
            proxmox_endpoint_ids=proxmox_endpoint_ids,
        )

        try:
            if enqueue_once:
                job = ProxboxSyncJob.enqueue_once(**enqueue_kwargs)
            else:
                job = ProxboxSyncJob.enqueue(**enqueue_kwargs)
        except Exception as exc:  # noqa: BLE001 — surface any enqueue failure
            raise CommandError(f"Failed to enqueue ProxboxSyncJob: {exc}") from exc

        job_pk = getattr(job, "pk", None)
        dedup_note = " (enqueue_once: reused pending or freshly created)" if enqueue_once else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"Enqueued ProxboxSyncJob (pk={job_pk}) on queue "
                f"'{PROXBOX_SYNC_QUEUE_NAME}' for {len(proxmox_endpoint_ids)} "
                f"Proxmox endpoint(s), attributed to user '{user}'{dedup_note}."
            )
        )

        if not wait:
            return

        self._wait_for_job(
            job=job,
            timeout=timeout,
            poll_interval=poll_interval,
            worker_grace=worker_grace,
        )

    def _resolve_user(self, username: str | None):
        """Look up the requested user or fall back to the oldest active superuser."""
        from django.contrib.auth import get_user_model

        user_model = get_user_model()

        if username:
            user = user_model.objects.filter(username=username).first()
            if user is None:
                raise CommandError(f"User '{username}' does not exist.")
            return user

        user = (
            user_model.objects.filter(is_active=True, is_superuser=True)
            .order_by("pk")
            .first()
        )
        if user is None:
            raise CommandError(
                "No active superuser found. Create one with "
                "`python manage.py createsuperuser` or pass --user USERNAME."
            )
        return user

    def _wait_for_job(
        self,
        *,
        job,
        timeout: int,
        poll_interval: float,
        worker_grace: float,
    ) -> None:
        """Poll the Job row until terminal and mirror its status to the exit code."""
        from netbox.jobs import Job

        job_pk = getattr(job, "pk", None)
        deadline = time.monotonic() + timeout
        worker_deadline = time.monotonic() + worker_grace
        worker_checked = False

        while True:
            now = time.monotonic()
            if now >= deadline:
                raise CommandError(
                    f"Timed out after {timeout}s waiting for Proxbox sync job "
                    f"(pk={job_pk}) to finish."
                )

            current = Job.objects.get(pk=job_pk)
            status = str(getattr(current, "status", "") or "").lower()

            if status in TERMINAL_JOB_STATUSES:
                if status in SUCCESS_JOB_STATUSES:
                    self.stdout.write(
                        self.style.SUCCESS(f"Proxbox sync job (pk={job_pk}) completed.")
                    )
                    return
                raise CommandError(
                    f"Proxbox sync job (pk={job_pk}) ended with status '{status}'."
                )

            if (
                not worker_checked
                and status in {"pending", "scheduled"}
                and now >= worker_deadline
            ):
                worker_checked = True
                if not self._default_queue_has_workers():
                    raise CommandError(
                        "No RQ worker is consuming the 'default' queue. "
                        "Start a worker with `python manage.py rqworker default` "
                        "or via the netbox-rq service, then re-run."
                    )

            time.sleep(poll_interval)

    def _default_queue_has_workers(self) -> bool:
        """Best-effort probe for active workers on the default RQ queue."""
        try:
            import django_rq  # noqa: PLC0415

            queue = django_rq.get_queue("default")
            workers = getattr(queue, "workers", None)
            if workers is None:
                # Older django-rq versions don't expose .workers — assume workers exist.
                return True
            try:
                return len(list(workers)) > 0
            except TypeError:
                return bool(workers)
        except Exception:  # noqa: BLE001 — probe is best-effort
            logger.debug("Could not probe RQ workers; assuming workers exist.")
            return True
