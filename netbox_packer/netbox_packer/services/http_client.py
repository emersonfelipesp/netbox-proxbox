"""Stub proxbox-api client for future Packer image factory calls."""

from __future__ import annotations

from typing import Any


def start_image_build(
    *,
    definition_id: int,
    variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Start a backend Packer image build in PHASE4."""
    raise NotImplementedError("Packer build start calls land in PHASE4.")


def fetch_image_build_status(*, backend_build_id: str) -> dict[str, Any]:
    """Fetch backend Packer image build status in PHASE4."""
    raise NotImplementedError("Packer build status calls land in PHASE4.")


def cancel_image_build(*, backend_build_id: str) -> dict[str, Any]:
    """Cancel a backend Packer image build in PHASE4."""
    raise NotImplementedError("Packer build cancellation calls land in PHASE4.")
