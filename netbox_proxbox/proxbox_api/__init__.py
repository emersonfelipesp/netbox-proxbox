from proxmoxer import ProxmoxAPI
import paramiko
import pynetbox

from netbox.settings import PLUGINS_CONFIG

'''
quit()
python3
import netbox_proxbox.proxbox_api
print(netbox_proxbox.proxbox_api.update.all())
'''

# Get Proxmox credentials values from PLUGIN_CONFIG
PLUGINS_CONFIG = PLUGINS_CONFIG.get("netbox_proxbox")
PROXMOX_SETTING = PLUGINS_CONFIG.get("proxmox")
NETBOX_SETTING = PLUGINS_CONFIG.get("netbox")

#
# Proxmox related settings
#
# API URI
PROXMOX = PROXMOX_SETTING.get("domain")
PROXMOX_PORT = PROXMOX_SETTING.get("http_port")
PROXMOX_SSL = PROXMOX_SETTING.get("ssl")

# ACCESS
PROXMOX_USER = PROXMOX_SETTING.get("user")
PROXMOX_PASSWORD = PROXMOX_SETTING.get("password")
PROXMOX_TOKEN_NAME = PROXMOX_SETTING.get("token").get("name")
PROXMOX_TOKEN_VALUE = PROXMOX_SETTING.get("token").get("value")

#
# Netbox related settings
#
# API URI
#
NETBOX = NETBOX_SETTING.get("domain")
NETBOX_PORT = NETBOX_SETTING.get("http_port")
NETBOX_SSL = NETBOX_SETTING.get("ssl")

# ACCESS
NETBOX_TOKEN = NETBOX_SETTING.get("token")

#
# PROXMOX SESSION 
#
# Check if token was provided
if PROXMOX_TOKEN_VALUE != None and len(PROXMOX_TOKEN_VALUE) > 0:
    try:
        # Start PROXMOX session using TOKEN
        PROXMOX_SESSION = ProxmoxAPI(
            PROXMOX,
            user=PROXMOX_USER,
            token_name=PROXMOX_TOKEN_NAME,
            token_value=PROXMOX_TOKEN_VALUE,
            verify_ssl=PROXMOX_SSL
        )
    except:
        print('Error trying to initialize Proxmox Session using TOKEN provided')

# If token not provided, start session using user and passwd
else:
    try:
        # Start PROXMOX session using USER CREDENTIALS
        PROXMOX_SESSION = ProxmoxAPI(
            PROXMOX,
            user=PROXMOX_USER,
            password=PROXMOX_PASSWORD,
            verify_ssl=PROXMOX_SSL
        )
    except:
        print('Error trying to initialize Proxmox Session using USER and PASSWORD')

#
# NETBOX SESSION 
#
if NETBOX_SSL == False:
    try:
        NETBOX = 'http://{}:{}'.format(NETBOX, NETBOX_PORT)
        # Inicia sessão com NETBOX
        NETBOX_SESSION = pynetbox.api(
            NETBOX,
            token=NETBOX_TOKEN
        )
    except:
        print('Error trying to initialize Netbox Session using TOKEN provided')
elif NETBOX_SSL == True:
    print("Netbox using SSL not developed yet, try using HTTP without SSL.")

else:
    print('Unexpected Error ocurred')


import netbox_proxbox.proxbox_api.main as update
import netbox_proxbox.proxbox_api.updates
import netbox_proxbox.proxbox_api.create

# Verifica se VM existe no Proxmox e deleta no Netbox, caso não exista
import netbox_proxbox.proxbox_api.remove









