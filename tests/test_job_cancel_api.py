"""Source contracts for the Proxbox Sync job cancel REST endpoint (issue #268)."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
API_JOBS = REPO_ROOT / "netbox_proxbox" / "api" / "jobs.py"
API_URLS = REPO_ROOT / "netbox_proxbox" / "api" / "urls.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_cancel_apiview_exists_and_is_post_only():
    src = _read(API_JOBS)
    assert "class ProxboxJobCancelAPIView(APIView):" in src
    # POST-only (plus options), never GET/PUT/PATCH/DELETE on this action.
    assert 'http_method_names = ["post", "options"]' in src
    assert "def post(self, request: Request, pk: int) -> Response:" in src


def test_cancel_apiview_reuses_ui_cancel_logic_not_a_reimplementation():
    src = _read(API_JOBS)
    # Must reuse the exact helpers the UI cancel uses, not duplicate RQ logic.
    assert (
        "from netbox_proxbox.views.job_cancel import cancel_rq_job_for_netbox_job"
        in src
    )
    assert "from netbox_proxbox.jobs import is_proxbox_sync_job" in src
    assert "cancel_rq_job_for_netbox_job(job)" in src
    assert "is_proxbox_sync_job(job)" in src
    assert "job.terminate(" in src
    assert "JobStatusChoices.STATUS_FAILED" in src


def test_cancel_apiview_gates_on_job_delete_permission():
    src = _read(API_JOBS)
    assert "class _ProxboxJobCancelPermission(BasePermission):" in src
    assert 'user.has_perm("core.delete_job")' in src
    assert "permission_classes = [_ProxboxJobCancelPermission]" in src


def test_cancel_apiview_restricts_queryset_and_validates_job_kind():
    src = _read(API_JOBS)
    assert 'Job.objects.restrict(request.user, "view")' in src
    # Non-Proxbox jobs are rejected; already-terminal jobs are a safe no-op.
    assert "This action only applies to Proxbox Sync jobs." in src
    assert "JobStatusChoices.TERMINAL_STATE_CHOICES" in src


def test_cancel_route_is_registered_under_jobs_pk_cancel():
    urls = _read(API_URLS)
    assert "from .jobs import ProxboxJobCancelAPIView" in urls
    assert '"jobs/<int:pk>/cancel/"' in urls
    assert "ProxboxJobCancelAPIView.as_view()" in urls
    assert 'name="api-job-cancel"' in urls
