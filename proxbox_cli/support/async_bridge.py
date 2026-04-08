"""Async bridge: run coroutines synchronously with a Rich spinner."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import TypeVar

from proxbox_cli.support.console import console

T = TypeVar("T")


def run_with_spinner(coro: Coroutine[object, object, T]) -> T:
    """Bridge an async coroutine to sync with a Rich spinner."""
    with console.status("[bold]Fetching...[/bold]", spinner="dots"):
        return asyncio.run(coro)
