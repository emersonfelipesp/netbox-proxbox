"""Testing-appliance configuration loaded after netbox-docker defaults."""

import os
from pathlib import Path


def _secret(name: str, environment_name: str) -> str:
    path = Path("/var/lib/proxbox-stack/secrets") / name
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return os.environ.get(environment_name, "")


SECRET_KEY = _secret("netbox-secret-key", "SECRET_KEY")
API_TOKEN_PEPPERS = {1: _secret("api-token-pepper", "API_TOKEN_PEPPER_1")}
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": "127.0.0.1",
        "NAME": "netbox",
        "USER": "netbox",
        "PASSWORD": _secret("postgres-password", "DB_PASSWORD"),
        "PORT": 5432,
        "CONN_MAX_AGE": 300,
    }
}
REDIS = {
    "tasks": {
        "HOST": "127.0.0.1",
        "PORT": 6379,
        "PASSWORD": "",
        "DATABASE": 0,
        "SSL": False,
    },
    "caching": {
        "HOST": "127.0.0.1",
        "PORT": 6379,
        "PASSWORD": "",
        "DATABASE": 1,
        "SSL": False,
    },
}

PLUGINS = ["netbox_proxbox"]
PLUGINS_CONFIG = {
    "netbox_proxbox": {
        "backend_url": "http://127.0.0.1:8800",
        "backend_verify_ssl": False,
    }
}
