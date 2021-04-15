"""NetBox configuration."""
import os
from distutils.util import strtobool
from packaging import version
from django.core.exceptions import ImproperlyConfigured
from .settings import VERSION  # pylint: disable=relative-beyond-top-level


NETBOX_RELEASE_CURRENT = version.parse(VERSION)
NETBOX_RELEASE_28 = version.parse("2.8")
NETBOX_RELEASE_29 = version.parse("2.9")
NETBOX_RELEASE_211 = version.parse("2.11")

# Enforce required configuration parameters
for key in [
    "ALLOWED_HOSTS",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_HOST",
    "POSTGRES_PASSWORD",
    "REDIS_HOST",
    "REDIS_PASSWORD",
    "SECRET_KEY",
]:
    if not os.environ.get(key):
        raise ImproperlyConfigured(f"Required environment variable {key} is missing.")


def is_truthy(arg):
    """Convert "truthy" strings into Booleans.

    Examples:
        >>> is_truthy('yes')
        True
    Args:
        arg (str): Truthy string (True values are y, yes, t, true, on and 1; false values are n, no,
        f, false, off and 0. Raises ValueError if val is anything else.
    """
    if isinstance(arg, bool):
        return arg

    try:
        bool_val = strtobool(arg)
    except ValueError:
        raise ImproperlyConfigured(f"Unexpected variable value: {arg}")  # pylint: disable=raise-missing-from

    return bool(bool_val)


# For reference see http://netbox.readthedocs.io/en/latest/configuration/mandatory-settings/
# Based on https://github.com/digitalocean/netbox/blob/develop/netbox/netbox/configuration.example.py

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#########################
#                       #
#   Required settings   #
#                       #
#########################

# This is a list of valid fully-qualified domain names (FQDNs) for the NetBox server. NetBox will not permit write
# access to the server via any other hostnames. The first FQDN in the list will be treated as the preferred name.
#
# Example: ALLOWED_HOSTS = ['netbox.example.com', 'netbox.internal.local']
ALLOWED_HOSTS = os.environ["ALLOWED_HOSTS"].split(" ")

# PostgreSQL database configuration.
DATABASE = {
    "NAME": os.environ["POSTGRES_DB"],  # Database name
    "USER": os.environ["POSTGRES_USER"],  # PostgreSQL username
    "PASSWORD": os.environ["POSTGRES_PASSWORD"],
    # PostgreSQL password
    "HOST": os.environ["POSTGRES_HOST"],  # Database server
    "PORT": 5432 if "POSTGRES_PORT" not in os.environ else int(os.environ["POSTGRES_PORT"]),  # Database port
}

# This key is used for secure generation of random numbers and strings. It must never be exposed outside of this file.
# For optimal security, SECRET_KEY should be at least 50 characters in length and contain a mix of letters, numbers, and
# symbols. NetBox will not run without this defined. For more information, see
# https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-SECRET_KEY
SECRET_KEY = os.environ["SECRET_KEY"]

# Redis database settings. The Redis database is used for caching and background processing such as webhooks
# Seperate sections for webhooks and caching allow for connecting to seperate Redis instances/datbases if desired.
# Full connection details are required in both sections, even if they are the same.
REDIS = {
    "caching": {
        "HOST": os.environ["REDIS_HOST"],
        "PORT": int(os.environ.get("REDIS_PORT", 6379)),
        "PASSWORD": os.environ["REDIS_PASSWORD"],
        "DATABASE": 1,
        "SSL": is_truthy(os.environ.get("REDIS_SSL", False)),
    },
    "tasks": {
        "HOST": os.environ["REDIS_HOST"],
        "PORT": int(os.environ.get("REDIS_PORT", 6379)),
        "PASSWORD": os.environ["REDIS_PASSWORD"],
        "DATABASE": 0,
        "SSL": is_truthy(os.environ.get("REDIS_SSL", False)),
    },
}

if NETBOX_RELEASE_28 < NETBOX_RELEASE_CURRENT < NETBOX_RELEASE_29:
    # NetBox 2.8.x Specific Settings
    REDIS["caching"]["DEFAULT_TIMEOUT"] = 300
    REDIS["tasks"]["DEFAULT_TIMEOUT"] = 300
elif NETBOX_RELEASE_CURRENT < NETBOX_RELEASE_211:
    RQ_DEFAULT_TIMEOUT = 300
else:
    raise ImproperlyConfigured(f"Version {NETBOX_RELEASE_CURRENT} of NetBox is unsupported at this time.")

#########################
#                       #
#   Optional settings   #
#                       #
#########################

# Specify one or more name and email address tuples representing NetBox administrators. These people will be notified of
# application errors (assuming correct email settings are provided).
ADMINS = [
    # ['John Doe', 'jdoe@example.com'],
]

# Optionally display a persistent banner at the top and/or bottom of every page. HTML is allowed. To display the same
# content in both banners, define BANNER_TOP and set BANNER_BOTTOM = BANNER_TOP.
BANNER_TOP = os.environ.get("BANNER_TOP", "")
BANNER_BOTTOM = os.environ.get("BANNER_BOTTOM", "")

# Text to include on the login page above the login form. HTML is allowed.
BANNER_LOGIN = os.environ.get("BANNER_LOGIN", "")

# Base URL path if accessing NetBox within a directory. For example, if installed at http://example.com/netbox/, set:
# BASE_PATH = 'netbox/'
BASE_PATH = os.environ.get("BASE_PATH", "")

# Maximum number of days to retain logged changes. Set to 0 to retain changes indefinitely. (Default: 90)
CHANGELOG_RETENTION = int(os.environ.get("CHANGELOG_RETENTION", 0))

# API Cross-Origin Resource Sharing (CORS) settings. If CORS_ORIGIN_ALLOW_ALL is set to True, all origins will be
# allowed. Otherwise, define a list of allowed origins using either CORS_ORIGIN_WHITELIST or
# CORS_ORIGIN_REGEX_WHITELIST. For more information, see https://github.com/ottoyiu/django-cors-headers
CORS_ORIGIN_ALLOW_ALL = is_truthy(os.environ.get("CORS_ORIGIN_ALLOW_ALL", False))
CORS_ORIGIN_WHITELIST = []
CORS_ORIGIN_REGEX_WHITELIST = []

# Set to True to enable server debugging. WARNING: Debugging introduces a substantial performance penalty and may reveal
# sensitive information about your installation. Only enable debugging while performing testing. Never enable debugging
# on a production system.
DEBUG = is_truthy(os.environ.get("DEBUG", False))
DEVELOPER = is_truthy(os.environ.get("DEVELOPER", False))

# Email settings
EMAIL = {
    "SERVER": os.environ.get("EMAIL_SERVER", "localhost"),
    "PORT": int(os.environ.get("EMAIL_PORT", 25)),
    "USERNAME": os.environ.get("EMAIL_USERNAME", ""),
    "PASSWORD": os.environ.get("EMAIL_PASSWORD", ""),
    "TIMEOUT": int(os.environ.get("EMAIL_TIMEOUT", 10)),  # seconds
    "FROM_EMAIL": os.environ.get("EMAIL_FROM", ""),
}

# Enforcement of unique IP space can be toggled on a per-VRF basis.
# To enforce unique IP space within the global table (all prefixes and IP addresses not assigned to a VRF),
# set ENFORCE_GLOBAL_UNIQUE to True.
ENFORCE_GLOBAL_UNIQUE = is_truthy(os.environ.get("ENFORCE_GLOBAL_UNIQUE", False))

# HTTP proxies NetBox should use when sending outbound HTTP requests (e.g. for webhooks).
# HTTP_PROXIES = {
#     "http": "http://192.0.2.1:3128",
#     "https": "http://192.0.2.1:1080",
# }

# IP addresses recognized as internal to the system. The debugging toolbar will be available only to clients accessing
# NetBox from an internal IP.
INTERNAL_IPS = ("127.0.0.1", "::1")

LOG_LEVEL = os.environ.get("LOG_LEVEL", "DEBUG" if DEBUG else "INFO")

# Enable custom logging. Please see the Django documentation for detailed guidance on configuring custom logs:
#   https://docs.djangoproject.com/en/1.11/topics/logging/
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} {levelname} {message} - {name} - {module} - {pathname}:{lineno}",
            "datefmt": "%H:%M:%S",
            "style": "{",
        },
    },
    "handlers": {"console": {"level": "DEBUG", "class": "rq.utils.ColorizingStreamHandler", "formatter": "verbose"}},
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
}

# Setting this to True will permit only authenticated users to access any part of NetBox. By default, anonymous users
# are permitted to access most data in NetBox (excluding secrets) but not make any changes.
LOGIN_REQUIRED = is_truthy(os.environ.get("LOGIN_REQUIRED", False))

# Setting this to True will display a "maintenance mode" banner at the top of every page.
MAINTENANCE_MODE = is_truthy(os.environ.get("MAINTENANCE_MODE", False))

# An API consumer can request an arbitrary number of objects =by appending the "limit" parameter to the URL (e.g.
# "?limit=1000"). This setting defines the maximum limit. Setting it to 0 or None will allow an API consumer to request
# all objects by specifying "?limit=0".
MAX_PAGE_SIZE = int(os.environ.get("MAX_PAGE_SIZE", 1000))

# The file path where uploaded media such as image attachments are stored. A trailing slash is not needed. Note that
# the default value of this setting is derived from the installed location.
MEDIA_ROOT = os.environ.get("MEDIA_ROOT", os.path.join(BASE_DIR, "media"))

# Expose Prometheus monitoring metrics at the HTTP endpoint '/metrics'
METRICS_ENABLED = True

NAPALM_USERNAME = os.environ.get("NAPALM_USERNAME", "")
NAPALM_PASSWORD = os.environ.get("NAPALM_PASSWORD", "")

# NAPALM timeout (in seconds). (Default: 30)
NAPALM_TIMEOUT = int(os.environ.get("NAPALM_TIMEOUT", 30))

# NAPALM optional arguments (see http://napalm.readthedocs.io/en/latest/support/#optional-arguments). Arguments must
# be provided as a dictionary.
NAPALM_ARGS = {
    "secret": NAPALM_PASSWORD,
    # Include any additional args here
}

# Determine how many objects to display per page within a list. (Default: 50)
PAGINATE_COUNT = int(os.environ.get("PAGINATE_COUNT", 50))

# Enable installed plugins. Add the name of each plugin to the list.
PLUGINS = ["netbox_onboarding"]

# Plugins configuration settings. These settings are used by various plugins that the user may have installed.
# Each key in the dictionary is the name of an installed plugin and its value is a dictionary of settings.
PLUGINS_CONFIG = {}

# When determining the primary IP address for a device, IPv6 is preferred over IPv4 by default. Set this to True to
# prefer IPv4 instead.
PREFER_IPV4 = is_truthy(os.environ.get("PREFER_IPV4", False))

# Remote authentication support
REMOTE_AUTH_ENABLED = False
REMOTE_AUTH_HEADER = "HTTP_REMOTE_USER"
REMOTE_AUTH_AUTO_CREATE_USER = True
REMOTE_AUTH_DEFAULT_GROUPS = []

if NETBOX_RELEASE_28 < NETBOX_RELEASE_CURRENT < NETBOX_RELEASE_29:
    # NetBox 2.8.x Specific Settings
    REMOTE_AUTH_BACKEND = "utilities.auth_backends.RemoteUserBackend"
    REMOTE_AUTH_DEFAULT_PERMISSIONS = []
elif NETBOX_RELEASE_CURRENT < NETBOX_RELEASE_211:
    REMOTE_AUTH_BACKEND = "netbox.authentication.RemoteUserBackend"
    REMOTE_AUTH_DEFAULT_PERMISSIONS = {}
else:
    raise ImproperlyConfigured(f"Version {NETBOX_RELEASE_CURRENT} of NetBox is unsupported at this time.")

# This determines how often the GitHub API is called to check the latest release of NetBox. Must be at least 1 hour.
RELEASE_CHECK_TIMEOUT = 24 * 3600

# This repository is used to check whether there is a new release of NetBox available. Set to None to disable the
# version check or use the URL below to check for release in the official NetBox repository.
RELEASE_CHECK_URL = None
# RELEASE_CHECK_URL = 'https://api.github.com/repos/netbox-community/netbox/releases'

SESSION_FILE_PATH = None

# The file path where custom reports will be stored. A trailing slash is not needed. Note that the default value of
# this setting is derived from the installed location.
REPORTS_ROOT = os.environ.get("REPORTS_ROOT", os.path.join(BASE_DIR, "reports"))

# The file path where custom scripts will be stored. A trailing slash is not needed. Note that the default value of
# this setting is derived from the installed location.
SCRIPTS_ROOT = os.environ.get("SCRIPTS_ROOT", os.path.join(BASE_DIR, "scripts"))

# Time zone (default: UTC)
TIME_ZONE = os.environ.get("TIME_ZONE", "UTC")

# Date/time formatting. See the following link for supported formats:
# https://docs.djangoproject.com/en/dev/ref/templates/builtins/#date
DATE_FORMAT = os.environ.get("DATE_FORMAT", "N j, Y")
SHORT_DATE_FORMAT = os.environ.get("SHORT_DATE_FORMAT", "Y-m-d")
TIME_FORMAT = os.environ.get("TIME_FORMAT", "g:i a")
SHORT_TIME_FORMAT = os.environ.get("SHORT_TIME_FORMAT", "H:i:s")
DATETIME_FORMAT = os.environ.get("DATETIME_FORMAT", "N j, Y g:i a")
SHORT_DATETIME_FORMAT = os.environ.get("SHORT_DATETIME_FORMAT", "Y-m-d H:i")
