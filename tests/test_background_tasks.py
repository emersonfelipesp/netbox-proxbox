"""Execute the strict configuration predicate without a Django application."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys
import types

import pytest


@pytest.fixture
def background_module(monkeypatch):
    path = Path(__file__).parents[1] / "netbox_proxbox/background_tasks.py"
    spec = importlib.util.spec_from_file_location("proxbox_background_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    conf = SimpleNamespace(settings=SimpleNamespace(PLUGINS_CONFIG={}))
    monkeypatch.setitem(sys.modules, "django.conf", conf)
    return module, conf.settings


@pytest.mark.parametrize(
    "config,expected",
    [
        ({}, True),
        ({"automatic_background_tasks": True}, True),
        ({"automatic_background_tasks": False}, False),
    ],
)
def test_default_and_explicit_boolean(background_module, config, expected):
    module, settings = background_module
    settings.PLUGINS_CONFIG = {"netbox_proxbox": config}
    assert module.automatic_background_tasks_enabled() is expected


@pytest.mark.parametrize("value", [None, 0, 1, "false", "true", [], {}])
def test_malformed_option_rejects(background_module, value):
    module, settings = background_module
    settings.PLUGINS_CONFIG = {"netbox_proxbox": {"automatic_background_tasks": value}}
    with pytest.raises(ValueError, match="must be a boolean"):
        module.automatic_background_tasks_enabled()


@pytest.mark.parametrize(
    "change",
    [
        {"user_id": 4},
        {"object_id": 3},
        {"object_type_id": 3},
        {"name": "Custom monitor"},
        {"interval": 2},
        {"interval": None},
    ],
)
def test_manual_and_custom_jobs_are_not_automatic(background_module, change):
    module, _settings = background_module
    fields = {
        "name": "Proxmox Service Monitoring",
        "user_id": None,
        "object_id": None,
        "interval": 1,
    }
    assert module.is_automatic_monitor(SimpleNamespace(**fields))
    assert not module.is_automatic_monitor(SimpleNamespace(**(fields | change)))


@pytest.fixture
def plugin_module(monkeypatch, background_module):
    background, settings = background_module
    root = Path(__file__).parents[1] / "netbox_proxbox"
    plugins = types.ModuleType("netbox.plugins")

    class PluginConfig:
        @classmethod
        def validate(cls, config, version):
            pass

    plugins.PluginConfig = PluginConfig
    compat = types.ModuleType("proxbox_startup_test.compat")
    compat.PLUGIN_MIN_VERSION = "4.5.8"
    compat.PLUGIN_MAX_VERSION = "4.7.0"
    compat.register_netbox_compatibility_check = lambda *_args: None
    monkeypatch.setitem(sys.modules, "netbox.plugins", plugins)
    monkeypatch.setitem(sys.modules, "proxbox_startup_test.compat", compat)
    monkeypatch.setitem(
        sys.modules, "proxbox_startup_test.background_tasks", background
    )
    spec = importlib.util.spec_from_file_location(
        "proxbox_startup_test",
        root / "__init__.py",
        submodule_search_locations=[str(root)],
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "proxbox_startup_test", module)
    spec.loader.exec_module(module)
    return module, settings


@pytest.mark.parametrize(
    "argv",
    [
        ["gunicorn"],
        ["uvicorn"],
        ["manage.py", "runserver"],
        ["manage.py", "rqworker"],
        ["manage.py", "migrate"],
        ["manage.py", "shell"],
    ],
)
@pytest.mark.parametrize("enabled", [False, True])
def test_startup_roles_obey_option(plugin_module, monkeypatch, argv, enabled):
    module, settings = plugin_module
    settings.PLUGINS_CONFIG = {
        "netbox_proxbox": {"automatic_background_tasks": enabled}
    }
    monkeypatch.setattr(sys, "argv", argv)
    created = []

    def thread(**kwargs):
        created.append(kwargs)
        return SimpleNamespace(start=lambda: None)

    monkeypatch.setattr(module.threading, "Thread", thread)
    module._start_automatic_startup_push()
    expected = enabled and (
        argv[0] != "manage.py" or argv[1] in {"runserver", "rqworker"}
    )
    assert bool(created) is expected
    if expected:
        assert created == [
            {
                "target": module._deferred_startup_push,
                "daemon": True,
                "name": "proxbox-startup-endpoint-push",
            }
        ]


def test_plugin_validation_and_default(plugin_module):
    module, _settings = plugin_module
    assert module.ProxboxConfig.default_settings["automatic_background_tasks"] is True
    assert module.ProxboxConfig.default_settings["sync_node_interfaces"] is False
    module.ProxboxConfig.validate({}, "4.7.0")
    module.ProxboxConfig.validate({"automatic_background_tasks": False}, "4.7.0")
    module.ProxboxConfig.validate({"sync_node_interfaces": True}, "4.7.0")
    with pytest.raises(ValueError):
        module.ProxboxConfig.validate({"automatic_background_tasks": "false"}, "4.7.0")
    with pytest.raises(ValueError, match="sync_node_interfaces must be a boolean"):
        module.ProxboxConfig.validate({"sync_node_interfaces": "true"}, "4.7.0")
