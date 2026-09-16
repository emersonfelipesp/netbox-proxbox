"""Production call-site contracts for public RPC backend selection."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _calls(relative_path: str) -> list[ast.Call]:
    tree = ast.parse((ROOT / relative_path).read_text())
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "collect_systemctl_services"
    ]


def _assert_public_backend_selection(relative_path: str, trigger: str) -> None:
    calls = _calls(relative_path)
    matching = [
        call
        for call in calls
        if any(
            keyword.arg == "trigger"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value == trigger
            for keyword in call.keywords
        )
    ]
    assert matching, relative_path
    assert all(
        all(keyword.arg != "backend" for keyword in call.keywords) for call in matching
    )


def test_api_refresh_uses_public_backend_selection() -> None:
    _assert_public_backend_selection("netbox_proxbox/api/views.py", "on_demand")


def test_ui_refresh_uses_public_backend_selection() -> None:
    _assert_public_backend_selection(
        "netbox_proxbox/views/endpoints/proxmox.py", "on_demand"
    )


def test_scheduled_job_uses_public_backend_selection() -> None:
    _assert_public_backend_selection("netbox_proxbox/jobs.py", "scheduled")
