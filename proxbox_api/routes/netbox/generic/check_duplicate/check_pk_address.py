from proxbox_api.logger import log

from fastapi import WebSocket

import asyncio

async def _check_pk_address(
    websocket: WebSocket,
    pynetbox_path,
    primary_field_value: str,
    object_name: str,
):
    await log(
        websocket=websocket,
        msg="<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> Checking duplicate OBJECT using the ADDRESS as PRIMARY FIELD."
    )
    
    result_by_address = None
    
    try:
        result_by_address = await asyncio.to_thread(
            pynetbox_path.get,
            address=primary_field_value
        )

    except Exception as error:
        if "get() returned more than one result" in f"{error}":
            try:
                result_by_filter_address = await asyncio.to_thread(pynetbox_path.filter, address=primary_field_value)
                
                if result_by_filter_address:
                    for address in result_by_filter_address:
                        print(f"ADDRESS OBJECT: {address}")
                        # TODO: Check if the address object is the same as the one being created.
                        
            except:
                await log(
                    websocket=websocket,
                    msg=f"<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> Error trying to <code>FILTER</code> <strong>{object_name}</strong> by address on Netbox.\nPython Error: {error}",
                )
                
       
        await log(
            websocket=websocket,
            msg=f"<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> Error trying to get <strong>{object_name}</strong> by address on Netbox.\nPython Error: {error}",
        )
    
    if result_by_address:
        await log(
            websocket=websocket,
            msg="<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> IP Address with the same network found. Returning it."
        )
        
        return result_by_address