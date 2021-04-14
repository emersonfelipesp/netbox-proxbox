"""
# Atualiza VM individualmente
from proxbox.main import virtual_machine

# Atualiza todas as VMs
from proxbox.main import all
"""

import proxbox.create
import proxbox.main as update

# Verifica se VM existe no Proxmox e deleta no Netbox, caso não exista
import proxbox.remove

import proxbox.session

import proxbox.updates


