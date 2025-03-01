from proxbox_api.exception import ProxboxException
from proxbox_api.logger import log

from fastapi import WebSocket

import asyncio

async def _check_default(
    websocket: WebSocket,
    pynetbox_path,
    default_name: str,
    default_slug: str,
    object_name: str,
    nb, 
    
):
    """
    Asynchronously checks for default objects in Netbox before creating a new one.
    """
    
    await log(
        websocket=websocket,
        msg="<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> Checking default object."
    )
    
    try:
        # Check if the default object exists in Netbox.
        result = await asyncio.to_thread(
            pynetbox_path.get,
            name=default_name,
            slug=default_slug,
            tag=[nb.tag.slug]
        )
        
        # If the default object exists, return it.
        if result:
            return result
        
        else:
            # If no object found searching using tag, try to find without it, using just name and slug.
            result = await asyncio.to_thread(
                pynetbox_path.get,
                name=default_name,
                slug=default_slug,
            )
            
            # If the default object exists, return it.
            if result:
                await log(
                    websocket=websocket,
                    msg=f"<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> Default <strong>{object_name}</strong> with ID <strong>{result.id}</strong> found on Netbox, but without Proxbox tag.\nPlease delete it (or add the tag) and try again.\nNetbox does not allow duplicated names and/or slugs."
                )
            else:
                return None
        
        # If the default object does not exist, return None.
        return None
    
    except ProxboxException as error:
        await log(
            websocket=websocket,
            msg=f'{error}'
        )
    
    except Exception as error:
        await log(
            websocket=websocket,
            msg=f"<span class='badge text-bg-red' title='Post'><strong><i class='mdi mdi-upload'></i></strong></span> Error trying to create default <strong>{object_name}</strong> on Netbox.\nPython Error: {error}",
        )