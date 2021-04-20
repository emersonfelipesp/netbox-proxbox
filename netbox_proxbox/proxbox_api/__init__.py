import os
from os.path import join, dirname
from dotenv import load_dotenv, find_dotenv

# take enviroment variables from .env
load_dotenv(find_dotenv()) 

from proxmoxer import ProxmoxAPI
import paramiko
import pynetbox

# Get Proxmox credentials values from .env
PROXMOX = os.getenv("PROXMOX")
PROXMOX_PORT = os.getenv("PROXMOX_PORT")
PROXMOX_USER = os.getenv("PROXMOX_USER")
PROXMOX_PASSWORD = os.getenv("PROXMOX_PASSWORD")
PROXMOX_SSL = os.getenv("PROXMOX_SSL")

# Get Netbox credentials values from .env
NETBOX = os.getenv("NETBOX")
NETBOX_TOKEN = os.getenv("NETBOX_TOKEN")
NETBOX_CLUSTER_ID = os.getenv("NETBOX_CLUSTER_ID")
NETBOX_ROLE_ID = os.getenv("NETBOX_ROLE_ID")

print('NETBOX:', NETBOX)
print('PROXMOX:', PROXMOX)

# Convert string to boolean
if PROXMOX_SSL == 'False':
    PROXMOX_SSL = False
else:
    PROXMOX_SSL = True

# Inicia sessão com PROXMOX
PROXMOX_SESSION = ProxmoxAPI(
    PROXMOX,
    user=PROXMOX_USER,
    password=PROXMOX_PASSWORD,
    verify_ssl=PROXMOX_SSL
)

# Inicia sessão com NETBOX
NETBOX_SESSION = pynetbox.api(
    NETBOX,
    token=NETBOX_TOKEN
)

'''
import api.main as update
import api.updates
import api.create

# Verifica se VM existe no Proxmox e deleta no Netbox, caso não exista
import api.remove
'''