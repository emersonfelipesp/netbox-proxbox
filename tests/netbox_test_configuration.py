"""Tests for netbox_test_configuration."""

import os

from netbox.configuration_testing import *  # noqa: F403
from netbox.configuration_testing import PLUGINS as BASE_PLUGINS

PLUGINS = [*BASE_PLUGINS, "netbox_proxbox"]
if os.environ.get("NETBOX_PROXBOX_TEST_PDM") == "1":
    PLUGINS.append("netbox_pdm")

# Local isolated harnesses may bind their disposable services away from the
# standard ports. CI leaves these unset and retains NetBox's stock test values.
if database_host := os.environ.get("NETBOX_TEST_DB_HOST"):
    DATABASES["default"]["HOST"] = database_host  # noqa: F405
if database_port := os.environ.get("NETBOX_TEST_DB_PORT"):
    DATABASES["default"]["PORT"] = int(database_port)  # noqa: F405
if redis_host := os.environ.get("NETBOX_TEST_REDIS_HOST"):
    for redis_config in REDIS.values():  # noqa: F405
        redis_config["HOST"] = redis_host
if redis_port := os.environ.get("NETBOX_TEST_REDIS_PORT"):
    for redis_config in REDIS.values():  # noqa: F405
        redis_config["PORT"] = int(redis_port)
