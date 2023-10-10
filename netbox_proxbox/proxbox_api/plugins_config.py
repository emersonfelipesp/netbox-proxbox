# Proxmox
from proxmoxer import ProxmoxAPI

# Netbox
import pynetbox
import requests

# Default Plugins settings 
from netbox_proxbox import ProxboxConfig

# PLUGIN_CONFIG variable defined by user in Netbox 'configuration.py' file
from netbox.settings import PLUGINS_CONFIG

# support for custom BASE_PATH

try:
    from netbox.settings import BASE_PATH
    DEFAULT_BASE_PATH = '/' + BASE_PATH
except ImportError:
    DEFAULT_BASE_PATH = ''

from utilities.exceptions import AbortRequest

####################################################################################################
#                                                                                                  #
#  DEFAULT VARIABLES DEFINED BY ProxboxConfig CLASS ON PROXBOX PLUGIN CONFIGURATION (__init__.py)  #
#                                                                                                  #
####################################################################################################

DEFAULT_PLUGINS_CONFIG = ProxboxConfig.default_settings
DEFAULT_PROXMOX_SETTING = DEFAULT_PLUGINS_CONFIG.get("proxmox")
DEFAULT_NETBOX_SETTING = DEFAULT_PLUGINS_CONFIG.get("netbox")

#
# Proxmox related settings
#
# API URI
DEFAULT_PROXMOX = DEFAULT_PROXMOX_SETTING[0].get("domain")
DEFAULT_PROXMOX_PORT = DEFAULT_PROXMOX_SETTING[0].get("http_port")
DEFAULT_PROXMOX_SSL = DEFAULT_PROXMOX_SETTING[0].get("ssl")

# ACCESS
DEFAULT_PROXMOX_USER = DEFAULT_PROXMOX_SETTING[0].get("user")
DEFAULT_PROXMOX_PASSWORD = DEFAULT_PROXMOX_SETTING[0].get("password")

DEFAULT_PROXMOX_TOKEN = DEFAULT_PROXMOX_SETTING[0].get("token")
DEFAULT_PROXMOX_TOKEN_NAME = DEFAULT_PROXMOX_TOKEN.get("name", None)
DEFAULT_PROXMOX_TOKEN_VALUE = DEFAULT_PROXMOX_TOKEN.get("value", None)

#
# NETBOX RELATED SETTINGS
#
# API URI
#
DEFAULT_NETBOX = DEFAULT_NETBOX_SETTING.get("domain")
DEFAULT_NETBOX_PORT = DEFAULT_NETBOX_SETTING.get("http_port")
DEFAULT_NETBOX_SSL = DEFAULT_NETBOX_SETTING.get("ssl")

# ACCESS
DEFAULT_NETBOX_TOKEN = DEFAULT_NETBOX_SETTING.get("token")

# SETTINGS
DEFAULT_NETBOX_SETTINGS = DEFAULT_NETBOX_SETTING.get("settings")
DEFAULT_NETBOX_VM_ROLE_ID = DEFAULT_NETBOX_SETTINGS.get("virtualmachine_role_id", 0)
DEFAULT_NETBOX_NODE_ROLE_ID = DEFAULT_NETBOX_SETTINGS.get("node_role_id", 0)
DEFAULT_NETBOX_SITE_ID = DEFAULT_NETBOX_SETTINGS.get("site_id", 0)

####################################################################################################
#                                                                                                  #
#         VARIABLES FROM PLUGINS_CONFIG DEFINED BY USER ON NETBOX configuration.py                 #
#                                                                                                  #
####################################################################################################

# Get Proxmox credentials values from PLUGIN_CONFIG
USER_PLUGINS_CONFIG = PLUGINS_CONFIG.get("netbox_proxbox")
PROXMOX_SETTING = USER_PLUGINS_CONFIG.get("proxmox", DEFAULT_PROXMOX_SETTING)
NETBOX_SETTING = USER_PLUGINS_CONFIG.get("netbox", DEFAULT_NETBOX_SETTING)

#
# NETBOX RELATED SETTINGS
#
# API URI
#
NETBOX = NETBOX_SETTING.get("domain", DEFAULT_NETBOX)
NETBOX_PORT = NETBOX_SETTING.get("http_port", DEFAULT_NETBOX_PORT)
NETBOX_SSL = NETBOX_SETTING.get("ssl", DEFAULT_NETBOX_SSL)

# ACCESS
NETBOX_TOKEN = NETBOX_SETTING.get("token", DEFAULT_NETBOX_TOKEN)

# SETTINGS
NETBOX_SETTINGS = NETBOX_SETTING.get("settings", DEFAULT_NETBOX_SETTINGS)

if NETBOX_SETTINGS != None:
    NETBOX_VM_ROLE_ID = NETBOX_SETTINGS.get("virtualmachine_role_id", DEFAULT_NETBOX_VM_ROLE_ID)
    NETBOX_NODE_ROLE_ID = NETBOX_SETTINGS.get("node_role_id", DEFAULT_NETBOX_NODE_ROLE_ID)
    NETBOX_SITE_ID = NETBOX_SETTINGS.get("site_id", DEFAULT_NETBOX_SITE_ID)

PROXMOX_SESSIONS = {}

def get_proxmox_session(proxmox_config, raise_for_error=True):
    #
    # Proxmox related settings
    #
    # API URI
    PROXMOX = proxmox_config.get("domain", DEFAULT_PROXMOX)
    PROXMOX_PORT = proxmox_config.get("http_port", DEFAULT_PROXMOX_PORT)
    PROXMOX_SSL = proxmox_config.get("ssl", DEFAULT_PROXMOX_SSL)

    # ACCESS
    PROXMOX_USER = proxmox_config.get("user", DEFAULT_PROXMOX_USER)
    PROXMOX_PASSWORD = proxmox_config.get("password", DEFAULT_PROXMOX_PASSWORD)

    output = {
        'PROXMOX': PROXMOX,
        'PROXMOX_PORT': PROXMOX_PORT,
        'PROXMOX_SSL': PROXMOX_SSL,
        'PROXMOX_TOKEN': None,
        'PROXMOX_TOKEN_NAME': None,
        'PROXMOX_TOKEN_VALUE': None
    }

    PROXMOX_TOKEN = proxmox_config.get("token", DEFAULT_PROXMOX_TOKEN)
    if PROXMOX_TOKEN is not None:
        PROXMOX_TOKEN_NAME = PROXMOX_TOKEN.get("name", DEFAULT_PROXMOX_TOKEN_NAME)
        PROXMOX_TOKEN_VALUE = PROXMOX_TOKEN.get("value", DEFAULT_PROXMOX_TOKEN_VALUE)
        output["PROXMOX_TOKEN"] = PROXMOX_TOKEN
        output["PROXMOX_TOKEN_NAME"] = PROXMOX_TOKEN_NAME
        output["PROXMOX_TOKEN_VALUE"] = PROXMOX_TOKEN_VALUE

    _auth_id = f"{PROXMOX}:{PROXMOX_PORT}/{PROXMOX_USER}"

    ####################################################################################################
    #                                                                                                  #
    #                 WITH PLUGIN CONFIGURED, STARTS BOTH PROXMOX AND NETBOX SESSION                   #
    #                                                                                                  #
    ####################################################################################################

    #
    # PROXMOX SESSION 
    #
    # Check if token was provided
    if PROXMOX_TOKEN_VALUE is not None and len(PROXMOX_TOKEN_VALUE) > 0:
        try:
            if PROXMOX_SSL == False:
                # DISABLE SSL WARNING
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

            # Start PROXMOX session using TOKEN
            PROXMOX_SESSION = ProxmoxAPI(
                PROXMOX,
                port=PROXMOX_PORT,
                user=PROXMOX_USER,
                token_name=PROXMOX_TOKEN_NAME,
                token_value=PROXMOX_TOKEN_VALUE,
                verify_ssl=PROXMOX_SSL
            )
        except:
            print(f'Error trying to initialize Proxmox ({_auth_id}) Session using TOKEN')
        else:
            output['PROXMOX_SESSION'] = PROXMOX_SESSION
            return output

    # start session using user and passwd
    if PROXMOX_PASSWORD is not None and len(PROXMOX_PASSWORD) > 0:
        try:
            if PROXMOX_SSL == False:
                # DISABLE SSL WARNING
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

            # Start PROXMOX session using USER CREDENTIALS
            PROXMOX_SESSION = ProxmoxAPI(
                PROXMOX,
                port=PROXMOX_PORT,
                user=PROXMOX_USER,
                password=PROXMOX_PASSWORD,
                verify_ssl=PROXMOX_SSL
            )
        except:
            print(f'Error trying to initialize Proxmox ({_auth_id}) Session using PASSWORD')
        else:
            output['PROXMOX_SESSION'] = PROXMOX_SESSION
            return output

    if raise_for_error:
        raise RuntimeError(f'Error establishing connection with Proxmox ({_auth_id}) instance')

for s in PROXMOX_SETTING:
    P_Setting = get_proxmox_session(s)
    if P_Setting is not None:
        v = P_Setting['PROXMOX']
        PROXMOX_SESSIONS[v] = P_Setting

#
# NETBOX SESSION 
#
# TODO: CREATES SSL VERIFICATION - Issue #32
try:
    # CHANGE SSL VERIFICATION TO FALSE
    session = requests.Session()
    session.verify = False

    NETBOX = 'http://{}:{}{}'.format(NETBOX, NETBOX_PORT, DEFAULT_BASE_PATH)

    # Start NETBOX session
    NETBOX_SESSION = pynetbox.api(
        NETBOX,
        token=NETBOX_TOKEN
    )
    # DISABLES SSL VERIFICATION
    NETBOX_SESSION.http_session = session

except:
    raise RuntimeError(f"Error trying to initialize Netbox Session using TOKEN {NETBOX_TOKEN} provided.")
