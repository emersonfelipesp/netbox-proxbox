from proxmoxer import ProxmoxAPI
import pynetbox

from __init__ import netbox as nb
from main import is_vm_on_proxmox

def virtual_machine(): # netbox_part()
    # Get all VM/CTs from Netbox
    netbox_all_vms = nb.virtualization.virtual_machines.all()

    for nb_vm_each in netbox_all_vms:
        netbox_obj = nb_vm_each
        netbox_name = netbox_obj.name

        # Verifica se VM existe ou não no Proxmox
        vm_on_proxmox = is_vm_on_proxmox(nb_vm_each)

        if vm_on_proxmox == True:
            print('[OK] VM existe em ambos sistemas -> {}'.format(netbox_name))
        
        # Se VM não existe no Proxmox, deleta a VM no Netbox
        elif vm_on_proxmox == False:
            print("[WARNING] VM existe no Netbox, mas não no Proxmox. Deletar a VM! -> {}".format(netbox_name))
            delete_vm = netbox_obj.delete()

            if delete_vm == True:
                print("[OK] VM removida do Netbox com sucesso")

        else:
            print('[ERROR] Erro inesperado ao verificar se VM existe no Proxmox')