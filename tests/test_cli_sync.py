"""Tests for the ``pxb sync run`` Typer command."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

for module_name in ("click", "typer", "rich"):
    pytest.importorskip(module_name)

from typer.testing import CliRunner  # noqa: E402 — guarded by importorskip above

import proxbox_cli  # noqa: E402
from proxbox_cli import _locate_manage  # noqa: E402
from proxbox_cli._locate_manage import (  # noqa: E402
    ManageLocation,
    ManagePyNotFoundError,
)
from proxbox_cli.commands import sync as sync_module  # noqa: E402
from proxbox_cli.config import (  # noqa: E402
    ALLOW_INSECURE_TRANSPORT_ENV_VAR,
    API_KEY_ENV_VAR,
    BASE_URL_ENV_VAR,
    MAX_RESPONSE_BYTES_ENV_VAR,
    TIMEOUT_ENV_VAR,
)

HTTP_ENV_NAMES = (
    ALLOW_INSECURE_TRANSPORT_ENV_VAR,
    API_KEY_ENV_VAR,
    BASE_URL_ENV_VAR,
    MAX_RESPONSE_BYTES_ENV_VAR,
    TIMEOUT_ENV_VAR,
)
INVALID_HTTP_CONFIG: dict[str, object] = {
    "base_url": "ftp://invalid.example/private",
    "api_key": "file-secret",
    "timeout": 999,
    "unknown_http_option": True,
    "netbox_manage_py": "/configured/manage.py",
}


class FakePopen:
    """Minimal ``subprocess.Popen`` stand-in for argv capture and output replay.

    Captures the argv/kwargs the CLI passes through, replays a canned
    `stdout` stream (with merged stderr per the production design), and
    exposes the lifecycle hooks the production code calls.
    """

    instances: list[FakePopen] = []

    def __init__(
        self,
        argv: list[str],
        *,
        output: str = "",
        returncode: int = 0,
        **kwargs: Any,
    ) -> None:
        self.argv = argv
        self.kwargs = kwargs
        self._output = output
        self.returncode = returncode
        self.stdout = io.StringIO(output)
        self._terminated = False
        FakePopen.instances.append(self)

    @classmethod
    def reset(cls) -> None:
        cls.instances = []

    def wait(self, timeout: float | None = None) -> int:  # noqa: ARG002
        return self.returncode

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:  # noqa: ARG002
        return self._output, ""

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self._terminated = True

    def kill(self) -> None:
        self._terminated = True


def _popen_factory(output: str = "", returncode: int = 0):
    def factory(argv: list[str], **kwargs: Any) -> FakePopen:
        return FakePopen(argv, output=output, returncode=returncode, **kwargs)

    return factory


@pytest.fixture(autouse=True)
def _stub_locate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Every test resolves manage.py to a deterministic stub location."""
    FakePopen.reset()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    fake_manage = Path("/opt/netbox/manage.py")
    fake_python = Path("/opt/netbox/venv/bin/python")
    location = ManageLocation(manage_py=fake_manage, python=fake_python)
    monkeypatch.setattr(sync_module, "locate_manage_py", lambda **_: location)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _invoke(runner: CliRunner, args: list[str]):
    return runner.invoke(proxbox_cli.app, ["sync", "run", *args])


def _write_cli_config(tmp_path: Path, data: dict[str, object]) -> None:
    config_dir = tmp_path / "proxbox-cli"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(json.dumps(data))


def test_run_no_flags_argv(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sync_module.subprocess, "Popen", _popen_factory())
    result = _invoke(runner, [])
    assert result.exit_code == 0
    assert len(FakePopen.instances) == 1
    argv = FakePopen.instances[0].argv
    assert argv[:4] == [
        "/opt/netbox/venv/bin/python",
        "-u",
        "/opt/netbox/manage.py",
        "proxbox_sync",
    ]
    assert "--wait" not in argv
    assert "--user" not in argv
    assert "--timeout" not in argv
    assert "--poll-interval" in argv
    assert "--worker-grace" in argv


def test_run_wait_flag(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sync_module.subprocess, "Popen", _popen_factory())
    result = _invoke(runner, ["--wait"])
    assert result.exit_code == 0
    assert "--wait" in FakePopen.instances[0].argv


def test_run_user_flag(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sync_module.subprocess, "Popen", _popen_factory())
    result = _invoke(runner, ["--user", "admin"])
    assert result.exit_code == 0
    argv = FakePopen.instances[0].argv
    assert argv[argv.index("--user") + 1] == "admin"


def test_run_timeout_flag(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sync_module.subprocess, "Popen", _popen_factory())
    result = _invoke(runner, ["--timeout", "120"])
    assert result.exit_code == 0
    argv = FakePopen.instances[0].argv
    assert argv[argv.index("--timeout") + 1] == "120"


def test_run_poll_interval_flag(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sync_module.subprocess, "Popen", _popen_factory())
    result = _invoke(runner, ["--poll-interval", "0.5"])
    assert result.exit_code == 0
    argv = FakePopen.instances[0].argv
    assert argv[argv.index("--poll-interval") + 1] == "0.5"


def test_run_worker_grace_flag(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sync_module.subprocess, "Popen", _popen_factory())
    result = _invoke(runner, ["--worker-grace", "10"])
    assert result.exit_code == 0
    argv = FakePopen.instances[0].argv
    assert argv[argv.index("--worker-grace") + 1] == "10.0"


def test_run_exit_code_forwarded_zero(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        sync_module.subprocess,
        "Popen",
        _popen_factory(output="Enqueued ProxboxSyncJob (pk=7)\n", returncode=0),
    )
    result = _invoke(runner, [])
    assert result.exit_code == 0


def test_run_exit_code_forwarded_nonzero(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        sync_module.subprocess,
        "Popen",
        _popen_factory(output="CommandError: backend unreachable\n", returncode=1),
    )
    result = _invoke(runner, [])
    assert result.exit_code == 1


def test_json_mode_shape(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    output = "Enqueued ProxboxSyncJob (pk=42) on queue 'default'\n"
    monkeypatch.setattr(
        sync_module.subprocess,
        "Popen",
        _popen_factory(output=output, returncode=0),
    )
    result = _invoke(runner, ["--json"])
    assert result.exit_code == 0
    # Locate the JSON document — the CliRunner captures stdout via Rich.
    # The CLI bypasses Rich for the JSON write, so `result.stdout` carries it.
    payload = json.loads(result.stdout)
    assert payload["exit_code"] == 0
    assert payload["success"] is True
    assert payload["job_pk"] == 42
    assert payload["manage_py"] == "/opt/netbox/manage.py"
    assert payload["command"][0] == "/opt/netbox/venv/bin/python"
    assert "Enqueued" in payload["output"]


def test_json_mode_job_pk_none_when_absent(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        sync_module.subprocess,
        "Popen",
        _popen_factory(output="No ProxmoxEndpoint records configured\n", returncode=0),
    )
    result = _invoke(runner, ["--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["job_pk"] is None


def test_locate_failure_exits_nonzero(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    def raising_locate(**_: Any) -> ManageLocation:
        raise ManagePyNotFoundError(
            "could not find manage.py — set $NETBOX_PATH or run from "
            "inside the project tree"
        )

    monkeypatch.setattr(sync_module, "locate_manage_py", raising_locate)
    monkeypatch.setattr(sync_module.subprocess, "Popen", _popen_factory())
    result = _invoke(runner, [])
    assert result.exit_code != 0
    # The subprocess must not have been launched.
    assert FakePopen.instances == []


def test_netbox_path_override(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    def capturing_locate(**kwargs: Any) -> ManageLocation:
        captured.update(kwargs)
        return ManageLocation(
            manage_py=Path("/some/manage.py"), python=Path(sys.executable)
        )

    monkeypatch.setattr(sync_module, "locate_manage_py", capturing_locate)
    monkeypatch.setattr(sync_module.subprocess, "Popen", _popen_factory())
    custom = tmp_path / "custom" / "manage.py"
    custom.parent.mkdir()
    custom.write_text("")
    result = _invoke(runner, ["--netbox-path", str(custom)])
    assert result.exit_code == 0
    assert captured["override"] == custom


def test_popen_uses_merged_stream(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: stderr must be merged into stdout to avoid pipe deadlock."""
    monkeypatch.setattr(sync_module.subprocess, "Popen", _popen_factory())
    _invoke(runner, [])
    kwargs = FakePopen.instances[0].kwargs
    assert kwargs["stderr"] == sync_module.subprocess.STDOUT
    assert kwargs["stdout"] == sync_module.subprocess.PIPE
    assert kwargs["bufsize"] == 1
    assert kwargs["text"] is True
    assert kwargs["env"]["PYTHONUNBUFFERED"] == "1"


def test_local_run_ignores_invalid_http_configuration(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _write_cli_config(tmp_path, INVALID_HTTP_CONFIG)
    captured: dict[str, Any] = {}

    def capturing_locate(**kwargs: Any) -> ManageLocation:
        captured.update(kwargs)
        return ManageLocation(Path("/opt/netbox/manage.py"), Path(sys.executable))

    monkeypatch.setattr(sync_module, "locate_manage_py", capturing_locate)
    monkeypatch.setattr(sync_module.subprocess, "Popen", _popen_factory())
    assert _invoke(runner, []).exit_code == 0
    assert captured["config_manage_py"] == "/configured/manage.py"


def test_local_run_strips_http_environment_from_child(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in HTTP_ENV_NAMES:
        monkeypatch.setenv(name, f"secret-{name}")
    monkeypatch.setenv("PRESERVED_FOR_NETBOX", "preserved")
    monkeypatch.setattr(sync_module.subprocess, "Popen", _popen_factory())

    assert _invoke(runner, []).exit_code == 0
    child_environment = FakePopen.instances[0].kwargs["env"]
    assert all(name not in child_environment for name in HTTP_ENV_NAMES)
    assert child_environment["PRESERVED_FOR_NETBOX"] == "preserved"
