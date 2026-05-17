"""NetBox test configuration for the netbox-packer sibling plugin."""

from netbox.configuration_testing import *  # noqa: F403
from netbox_branching.utilities import DynamicSchemaDict


DATABASES = DynamicSchemaDict(DATABASES)  # noqa: F405
DATABASE_ROUTERS = ["netbox_branching.database.BranchAwareRouter"]
DEVELOPER = True
PLUGINS = ["netbox_proxbox", "netbox_packer", "netbox_branching"]
