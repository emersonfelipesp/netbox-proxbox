"""Tests for netbox_test_configuration."""

import sys
from pathlib import Path

from netbox.configuration_testing import *  # noqa: F403
from netbox.configuration_testing import PLUGINS as BASE_PLUGINS


PACKER_ROOT = Path(__file__).resolve().parents[1] / "netbox_packer"
if PACKER_ROOT.exists() and str(PACKER_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKER_ROOT))

PLUGINS = [*BASE_PLUGINS, "netbox_proxbox", "netbox_packer"]
