"""SDK-disabled compatibility regressions for all application factories."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROBE = Path(__file__).with_name("sdk_disabled_probe.py")


@pytest.mark.parametrize("provider_mode", ("explicit", "global"))
def test_sdk_disabled_preserves_selected_providers_without_application_export(
    provider_mode: str,
) -> None:
    """Run the real factory and OTLP exporters in a fresh process."""
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("OTEL_")
    }
    environment["PYTHONPATH"] = str(ROOT)
    result = subprocess.run(
        [sys.executable, str(PROBE), "mock", provider_mode],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"status": "passed"' in result.stdout
