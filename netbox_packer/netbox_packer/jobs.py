"""Stub background job shell for netbox-packer.

Real Packer build dispatch is intentionally deferred to PHASE4.
"""

from __future__ import annotations

from netbox.jobs import JobRunner


class PackerImageBuildJob(JobRunner):
    """Placeholder job runner for a future image build action."""

    class Meta:
        name = "Packer Image Build"

    def run(self, **_kwargs: object) -> None:
        raise NotImplementedError("Packer image build execution lands in PHASE4.")


__all__ = ("PackerImageBuildJob",)
