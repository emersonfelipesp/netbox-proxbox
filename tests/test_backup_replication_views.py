"""Contract tests for backup routine and replication view modules."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _src(path: str) -> str:
    return (REPO_ROOT / path).read_text()


# ── BackupRoutine view contracts ───────────────────────────────────────────────


def test_backup_routine_view_module_exports_expected_classes():
    src = _src("netbox_proxbox/views/backup_routine.py")
    expected = [
        "BackupRoutineView",
        "BackupRoutineListView",
        "BackupRoutineEditView",
        "BackupRoutineDeleteView",
        "BackupRoutineBulkDeleteView",
    ]
    for name in expected:
        assert name in src, f"Expected {name!r} in backup_routine.py"


def test_backup_routine_list_view_references_correct_template():
    src = _src("netbox_proxbox/views/backup_routine.py")
    assert "netbox_proxbox/backup_routine_list.html" in src


def test_backup_routine_list_template_exists():
    path = (
        REPO_ROOT
        / "netbox_proxbox"
        / "templates"
        / "netbox_proxbox"
        / "backup_routine_list.html"
    )
    assert path.exists(), "backup_routine_list.html template is missing"


def test_backup_routine_detail_template_exists():
    path = (
        REPO_ROOT
        / "netbox_proxbox"
        / "templates"
        / "netbox_proxbox"
        / "backup_routine.html"
    )
    assert path.exists(), "backup_routine.html detail template is missing"


def test_backup_routine_view_uses_select_related():
    src = _src("netbox_proxbox/views/backup_routine.py")
    assert "select_related" in src


def test_backup_routine_view_registers_model_view():
    src = _src("netbox_proxbox/views/backup_routine.py")
    assert "register_model_view" in src
    assert "BackupRoutine" in src


# ── Replication view contracts ─────────────────────────────────────────────────


def test_replication_view_module_exports_expected_classes():
    src = _src("netbox_proxbox/views/replication.py")
    expected = [
        "ReplicationView",
        "ReplicationListView",
        "ReplicationEditView",
        "ReplicationDeleteView",
        "ReplicationBulkDeleteView",
        "ReplicationTabView",
    ]
    for name in expected:
        assert name in src, f"Expected {name!r} in replication.py"


def test_replication_list_view_references_correct_template():
    src = _src("netbox_proxbox/views/replication.py")
    assert "netbox_proxbox/replication_list.html" in src


def test_replication_list_template_exists():
    path = (
        REPO_ROOT
        / "netbox_proxbox"
        / "templates"
        / "netbox_proxbox"
        / "replication_list.html"
    )
    assert path.exists(), "replication_list.html template is missing"


def test_replication_detail_template_exists():
    path = (
        REPO_ROOT
        / "netbox_proxbox"
        / "templates"
        / "netbox_proxbox"
        / "replication.html"
    )
    assert path.exists(), "replication.html detail template is missing"


def test_replication_view_uses_select_related():
    src = _src("netbox_proxbox/views/replication.py")
    assert "select_related" in src


def test_replication_has_vm_tab_view():
    src = _src("netbox_proxbox/views/replication.py")
    assert "ReplicationTabView" in src
    assert "VirtualMachine" in src
