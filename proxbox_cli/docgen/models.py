"""Value objects for Proxbox CLI documentation generation."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

DEFAULT_CAPTURE_TIMEOUT_SECONDS = 15.0


@dataclass(frozen=True, slots=True)
class CaptureSpec:
    """Describe one CLI command invocation to capture for docs."""

    section: str
    title: str
    argv: list[str]
    notes: str = ""


@dataclass(slots=True)
class CaptureResult:
    """Store one captured CLI invocation and its rendered output."""

    section: str
    title: str
    argv: list[str]
    exit_code: int
    elapsed_seconds: float
    stdout: str
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Handle to dict."""
        return {
            "section": self.section,
            "title": self.title,
            "argv": list(self.argv),
            "exit_code": self.exit_code,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "stdout": self.stdout,
            "notes": self.notes,
        }


def build_slug(section: str, title: str) -> str:
    """Create a stable filesystem-safe slug for a captured command."""
    raw = f"{section}-{title}".lower()
    slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug
