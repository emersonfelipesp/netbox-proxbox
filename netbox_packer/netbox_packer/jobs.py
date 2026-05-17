"""Background job runner for Packer image builds."""

from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone
from django.utils.text import slugify
from rq.timeouts import JobTimeoutException

from netbox.jobs import JobRunner

from netbox_packer.choices import PackerBuildStatusChoices
from netbox_packer.services.http_client import (
    ImageFactoryBackendError,
    cancel_image_build,
    stream_image_build,
    submit_image_build,
)

logger = logging.getLogger("netbox_packer.jobs")

# Default RQ wall-clock timeout (4 hours). Views may override per-settings row.
PACKER_BUILD_JOB_TIMEOUT = 14400


class PackerImageBuildJob(JobRunner):
    """Execute a Packer image build via the proxbox-api image factory."""

    class Meta:
        name = "Packer Image Build"

    @classmethod
    def enqueue(cls, *args: Any, **kwargs: Any) -> Any:
        kwargs.setdefault("job_timeout", PACKER_BUILD_JOB_TIMEOUT)
        return super().enqueue(*args, **kwargs)

    # ------------------------------------------------------------------
    # run
    # ------------------------------------------------------------------

    def run(self, **kwargs: Any) -> None:
        build = self.job.object
        if build is None:
            logger.error("PackerImageBuildJob: no build object found on job %s", self.job.pk)
            return

        force: bool = bool(kwargs.get("force", False))
        dry_run: bool = bool(kwargs.get("dry_run", False))

        # Submit the build to proxbox-api --------------------------------
        try:
            response = submit_image_build(build=build, force=force, dry_run=dry_run)
        except ImageFactoryBackendError as exc:
            self._fail_build(build, str(exc))
            self.logger.error("Image factory submit failed: %s", exc)
            return

        backend_build_id: str = response.get("build_id", "")
        build.backend_build_id = backend_build_id
        build.save(update_fields=["backend_build_id", "last_updated"])

        # Stream SSE events ----------------------------------------------
        try:
            self._stream_and_update(build, backend_build_id)
        except JobTimeoutException:
            self.logger.error("Packer build job timed out; sending cancel to backend")
            if backend_build_id:
                try:
                    cancel_image_build(backend_build_id=backend_build_id)
                except ImageFactoryBackendError as exc:
                    self.logger.error("Failed to cancel backend build after timeout: %s", exc)
            self._fail_build(build, "Job timed out.")
            raise

    # ------------------------------------------------------------------
    # SSE streaming
    # ------------------------------------------------------------------

    def _stream_and_update(self, build: Any, backend_build_id: str) -> None:
        """Consume SSE events from the backend and update the build record."""
        try:
            for event_name, data in stream_image_build(backend_build_id=backend_build_id):
                if event_name == "build_started":
                    build.status = PackerBuildStatusChoices.RUNNING
                    build.started_at = timezone.now()
                    build.save(update_fields=["status", "started_at", "last_updated"])
                    self.logger.info("Packer build started: %s", backend_build_id)

                elif event_name in ("packer_init", "packer_validate"):
                    message = data.get("message") or data.get("log") or str(data)
                    self.logger.info("[%s] %s", event_name, message)

                elif event_name == "packer_log":
                    message = data.get("message") or data.get("log") or str(data)
                    self.logger.debug("packer: %s", message)

                elif event_name == "packer_artifact":
                    self.logger.info("Packer artifact: vmid=%s node=%s", data.get("vmid"), data.get("node"))

                elif event_name == "build_completed":
                    build.status = PackerBuildStatusChoices.COMPLETED
                    build.completed_at = timezone.now()
                    build.backend_response = data
                    build.save(
                        update_fields=["status", "completed_at", "backend_response", "last_updated"]
                    )
                    self.logger.info("Packer build completed: %s", backend_build_id)
                    self._publish_to_catalog(build)

                elif event_name == "build_failed":
                    error_msg = str(data.get("error") or data.get("detail") or data)
                    build.status = PackerBuildStatusChoices.FAILED
                    build.completed_at = timezone.now()
                    build.error = error_msg
                    build.backend_response = data
                    build.save(
                        update_fields=["status", "completed_at", "error", "backend_response", "last_updated"]
                    )
                    self.logger.error("Packer build failed: %s", error_msg)

                elif event_name == "complete":
                    break

        except ImageFactoryBackendError as exc:
            self._fail_build(build, str(exc))
            self.logger.error("Image factory stream error: %s", exc)

    # ------------------------------------------------------------------
    # Catalog publish (PHASE5)
    # ------------------------------------------------------------------

    def _publish_to_catalog(self, build: Any) -> None:
        """Create or update a CloudImageTemplate from a completed build (PHASE5)."""
        from netbox_proxbox.choices import CloudImageOSFamilyChoices
        from netbox_proxbox.models import CloudImageTemplate

        definition = build.definition
        if not definition.target_cluster_id:
            self.logger.warning(
                "Build %s completed but definition has no target_cluster; skipping catalog publish",
                build.pk,
            )
            return

        valid_families = {c[0] for c in CloudImageOSFamilyChoices.CHOICES}
        os_family = (
            definition.os_family
            if definition.os_family in valid_families
            else CloudImageOSFamilyChoices.GENERIC
        )

        # Slug: slugified output name + vmid suffix for uniqueness.
        slug = (slugify(build.output_name) or "packer-build") + f"-{build.output_vmid}"
        slug = slug[:255]

        try:
            template, created = CloudImageTemplate.objects.update_or_create(
                cluster_id=definition.target_cluster_id,
                source_vmid=build.output_vmid,
                defaults={
                    "name": build.output_name,
                    "slug": slug,
                    "os_family": os_family,
                    "os_release": definition.os_release or "",
                    "is_active": True,
                },
            )
        except Exception as exc:
            self.logger.error("Failed to publish build %s to catalog: %s", build.pk, exc)
            return

        build.cloud_image_template = template
        build.save(update_fields=["cloud_image_template", "last_updated"])
        action = "created" if created else "updated"
        self.logger.info(
            "Cloud image template %r %s for build %s", str(template), action, build.pk
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _fail_build(self, build: Any, error: str) -> None:
        build.status = PackerBuildStatusChoices.FAILED
        build.error = error
        build.completed_at = timezone.now()
        build.save(update_fields=["status", "error", "completed_at", "last_updated"])


__all__ = ("PackerImageBuildJob",)
