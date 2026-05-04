"""Tests for conftest."""

from __future__ import annotations

import importlib
import importlib.util
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest


class HttpResponse:
    def __init__(self, status: int = 200, content: str | None = None):
        self.status_code = status
        self.content = content
        self._headers = {}

    def __setitem__(self, key, value):
        self._headers[key] = value

    def __getitem__(self, key):
        return self._headers[key]


class HttpResponseRedirect(HttpResponse):
    def __init__(self, redirect_to: str, status: int = 302):
        super().__init__(status=status)
        self.url = redirect_to
        self["Location"] = redirect_to


class JsonResponse(HttpResponse):
    def __init__(self, payload=None, status: int = 200, safe: bool = True):
        super().__init__(status=status, content=payload)
        self.payload = payload
        self.safe = safe

    def json(self):
        return self.payload


class StreamingHttpResponse(HttpResponse):
    def __init__(
        self, streaming_content=None, status: int = 200, content_type: str | None = None
    ):
        super().__init__(status=status)
        self.streaming_content = streaming_content
        self.content_type = content_type


class HttpRequest:
    pass


class Http404(Exception):
    pass


class View:
    """Minimal Django CBV stub for plugin view tests."""

    http_method_names = [
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "head",
        "options",
        "trace",
    ]

    @classmethod
    def as_view(cls, **initkwargs):
        def view(request, *args, **kwargs):
            self = cls(**initkwargs)
            self.request = request
            self.args = args
            self.kwargs = kwargs
            return self.dispatch(request, *args, **kwargs)

        view.view_class = cls
        view.view_initkwargs = initkwargs
        return view

    def dispatch(self, request, *args, **kwargs):
        if request is None:
            request = SimpleNamespace(
                method="GET",
                user=SimpleNamespace(
                    is_authenticated=True,
                    has_perms=lambda *a, **k: True,
                    has_perm=lambda *a, **k: True,
                ),
            )
        method = (getattr(request, "method", "GET") or "GET").lower()
        if method in self.http_method_names:
            handler = getattr(self, method, self.http_method_not_allowed)
            return handler(request, *args, **kwargs)
        return self.http_method_not_allowed(request, *args, **kwargs)

    def http_method_not_allowed(self, request, *args, **kwargs):
        return HttpResponse(status=405)


class DummyPluginConfig:
    pass


class MessagesStub:
    def __init__(self):
        self.calls = []

    def success(self, request, message):
        self.calls.append(("success", message))

    def error(self, request, message):
        self.calls.append(("error", message))


@dataclass
class ResponseStub:
    payload: object
    status_code: int = 200
    ok: bool = True
    error: Exception | None = None

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.error:
            raise self.error
        if not self.ok or self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")


def _manager(*, first=None, objects_by_pk=None, does_not_exist=None):
    objects_by_pk = objects_by_pk or {}

    class Manager:
        def restrict(self, user, action):
            return self

        def first(self):
            return first

        def exists(self):
            return first is not None or bool(objects_by_pk)

        def filter(self, *args, **kwargs):
            return self

        def values_list(self, field_name, flat=False):
            values = []
            if objects_by_pk:
                values = [
                    getattr(obj, field_name, pk) for pk, obj in objects_by_pk.items()
                ]
            elif first is not None:
                values = [getattr(first, field_name, getattr(first, "pk", None))]
            if flat:
                return values
            return [(value,) for value in values]

        def count(self):
            return 0

        def aggregate(self, **kwargs):
            return {k: 0 for k in kwargs}

        def order_by(self, *args, **kwargs):
            return self

        def iterator(self, chunk_size=64):
            return iter(self)

        def get(self, *args, **kwargs):
            pk = kwargs.get("pk")
            if pk is None and args:
                pk = args[0]
            if pk in objects_by_pk:
                return objects_by_pk[pk]
            raise does_not_exist()

        def __iter__(self):
            if objects_by_pk:
                return iter(objects_by_pk.values())
            if first is not None:
                return iter([first])
            return iter([])

    return Manager()


def _make_model_class(name: str, *, first=None, objects_by_pk=None):
    does_not_exist = type("DoesNotExist", (Exception,), {})
    cls = type(name, (), {"DoesNotExist": does_not_exist})
    _mn = {
        "FastAPIEndpoint": "fastapiendpoint",
        "NetBoxEndpoint": "netboxendpoint",
        "ProxmoxEndpoint": "proxmoxendpoint",
    }.get(name, name.lower())
    cls._meta = SimpleNamespace(app_label="netbox_proxbox", model_name=_mn)
    cls.objects = _manager(
        first=first,
        objects_by_pk=objects_by_pk,
        does_not_exist=does_not_exist,
    )
    return cls


def load_plugin_module(
    module_name: str,
    *,
    monkeypatch,
    fastapi_endpoint=None,
    netbox_endpoint=None,
    proxmox_endpoint=None,
    proxbox_settings=None,
    get_fastapi_url=None,
):
    django_module = types.ModuleType("django")
    django_http = types.ModuleType("django.http")
    django_http.HttpRequest = HttpRequest
    django_http.HttpResponse = HttpResponse
    django_http.HttpResponseRedirect = HttpResponseRedirect
    django_http.JsonResponse = JsonResponse
    django_http.StreamingHttpResponse = StreamingHttpResponse
    django_http.Http404 = Http404

    django_shortcuts = types.ModuleType("django.shortcuts")
    django_shortcuts.render = lambda request, template_name, context=None: {
        "template": template_name,
        "context": context or {},
    }
    django_shortcuts.redirect = lambda name: {"redirect": name}

    def get_object_or_404(klass, *args, **kwargs):
        try:
            if hasattr(klass, "get"):
                return klass.get(*args, **kwargs)
        except Exception as exc:
            if type(exc).__name__ == "DoesNotExist":
                raise Http404 from exc
            raise
        raise Http404()

    django_shortcuts.get_object_or_404 = get_object_or_404

    django_views = types.ModuleType("django.views")
    django_views.View = View

    django_views_decorators = types.ModuleType("django.views.decorators")
    django_views_http = types.ModuleType("django.views.decorators.http")
    django_views_http.require_GET = lambda func: func
    django_views_http.require_http_methods = lambda methods: lambda func: func

    django_urls = types.ModuleType("django.urls")
    django_urls.reverse = lambda *args, **kwargs: "/dummy/"

    django_contrib = types.ModuleType("django.contrib")
    django_messages = MessagesStub()
    django_contrib.messages = django_messages

    django_utils = types.ModuleType("django.utils")
    django_utils_html = types.ModuleType("django.utils.html")

    def _format_html(*args, **kwargs):
        return "".join(str(a) for a in args)

    django_utils_html.format_html = _format_html

    django_utils_text = types.ModuleType("django.utils.text")
    django_utils_text.format_lazy = lambda *parts: "".join(str(p) for p in parts)

    django_utils_translation = types.ModuleType("django.utils.translation")
    django_utils_translation.gettext = lambda x: x
    django_utils_translation.gettext_lazy = lambda x: x

    django_utils_timezone = types.ModuleType("django.utils.timezone")
    django_utils_timezone.now = lambda: __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    )
    django_utils.timezone = django_utils_timezone

    django_db_models = types.ModuleType("django.db.models")

    class Q:
        def __init__(self, *args, **kwargs):
            pass

        def __or__(self, other):
            return self

    django_db_models.Q = Q

    class Count:
        def __init__(self, *args, **kwargs):
            pass

    django_db_models.Count = Count

    utilities_datetime = types.ModuleType("utilities.datetime")
    utilities_datetime.local_now = lambda: __import__("datetime").datetime(
        2026, 1, 1, 1, 0, 0, tzinfo=__import__("datetime").timezone.utc
    )

    netbox_constants = types.ModuleType("netbox.constants")
    netbox_constants.RQ_QUEUE_DEFAULT = "default"

    netbox_jobs = types.ModuleType("netbox.jobs")

    class JobRunner:
        pass

    netbox_jobs.JobRunner = JobRunner

    django_auth = types.ModuleType("django.contrib.auth")
    django_auth_decorators = types.ModuleType("django.contrib.auth.decorators")
    django_auth_decorators.login_required = lambda func: func
    django_auth_mixins = types.ModuleType("django.contrib.auth.mixins")

    class AccessMixin:
        def handle_no_permission(self):
            return HttpResponse(status=403)

    class LoginRequiredMixin:
        pass

    django_auth_mixins.AccessMixin = AccessMixin
    django_auth_mixins.LoginRequiredMixin = LoginRequiredMixin
    django_contrib.auth = django_auth

    utilities_permissions = types.ModuleType("utilities.permissions")
    utilities_permissions.get_permission_for_model = lambda model, action: (
        f"{getattr(model._meta, 'app_label', 'stub')}.{action}_"
        f"{getattr(model._meta, 'model_name', 'stub')}"
    )

    utilities_views = types.ModuleType("utilities.views")

    class ConditionalLoginRequiredMixin:
        def dispatch(self, request, *args, **kwargs):
            return super().dispatch(request, *args, **kwargs)

    class TokenConditionalLoginRequiredMixin:
        def dispatch(self, request, *args, **kwargs):
            return super().dispatch(request, *args, **kwargs)

    class ContentTypePermissionRequiredMixin:
        additional_permissions = []

        def get_required_permission(self):
            return "stub.view_stub"

        def has_permission(self):
            return True

        def dispatch(self, request, *args, **kwargs):
            if not self.has_permission():
                return HttpResponse(status=403)
            return super().dispatch(request, *args, **kwargs)

    def register_model_view(*args, **kwargs):
        def decorator(view_cls):
            return view_cls

        return decorator

    utilities_views.ConditionalLoginRequiredMixin = ConditionalLoginRequiredMixin
    utilities_views.TokenConditionalLoginRequiredMixin = (
        TokenConditionalLoginRequiredMixin
    )
    utilities_views.ContentTypePermissionRequiredMixin = (
        ContentTypePermissionRequiredMixin
    )
    utilities_views.register_model_view = register_model_view

    netbox_module = types.ModuleType("netbox")
    netbox_plugins = types.ModuleType("netbox.plugins")
    netbox_plugins.PluginConfig = DummyPluginConfig

    models_module = types.ModuleType("netbox_proxbox.models")
    models_module.FastAPIEndpoint = _make_model_class(
        "FastAPIEndpoint",
        first=fastapi_endpoint,
        objects_by_pk={1: fastapi_endpoint} if fastapi_endpoint is not None else {},
    )
    models_module.NetBoxEndpoint = _make_model_class(
        "NetBoxEndpoint",
        first=netbox_endpoint,
        objects_by_pk={1: netbox_endpoint} if netbox_endpoint is not None else {},
    )
    models_module.ProxmoxEndpoint = _make_model_class(
        "ProxmoxEndpoint",
        first=proxmox_endpoint,
        objects_by_pk={1: proxmox_endpoint} if proxmox_endpoint is not None else {},
    )
    virtualization_module = types.ModuleType("virtualization")
    virtualization_models_module = types.ModuleType("virtualization.models")
    virtualization_models_module.Cluster = _make_model_class("Cluster")
    virtualization_models_module.VirtualMachine = _make_model_class("VirtualMachine")
    virtualization_module.models = virtualization_models_module
    core_module = types.ModuleType("core")
    core_choices = types.ModuleType("core.choices")
    core_choices.JobStatusChoices = SimpleNamespace(
        ENQUEUED_STATE_CHOICES=("pending", "scheduled", "running"),
        TERMINAL_STATE_CHOICES=("completed", "errored", "failed"),
        STATUS_PENDING="pending",
        STATUS_SCHEDULED="scheduled",
        STATUS_RUNNING="running",
        STATUS_COMPLETED="completed",
        STATUS_ERRORED="errored",
        STATUS_FAILED="failed",
        STATUS_CANCELED="canceled",
    )
    core_models = types.ModuleType("core.models")
    core_models.Job = _make_model_class("Job")
    core_utils = types.ModuleType("core.utils")
    core_utils.stop_rq_job = lambda job_id: []
    core_module.choices = core_choices
    core_module.models = core_models
    models_module.ProxmoxCluster = _make_model_class("ProxmoxCluster")
    models_module.ProxmoxNode = _make_model_class("ProxmoxNode")
    models_module.ProxmoxStorage = _make_model_class("ProxmoxStorage")
    models_module.ProxmoxStorageVirtualDisk = _make_model_class(
        "ProxmoxStorageVirtualDisk"
    )
    models_module.BackupRoutine = _make_model_class("BackupRoutine")
    models_module.Replication = _make_model_class("Replication")
    models_module.VMBackup = _make_model_class("VMBackup")
    models_module.VMSnapshot = _make_model_class("VMSnapshot")

    if proxbox_settings is None:
        proxbox_settings = SimpleNamespace(
            backend_log_file_path="/var/log/proxbox.log",
            primary_ip_preference="ipv4",
            encryption_key="",
            save=lambda **kwargs: None,
        )

    class _ProxboxPluginSettings:
        @classmethod
        def get_solo(cls):
            return proxbox_settings

    _ProxboxPluginSettings._meta = SimpleNamespace(
        app_label="netbox_proxbox",
        model_name="proxboxpluginsettings",
    )
    models_module.ProxboxPluginSettings = _ProxboxPluginSettings

    utils_module = types.ModuleType("netbox_proxbox.utils")
    utils_module.get_fastapi_url = get_fastapi_url or (
        lambda obj: {
            "http_url": "https://proxbox.local:8800",
            "ip_address_url": "https://10.0.0.5:8800",
            "verify_ssl": True,
            "websocket_url": "wss://proxbox.local:8801/ws",
        }
    )
    utils_module.get_backend_auth_headers = lambda obj: (
        {}
        if not (getattr(obj, "token", "") or "").strip()
        else {
            "Authorization": (
                getattr(obj, "token").strip()
                if getattr(obj, "token").strip().startswith(("Bearer ", "Token "))
                else f"Bearer {getattr(obj, 'token').strip()}"
            )
        }
    )
    utils_module.get_ip_address_host = lambda value: (
        str(value).split("/")[0] if value else "127.0.0.1"
    )

    def _resolve_vm_type_stub(vm: object) -> str:
        vm_type_obj = getattr(vm, "virtual_machine_type", None)
        if vm_type_obj and hasattr(vm_type_obj, "slug"):
            slug = str(vm_type_obj.slug)
            if "lxc" in slug:
                return "lxc"
            if "qemu" in slug:
                return "qemu"
        cf = getattr(vm, "custom_field_data", None) or {}
        return str(cf.get("proxmox_vm_type") or cf.get("cf_proxmox_vm_type") or "qemu")

    utils_module.resolve_vm_type = _resolve_vm_type_stub

    stub_modules = {
        "django": django_module,
        "django.http": django_http,
        "django.shortcuts": django_shortcuts,
        "django.views": django_views,
        "django.views.decorators": django_views_decorators,
        "django.views.decorators.http": django_views_http,
        "django.urls": django_urls,
        "django.utils": django_utils,
        "django.utils.html": django_utils_html,
        "django.utils.text": django_utils_text,
        "django.utils.timezone": django_utils_timezone,
        "django.utils.translation": django_utils_translation,
        "django.db.models": django_db_models,
        "utilities.datetime": utilities_datetime,
        "netbox.constants": netbox_constants,
        "netbox.jobs": netbox_jobs,
        "django.contrib": django_contrib,
        "django.contrib.auth": django_auth,
        "django.contrib.auth.decorators": django_auth_decorators,
        "django.contrib.auth.mixins": django_auth_mixins,
        "django.contrib.messages": django_messages,
        "core": core_module,
        "core.choices": core_choices,
        "core.models": core_models,
        "core.utils": core_utils,
        "netbox": netbox_module,
        "netbox.plugins": netbox_plugins,
        "netbox_proxbox.models": models_module,
        "virtualization": virtualization_module,
        "virtualization.models": virtualization_models_module,
        "netbox_proxbox.utils": utils_module,
        "utilities.permissions": utilities_permissions,
        "utilities.views": utilities_views,
    }

    django_rq_mod = types.ModuleType("django_rq")

    class _QueueStub:
        def fetch_job(self, jid):
            return None

    django_rq_mod.get_queue = lambda queue_name: _QueueStub()
    stub_modules["django_rq"] = django_rq_mod

    rq_root = types.ModuleType("rq")
    rq_exceptions = types.ModuleType("rq.exceptions")

    class InvalidJobOperation(Exception):
        pass

    rq_exceptions.InvalidJobOperation = InvalidJobOperation

    rq_job_mod = types.ModuleType("rq.job")

    class Job:
        pass

    class JobStatus:
        QUEUED = "queued"
        DEFERRED = "deferred"
        SCHEDULED = "scheduled"
        STARTED = "started"

    rq_job_mod.Job = Job
    rq_job_mod.JobStatus = JobStatus

    stub_modules["rq"] = rq_root
    stub_modules["rq.exceptions"] = rq_exceptions
    stub_modules["rq.job"] = rq_job_mod

    for name, module in stub_modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    repo = Path(__file__).resolve().parents[1]

    utilities_root = types.ModuleType("utilities")
    monkeypatch.setitem(sys.modules, "utilities", utilities_root)
    utilities_choices_mod = types.ModuleType("utilities.choices")

    class _StubChoiceSet:
        pass

    utilities_choices_mod.ChoiceSet = _StubChoiceSet
    monkeypatch.setitem(sys.modules, "utilities.choices", utilities_choices_mod)

    nbp_root = types.ModuleType("netbox_proxbox")
    nbp_root.__path__ = [str(repo / "netbox_proxbox")]
    nbp_root.ProxboxConfig = SimpleNamespace(default_settings={})
    monkeypatch.setitem(sys.modules, "netbox_proxbox", nbp_root)

    nbp_choices = types.ModuleType("netbox_proxbox.choices")

    class _SyncTypeChoices(_StubChoiceSet):
        BACKUP_ROUTINES = "backup-routines"
        REPLICATIONS = "replications"
        TASK_HISTORY = "task-history"
        VIRTUAL_MACHINES = "virtual-machines"
        STORAGE = "storage"
        VIRTUAL_MACHINES_DISKS = "vm-disks"
        VIRTUAL_MACHINES_BACKUPS = "vm-backups"
        VIRTUAL_MACHINES_SNAPSHOTS = "vm-snapshots"
        DEVICES = "devices"
        NETWORK_INTERFACES = "network-interfaces"
        IP_ADDRESSES = "ip-addresses"
        ALL = "all"

    nbp_choices.SyncTypeChoices = _SyncTypeChoices
    nbp_choices.NetBoxTokenVersionChoices = SimpleNamespace(V1="v1", V2="v2")
    nbp_choices.ReplicationStatusChoices = SimpleNamespace(
        ACTIVE="active", STALE="stale"
    )
    nbp_choices.ProxmoxVMTypeChoices = SimpleNamespace(QEMU="qemu", LXC="lxc")
    monkeypatch.setitem(sys.modules, "netbox_proxbox.choices", nbp_choices)

    nbp_jobs = types.ModuleType("netbox_proxbox.jobs")

    class _ProxboxSyncJob:
        @classmethod
        def enqueue(cls, **kwargs):
            raise RuntimeError("ProxboxSyncJob.enqueue must be patched in tests")

    nbp_jobs.ProxboxSyncJob = _ProxboxSyncJob
    nbp_jobs.PROXBOX_SYNC_QUEUE_NAME = "default"
    nbp_jobs.is_proxbox_sync_job = lambda job: True
    nbp_jobs.proxbox_sync_params_from_job = lambda job: {"sync_types": ["all"]}
    monkeypatch.setitem(sys.modules, "netbox_proxbox.jobs", nbp_jobs)

    forms_package = types.ModuleType("netbox_proxbox.forms")
    forms_package.__path__ = [str(repo / "netbox_proxbox" / "forms")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox.forms", forms_package)

    schedule_sync_stub = types.ModuleType("netbox_proxbox.forms.schedule_sync")

    class ScheduleSyncForm:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    schedule_sync_stub.ScheduleSyncForm = ScheduleSyncForm
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.forms.schedule_sync", schedule_sync_stub
    )

    schedule_hints_stub = types.ModuleType("netbox_proxbox.schedule_hints")
    schedule_hints_stub.has_recurring_proxbox_sync_all = lambda user: True
    schedule_hints_stub.quick_schedule_home_form_kwargs = lambda: {}
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.schedule_hints", schedule_hints_stub
    )

    package_name = "netbox_proxbox.views"
    package_module = types.ModuleType(package_name)
    package_module.__path__ = [str(repo / "netbox_proxbox" / "views")]
    monkeypatch.setitem(sys.modules, package_name, package_module)

    proxbox_access = types.ModuleType("netbox_proxbox.views.proxbox_access")
    proxbox_access.permission_enqueue_proxbox_sync = lambda: "stub.enqueue_proxbox_sync"
    proxbox_access.permission_change_proxbox_plugin_settings = lambda: (
        "stub.change_proxboxpluginsettings"
    )
    proxbox_access.user_may_access_proxbox_dashboard = lambda user: True
    monkeypatch.setitem(
        sys.modules, "netbox_proxbox.views.proxbox_access", proxbox_access
    )

    sys.modules.pop(module_name, None)
    sys.modules.pop("netbox_proxbox.services.service_status", None)
    sys.modules.pop("netbox_proxbox.services.backend_proxy", None)
    sys.modules.pop("netbox_proxbox.services", None)
    relative_parts = module_name.split(".")[2:]
    module_path = (
        Path(__file__).resolve().parents[1]
        / "netbox_proxbox"
        / "views"
        / Path(*relative_parts)
    ).with_suffix(".py")
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    module._messages_stub = django_messages
    return module


@pytest.fixture
def fastapi_endpoint():
    return SimpleNamespace(
        id=1,
        name="proxbox-api",
        domain="proxbox.local",
        ip_address="10.0.0.5/24",
        port=8800,
        verify_ssl=True,
        token="backend-token",
        websocket_port=8801,
        websocket_domain="proxbox.local",
        use_websocket=True,
    )


@pytest.fixture
def netbox_endpoint():
    return SimpleNamespace(
        id=1,
        pk=1,
        name="netbox",
        domain="netbox.local",
        ip_address=SimpleNamespace(address="10.0.0.20/24"),
        port=443,
        token=SimpleNamespace(key="token-1"),
        effective_token_value="token-1",
        effective_token_version="v1",
        token_key="",
        token_secret="",
        verify_ssl=True,
    )


@pytest.fixture
def proxmox_endpoint():
    return SimpleNamespace(
        id=1,
        pk=1,
        name="pve01",
        domain="pve.local",
        ip_address="10.0.0.30/24",
        port=8006,
        username="root@pam",
        password="secret",
        token_name="proxbox2",
        token_value="token-secret",
        verify_ssl=False,
    )
