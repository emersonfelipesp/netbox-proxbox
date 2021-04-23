from proxmoxer import ProxmoxAPI
import pynetbox

from netbox_proxbox.proxbox_api import NETBOX_SESSION as nb, PROXMOX_SESSION as proxmox

def role():
    role_count = nb.dcim.device_roles.count() 

    if role_count == 0:
        role = nb.dcim.device_roles.create(name="Proxbox Basic VM Role", slug="proxbox-basic-vm-role", vm_role=True)
    
    else:
        role_list = []
        for role in nb.dcim.device_roles.all():
            role_list.append(role)
        
        role = role_list[0]
    
    return role.id

def cluster():
    # Verify if there any cluster_type and cluster already created
    cluster_type_count = nb.virtualization.cluster_types.count()
    cluster_count = nb.virtualization.clusters.count()

    # Cluster Type
    # If no 'cluster_type' found, create one
    if cluster_type_count == 0:
        cluster_type = nb.virtualization.cluster_types.create(name="Proxbox Basic Cluster Type", slug="proxbox-cluster-type")

    # If at least one 'cluster_type' found, use the existing one getting the the one with the lowest ID
    else:
        cluster_type_list = []
        for ct in nb.virtualization.cluster_types.all():
            cluster_type_list.append(ct)

        cluster_type = cluster_type_list[0]

    # Cluster
    # If no 'cluster' found, create one using the name from Proxmox
    if cluster_count == 0:
        # Search cluster name on Proxmox
        proxmox_cluster = proxmox.cluster.status.get()
        proxmox_cluster_name = proxmox_cluster[0].get("name")

        # Create the cluster with onlye name and cluster_type
        cluster = nb.virtualization.clusters.create(name=proxmox_cluster_name, type=cluster_type.id)

    # If at least one 'cluster' found, use the existing one getting the the one with the lowest ID
    else:
        cluster_list = []
        for c in nb.virtualization.clusters.all():
            cluster_list.append(c)

        cluster = cluster_list[0]

    return cluster.id

# Cria VM/CT
def virtual_machine(proxmox_vm):
    # Salva VM/CT com informações básicas
    vm_json = {}
    vm_json["name"] = proxmox_vm['name']
    vm_json["status"] = 'active'
    vm_json["cluster"] = cluster()      # Proxmox cluster
    vm_json["role"] = role()        # Aplicacao
    
    # Cria VM/CT com json criado
    try:
        netbox_obj = nb.virtualization.virtual_machines.create(vm_json)

    except:
        print("[proxbox.create.virtual_machine] Falha na criação da VM")
        netbox_obj = None

    else:
        return netbox_obj

    # Caso nada funcione, volte erro
    netbox_obj = None
    return netbox_obj


