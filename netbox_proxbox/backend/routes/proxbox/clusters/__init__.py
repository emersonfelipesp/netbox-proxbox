from fastapi import APIRouter, Depends

from typing import Annotated, Any

# Import Both Proxmox Sessions and Netbox Session Dependencies
from netbox_proxbox.backend.session.proxmox import ProxmoxSessionsDep
from netbox_proxbox.backend.session.netbox import NetboxSessionDep

from netbox_proxbox.backend.logging import logger, log

from netbox_proxbox.backend.exception import ProxboxException, exception_log

from netbox_proxbox.backend import (
    ClusterType,
    Cluster,
    Site,
    DeviceRole,
    DeviceType,
    Device,
    VirtualMachine,
    VMInterface,
    Interface,
    IPAddress,
)

from fastapi import WebSocket

router = APIRouter()


async def proxmox_session_with_cluster(
    pxs: ProxmoxSessionsDep,
    nb: NetboxSessionDep
):
    """Get Proxmox Session with Cluster"""
    pass


@router.get("/")
async def proxbox_get_clusters(
    pxs: ProxmoxSessionsDep,
    nb: NetboxSessionDep,
    websocket: WebSocket
):
    """
    Automatically sync Proxmox Clusters with Netbox Clusters.
    This asynchronous function iterates over a list of Proxmox sessions and creates corresponding 
    Cluster Types and Clusters in Netbox. It handles both standalone and clustered Proxmox modes.
    
    **Args:**
    - **pxs (ProxmoxSessionsDep):** Dependency injection for Proxmox sessions.
    - **nb (NetboxSessionDep):** Dependency injection for Netbox session.
    
    **Returns:**
    - **list:** A list of dictionaries containing the name of the Proxmox session and the corresponding 
    Netbox cluster object.
    
    **Raises:**
    - **`ProxboxException`:** If there is an error creating the cluster type or the cluster.
    """
    
    result = []
    
    for px in pxs:
        
        """
        Before creating the Cluster, we need to create the Cluster Type.
        """
        cluster_type_name = f"Proxmox {px.mode.capitalize()}"
        cluster_type_slug = f"proxmox-{px.mode}"
        
        
        standalone_description = "Proxmox Standalone. This Proxmox has only one node and thus is not part of a Cluster."
        cluster_description = "Proxmox Cluster. This Proxmox has more than one node and thus is part of a Cluster."
        
        
        description = ""
        if px.mode == "standalone":
            description = standalone_description
        elif px.mode == "cluster":
            description = cluster_description
        
        # Create Cluster Type object before the Cluster itself
        try:
            await log(websocket, "Creating the <strong>Cluster Type</strong> before Cluster...")
            cluster_type_obj = await ClusterType(nb = nb, websocket = websocket).post(
                data = {
                    "name": cluster_type_name,
                    "slug": cluster_type_slug,
                    "description": description
                }
            )
        #except Exception as error: raise ProxboxException(message="Error trying to create the cluster type.", python_exception=error)
        except Exception as error: await exception_log(logger=log,websocket=websocket, message="Error trying to create the cluster type.", python_exception=error)
        
        # Create the Cluster
        try:
            await log(websocket, "Creating the Cluster...")
            cluster_obj = await Cluster(nb = nb, websocket = websocket).post(
                data = {
                    "name": px.name,
                    "slug": px.name,
                    "type": cluster_type_obj["id"],
                    "status": "active",
                }
            )
        #except Exception as error: raise ProxboxException(message="Error trying to create the cluster.", python_exception=error)
        except Exception as error: await exception_log(logger=log,websocket=websocket, message="Error trying to create the cluster.", python_exception=error)
            
            
        result.append(
            {
                "name": px.name,
                "netbox": {
                    "cluster": cluster_obj,
                }
            }
        )
    
    return result


def find_interface_type(
    proxmox_int_type: str,
    proxmox_int_name: str
):
    """
    ### Determine the interface type based on the provided Proxmox interface type and name.
    
    **Args:**
    - **proxmox_int_type (`str`):** The type of the Proxmox interface (e.g., "eth", "bridge", "bond").
    - **proxmox_int_name (`str`):** The name of the Proxmox interface (e.g., "eno1", "enp0s3").
    
    **Returns:**
    - `str`: The determined interface type as a string.
    """
    
    if proxmox_int_type == "eth":
            
        if 'eno' in proxmox_int_name: interface_type = '1000base-t'
        elif 'en' in proxmox_int_name: interface_type = '10gbase-t'
        
    elif proxmox_int_type == "bridge": interface_type = proxmox_int_type   
    elif proxmox_int_type == "bond": interface_type = 'lag'
    else: interface_type = 'other'
    
    print(f'interface_type: {interface_type} / {type(interface_type)}')
    return str(interface_type)

from fastapi import WebSocket

@router.get("/nodes")
async def get_nodes(
    nb: NetboxSessionDep,
    pxs: ProxmoxSessionsDep,
    websocket: WebSocket
):
    """
    ### Synchronizes nodes and their interfaces from Proxmox to Netbox.
    
    **Args:**
    - **nb (`NetboxSessionDep`):** The Netbox session dependency.
    - **pxs (`ProxmoxSessionsDep`):** The Proxmox sessions dependency.
    - **websocket (`WebSocket`):** The WebSocket connection for logging.
    
    **Returns:**
    - **`list`:** A list of dictionaries containing the Proxmox cluster name and the corresponding Netbox nodes.
    
    **Raises:**
    - **`ProxboxException`:** If there is an error during the synchronization process.
    
    **Workflow:**
        1. For each Proxmox session:
            a. Retrieve the corresponding cluster from Netbox.
            b. Get the nodes from the Proxmox cluster.
            c. For each node:
                i. Log the creation process.
                ii. Create the node in Netbox.
                iii. Log the success or failure of the creation.
                iv. Retrieve the network interfaces of the node.
                v. For each interface:
                    - Determine the interface type.
                    - Log the interface creation process.
                    - Create the interface in Netbox.
                    - Log the success or failure of the creation.
                    - If the interface has a CIDR, create the IP address in Netbox.
                    - If the interface is a bridge, handle the bridge ports.
    """
    
    
    result = []
    
    for px in pxs:
        
        # Get Cluster from Netbox based on Proxmox Cluster Name
        get_cluster_from_netbox = await Cluster(nb = nb, websocket = websocket).get(name = px.name)
    
        # Get Proxmox Nodes from the current Proxmox Cluster
        proxmox_nodes = px.session.nodes.get()
        
        # List Comprehension to create the Nodes in Netbox
        nodes = [
        ]
        
        for node in proxmox_nodes:
            
            try:
                msg = f"<span class='badge text-bg-yellow' title='Syncing'><strong><i class='mdi mdi-download'></i></strong></span> Creating Device <strong>{node.get("node")}</strong> related with the Virtual Machine(s)"
                await log(websocket, msg)
                
                current_node = await Device(nb=nb, websocket=websocket).post(
                    data = {
                        "name": node.get("node"),
                        "cluster": get_cluster_from_netbox.id,
                        "status": "active",
                    }
                )
                
                if current_node:
                    nodes.append(current_node)
                    
                msg = f"<span class='badge text-bg-green' title='Success'><strong><i class='mdi mdi-download'></i></strong></span> Device <strong><a href='{current_node.display_url}' target='_blank'>{current_node}</a> created successfully.</strong>"
                await log(websocket, msg)
                
            except Exception as error:
                #raise ProxboxException(
                await exception_log(
                    logger=log,
                    websocket=websocket,
                    message="<span class='text-red'><strong><i class='mdi mdi-error'></i></strong></span> Error trying to create Netbox Device object.",
                    python_exception=error
                )
            
                
            print(node)
            node_interfaces = px.session.nodes(node.get("node")).network.get()
            #print(node_interfaces)
            
            print("\n")
            
            for interface in node_interfaces:
                interface_type = find_interface_type(
                    interface.get("type"),
                    interface.get("iface")
                )
                print(f'[0] interface: {interface}')
                print(f'interface_type: {interface_type}')
                interface_name = interface.get("iface")
                
                if interface.get("active") == 1:
                    enabled = True
                else: enabled = False
                
                create_interface = None
                
                try:
                    await log(websocket, f"<span class='badge text-bg-yellow' title='Syncing'><strong><i class='mdi mdi-download'></i></strong></span> {interface_name}</strong> Interface on <strong><a href='{current_node.display_url}' target='_blank'>{current_node.name}</a></strong> Device...")
                    create_interface = await Interface(nb=nb, websocket=websocket, primary_field_value=current_node.id).post(data={
                        "device": current_node.id,
                        "name": interface_name,
                        "enabled": enabled,
                        "type": interface_type,
                        "mtu": interface.get("mtu", None),
                        "description": interface.get("comments", "")
                    })
                    
                    if create_interface:
                        print(f'create_interface: {create_interface}')
                        await log(websocket, f"<span class='badge text-bg-green' title='Success'><strong><i class='mdi mdi-download'></i></strong></span> Netbox Interface <strong><a href='{create_interface.display_url}' target='_blank'>{create_interface.name}</a> created successfully.</strong>")
                    
                except Exception as error:
                    #raise ProxboxException(
                    await exception_log(
                        logger=log,
                        websocket=websocket,
                        message="<span class='text-red'><strong><i class='mdi mdi-error'></i></strong></span> Error trying to create Netbox interface.",
                        python_exception=error
                    )
            
                
                print(f"interface value type: {type(interface)}")
                
                cidr = interface.get("cidr")
                print(f"cidr: {cidr}")
                
                if create_interface and cidr:
                    try:
                        await log(websocket, f"<span class='badge text-bg-yellow' title='Syncing'><strong><i class='mdi mdi-download'></i></strong></span> Interface with CIDR/Network. Creating the IP Address <strong>{cidr}</strong> object of Interface <strong><a href='{create_interface.display_url}' target='_blank'>{create_interface.name}</a></strong> on Netbox...")
                        # If interface with network configured, create IP Address and attach interface to it.
                        create_ipaddress = await IPAddress(nb=nb, websocket=websocket, primary_field_value=cidr).post(data={
                            "address": cidr,
                            "assigned_object_id": create_interface.id,
                            "assigned_object_type": "dcim.interface"
                        })
                        
                        if create_ipaddress:
                            log(websocket, f"<span class='badge text-bg-green' title='Success'><strong><i class='mdi mdi-download'></i></strong></span> IP Address <strong><a href='{create_ipaddress.display_url}' target='_blank'>{create_ipaddress.address}</a></strong> of Interface <strong><a href='{create_interface.display_url}' target='_blank'>{create_interface.name}</a><span class='text-green'>created successfully.</span></strong>")
                            
                        print(f'create_ipaddress: {create_ipaddress}')
                    except Exception as error:
                        #raise ProxboxException(
                        await exception_log(
                            logger=log,
                            websocket=websocket,
                            message="<span class='text-red'><strong><i class='mdi mdi-error'></i></strong></span> Error trying to create IP Address of Interface on Netbox.",
                            python_exception=error
                        )
            
                    
                if interface_type == "bridge":
                    
                    bridge_ports = interface.get("bridge_ports")
                    print(f'bridge_ports: {bridge_ports}')
                    if bridge_ports:
                        bridge_ports = bridge_ports.split(" ")
                        
                        
                        for port in bridge_ports:
                            # print(f'current_node: {current_node}')
                            
                            netbox_port = None
                            
                            try:
                                await log(websocket, f"<span class='badge text-bg-yellow' title='Syncing'><strong><i class='mdi mdi-download'></i></strong></span> Searching children interface of bridge interface <strong><a href='{create_interface.display_url}' target='_blank'>{create_interface.name}</a></strong>.")
                                print(f"current_node.id: {current_node.id} / current_node: {current_node} / current_node.name: {current_node.name}")
                                
                                await log(websocket, f"<span class='badge text-bg-yellow' title='Syncing'><strong><i class='mdi mdi-download'></i></strong></span> Child interface <strong>{port}</strong> with Device ID <strong>{current_node.id}</strong>")
                                netbox_port = await Interface(nb=nb, websocket=websocket, primary_field_value=current_node.id).get(
                                    name=port
                                )
                                
                                if netbox_port:
                                    print(f"netbox_port: {netbox_port}")
                                    
                            except Exception as error: 
                                #raise ProxboxException(
                                await exception_log(
                                    logger=log,
                                    websocket=websocket,
                                    message="<span class='text-red'><strong><i class='mdi mdi-error'></i></strong></span> Error trying to search bridge child interface.", 
                                    python_exception=f"{error}"
                                )
                                
                            
                            print(f"port: {port}")
                            
                            if not netbox_port:
                                
                                proxmox_port = px.session.nodes(node.get("node")).network(port).get()
                                
                                print(f"proxmox_port: {proxmox_port}")
                                
                                if proxmox_port.get("active") == 1:
                                    enabled = True
                                else: enabled = False
                                

                                
                            # Interface and Bridge Interface must belong to the same Device
                            await log(websocket, "<span class='badge text-bg-yellow' title='Syncing'><strong><i class='mdi mdi-download'></i></strong></span> Creating child interface of a bridge. Bridge interface and child must belong to the same device.")
                            #print(f"create_interface.device: {create_interface.device}\ncurrent_node.id: {current_node.id}")
                            if create_interface:
                                if create_interface.device == current_node.id:
                                
                                    await log(websocket, f"<span class='badge text-bg-blue' title='Get'><strong><i class='mdi mdi-download'></i></strong></span> Creating interface <strong>{port}</strong>...")
                                    
                                    try:
                                        new_netbox_port = await Interface(nb=nb, websocket=websocket, primary_field_value=current_node.id).post(data={
                                            "device": current_node.id,
                                            "name": port,
                                            "enabled": enabled,
                                            "type": interface_type,
                                            "mtu": proxmox_port.get("mtu", None),
                                            "description": proxmox_port.get("comments", ""),
                                            "bridge": create_interface.id
                                        })
                                        
                                        if new_netbox_port:
                                            await log(websocket, f"<span class='badge text-bg-green' title='Success'><strong><i class='mdi mdi-download'></i></strong></span> Child Bridge Interface <strong><a href='{new_netbox_port.display_url}' target='_blank'>{port}</a> of <a href='{create_interface.display_url}' target='_blank'>{create_interface.name}</a> created successfully.</strong>")
                                        
                                    except Exception as error:
                                        
                                        #raise ProxboxException(
                                        await log_exception(
                                            websocket=websocket,
                                            message="<span class='text-red'><strong><i class='mdi mdi-error'></i></strong></span> Error trying to create child interface of bridge interface.",
                                            python_exception=error
                                    )
                                            
                                    cidr = proxmox_port.get("cidr")
                                    print(f"[2] cidr: {cidr}")
                                
                                    if cidr:
                                        await log(websocket, f"<span class='badge text-bg-yellow' title='Syncing'><strong><i class='mdi mdi-download'></i></strong></span> If interface with network configured, create IP Address <strong>{cidr}</strong> and attach interface to it.")
                                        try:
                                            create_ipaddress = await IPAddress(nb=nb, websocket=websocket, primary_field_value=cidr).post(data={
                                                "address": cidr,
                                                "assigned_object_id": new_netbox_port.id,
                                                "assigned_object_type": "dcim.interface"
                                            })
                                            
                                            if create_ipaddress:
                                                log(websocket, f"<span class='badge text-bg-green' title='Success'><strong><i class='mdi mdi-download'></i></strong></span> IP Address <strong><a href='{create_ipaddress.display_url}' target='_blank'>{create_ipaddress.address}</a></strong> of Interface <strong><a href='{new_netbox_port.display_url}' target='_blank'>{new_netbox_port.name}</a> created successfully.</strong>")
                                                
                                        #except Exception as error: raise ProxboxException(message="<span class='text-red'><strong><i class='mdi mdi-error'></i></strong></span> Error trying to create IP Address on Netbox", python_exception=error)
                                        except Exception as error: await exception_log(logger=log,websocket=websocket,message="<span class='text-red'><strong><i class='mdi mdi-error'></i></strong></span> Error trying to create IP Address on Netbox", python_exception=error)
                                    
                                    
                            
                                else:
                                    print(f"netbox_port {netbox_port}\ncreate_interface.device {create_interface.device}\ncurrent_node.id: {current_node.id}")

                                    await log(websocket, f"<span class='badge text-bg-green' title='Success'><strong><i class='mdi mdi-download'></i></strong></span> Interface already exists. Attaching Bridge to Interface <strong><a href='{create_interface.display_url}' target='_blank'>{create_interface.name}</a></strong>")
                                    print(f'create_interface: {create_interface}')
                                    # Interface and Bridge Interface must belong to the same Device
                                    if create_interface.device == current_node.id:
                                        netbox_port.bridge = create_interface.id
                                        netbox_port.device = current_node.id
                                        netbox_port.save()

                print(f'interface: {interface}')
            
            print("\n")

        
        await log(websocket, f"<span class='badge text-bg-yellow' title='Syncing'><strong><i class='mdi mdi-download'></i></strong></span> Nodes: {nodes}", "debug")
    
        
        result.append({
            "name": px.name,
            "netbox": {
                "nodes": nodes
            }
        })
        
        
    return result

@router.get("/nodes/interfaces")
async def get_nodes_interfaces():
    """
    Asynchronously retrieves the network interfaces of nodes in a cluster.
    This function is a placeholder and currently does not contain any implementation.
    """
    
    pass

@router.get("/virtual-machines")
async def get_virtual_machines(
    nb: NetboxSessionDep,
    pxs: ProxmoxSessionsDep,
    websocket: WebSocket
):    
    """
    ### Asynchronously retrieves virtual machines from Proxmox and creates corresponding entries in Netbox.
    
    **Args:**
    - **nb (`NetboxSessionDep`):** The Netbox session dependency.
    - **pxs (`ProxmoxSessionsDep`):** The Proxmox sessions dependency.
    - **websocket (`WebSocket`):** The WebSocket connection for logging and communication.
    
    **Returns:**
    - **`list`:** A list of dictionaries containing the name of the Proxmox cluster and the created virtual machines in Netbox.
    
    **Raises:**
    - **`ProxboxException:`** If there is an error creating virtual machines or their interfaces in Netbox.
    """
    

    from enum import Enum
    class VirtualMachineStatus(Enum):
        """
        Key are Netbox Status.
        Values are Proxmox Status.
        """
        active = "running"
        offline = "stopped"
    
    result = []
    
    
    containers = []
    
    from netbox_proxbox.backend.cache import cache
    
    print("CACHE start:", cache.cache)
    
    for px in pxs:
        virtual_machines = px.session.cluster.resources.get(type="vm")
        
        created_virtual_machines = []
        
        
        devices = {}
        clusters = {}
        for vm in virtual_machines:
            
            print(f"\n[VM] {vm}\n")
            
            vm_node: str = vm.get("node")
            print(f"vm_node: {vm_node} | {type(vm_node)}")
            
            """
            Get Device from Netbox based on Proxmox Node Name only if it's not already in the devices dict
            This way we are able to minimize the number of requests to Netbox API
            """
            if devices.get(vm_node) == None:
                devices[vm_node] = await Device(nb = nb, websocket = websocket).get(name = vm.get("node"))
                
            device = devices[vm_node]
            print(f"devices[vm_node]: {devices[vm_node]} | {device}")
            print(f"DEVICE TEST: {device}")
            
            
            """
            Get Cluster from Netbox based on Cluster Name only if it's not already in the devices dict
            This way we are able to minimize the number of requests to Netbox API
            """
            if clusters.get(px.name) == None:
                clusters[px.name] = await Cluster(nb = nb, websocket = websocket).get(name = px.name)
            
            cluster = clusters[px.name]
        
        
        
            role = await DeviceRole(nb = nb, websocket = websocket).get(slug = vm.get("type"))
            if role == None:
            
                vm_type = vm.get("type")
                
                vm_name = None
                
                color = "000000"
                
                if vm_type == "qemu":
                    vm_name = "Virtual Machine (QEMU)"
                    color = "00ffff"
                    description = "Proxmox Virtual Machine"

                if vm_type == "lxc":
                    vm_name = "Container (LXC)"
                    color = "7fffd4"
                    description = "Proxmox Container"
                
                role = await DeviceRole(nb = nb, websocket = websocket).post(data = {
                    "name": vm_name,
                    "slug": vm_type,
                    "vm_role": True,
                    "color": color,
                    "description": description
                })
                
            """
            Proxmox Virtual Machine ID Custom Field
            """    
           
            custom_field_id = nb.session.extras.custom_fields.get(name="proxmox_vm_id")
            
            if not custom_field_id:
                custom_field_id = nb.session.extras.custom_fields.create(
                    {
                        "object_types": [
                            "virtualization.virtualmachine"
                        ],
                        "type": "integer",
                        "name": "proxmox_vm_id",
                        "label": "VM ID",
                        "description": "Proxmox Virtual Machine or Container ID",
                        "ui_visible": "always",
                        "ui_editable": "hidden",
                        "weight": 100,
                        "filter_logic": "loose",
                        "search_weight": 1000,
                        "group_name": "Proxmox"
                    }
                )
            #print(f'custom_field_id: {custom_field_id}')
            
            """
            Proxmox Start at Boot Custom Field
            """            
            start_at_boot_field = nb.session.extras.custom_fields.get(name="proxmox_start_at_boot")

            if not start_at_boot_field:
                start_at_boot_field = nb.session.extras.custom_fields.create(
                    {
                        "object_types": [
                            "virtualization.virtualmachine"
                        ],
                        "type": "boolean",
                        "name": "proxmox_start_at_boot",
                        "label": "Start at Boot",
                        "description": "Proxmox Start at Boot Option",
                        "ui_visible": "always",
                        "ui_editable": "hidden",
                        "weight": 100,
                        "filter_logic": "loose",
                        "search_weight": 1000,
                        "group_name": "Proxmox"
                    }
                )
            
            print(f"start_at_boot_field: {start_at_boot_field}")
                        
            """
            Proxmox Unprivileged Container Custom Field
            """            
            start_unprivileged_field = nb.session.extras.custom_fields.get(name="proxmox_unprivileged_container")

            if not start_unprivileged_field:
                start_unprivileged_field = nb.session.extras.custom_fields.create(
                    {
                        "object_types": [
                            "virtualization.virtualmachine"
                        ],
                        "type": "boolean",
                        "name": "proxmox_unprivileged_container",
                        "label": "Unprivileged Container",
                        "description": "Proxmox Unprivileged Container",
                        "ui_visible": "if-set",
                        "ui_editable": "hidden",
                        "weight": 100,
                        "filter_logic": "loose",
                        "search_weight": 1000,
                        "group_name": "Proxmox"
                    }
                )
            
            unprivileged_container = None
            
            
            """
            Proxmox QEMU Guest Agent Custom Field
            """            
            start_qemu_agent_field = nb.session.extras.custom_fields.get(name="proxmox_qemu_agent")

            if not start_qemu_agent_field:
                start_qemu_agent_field = nb.session.extras.custom_fields.create(
                    {
                        "object_types": [
                            "virtualization.virtualmachine"
                        ],
                        "type": "boolean",
                        "name": "proxmox_qemu_agent",
                        "label": "QEMU Guest Agent",
                        "description": "Proxmox QEMU Guest Agent",
                        "ui_visible": "if-set",
                        "ui_editable": "hidden",
                        "weight": 100,
                        "filter_logic": "loose",
                        "search_weight": 1000,
                        "group_name": "Proxmox"
                    }
                )
                
            """
            Proxmox Search Domain Field
            """
            search_domain_field = nb.session.extras.custom_fields.get(name="proxmox_search_domain")
            
            if not search_domain_field:
                search_domain_field = nb.session.extras.custom_fields.create(
                    {
                        "object_types": [
                            "virtualization.virtualmachine"
                        ],
                        "type": "text",
                        "name": "proxmox_search_domain",
                        "label": "Search Domain",
                        "description": "Proxmox Search Domain",
                        "ui_visible": "if-set",
                        "ui_editable": "hidden",
                        "weight": 100,
                        "filter_logic": "loose",
                        "search_weight": 1000,
                        "group_name": "Proxmox"
                    }
                )
            
                    
            
            platform = None
            search_domain = None
            
            #if vm.get("type") == 'lxc': print(px.session.nodes.get(f'nodes/{vm.get("node")}/lxc/{vm.get("vmid")}/config')
            if vm.get("type") == 'lxc': 
                vm_config = px.session.nodes(vm.get("node")).lxc(vm.get("vmid")).config.get()
                
                platform_name = vm_config.get("ostype").capitalize()
                platform_slug = vm_config.get("ostype")
                
                search_domain = vm_config.get("searchdomain", None)
                
                unprivileged = int(vm_config.get("unprivileged", 0))
                
                if unprivileged == 1:
                    unprivileged_container = True
                
                platform = nb.session.dcim.platforms.get(name = platform_name).id
                if not platform:
                    platform = nb.session.dcim.platforms.create(
                        name = platform_name,
                        slug = platform_slug
                    ).id


            start_at_boot = False    
                
            if vm.get("type") == 'qemu':
                vm_config = px.session.nodes(vm.get("node")).qemu(vm.get("vmid")).config.get()
                
                onboot = int(vm_config.get("onboot", 0))
                
                if onboot == 1:
                    start_at_boot = True
                
                agent = int(vm_config.get("agent", 0))
                
                qemu_agent = None 
                
                if agent == 1:
                    qemu_agent = True
                else:
                    qemu_agent = False

            
                
            print(f"\n\nvm_config: {vm_config}\n\n")
            
            print(f"\nplatform: {platform}\n")
            
            print(f"device: {device} / type: {type(device)}")
            
            # Create Custom Field and add Virtual Machine Proxmox ID
            
            virtual_machine_data = {
                "name": vm.get("name"),
                "cluster": cluster.id,
                "device": int(device.id),
                "status": VirtualMachineStatus(vm.get("status")).name,
                "vcpus": int(vm.get("maxcpu", 0)),
                "memory": int(vm_config.get("memory")),
                "disk": int(int(vm.get("maxdisk", 0)) / 1000000),
                "role": role.id,
                "custom_fields": {
                    "proxmox_vm_id": vm.get("vmid"),
                    "proxmox_start_at_boot": start_at_boot,
                    "proxmox_unprivileged_container": unprivileged_container,
                    "proxmox_qemu_agent": qemu_agent,
                    "proxmox_search_domain": search_domain,
                },
                "platform": platform
            }
            
            try:
                await log(websocket, f"<span class='badge text-bg-yellow' title='Syncing'><strong><i class='mdi mdi-download'></i></strong></span> Creating Virtual Machine <strong>{vm.get("name")}</strong> on Netbox...")
                new_virtual_machine =  await VirtualMachine(nb = nb, websocket = websocket).post(data = virtual_machine_data)
                
                if new_virtual_machine:
                    log(websocket, f"<span class='badge text-bg-green' title='Success'><strong><i class='mdi mdi-download'></i></strong></span> Virtual Machine <strong><a href='{new_virtual_machine.display_url}' target='_blank'>{new_virtual_machine.name}</a></strong> created successfully.")


            except Exception as error:
                
                if "Virtual machine name must be unique per cluster." in str(error):
                    print("\nDUPLICATED VIRTUAL MACHINE NAME\n")
                    
                    log(websocket, f"<span class='badge text-bg-yellow' title='Syncing'><strong><i class='mdi mdi-download'></i></strong></span> Duplicated virtual machine NAME <strong>{virtual_machine_data["name"]}</strong> found within the same cluster. Appending '(2)' to the name")
                    virtual_machine_data["name"] = f"{virtual_machine_data["name"]} (2)"
                    
                    duplicated_virtual_machine = await VirtualMachine(nb = nb, websocket = websocket).post(data = virtual_machine_data)
                    
                    if duplicated_virtual_machine:
                        new_virtual_machine = duplicated_virtual_machine
                
                print(f"error: {error} / {type(error)}")
                raise ProxboxException(
                    message=f"<span class='text-red'><strong><i class='mdi mdi-error'></i></strong></span> [CHECK DUPLICATE] Error trying to create Virtual Machine '{vm.get("name")}' on Netbox.",
                    python_exception=f"{error}"
                )


            if new_virtual_machine:
                created_virtual_machines.append(new_virtual_machine)
                print(f"new_virtual_machine: {new_virtual_machine} | {type(new_virtual_machine)}")
                
                
                vm_networks = []
                network_id = 0
                
                await log(websocket, "<span class='badge text-bg-yellow' title='Syncing'><strong><i class='mdi mdi-download'></i></strong></span> Getting network info and parsing data into JSON (dict)")
                
                while True:
                    network_name = f"net{network_id}"
                    
                    vm_network_info = vm_config.get(network_name, None)
                    if vm_network_info != None:
                        
                        net_fields = vm_network_info.split(",")
                        
                        net_data = {}
                        
                        for field in net_fields:
                            key, value = field.split("=")
                        
                            net_data[key] = value
                        
                        
                        vm_networks.append({f"{network_name}": net_data})
                        
                        network_id += 1
                    else:
                        break
                    
                print(f"\nvm_networks: {vm_networks}\n")
                
                if vm_networks:
                    for network in vm_networks:
                        try:
                            print(f"network: {network}")
                            print(f"network (items): {network.items()}")
                            for k, v in network.items():
                                print(f'k: {k} / v: {v}')
                                
                                
                                mac_address = None
                                
                                virtio = v.get("virtio", None)
                                if virtio: mac_address=virtio
                        
                                hwaddr = v.get("hwaddr", None)
                                if hwaddr: mac_address=hwaddr
                                
                                await log(websocket, f"<span class='badge text-bg-yellow' title='Syncing'><strong><i class='mdi mdi-download'></i></strong></span> Try creating VirtualMachine Interface <strong>{str(k)}</strong> on Netbox...")
                                try:
                                    
                                    
                                    #vm_already_exists = await VMInterface(nb=nb, websocket=websocket).get({
                                    #    "virtual_machine": new_virtual_machine.id,
                                    #    "name": str(k)
                                    #})
                                    
                                    #if not vm_already_exists:
                                
                                    netbox_interface = await VMInterface(nb=nb, websocket=websocket).post(data={
                                        "virtual_machine": new_virtual_machine.id,
                                        "name": str(k),
                                        "enabled": True,
                                        "mac_address": mac_address,
                                    })
                                    
                                    if netbox_interface:
                                        await log(websocket, f"<span class='badge text-bg-green' title='Success'><strong><i class='mdi mdi-download'></i></strong></span> Virtual Machine Interface <strong><a href='{netbox_interface.display_url}' target='_blank' {netbox_interface.name}</a></strong> created successfully.")
                                
                                except Exception as error:
                                    raise ProxboxException(
                                        message="<span class='text-red'><strong><i class='mdi mdi-error'></i></strong></span> Error trying to create VM interface on Netbox",
                                    )
                        except Exception as error:
                            raise ProxboxException(
                                message=f"<span class='text-red'><strong><i class='mdi mdi-error'></i></strong></span> Error trying to create {new_virtual_machine.name} VM Network Interfaces",
                            )

        result.append({
            "name": px.name,
            "netbox": {
                "virtual_machines": created_virtual_machines
            }
        })
    
    print("CACHE end:", cache.cache)
    return result