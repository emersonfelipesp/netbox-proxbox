from netbox_proxbox.backend.exception import ProxboxException
from netbox_proxbox.backend.logging import log
from netbox_proxbox.backend.cache import cache

from fastapi import WebSocket

async def _post(
    websocket: WebSocket,
    data: dict = {},
): 
    """
    ### Asynchronously handles the POST request to create an object on Netbox.
    
    **Args:**
    - **data (dict, optional):** The data payload for creating the object. Defaults to None.
    
    **Returns:**
    - **response:** The created object response from Netbox if successful, or the existing object if a duplicate is found.
    - **None:** If the object could not be created due to a unique constraint violation.
    
    **Raises:**
    - **ProxboxException:** If there is an error parsing the Pydantic model to a dictionary, 
                            if required fields are missing, or if there is an error during the creation process.
    
    **Workflow:**
        1. Retrieves the base dictionary from the cache or fetches it if not present.
        2. Logs the creation attempt.
        3. Converts the Pydantic model to a dictionary if necessary.
        4. Generates a slug from the name or model field if not provided.
        5. Uses the base dictionary if no data is provided or if default is set.
        6. Merges the base dictionary with the provided data.
        7. Checks for duplicates.
        8. Appends the Proxbox tag to the tags field if present, or creates it.
        9. Attempts to create the object on Netbox.
        10. Logs the success or failure of the creation attempt.
    """ 
    
    self.base_dict = cache.get(self.endpoint)
    if self.base_dict is None:
        self.base_dict = await self.get_base_dict()
        cache.set(self.endpoint, self.base_dict)

    if data:
        await log(self.websocket, f"<span class='badge text-bg-red' title='Post'><strong><i class='mdi mdi-upload'></i></strong></span> Creating <strong>{self.object_name}</strong> object on Netbox.")
    
        if isinstance(data, dict) is False:
            try:
                # Convert Pydantic model to Dict through 'model_dump' Pydantic method.
                data = data.model_dump(exclude_unset=True)
                
            except Exception as error:
                raise ProxboxException(
                    message="<span class='text-red'><strong><i class='mdi mdi-upload'></i></strong></span> <span class='text-red'><strong><i class='mdi mdi-error'></i></strong></span> <strong>[POST]</strong> Error parsing Pydantic model to Dict.",
                    python_exception=f"{error}",
                )
            
        # If no explicit slug was provided by the payload, create one based on the name.
        if data.get("slug") is None:
            if not self.primary_field:
                await log(self.websocket, "<span class='badge text-bg-red' title='Post'><strong><i class='mdi mdi-upload'></i></strong></span> <strong>SLUG</strong> field not provided on the payload. Creating one based on the NAME or MODEL field.")
                try:
                    data["slug"] = data.get("name").replace(" ", "-").lower()
                except AttributeError:
                    
                    try:
                        data["slug"] = data.get("model").replace(" ", "-").lower()
                    except AttributeError:
                        raise ProxboxException(
                            message="<span class='badge text-bg-red' title='Post'><strong><i class='mdi mdi-upload'></i></strong></span> No <strong>NAME</strong> or <strong>model</strong> field provided on the payload. Please provide one of them.",
                        )
            
    if self.default or data is None:
        await log(self.websocket, f"<span class='badge text-bg-red' title='Post'><strong><i class='mdi mdi-upload'></i></strong></span> Creating DEFAULT <strong>{self.object_name}</strong> object on Netbox.")
        data: dict = self.base_dict
        
    try:

        """
        Merge base_dict and data dict.
        The fields not specificied on data dict will be filled with the base_dict values.
        """
        data: dict = self.base_dict | data
        
        check_duplicate_result = await self._check_duplicate(object = data)
        
        if check_duplicate_result is None:
            response = None
            
            # Check if tags field exists on the payload and if true, append the Proxbox tag. If not, create it.
            if data.get("tags") is None:
                data["tags"] = [self.nb.tag.id]
            else:
                data["tags"].append(self.nb.tag.id)
                
            try:
                await log(self.websocket, f"<span class='badge text-bg-red' title='Post'><strong><i class='mdi mdi-upload'></i></strong></span> Trying to create <strong>{self.object_name}</strong> object on Netbox.")
                
                response = await asyncio.to_thread(self.pynetbox_path.create, data)
                
                if response:
                    await log(
                        self.websocket,
                        f"<span class='badge text-bg-red' title='Post'><strong><i class='mdi mdi-upload'></i></strong></span> <strong>{self.object_name}</strong> object created successfully. {self.object_name} ID: {getattr(response, 'id', 'Not specified.')}"
                    )
                    return response
                
                else:
                    await log(
                        self.websocket,
                        f"<span class='badge text-bg-red' title='Post'><strong><i class='mdi mdi-upload'></i></strong></span> <strong>{self.object_name}</strong> object could not be created.\nPayload: <code>{data}</code>"
                    )
                    
            except Exception as error:
                
                if "['The fields virtual_machine, name must make a unique set.']}" in f"{error}":
                    await log(
                        self.websocket,
                        f"Error trying to create <strong>Virtual Machine Interface</strong> because the same <strong>virtual_machine</strong> name already exists.\nPayload: {data}"
                    )
                    return None
                
                if "['Virtual machine name must be unique per cluster.']" in f"{error}":
                    await log(
                        self.websocket,
                        f"Error trying to create <strong>Virtual Machine</strong> because Virtual Machine Name <strong>must be unique.</strong>\nPayload: {data}"
                    )
                    return None
                
                else:
                    await log(
                        self.websocket,
                        msg=f"<span class='badge text-bg-red' title='Post'><strong><i class='mdi mdi-upload'></i></strong></span> Error trying to create <strong>{self.object_name}</strong> object on Netbox.\n   > {f'{error}'}",
                    )
        else:
            await log(self.websocket, f"<span class='badge text-bg-red' title='Post'><strong><i class='mdi mdi-upload'></i></strong></span> <strong>{self.object_name}</strong> object already exists on Netbox. Returning it.")
            return check_duplicate_result

    except Exception as error:
        raise ProxboxException(
            message=f"Error trying to create <strong>{self.object_name}</strong> on Netbox.",
            detail=f"Payload provided: {data}",
            python_exception=f"{error}"
        )