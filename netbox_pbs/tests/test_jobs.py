"""AST-based contract tests for the PR C3 PBSSyncJob.

Pin the six-step branching pattern at the source level so the per-commit
gate runs offline: PBSSyncJob inherits from ``JobRunner``, declares
``Meta.name = "PBS Sync"``, calls ``branching_enabled_settings``,
creates+merges a branch when enabled, and threads
``netbox_branch_schema_id`` into the params dict shared with the HTTP
stage runner.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PKG_DIR = REPO_ROOT / "netbox_pbs"
JOBS = PKG_DIR / "jobs.py"
HTTP_CLIENT = PKG_DIR / "services" / "http_client.py"


def _module(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _find_class(module: ast.Module, name: str) -> ast.ClassDef | None:
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    return None


def _find_method(cls: ast.ClassDef, name: str) -> ast.FunctionDef | None:
    for node in cls.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def test_jobs_module_exists():
    assert JOBS.is_file(), f"missing {JOBS.relative_to(REPO_ROOT)}"


def test_pbs_sync_job_inherits_from_job_runner():
    module = _module(JOBS)
    cls = _find_class(module, "PBSSyncJob")
    assert cls is not None, "missing PBSSyncJob"
    base_names = [base.id if isinstance(base, ast.Name) else None for base in cls.bases]
    assert "JobRunner" in base_names, (
        f"PBSSyncJob must inherit from JobRunner; got {base_names}"
    )


def test_pbs_sync_job_meta_name():
    text = JOBS.read_text(encoding="utf-8")
    assert 'name = "PBS Sync"' in text, 'PBSSyncJob.Meta must declare name = "PBS Sync"'


def test_pbs_sync_job_run_reads_branching_enabled_settings():
    text = JOBS.read_text(encoding="utf-8")
    assert "branching_enabled_settings" in text, (
        "PBSSyncJob.run() must read branching_enabled_settings"
    )
    assert "create_and_provision_branch" in text, (
        "PBSSyncJob.run() must call create_and_provision_branch when enabled"
    )
    assert "merge_branch" in text, "PBSSyncJob.run() must call merge_branch on success"


def test_pbs_sync_job_threads_netbox_branch_schema_id():
    """The schema_id must be threaded into the params dict shared with stages."""
    text = JOBS.read_text(encoding="utf-8")
    assert '"netbox_branch_schema_id"' in text, (
        "PBSSyncJob.run() must populate params['netbox_branch_schema_id']"
    )
    assert "branch.schema_id" in text, (
        "PBSSyncJob.run() must read branch.schema_id when a branch is active"
    )


def test_pbs_sync_job_imports_run_pbs_sync_stage():
    text = JOBS.read_text(encoding="utf-8")
    assert "from netbox_pbs.services.http_client import" in text, (
        "PBSSyncJob must import its HTTP transport from netbox_pbs.services.http_client"
    )
    assert "run_pbs_sync_stage" in text, (
        "PBSSyncJob.run() must call run_pbs_sync_stage for each stage"
    )


def test_pbs_sync_job_enqueue_sets_long_timeout():
    text = JOBS.read_text(encoding="utf-8")
    assert "PBS_SYNC_JOB_TIMEOUT" in text, (
        "PBSSyncJob.enqueue must default to a long RQ job_timeout"
    )
    assert 'kwargs.setdefault("job_timeout", PBS_SYNC_JOB_TIMEOUT)' in text, (
        "PBSSyncJob.enqueue must apply PBS_SYNC_JOB_TIMEOUT via setdefault"
    )


def test_pbs_sync_job_queue_is_rq_queue_default():
    """Stock ``manage.py rqworker`` must pick up PBS jobs."""
    text = JOBS.read_text(encoding="utf-8")
    assert "PBS_SYNC_QUEUE_NAME = RQ_QUEUE_DEFAULT" in text, (
        "PBSSyncJob must enqueue on NetBox's default RQ queue"
    )


def test_http_client_defines_pbs_stages_full():
    text = HTTP_CLIENT.read_text(encoding="utf-8")
    assert "PBS_STAGES_FULL" in text, "http_client must expose PBS_STAGES_FULL"
    for stage in ("datastores", "snapshots", "jobs", "node"):
        assert f'"{stage}"' in text, f"http_client must declare the {stage!r} stage"


def test_run_pbs_sync_stage_threads_schema_id_into_query():
    """The HTTP transport must include netbox_branch_schema_id in the query string."""
    text = HTTP_CLIENT.read_text(encoding="utf-8")
    assert '"netbox_branch_schema_id"' in text, (
        "run_pbs_sync_stage must thread netbox_branch_schema_id into the query string"
    )


def test_run_pbs_sync_stage_uses_sse_accept_header():
    text = HTTP_CLIENT.read_text(encoding="utf-8")
    assert '"Accept": "text/event-stream"' in text, (
        "run_pbs_sync_stage must announce SSE via the Accept header"
    )
