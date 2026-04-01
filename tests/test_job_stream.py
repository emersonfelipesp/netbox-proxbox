"""Tests for the live job SSE stream used by the Proxbox job detail page."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def job_stream_module(monkeypatch):
    """Load the job stream view with lightweight Django/NetBox stubs."""
    repo_root = Path(__file__).resolve().parents[1]

    django_module = types.ModuleType("django")
    django_http = types.ModuleType("django.http")

    class Http404(Exception):
        pass

    class HttpRequest:
        pass

    class StreamingHttpResponse:
        def __init__(self, streaming_content=None, status: int = 200, content_type=None):
            self.streaming_content = streaming_content
            self.status_code = status
            self.content_type = content_type

    class View:
        pass

    django_http.Http404 = Http404
    django_http.HttpRequest = HttpRequest
    django_http.StreamingHttpResponse = StreamingHttpResponse
    django_views = types.ModuleType("django.views")
    django_views.View = View
    django_views_decorators = types.ModuleType("django.views.decorators")
    django_views_decorators_csrf = types.ModuleType("django.views.decorators.csrf")
    django_views_decorators_csrf.csrf_exempt = lambda func: func
    django_utils = types.ModuleType("django.utils")
    django_utils_decorators = types.ModuleType("django.utils.decorators")
    django_utils_decorators.method_decorator = lambda decorator, name=None: (
        lambda obj: obj
    )

    netbox_module = types.ModuleType("netbox")
    netbox_jobs = types.ModuleType("netbox.jobs")

    class Job:
        objects = SimpleNamespace(filter=lambda **kwargs: SimpleNamespace(first=lambda: None))

    netbox_jobs.Job = Job
    netbox_module.jobs = netbox_jobs

    nbp_root = types.ModuleType("netbox_proxbox")
    nbp_root.__path__ = [str(repo_root / "netbox_proxbox")]
    nbp_views = types.ModuleType("netbox_proxbox.views")
    nbp_views.__path__ = [str(repo_root / "netbox_proxbox" / "views")]
    nbp_jobs = types.ModuleType("netbox_proxbox.jobs")
    nbp_jobs.SyncTypeChoices = SimpleNamespace(
        ALL="all",
        DEVICES="devices",
        STORAGE="storage",
        VIRTUAL_MACHINES="virtual-machines",
        VIRTUAL_MACHINES_DISKS="vm-disks",
        VIRTUAL_MACHINES_BACKUPS="vm-backups",
        VIRTUAL_MACHINES_SNAPSHOTS="vm-snapshots",
        NETWORK_INTERFACES="network-interfaces",
        IP_ADDRESSES="ip-addresses",
    )
    nbp_jobs.is_proxbox_sync_job = lambda job: True
    nbp_jobs.proxbox_sync_params_from_job = lambda job: {
        "sync_types": ["devices"],
        "proxmox_endpoint_ids": [],
        "netbox_endpoint_ids": [],
        "netbox_vm_ids": [],
    }
    nbp_jobs.expanded_sync_stages = lambda types: ["devices"]
    nbp_jobs.normalize_sync_types = lambda selected: selected
    nbp_jobs._sync_stream_path = lambda sync_type: f"dcim/{sync_type}/create/stream"
    nbp_jobs._VM_SCOPED_PATH_TEMPLATES = {}
    nbp_jobs._use_guest_agent_interface_name_setting = lambda: True
    nbp_jobs._proxbox_fetch_max_concurrency_setting = lambda: 8
    nbp_jobs._ignore_ipv6_link_local_addresses_setting = lambda: True
    nbp_services = types.ModuleType("netbox_proxbox.services")
    nbp_services.__path__ = [str(repo_root / "netbox_proxbox" / "services")]
    nbp_services.run_sync_stream = lambda *args, **kwargs: (
        {"stream": True, "response": {"ok": True, "message": "done"}},
        200,
    )

    monkeypatch.setitem(sys.modules, "django", django_module)
    monkeypatch.setitem(sys.modules, "django.http", django_http)
    monkeypatch.setitem(sys.modules, "django.views", django_views)
    monkeypatch.setitem(sys.modules, "django.views.decorators", django_views_decorators)
    monkeypatch.setitem(
        sys.modules, "django.views.decorators.csrf", django_views_decorators_csrf
    )
    monkeypatch.setitem(sys.modules, "django.utils", django_utils)
    monkeypatch.setitem(
        sys.modules, "django.utils.decorators", django_utils_decorators
    )
    monkeypatch.setitem(sys.modules, "netbox", netbox_module)
    monkeypatch.setitem(sys.modules, "netbox.jobs", netbox_jobs)
    monkeypatch.setitem(sys.modules, "netbox_proxbox", nbp_root)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.views", nbp_views)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.jobs", nbp_jobs)
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", nbp_services)

    sys.modules.pop("netbox_proxbox.views.job_stream", None)
    spec = importlib.util.spec_from_file_location(
        "netbox_proxbox.views.job_stream",
        repo_root / "netbox_proxbox" / "views" / "job_stream.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["netbox_proxbox.views.job_stream"] = module
    spec.loader.exec_module(module)
    return module


def test_job_stream_forwards_backend_message_frames(job_stream_module, monkeypatch):
    """The SSE bridge should stream backend frames, not just final stage markers."""
    module = job_stream_module
    services_mod = sys.modules["netbox_proxbox.services"]
    seen_paths: list[str] = []

    def fake_run_sync_stream(path, query_params=None, on_frame=None):
        seen_paths.append(path)
        if on_frame is not None:
            on_frame(
                "step",
                {
                    "step": "devices",
                    "status": "syncing",
                    "message": "Creating device pve01",
                },
            )
            on_frame(
                "message",
                {
                    "message": "Backend message: imported host data",
                },
            )
        return {"stream": True, "response": {"ok": True, "message": "done"}}, 200

    monkeypatch.setattr(services_mod, "run_sync_stream", fake_run_sync_stream)

    job = SimpleNamespace(pk=54, data={"proxbox_sync": {"params": {}}}, save=lambda **kwargs: None)
    view = module.JobStreamSSEView()
    chunks = list(view._stream_job_events(job))

    assert seen_paths == ["dcim/devices/create/stream"]
    assert any("event: step" in chunk and "Creating device pve01" in chunk for chunk in chunks)
    assert any("event: message" in chunk and "Backend message: imported host data" in chunk for chunk in chunks)
    assert any("event: complete" in chunk and '"ok": true' in chunk for chunk in chunks)
