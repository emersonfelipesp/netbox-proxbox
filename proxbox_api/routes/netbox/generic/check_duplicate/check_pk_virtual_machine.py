from proxbox_api.logger import log

from fastapi import WebSocket

import asyncio

async def _check_pk_virtual_machine(
    websocket: WebSocket,
    pynetbox_path,
    primary_field_value: str,
    object_name: str,
    endpoint: str
):
    await log(
        websocket=websocket,
        msg="<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> Checking duplicate device using the VIRTUAL MACHINE as PRIMARY FIELD."
    )
  
    if endpoint == "interfaces":                  
        result_by_virtual_machine = None
        
        try:
            # THE ERROR IS HERE.
            #
            # GET
            result_by_virtual_machine = await asyncio.to_thread(
                pynetbox_path.get,
                virtual_machine=primary_field_value
            )
            
            if result_by_virtual_machine:
                for interface in result_by_virtual_machine:
                    print(f"INTERFACE OBJECT: {interface} | {interface.virtual_machine}")
                    
                    print(f"interface.virtual_machine: {interface.virtual_mchine} | primary_field_value: {primary_field_value}")
                    
                    # Check if Virtual Machine registered on the interface is the same as the one being created.
                    if interface.virtual_machine == primary_field_value:
                        return interface
                    
                    else:
                        return None
        
        except Exception as error:
            await log(
                websocket=websocket,
                msg=f"<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> Error trying to get interface using only 'virtual_machine' field as parameter.\n   >{error}"
            )
            
            if "get() returned more than one result" in f"{error}":
                # FILTER
                await log(
                    websocket=websocket,
                    msg="<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> Found more than one <strong>VM INTERFACE</strong> object with the same <strong>virtual_machine</strong> field.\nTrying to use <code>.filter</code> pynetbox method now."
                )
            
                try:
                    result_by_virtual_machine = await asyncio.to_thread(
                        pynetbox_path.filter,
                        virtual_machine=primary_field_value,
                    )
                    
                    if result_by_virtual_machine:
                        for interface in result_by_virtual_machine:
                            print(f"INTERFACE OBJECT: {interface} | {interface.virtual_machine}")
                            
                            print(f"interface.virtual_machine: {interface.virtual_mchine} | primary_field_value: {primary_field_value}")
                            if interface.virtual_machine == primary_field_value:
                                return interface
                            else:
                                return None

                except Exception as error:
                    await log(
                        websocket=websocket,
                        msg=f"Error trying to get 'VM Interface' object using 'virtual_machine' and 'name' fields.\nPython Error: {error}",
                    )