from proxbox_api.exception import ProxboxException
from proxbox_api.logging import log
from proxbox_api.cache import cache

from fastapi import WebSocket

import asyncio

async def _get_by_kwargs(
    websocket: WebSocket,
    pynetbox_path,
    endpoint: str,
    primary_field: str,
    primary_field_value: str,
    object_name: str,
    **kwargs
):
    """
    Asynchronously retrieves an object based on the provided keyword arguments.
    This method attempts to fetch an object from the Netbox API using the specified
    keyword arguments. If multiple objects are found, it handles the duplication
    by checking specific conditions based on the endpoint and primary field.
    
    **Args:**
    - **kwargs: Arbitrary keyword arguments used to filter the objects.
    
    **Returns:**
    - The object retrieved from the Netbox API if found, otherwise None.
    
    **Raises:**
    - **ProxboxException:** If an error occurs while fetching the object or if
    multiple objects are found and cannot be resolved.
    """
    
    await log(websocket, f"<span class='badge text-bg-blue' title='Get'><strong><i class='mdi mdi-download'></i></strong></span> Searching <strong>{object_name}</strong> by kwargs {kwargs}.")
    try:
        try:
            response = await asyncio.to_thread(pynetbox_path.get, **kwargs)
            return response
        except Exception as error:
            if "get() returned more than one result." in f"{error}":
                await log(websocket, f"<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> Object <strong>{object_name}</strong> with the same name already found. Checking with '.filter' method")
                
                if endpoint == "interfaces" and primary_field == "device":

                    await log(websocket, "<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> Checking duplicate device using as PRIMARY FIELD the DEVICE.")
                    result_by_primary = await asyncio.to_thread(pynetbox_path.get, virtual_machine=primary_field_value)

                    if result_by_primary:
                        if result_by_primary.virtual_machine == primary_field_value:
                            await log(websocket, "<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> Interface with the same Device found. Duplicated object, returning it.")
                            return result_by_primary
                
                    else:
                        await log(websocket, "<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> If interface equal, but different devices, return as NOT duplicated.")
                        return None

    except ProxboxException as error:
        raise error
    
    except Exception as error:
        await log(
            websocket=websocket,
            msg=f"<span class='badge text-bg-blue' title='Get'><strong><i class='mdi mdi-download'></i></strong></span> Error trying to get <strong>{object_name}</strong> from Netbox using the specified kwargs <code>{kwargs}</code>.\nPython Error: {error}",
        )


async def _get_by_id(
    websocket: WebSocket,
    nb,
    pynetbox_path,
    ignore_tag: bool,
    object_name: str,
    id: int
):
    """
    Asynchronously retrieves an object from Netbox using its ID.
    If the 'id' query parameter is provided, this method attempts to fetch the object
    from Netbox. It logs the process and handles exceptions appropriately.
    
    **Raises:**
    - **ProxboxException:** If the object is not found or if any other error occurs during retrieval.
    
    **Returns:**
    - The object retrieved from Netbox if found.
    
    If Query Parameter 'id' provided, use it to get the object from Netbox.
    """
    
    await log(websocket, f"<span class='badge text-bg-blue' title='Get'><strong><i class='mdi mdi-download'></i></strong></span> Searching <strong>{self.object_name}</strong> by ID {self.id}.")
    
    response = None
    
    try:
        if ignore_tag:
            response = await asyncio.to_thread(pynetbox_path.get, id)
        
        else:
            response = await asyncio.to_thread(pynetbox_path.get,
                id=id,
                tag=[nb.tag.slug]
            )
            
        # 1.1. Return found object.
        if response is None:
            await log(
                websocket=websocket,
                msg=f"<span class='badge text-bg-blue' title='Get'><strong><i class='mdi mdi-download'></i></strong></span> <strong>{object_name}</strong> with ID <strong>{id}</strong> found on Netbox. Returning it."
            )
            
            return response
        
        # 1.2. Raise ProxboxException if object is not found.
        else:
            await log(
                websocket=websocket,
                msg=f"<span class='text-blue'><strong><i class='mdi mdi-download'></i></strong></span> <span class='text-grey'><strong>[GET]</strong></span> <strong>{object_name}</strong> with ID <strong>{id}</strong> not found on Netbox.\nPlease check if the ID provided is correct. If it is, please check if the object has the Proxbox tag. (You can use the 'ignore_tag' query parameter to ignore this check and return object without Proxbox tag)",
            )
        
        
    except ProxboxException as error:
        await log(websocket=websocket, msg=f'{error}')
    
    except Exception as error:
        await log(
            websocket=websocket,
            msg=f"<span class='badge text-bg-blue' title='Get'><strong><i class='mdi mdi-download'></i></strong></span> Error trying to get <strong>{object_name}</strong> from Netbox using the specified ID <strong>{id}</strong>.\nPython Error: {error}",
        )


async def _get_all(
    websocket: WebSocket,
    nb,
    pynetbox_path,
    ignore_tag: bool,
    object_name: str,                 
):
    """
    ### Asynchronously retrieves all objects from Netbox.
    
    If `ignore_tag` is True, it returns all objects from Netbox.
    If `ignore_tag` is False, it returns only objects with the Proxbox tag.
    
    **Returns:**
    - **list:** A list of objects retrieved from Netbox.
    
    **Raises:**
    - **ProxboxException:** If there is an error while trying to retrieve the objects.
    """

    
    if ignore_tag:
        try:
            # If ignore_tag is True, return all objects from Netbox.
            return [item for item in await asyncio.to_thread(pynetbox_path.all())]
        except Exception as error:
            await log(
                websocket=websocket,
                msg=f"Error trying to get all <strong>{object_name}</strong> from Netbox.\nPython Error: {error}",
            )
        
    try:       
        # If ignore_tag is False, return only objects with Proxbox tag.
        return [item for item in asyncio.to_thread(pynetbox_path.filter, tag = [nb.tag.slug])]
    
    except Exception as error:
        await log(
            websocket=websocket,
            msg=f"Error trying to get all Proxbox <strong>{object_name}</strong> from Netbox.\nPython Error: {error}",
        )