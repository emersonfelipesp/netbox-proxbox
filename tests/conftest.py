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


class JsonResponse(HttpResponse):
    def __init__(self, payload=None, status: int = 200, safe: bool = True):
        super().__init__(status=status, content=payload)
        self.payload = payload
        self.safe = safe

    def json(self):
        return self.payload


class HttpRequest:
    pass


class View:
    pass


class DummyPluginConfig:
    pass


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
        def first(self):
            return first

        def get(self, pk):
            if pk in objects_by_pk:
                return objects_by_pk[pk]
            raise does_not_exist()

    return Manager()


def _make_model_class(name: str, *, first=None, objects_by_pk=None):
    does_not_exist = type("DoesNotExist", (Exception,), {})
    cls = type(name, (), {"DoesNotExist": does_not_exist})
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
    get_fastapi_url=None,
):
    django_module = types.ModuleType("django")
    django_http = types.ModuleType("django.http")
    django_http.HttpRequest = HttpRequest
    django_http.HttpResponse = HttpResponse
    django_http.JsonResponse = JsonResponse

    django_shortcuts = types.ModuleType("django.shortcuts")
    django_shortcuts.render = lambda request, template_name, context=None: {
        "template": template_name,
        "context": context or {},
    }
    django_shortcuts.redirect = lambda name: {"redirect": name}

    django_views = types.ModuleType("django.views")
    django_views.View = View

    django_views_decorators = types.ModuleType("django.views.decorators")
    django_views_http = types.ModuleType("django.views.decorators.http")
    django_views_http.require_GET = lambda func: func

    django_urls = types.ModuleType("django.urls")
    django_urls.reverse = lambda *args, **kwargs: "/dummy/"

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

    utils_module = types.ModuleType("netbox_proxbox.utils")
    utils_module.get_fastapi_url = get_fastapi_url or (
        lambda obj: {
            "http_url": "https://proxbox.local:8800",
            "ip_address_url": "https://10.0.0.5:8800",
            "verify_ssl": True,
            "websocket_url": "wss://proxbox.local:8801/ws",
        }
    )
    utils_module.get_ip_address_host = lambda value: (
        str(value).split("/")[0] if value else "127.0.0.1"
    )

    stub_modules = {
        "django": django_module,
        "django.http": django_http,
        "django.shortcuts": django_shortcuts,
        "django.views": django_views,
        "django.views.decorators": django_views_decorators,
        "django.views.decorators.http": django_views_http,
        "django.urls": django_urls,
        "netbox": netbox_module,
        "netbox.plugins": netbox_plugins,
        "netbox_proxbox.models": models_module,
        "netbox_proxbox.utils": utils_module,
    }

    for name, module in stub_modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    package_name = "netbox_proxbox.views"
    package_module = types.ModuleType(package_name)
    package_module.__path__ = [
        str(Path(__file__).resolve().parents[1] / "netbox_proxbox" / "views")
    ]
    monkeypatch.setitem(sys.modules, package_name, package_module)

    sys.modules.pop(module_name, None)
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
        name="pve01",
        domain="pve.local",
        ip_address="10.0.0.30/24",
        port=8006,
        verify_ssl=False,
    )
