from ..plugins_config import (
    PROXMOX,
    PROXMOX_PORT,
    PROXMOX_USER,
    PROXMOX_PASSWORD,
    PROXMOX_SSL,
    NETBOX,
    NETBOX_TOKEN,
    PROXMOX_SESSION as proxmox,
    NETBOX_SESSION as nb,
)

from .. import (
    create,
)

import logging

# Update STATUS field on /dcim/device/{id}
def status(netbox_node, proxmox_node):
    #
    # Compare STATUS
    #
    if proxmox_node['online'] == 1:
        # If Proxmox is 'online' and Netbox is 'offline', update it.
        if netbox_node.status.value == 'offline':
            netbox_node.status.value = 'active'
            
            if netbox_node.save() == True:
                status_updated = True
            else:
                status_updated = False

        else:
            status_updated = False


    elif proxmox_node['online'] == 0:
        # If Proxmox is 'offline' and Netbox' is 'active', update it.
        if netbox_node.status.value == 'active':
            netbox_node.status.value = 'offline'

            if netbox_node.save() == True:
                status_updated = True
            else:
                status_updated = False

        else:
            status_updated = False

    else:
        status_updated = False

    return status_updated




# Update CLUSTER field on /dcim/device/{id}
def cluster(netbox_node, proxmox_node, proxmox_cluster):
    #
    # Compare CLUSTER
    #
    cluster_updated = False

    if netbox_node != None:
        try:
            if proxmox_cluster != None: 
                # If cluster is not filled or even filled, but different from actual cluster, update it.
                if netbox_node.cluster.name != proxmox_cluster['name'] or netbox_node.cluster.name == None:
                    # Search for Proxmox Cluster using create.cluster() function
                    cluster_id = create.virtualization.cluster().id

                    # Use Cluster ID to update NODE information
                    netbox_node.cluster.id = cluster_id

                    if netbox_node.save() == True:
                        cluster_updated = True
                    else:
                        cluster_updated = False

                else:
                    cluster_updated = False

            # If cluster is empty, update it.
            elif proxmox_cluster == None:
                # Search for Proxmox Cluster using create.cluster() function
                cluster_id = create.virtualization.cluster().id

                # Use Cluster ID to update NODE information
                netbox_node.cluster.id = cluster_id

                if netbox_node.save() == True:
                    cluster_updated = True
                else:
                    cluster_updated = False
            
            # If cluster was not empty and also not different, do not make any change.
            else:
                cluster_updated = False

        except Exception as error:
            logging.error(f"[ERROR] {error}")
    else:
        cluster_updated = False

    return cluster_updated

def interfaces(netbox_node, proxmox_json):
    updated = False
    _int_port = ['OVSIntPort']
    _lag_port = ['OVSBond']
    _brg_port = ['OVSBridge']
    _pmx_iface = []
    _ntb_iface = [{'name': iface.name, 'mtu' : int(iface.mtu) if iface.mtu else 1500, 'tagged_vlans': [int(x['vid']) for x in iface.tagged_vlans]} for iface in nb.dcim.interfaces.filter(device_id=netbox_node.id)]
    _eth =  [iface for iface in proxmox.nodes(proxmox_json['name']).network.get() if iface['type'] == 'eth']
    _virt = [iface for iface in proxmox.nodes(proxmox_json['name']).network.get() if iface['type'] in _int_port]
    _bond = [iface for iface in proxmox.nodes(proxmox_json['name']).network.get() if iface['type'] in _lag_port]
    _bridge = [iface for iface in proxmox.nodes(proxmox_json['name']).network.get() if iface['type'] in _brg_port]

    for iface in _eth:
        ntb_iface = list(nb.dcim.interfaces.filter(device_id=netbox_node.id, name=iface['iface']))
        if iface.get('ovs_tag') is not None:
            _tagged_vlans = [int(iface.get('ovs_tag'))]
        else:
            _tagged_vlans = []
        _pmx_iface.append({'name': iface['iface'], 'mtu' : int(iface.get('mtu', 1500)), 'tagged_vlans': _tagged_vlans})
        pmx_if = next((_if for _if in _pmx_iface if _if['name'] == iface['iface']), None)
        if not len(ntb_iface):
            if len(_tagged_vlans):
                ntb_iface = nb.dcim.interfaces.create(device=netbox_node.id, name=pmx_if['name'], type='other', mtu=pmx_if['mtu'], mode='tagged', tagged_vlans=[nb.ipam.vlans.get(vid=_tagged_vlans[0]).id])
            else:
                ntb_iface = nb.dcim.interfaces.create(device=netbox_node.id, name=pmx_if['name'], type='other', mtu=pmx_if['mtu'])
            updated = True
        else:
            if len(ntb_iface) == 1:
                ntb_iface = ntb_iface[0]
                ntb_if = next((_if for _if in _ntb_iface if _if['name'] == iface['iface']), None)
                if pmx_if != ntb_if:
                    if len(pmx_if['tagged_vlans']):
                        nb.dcim.interfaces.update([{'id': ntb_iface.id, 'mtu': pmx_if['mtu'], 'mode': 'tagged', 'tagged_vlans': [nb.ipam.vlans.get(vid=_tagged_vlans[0]).id]}])
                    else:
                        nb.dcim.interfaces.update([{'id': ntb_iface.id, 'mtu': pmx_if['mtu']}])
                    updated = True

    for iface in _bond:
        ntb_iface = list(nb.dcim.interfaces.filter(device_id=netbox_node.id, name=iface['iface']))
        if iface.get('ovs_tag') is not None:
            _tagged_vlans = [int(iface.get('ovs_tag'))]
        else:
            _tagged_vlans = []
        _pmx_iface.append({'name': iface['iface'], 'mtu' : int(iface.get('mtu', 1500)), 'tagged_vlans': _tagged_vlans})
        if not len(ntb_iface):
            if len(_tagged_vlans):
                ntb_iface = nb.dcim.interfaces.create(device=netbox_node.id, name=iface['iface'], type='lag', mtu=int(iface.get('mtu', 1500)), mode='tagged', tagged_vlans=[nb.ipam.vlans.get(vid=_tagged_vlans[0]).id])
            else:
                ntb_iface = nb.dcim.interfaces.create(device=netbox_node.id, name=iface['iface'], type='lag', mtu=int(iface.get('mtu', 1500)))
        else:
            if len(ntb_iface) == 1:
                ntb_iface = ntb_iface[0]
                pmx_if = next((_if for _if in _pmx_iface if _if['name'] == iface['iface']), None)
                ntb_if = next((_if for _if in _ntb_iface if _if['name'] == iface['iface']), None)
                if pmx_if != ntb_if:
                    if len(pmx_if['tagged_vlans']):
                        nb.dcim.interfaces.update([{'id': ntb_iface.id, 'mtu': pmx_if['mtu'], 'mode': 'tagged', 'tagged_vlans': [nb.ipam.vlans.get(vid=_tagged_vlans[0]).id]}])
                    else:
                        nb.dcim.interfaces.update([{'id': ntb_iface.id, 'mtu': pmx_if['mtu']}])
                    updated = True
        if 'ovs_bonds' in iface:
            for _sif in iface['ovs_bonds'].split(' '):
                _nb_iface = list(nb.dcim.interfaces.filter(device_id=netbox_node.id, name=_sif))
                if len(_nb_iface) == 1:
                    nb.dcim.interfaces.update([{'id': _nb_iface[0].id, 'lag': {'id': ntb_iface.id}}])

    for iface in _virt:
        ntb_iface = list(nb.dcim.interfaces.filter(device_id=netbox_node.id, name=iface['iface']))
        if iface.get('ovs_tag') is not None:
            _tagged_vlans = [int(iface.get('ovs_tag'))]
        else:
            _tagged_vlans = []
        _pmx_iface.append({'name': iface['iface'], 'mtu' : int(iface.get('mtu', 1500)), 'tagged_vlans': _tagged_vlans})
        if not len(ntb_iface):
            if len(_tagged_vlans):
                ntb_iface = nb.dcim.interfaces.create(device=netbox_node.id, name=iface['iface'], type='virtual', mtu=int(iface.get('mtu', 1500)), mode='tagged', tagged_vlans=[nb.ipam.vlans.get(vid=_tagged_vlans[0]).id])
            else:
                ntb_iface = nb.dcim.interfaces.create(device=netbox_node.id, name=iface['iface'], type='virtual', mtu=int(iface.get('mtu', 1500)))
        else:
            if len(ntb_iface) == 1:
                ntb_iface = ntb_iface[0]
                pmx_if = next((_if for _if in _pmx_iface if _if['name'] == iface['iface']), None)
                ntb_if = next((_if for _if in _ntb_iface if _if['name'] == iface['iface']), None)
                if pmx_if != ntb_if:
                    if len(pmx_if['tagged_vlans']):
                        nb.dcim.interfaces.update([{'id': ntb_iface.id, 'mtu': pmx_if['mtu'], 'mode': 'tagged', 'tagged_vlans': [nb.ipam.vlans.get(vid=_tagged_vlans[0]).id]}])
                    else:
                        nb.dcim.interfaces.update([{'id': ntb_iface.id, 'mtu': pmx_if['mtu']}])
                    updated = True

    for iface in _bridge:
        ntb_iface = list(nb.dcim.interfaces.filter(device_id=netbox_node.id, name=iface['iface']))
        if iface.get('ovs_tag') is not None:
            _tagged_vlans = [int(iface.get('ovs_tag'))]
        else:
            _tagged_vlans = []
        _pmx_iface.append({'name': iface['iface'], 'mtu' : int(iface.get('mtu', 1500)), 'tagged_vlans': _tagged_vlans})
        if not len(ntb_iface):
            if len(_tagged_vlans):
                ntb_iface = nb.dcim.interfaces.create(device=netbox_node.id, name=iface['iface'], type='bridge', mtu=int(iface.get('mtu', 1500)), mode='tagged', tagged_vlans=[nb.ipam.vlans.get(vid=_tagged_vlans[0]).id])
            else:
                ntb_iface = nb.dcim.interfaces.create(device=netbox_node.id, name=iface['iface'], type='bridge', mtu=int(iface.get('mtu', 1500)))
        else:
            if len(ntb_iface) == 1:
                ntb_iface = ntb_iface[0]
                pmx_if = next((_if for _if in _pmx_iface if _if['name'] == iface['iface']), None)
                ntb_if = next((_if for _if in _ntb_iface if _if['name'] == iface['iface']), None)
                if pmx_if != ntb_if:
                    if len(pmx_if['tagged_vlans']):
                        nb.dcim.interfaces.update([{'id': ntb_iface.id, 'mtu': pmx_if['mtu'], 'mode': 'tagged', 'tagged_vlans': [nb.ipam.vlans.get(vid=_tagged_vlans[0]).id]}])
                    else:
                        nb.dcim.interfaces.update([{'id': ntb_iface.id, 'mtu': pmx_if['mtu']}])
                    updated = True
        if 'ovs_ports' in iface:
            for _sif in iface['ovs_ports'].split(' '):
                _nb_iface = list(nb.dcim.interfaces.filter(device_id=netbox_node.id, name=_sif))
                if len(_nb_iface) == 1:
                    nb.dcim.interfaces.update([{'id': _nb_iface[0].id, 'bridge': {'id': ntb_iface.id}}])

    for iface in [x.get('name') for x in _ntb_iface]:
        if iface not in [x.get('name') for x in _pmx_iface]:
            ntb_iface = list(nb.dcim.interfaces.filter(device_id=netbox_node.id, name=iface))
            if len(ntb_iface) == 1:
                if not ntb_iface[0].mgmt_only and not ntb_iface[0].custom_fields.get('proxmox_keep_interface', False):
                    ntb_iface[0].delete()

    return updated
