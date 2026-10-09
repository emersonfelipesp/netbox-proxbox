"""Actual native telemetry and explicit public export policy."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "provider_mode,mode",
    [
        ("global", "default"),
        ("global", "enabled"),
        ("global", "uppercase"),
        ("explicit", "enabled"),
        ("global", "disabled"),
        ("explicit", "disabled"),
        ("global", "empty"),
        ("global", "signals"),
        ("global", "logs-only"),
        ("global", "override"),
        ("explicit", "caller-empty"),
    ],
)
def test_native_export_contract(provider_mode: str, mode: str) -> None:
    """Verify native export controls and sensitive payload redaction."""
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("OTEL_", "FASTAPI_OTEL_"))
    }
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("native_telemetry_probe.py")),
            "tests.e2e.mock_proxmox_api",
            mode,
            provider_mode,
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OTLP export contract passed" in result.stdout


def test_public_factory_preserves_unconfigured_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep the public E2E mock exporter opt-in."""
    from tests.e2e.mock_proxmox_api import create_app

    for name in list(os.environ):
        if name.startswith(("OTEL_", "FASTAPI_OTEL_")):
            monkeypatch.delenv(name)
    create_app()
    assert not any(name.startswith("OTEL_") for name in os.environ)


@pytest.mark.parametrize(
    "flag,enabled",
    [
        (None, False),
        ("", False),
        ("true", True),
        ("True", True),
        ("TRUE", True),
        (" true ", False),
    ],
)
def test_native_auto_configure_environment(
    flag: str | None, enabled: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Use the native case-insensitive opt-in and explicit dictionary precedence."""
    from tests.e2e.mock_proxmox_api import create_app

    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    if flag is None:
        monkeypatch.delenv("FASTAPI_OTEL_AUTO_CONFIGURE", raising=False)
    else:
        monkeypatch.setenv("FASTAPI_OTEL_AUTO_CONFIGURE", flag)
    assert create_app()._telemetry["auto_configure"] is enabled
    assert (
        create_app(telemetry={"auto_configure": not enabled})._telemetry[
            "auto_configure"
        ]
        is not enabled
    )
