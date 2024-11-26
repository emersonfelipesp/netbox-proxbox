from netbox_proxbox.backend.exception import ProxboxException
from netbox_proxbox.backend.logging import log
from netbox_proxbox.backend.cache import cache

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
                    msg=f"<span class='badge text-bg-purple' title='Check Duplicate'>
                        <i class='mdi mdi-content-duplicate'></i>
                    </span> Default <strong>{object_name}</strong> with ID <strong>{result.id}</strong> found on Netbox, but without Proxbox tag. 
                    Please delete it (or add the tag) and try again.\nNetbox does not allow duplicated names and/or slugs."
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

async def _check_duplicate(
    websocket: WebSocket,
    search_params: dict = {},
    object: dict = {},
):
    """
    Asynchronously checks for duplicate objects in Netbox before creating a new one.
    This method performs several checks to determine if an object already exists in Netbox based on various criteria 
    such as default settings, primary fields, and specific attributes provided in the `object` parameter.
    
    **Args:**
    - **search_params (dict, optional):** Parameters to search for duplicates. Defaults to None.
    - **object (dict, optional):** The object to check for duplication. Defaults to None.
    
    **Returns:**
    - **dict or None:** The existing object if a duplicate is found, otherwise None.
    
    **Raises:**
    - **ProxboxException:** If an error occurs during the duplicate check process.
    """
    
    await log(self.websocket, f"<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> Checking if <strong>{self.object_name}</strong> exists on Netbox before creating it.")
    
    if self.default:
        await log(self.websocket, "<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> Checking default object.")
        try:
            result = await asyncio.to_thread(self.pynetbox_path.get,
                name=self.default_name,
                slug=self.default_slug,
                tag=[self.nb.tag.slug]
            )
            
            
            if result:
                return result
            
            else:
                # If no object found searching using tag, try to find without it, using just name and slug.
                result = await asyncio.to_thread(self.pynetbox_path.get,
                    name=self.default_name,
                    slug=self.default_slug,
                )
                
                
                if result:
                    raise ProxboxException(
                        message=f"<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> Default <strong>{self.object_name}</strong> with ID <strong>{result.id}</strong> found on Netbox, but without Proxbox tag. Please delete it (or add the tag) and try again.",
                        detail="Netbox does not allow duplicated names and/or slugs."
                    )
                
            return None
            
            # create = self.pynetbox_path.create(self.default_dict)
            # return create
        
        except ProxboxException as error:
            raise error
        
        except Exception as error:
            raise ProxboxException(
                message=f"<span class='badge text-bg-red' title='Post'><strong><i class='mdi mdi-upload'></i></strong></span> Error trying to create default <strong>{self.object_name}</strong> on Netbox.",
                python_exception=f"{error}"
            )
            
    if object:
        try:
            if (self.primary_field):
                await log(self.websocket, "<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> (0.5) Checking object using only custom PRIMARY FIELD and Proxbox TAG provided by the class attribute.")
                print(f"primary field: {self.primary_field} - primary_field_value: {self.primary_field_value}")
                
                
                print(f'self.primary_field = {self.primary_field} / {self.endpoint}')
                
                if self.primary_field == "address":
                    await log(self.websocket, "<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> Checking duplicate device using as PRIMARY FIELD the ADDRESS.")
                    
                    result_by_primary = None
                    
                    try:
                        result_by_primary = await asyncio.to_thread(self.pynetbox_path.get, address=self.primary_field_value)
                        
                    except Exception as error:
                        if "get() returned more than one result" in f"{error}":
                            try:
                                result_by_primary = await asyncio.to_thread(self.pynetbox_path.filter, address=self.primary_field_value)
                                
                                if result_by_primary:
                                    for address in result_by_primary:
                                        print(f"ADDRESS OBJECT: {address}")
                                        
                            except Exception as error:
                                raise ProxboxException(
                                    message="Error trying to filter IP ADDRESS objects.",
                                    python_exception=error,
                                )
                                    
                    print(f"self.primary_field_value = {self.primary_field_value}")
                    
                    if result_by_primary:
                        await log(self.websocket, "<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> IP Address with the same network found. Returning it.")
                        return result_by_primary
                    
                if self.primary_field == "virtual_machine" and self.endpoint == "interfaces":
                    await log(self.websocket, "<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> Checking duplicate device using as PRIMARY FIELD the DEVICE.")
                    
                    result_by_primary = None
                    
                    try:
                        #
                        # THE ERROR IS HERE.
                        #
                        # GET
                        print("THE ERROR IS HERE.")
                        result_by_primary = await asyncio.to_thread(
                            self.pynetbox_path.get,
                            virtual_machine=self.primary_field_value,
                            name=object.get("name", "Not specified.")
                        )
                        print(f"result_by_primary: {result_by_primary}")

                        if result_by_primary:
                            for interface in result_by_primary:
                                print(f"INTERFACE OBJECT: {interface} | {interface.virtual_machine}")
                                
                                print(f"interface.virtual_machine: {interface.virtual_mchine} | primary_field_value: {self.primary_field_value}")
                                if interface.virtual_machine == self.primary_field_value:
                                    return interface
                                else:
                                    return None
                    
                    except Exception as error:
                        await log(self.websocket, f"<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> Error trying to get interface using only 'virtual_machine' field as parameter.\n   >{error}")
                        if "get() returned more than one result" in f"{error}":
                            # FILTER
                            await log(self.websocket, "<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> Found more than one VM INTERFACE object with the same 'virtual_machine' field. Trying to use '.filter' pynetbox method now.")
                            
                            
                            try:
                                result_by_primary = await asyncio.to_thread(
                                    self.pynetbox_path.filter,
                                    virtual_machine=self.primary_field_value,
                                    name=object.get("name", "Not specified.")
                                )
                                
                                if result_by_primary:
                                    for interface in result_by_primary:
                                        print(f"INTERFACE OBJECT: {interface} | {interface.virtual_machine}")
                                        
                                        print(f"interface.virtual_machine: {interface.virtual_mchine} | primary_field_value: {self.primary_field_value}")
                                        if interface.virtual_machine == self.primary_field_value:
                                            return interface
                                        else:
                                            return None
    
                            except Exception as error:
                                await log(
                                    self.websocket,
                                    msg=f"Error trying to get 'VM Interface' object using 'virtual_machine' and 'name' fields.\nPython Error: {error}",
                                )

                else:
                    result_by_primary = await asyncio.to_thread(self.pynetbox_path.get,
                        {
                            f"{self.primary_field}": self.primary_field_value,
                        }
                    )
                
                print(f"result_by_primary: {result_by_primary}")
                if result_by_primary:
                    
                    if self.endpoint == "interfaces":
                        await log(self.websocket, "<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> If duplicate interface found, check if the devices are the same.")
                        if result_by_primary.device == self.primary_field_value:
                            await log(self.websocket, "<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> Interface with the same Device found. Duplicated object, returning it.")
                            return result_by_primary
                        else:
                            await log(self.websocket, "<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> If interface equal, but different devices, return as NOT duplicated.")
                            return None
                    
                    await log(self.websocket, "[CHECK_DUPLICATE] Object found on Netbox. Returning it.")
                    print(f'result_by_primary: {result_by_primary}')
                    return result_by_primary
                
                return None
                
            await log(self.websocket, "<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> (1) First attempt: Checking object making <strong>EXACT MATCH</strong> with the Payload provided...")
            result = await asyncio.to_thread(self.pynetbox_path.get, dict(object))
            
            if result:
                await log(
                    self.websocket,
                    "<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> <strong>Object found</strong> on Netbox. Returning it."
                )
                
                return result
            
            else:
                
                await log(self.websocket, "<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> (1.5) Checking object using <strong>NAME</strong> and <strong>DEVICE</strong> provided by the Payload and also the <strong>PROXBOX TAG</strong>. If found, return it.")
                
                result_by_device = None
                
                device_id: int = object.get('device', 0)
                
                device_obj = None
                result_by_device_id = None
                result_by_device_name = None
                
                print(f"object: {object}")
                print(f"device_obj: {device_obj}") 
                print(f"device_obj.name: {getattr(device_obj, 'name', 'Not specified.')}")
                print(f"object.get('name'): {object.get('name', 'Not specified.')}")
                print(f"device_obj.id: {getattr(device_obj, 'id', 'Not specified')}")
                
                try:
                    await log(self.websocket, "<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> (1.5.1) Checking duplicate using <strong>Device Object</strong> as parameter.")
                    
                    if device_id > 0:
                        await log(
                            self.websocket,
                            "<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> (1.5.1.1) Searching for <strong>Device Object</strong> using <strong>Device ID</strong> as parameter."
                        )
                        result_by_device_id = self.nb.session.dcim.devices.get(int(device_id))
                        
                        if result_by_device_id:
                            return result_by_device_id
                        
                    if result_by_device_id is None:
                        await log(
                            self.websocket,
                            "<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> (1.5.1.2) Device Object <strong>NOT</strong> found using <strong>Device ID</strong> as parameter. Trying to use <strong>Device NAME</strong> as parameter."
                        )
                        
                        result_by_device_name = await asyncio.to_thread(self.pynetbox_path.get,
                            name=object.get('name', "Not specified."),
                            tag=[self.nb.tag.slug]
                        )
                        
                        if result_by_device_name:
                            return result_by_device_name
                        
                        else:
                            await log(
                                self.websocket,
                                "<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> Not abe to get <strong>Device Object</strong> using <strong>Device NAME</strong> neither <strong>Device ID</strong> as parameter."
                            )
                    
                except Exception as error:
                    await log(
                        self.websocket,
                        f"<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> (1.5.1) Device Object <strong>NOT</strong> found when checking for duplicated using <strong>Device<strong> as parameter.<br>{error}"
                    )
                
                
                if result_by_device:
                    if int(object.get('device', 0)) != int(result_by_device.device.id):
                        return None
                    
                    await log(self.websocket, "<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> (1.5.1) <strong>Object found</strong> on Netbox. Returning it.")
                    return result_by_device

                    
                await log(self.websocket, "<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> (2) Checking object using only <strong>NAME</strong> and <strong>SLUG</strong> provided by the Payload and also the <strong>PROXBOX TAG</strong>. If found, return it.")
                
                
                result_by_tag = None
                try:
                    await log(self.websocket, "<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> (2.1) Searching object using <strong>GET</strong> method")
                    result_by_tag = await asyncio.to_thread(self.pynetbox_path.get,
                        name=object.get("name"),
                        slug=object.get("slug"),
                        tag=[self.nb.tag.slug]
                    )
                    print(result_by_tag)
                
                except Exception as error:
                    print(f'Error: {error}')
                    
                    try:
                        result_by_tag = await asyncio.to_thread(self.pynetbox_path.filter,
                            name=object.get("name"),
                            slug=object.get("slug"),
                            tag=[self.nb.tag.slug]
                        )
                        
                        if result_by_tag:
                            await log(self.websocket, "<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> (2) More than one <strong>object found</strong>.")
                            
                            for obj in result_by_tag:
                                print(f"obj.id: {obj.device.id} / device_obj.id: {device_obj.id}")
                                
                                if int(obj.device.id) == int(device_obj.id):
                                    await log(self.websocket, "<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> (2) More than one <strong>object found</strong>, but returning with the <strong>same ID</strong>.")
                                    return obj
                            return None
                        print(f"filter: {result_by_tag}")
                        
                    except Exception as error:
                        await log(self.websocket, f'{error}')
                    
                if result_by_tag:
                    await log(
                        self.websocket,
                        "<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> <strong>Object found</strong> on Netbox. Returning it."
                    )
                    
                    return result_by_tag
                    
                await log(
                    self.websocket,
                    "<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> (3) Checking <strong>duplicate object</strong> using only <strong>NAME</strong> and <strong>SLUG</strong>"
                )
                
                result_by_name_and_slug = await asyncio.to_thread(self.pynetbox_path.get,
                    name=object.get("name"),
                    slug=object.get("slug"),
                )
                
                if result_by_name_and_slug:
                    await log(
                        self.websocket,
                        msg=f"<span class='badge text-bg-purple' title='Check Duplicate'><i class='mdi mdi-content-duplicate'></i></span> <strong>{self.object_name}</strong> with ID <strong>{getattr(result_by_name_and_slug, 'id', 0)}</strong> found on Netbox, but <strong>without PROXBOX TAG</strong> Please delete it (or add the tag) and try again.\nNetbox does not allow duplicated names and/or slugs.",
                    )

            return None
            
        except ProxboxException as error:
            raise error

    return None