"""Shared Rich console instances for CLI support helpers."""

from __future__ import annotations

from rich.console import Console

console = Console()
stderr = Console(stderr=True)

__all__ = ["console", "stderr"]
