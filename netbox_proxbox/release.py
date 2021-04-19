from packaging import version
from django.conf import settings

NETBOX_RELEASE_CURRENT = version.parse(settings.VERSION)
NETBOX_RELEASE_28 = version.parse("2.8")
NETBOX_RELEASE_29 = version.parse("2.9")
NETBOX_RELEASE_210 = version.parse("2.10")