from proxbox_api.logging import log

from fastapi import WebSocket

import asyncio

async def _check_vm_interface(
    websocket: WebSocket,
    pynetbox_path,
    primary_field_value: str,
    vm_interface_object: dict
):
    result_by_vm_interface = None
    
    try:
        # GET
        result_by_vm_interface = await asyncio.to_thread(
            pynetbox_path.get,
            virtual_machine=primary_field_value,
            name=vm_interface_object.get("name", "")
        )
        
        await log(
            websocket=websocket,
            msg="<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> If duplicate interface found, check if the virtual machines are the same."
        )
            
        # Check if result is not None.
        if result_by_vm_interface:
            await log(
                websocket=websocket,
                msg="<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> VM Interface with the same Virtual Machine ID found. Duplicated object, returning it."
            )
            
            # Check if Virtual Machine registered on the VM Interface is the same as the one being created.
            if result_by_vm_interface.virtual_machine == primary_field_value:
                return result_by_vm_interface

            # If the Virtual Machine is different, return as NOT duplicated. Interface NAME is the same, but the Virtual Machine fields are different.
            else:
                await log(
                    websocket=websocket,
                    msg="<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> If interface equal, but different devices, return as NOT duplicated."
                )
                
                return None
            
    except Exception as error:
        await log(
            websocket=websocket,
            msg=f"Error trying to get 'VM Interface' object using 'virtual_machine' and 'name' fields.\nPython Error: {error}",
        )
    
    return None