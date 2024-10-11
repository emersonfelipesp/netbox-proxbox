from fastapi import Query, Body

from typing import Annotated
from typing_extensions import Doc

from netbox_proxbox.backend.session.netbox import NetboxSessionDep
from netbox_proxbox.backend.exception import ProxboxException

from netbox_proxbox.backend.logging import logger

from netbox_proxbox.backend.cache import cache

import asyncio

class NetboxBase:
    """
    ## Class to handle Netbox Objects.
    
    !!! Logic
        - it will use `id` to get the `Objects` from Netbox if provided.\n
            - if object is returned, it will return it.\n
            - if object is not returned, it will raise an `ProxboxException`.
            
        - if 'site_id' is not provided, it will check if there's any Site registered on Netbox.\n
            - if there's no 'Objects' registered on Netbox, it will create a default one.\n
            - if there's any 'Objects' registered on Netbox, it will check if is Proxbox one by checking tag and name.\n
                
                -  if it's Proxbox one, it will return it.\n
                - if it's not Proxbox one, it will create a default one.\n
                
        - if 'all' is True, it will return all 'Objects' registered on Netbox.
    
    """

    def __init__(
        self,
        nb: NetboxSessionDep,
        id: Annotated[
            int,
            Query(
                title="Object ID"
            )
        ] = None,
        all: Annotated[
            bool,
            Query(title="List All Objects", description="List all Objects registered on Netbox.")
        ] = False,
        default: Annotated[
            bool,
            Query(title="Create Default Object", description="Create a default Object if there's no Object registered on Netbox."),
        ] = False,
        # default_extra_fields: Annotated[
        #     dict,
        #     Body(title="Extra Fields", description="Extra fields to be added to the default Object.")
        # ] = None,
        ignore_tag: Annotated[
            bool,
            Query(
                title="Ignore Proxbox Tag",
                description="Ignore Proxbox tag filter when searching for objects in Netbox. This will return all Netbox objects, not only Proxbox related ones."
            ),
            Doc(
                "Ignore Proxbox tag filter when searching for objects in Netbox. This will return all Netbox objects, not only Proxbox related ones."
            ),
        ] = False,
        primary_field_value: str = None,
    ):
        self.nb = nb
        self.id = id
        self.all = all
        self.default = default
        self.ignore_tag = ignore_tag
        self.primary_field_value = primary_field_value
        #self.default_extra_fields = default_extra_fields
        
        self.pynetbox_path = getattr(getattr(self.nb.session, self.app), self.endpoint)
        
        # self.default_dict = {
        #     "name": self.default_name,
        #     "slug": self.default_slug,
        #     "description": self.default_description,
        #     "tags": [self.nb.tag.id]
        # }
        
        
    # New Implementantion of "default_dict" and "default_extra_fields".
    async def get_base_dict(self):
        "This method MUST be overwritten by the child class."
        pass
    
    # Default Object Parameters.
    # It should be overwritten by the child class.
    # default_name = None
    # default_slug = None
    # default_description = None
    
    # Parameters to be used as Pynetbox class attributes. 
    # It should be overwritten by the child class.
    app = None
    endpoint = None
    object_name = None
    primary_field = None
        
    async def get(
        self,
        **kwargs
    ):
        self.base_dict = cache.get(self.endpoint)
        if self.base_dict is None:
            self.base_dict = await self.get_base_dict()
            cache.set(self.endpoint, self.base_dict)

            
        # if self.base_dict is None:
        #     await self.get_base_dict()
            
        #base_dict = await self.get_base_dict()
        
        print(kwargs)
        logger.info(f"[GET] Getting '{self.object_name}' from Netbox.")
        
        if self.id: return await self._get_by_id()
        if self.all: return await self._get_all()
        
        if kwargs: return await self._get_by_kwargs(**kwargs)
        

        if self.pynetbox_path.count() == 0:
            
            logger.info(f"[GET] There's no '{self.object_name}' registered on Netbox. Creating a DEFAULT ONE.")
            
            self.default = True
            create_default_object = await self.post()
             
            if create_default_object != None:
                logger.info(f"[GET] Default '{self.object_name}' created successfully. {self.object_name} ID: {create_default_object.id}")
                return create_default_object
                
            else:
                raise ProxboxException(
                    message=f"[GET] Error trying to create default '{self.object_name}' on Netbox.",
                    detail=f"No objects found. Default '{self.object_name}' could not be created."
                )
            
        
                    
        # 2. Check if there's any 'Object' registered on Netbox.
        try:
            
            # 2.2
            # 2.2.1 If there's any 'Object' registered on Netbox, check if is Proxbox one by checking tag and name.
            try:
                logger.info(f"[GET] '{self.object_name}' found on Netbox. Checking if it's 'Proxbox' one...")
                get_object = await asyncio.to_thread(self.pynetbox_path.get,
                    name=self.default_name,
                    slug=self.default_slug,
                    tag=[self.nb.tag.slug]
                )
                
            except ValueError as error:
                logger.warning(f"Mutiple objects by get() returned. Proxbox will use filter(), delete duplicate objects and return only the first one.\n   > {error}")
                get_object = await self._check_duplicate(
                    search_params = {
                        "name": self.default_name,
                        "slug": self.default_slug,
                        "tag": [self.nb.tag.slug],
                    }
                )

            if get_object != None:
                logger.info(f"[GET] The '{self.object_name}' found is from 'Proxbox' (because it has the tag). Returning it.")
                return get_object
            
            # 2.2.2. If it's not Proxbox one, create a default one.
            logger.info(f"[GET] The '{self.object_name}' object found IS NOT from 'Proxbox'. Creating a default one.")
            self.default = True
            default_object = await self.post()
            return default_object
        
        except ProxboxException as error: raise error
            
        except Exception as error:
            raise ProxboxException(
                message=f"Error trying to get '{self.object_name}' from Netbox.",
                python_exception=f"{error}"
            )
    
    async def _get_by_kwargs(self, **kwargs):
        
        logger.info(f"[GET] Searching '{self.object_name}' by kwargs {kwargs}.")
        try:
            try:
                response = await asyncio.to_thread(self.pynetbox_path.get, **kwargs)
                return response
            except Exception as error:
                if "get() returned more than one result." in f"{error}":
                    logger.info(f"[CHECK DUPLICATE] Object '{self.object_name}' with the same name already found. Checking with '.filter' method")
                    
                    if self.endpoint == "interfaces" and self.primary_field == "device":

                        logger.info("[CHECK DUPLICATE] Checking duplicate device using as PRIMARY FIELD the DEVICE.")
                        result_by_primary = await asyncio.to_thread(self.pynetbox_path.get, virtual_machine=self.primary_field_value)

                        if result_by_primary:
                            if result_by_primary.virtual_machine == self.primary_field_value:
                                logger.info("[CHECK DUPLICATE] Interface with the same Device found. Duplicated object, returning it.")
                                return result_by_primary
                    
                        else:
                            logger.info("[CHECK DUPLICATE] If interface equal, but different devices, return as NOT duplicated.")
                            return None

            
        except ProxboxException as error: raise error
        
        except Exception as error:
            raise ProxboxException(
                message=f"[GET] Error trying to get '{self.object_name}' from Netbox using the specified kwargs '{kwargs}'.",
                python_exception=f"{error}"
            )
        
        
        
    
    async def _get_by_id(self):
        """
        If Query Parameter 'id' provided, use it to get the object from Netbox.
        """
        
        logger.info(f"[GET] Searching '{self.object_name}' by ID {self.id}.")
        
        response = None
        
        try:
            if self.ignore_tag:
                response = await asyncio.to_thread(self.pynetbox_path.get, self.id)
            
            else:
                response = await asyncio.to_thread(self.pynetbox_path.get,
                    id=self.id,
                    tag=[self.nb.tag.slug]
                )
             
            # 1.1. Return found object.
            if response != None:
                logger.info(f"[GET] '{self.object_name}' with ID '{self.id}' found on Netbox. Returning it.")
                return response
            
            # 1.2. Raise ProxboxException if object is not found.
            else:
                raise ProxboxException(
                    message=f"[GET]' {self.object_name}' with ID '{self.id}' not found on Netbox.",
                    detail=f"Please check if the ID provided is correct. If it is, please check if the object has the Proxbox tag. (You can use the 'ignore_tag' query parameter to ignore this check and return object without Proxbox tag)"
                )
            
            
        except ProxboxException as error: raise error
        
        except Exception as error:
            raise ProxboxException(
                message=f"[GET] Error trying to get '{self.object_name}' from Netbox using the specified ID '{self.id}'.",
                python_exception=f"{error}"
            )
        
        
        
    
    
    
    
    async def _get_all(self):
        """
        # If Query Parameter 'all' is True, return all Objects registered from Netbox.
        """
        
        if self.ignore_tag:
            try:
                # If ignore_tag is True, return all objects from Netbox.
                return [item for item in await asyncio.to_thread(self.pynetbox_path.all())]
            except Exception as error:
                raise ProxboxException(
                    message=f"Error trying to get all '{self.object_name}' from Netbox.",
                    python_exception=f"{error}"
                )
            
        try:       
            # If ignore_tag is False, return only objects with Proxbox tag.
            return [item for item in asyncio.to_thread(self.pynetbox_path.filter, tag = [self.nb.tag.slug])]
        
        except Exception as error:
            raise ProxboxException(
                message=f"Error trying to get all Proxbox '{self.object_name}' from Netbox.",
                python_exception=f"{error}"
            )
        

        
        
        
              
    async def post(
        self,
        data: dict = None,
    ): 
        self.base_dict = cache.get(self.endpoint)
        if self.base_dict is None:
            self.base_dict = await self.get_base_dict()
            cache.set(self.endpoint, self.base_dict)

        if data:
            logger.info(f"[POST] Creating '{self.object_name}' object on Netbox.")
        
            if isinstance(data, dict) == False:
                try:
                    # Convert Pydantic model to Dict through 'model_dump' Pydantic method.
                    data = data.model_dump(exclude_unset=True)
                except Exception as error:
                    raise ProxboxException(
                        message=f"[POST] Error parsing Pydantic model to Dict.",
                        python_exception=f"{error}",
                    )
                
            # If no explicit slug was provided by the payload, create one based on the name.
            if data.get("slug") == None:
                if not self.primary_field:
                    logger.info("[POST] SLUG field not provided on the payload. Creating one based on the NAME or MODEL field.")
                    try:
                        data["slug"] = data.get("name").replace(" ", "-").lower()
                    except AttributeError:
                        
                        try:
                            data["slug"] = data.get("model").replace(" ", "-").lower()
                        except AttributeError:
                            raise ProxboxException(
                                message=f"[POST] No 'name' or 'model' field provided on the payload. Please provide one of them.",
                            )
                
        if self.default or data == None:
            logger.info(f"[POST] Creating DEFAULT '{self.object_name}' object on Netbox.")
            data = self.base_dict
            
        try:

            """
            Merge base_dict and data dict.
            The fields not specificied on data dict will be filled with the base_dict values.
            """
            data = self.base_dict | data
            
            check_duplicate_result = await self._check_duplicate(object = data)
            
            if check_duplicate_result == None:
                
                # Check if tags field exists on the payload and if true, append the Proxbox tag. If not, create it.
                if data.get("tags") == None:
                    data["tags"] = [self.nb.tag.id]
                else:
                    data["tags"].append(self.nb.tag.id)
                 
                try:
                    logger.info(f"[POST] Trying to create {self.object_name} object on Netbox.")
                    
                    response = await asyncio.to_thread(self.pynetbox_path.create, data)
                    
                    
                except Exception as error:
                    
                    if "['The fields virtual_machine, name must make a unique set.']}" in f"{error}":
                        logger.error(f"Error trying to create 'Virtual Machine Interface' because the same 'virtual_machine' name already exists.\nPayload: {data}")
                        return None
                    
                    if "['Virtual machine name must be unique per cluster.']" in f"{error}":
                        logger.error(f"Error trying to create 'Virtual Machine' because Virtual Machine Name must be unique.\nPayload: {data}")
                        return None
                    
                    else:
                        raise ProxboxException(
                            message=f"[POST] Error trying to create '{self.object_name}' object on Netbox.",
                            python_exception=error
                        )
                
                if response:
                    logger.info(f"[POST] '{self.object_name}' object created successfully. {self.object_name} ID: {response.id}")
                    return response
                
                else:
                    logger.error(f"[POST] '{self.object_name}' object could not be created.")
            else:
                logger.info(f"[POST] '{self.object_name}' object already exists on Netbox. Returning it.")
                return check_duplicate_result
        
        #except ProxboxException as error: raise error
        
        except Exception as error:
            raise ProxboxException(
                message=f"Error trying to create {self.object_name} on Netbox.",
                detail=f"Payload provided: {data}",
                python_exception=f"{error}"
            )
    
        # raise ProxboxException(
        #     message=f"[POST] No data provided to create '{self.object_name}' on Netbox.",
        #     detail=f"Please provide a JSON payload to create the '{self.object_name}' on Netbox or set 'default' to 'True' on Query Parameter to create a default one."
        # )






    async def _check_duplicate(self, search_params: dict = None, object: dict = None):
        
        logger.info(f"[CHECK DUPLICATE] Checking if '{self.object_name}' exists on Netbox before creating it.")
        
        if self.default:
            logger.info("[CHECK DUPLICATE] Checking default object.")
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
                            message=f"[CHECK DUPLICATE] Default '{self.object_name}' with ID '{result.id}' found on Netbox, but without Proxbox tag. Please delete it (or add the tag) and try again.",
                            detail="Netbox does not allow duplicated names and/or slugs."
                        )
                    
                return None
                
                # create = self.pynetbox_path.create(self.default_dict)
                # return create
            
            except ProxboxException as error: raise error
            
            except Exception as error:
                raise ProxboxException(
                    message=f"[POST] Error trying to create default {self.object_name} on Netbox.",
                    python_exception=f"{error}"
                )
                
        if object:
            try:
                if (self.primary_field):
                    logger.info("[CHECK DUPLICATE] (0.5) Checking object using only custom PRIMARY FIELD and Proxbox TAG provided by the class attribute.")
                    print(f"primary field: {self.primary_field} - primary_field_value: {self.primary_field_value}")
                    
                    
                    print(f'self.primary_field = {self.primary_field} / {self.endpoint}')
                    
                    if self.primary_field == "address":
                        logger.info("[CHECK DUPLICATE] Checking duplicate device using as PRIMARY FIELD the ADDRESS.")
                        
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
                            logger.info("[CHECK DUPLICATE] IP Address with the same network found. Returning it.")
                            return result_by_primary
                        
                    if self.primary_field == "virtual_machine" and self.endpoint == "interfaces":
                        logger.info("[CHECK DUPLICATE] Checking duplicate device using as PRIMARY FIELD the DEVICE.")
                        
                        result_by_primary = None
                        
                        try:
                            #
                            # THE ERROR IS HERE.
                            #
                            # GET
                            logger.error("THE ERROR IS HERE.")
                            result_by_primary = await asyncio.to_thread(
                                self.pynetbox_path.get,
                                virtual_machine=self.primary_field_value,
                                name=object.get("name")
                            )
                            logger.error(f"result_by_primary: {result_by_primary}")

                            if result_by_primary:
                                for interface in result_by_primary:
                                    print(f"INTERFACE OBJECT: {interface} | {interface.virtual_machine}")
                                    
                                    print(f"interface.virtual_machine: {interface.virtual_mchine} | primary_field_value: {self.primary_field_value}")
                                    if interface.virtual_machine == self.primary_field_value:
                                        return interface
                                    else:
                                        return None
                        
                        except Exception as error:
                            logger.info(f"[CHECK DUPLICATE] Error trying to get interface using only 'virtual_machine' field as parameter.\n   >{error}")
                            if "get() returned more than one result" in f"{error}":
                                # FILTER
                                logger.info("[CHECK DUPLICATE] Found more than one VM INTERFACE object with the same 'virtual_machine' field. Trying to use '.filter' pynetbox method now.")
                                
                                
                                try:
                                    result_by_primary = await asyncio.to_thread(
                                        self.pynetbox_path.filter,
                                        virtual_machine=self.primary_field_value,
                                        name=object.get("name")
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
                                    raise ProxboxException(
                                        message="Error trying to get 'VM Interface' object using 'virtual_machine' and 'name' fields.",
                                        python_exception=f"{error}"
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
                            logger.info("[CHECK DUPLICATE] If duplicate interface found, check if the devices are the same.")
                            if result_by_primary.device == self.primary_field_value:
                                logger.info("[CHECK DUPLICATE] Interface with the same Device found. Duplicated object, returning it.")
                                return result_by_primary
                            else:
                                logger.info("[CHECK DUPLICATE] If interface equal, but different devices, return as NOT duplicated.")
                                return None
                        
                        logger.info(f"[CHECK_DUPLICATE] Object found on Netbox. Returning it.")
                        print(f'result_by_primary: {result_by_primary}')
                        return result_by_primary
                    
                    return None
                    
                logger.info("[CHECK DUPLICATE] (1) First attempt: Checking object making EXACT MATCH with the Payload provided...")
                result = await asyncio.to_thread(self.pynetbox_path.get, dict(object))
                
                if result:
                    logger.info(f"[CHECK DUPLICATE] Object found on Netbox. Returning it.")
                    return result
                
                else:
                    
                    logger.info("[CHECK DUPLICATE] (1.5) Checking object using NAME and DEVICE provided by the Payload and also the PROXBOX TAG. If found, return it.")
                    
                    result_by_device = None
                    
                    device_id = object.get("device")
                    
                    print(f"object: {object}")
                    device_obj = None
                    try:
                        logger.info("[CHECK DUPLICATE] (1.5.1) Checking duplicate using Device Object as parameter.")
                        device_obj = self.nb.session.dcim.devices.get(int(device_id))
                        print(f"device_obj: {device_obj}")
                        
                        print(f"device_obj.name: {device_obj.name}")
                        
                        print(f'object.get("name"): {object.get("name")}')
                        
                        print(f"device_obj.id: {device_obj.id}")
                        
                        result_by_device = await asyncio.to_thread(self.pynetbox_path.get,
                            name=object.get("name"),
                            tag=[self.nb.tag.slug]
                        )
                        
                        
                    
                    except:
                        logger.info("[CHECK DUPLICATE] (1.5.1) Device Object NOT found when checking for duplicated using Device as parameter.")
                    
                    
                    if result_by_device:
                        
                        if result_by_device.device:
                            print(f"result_by_device: {result_by_device.device}")
                            print(f"result_by_device.device.id: {result_by_device.device.id}")
                            print(f"object: {object} \n{object.get("device")}")
                            print(f"object.device: {object.get("device")}")
                            
                        print(f"result_by_device - object device: {result_by_device} / {result_by_device.device} / {result_by_device.device.id}")
                        # If this happens, it means that the interface name is equal, but device is different.
                        print(f"int(object.id): {int(object.get("device"))} | int(result_by_device.device.id): {int(result_by_device.device.id)}")
                        if int(object.get("device")) != int(result_by_device.device.id):
                            return None
                        
                        logger.info("[CHECK DUPLICATE] (1.5.1) Object found on Netbox. Returning it.")
                        return result_by_device
 
                        
                    logger.info("[CHECK DUPLICATE] (2) Checking object using only NAME and SLUG provided by the Payload and also the PROXBOX TAG. If found, return it.")
                    
                    
                    result_by_tag = None
                    try:
                        logger.info("[CHECK DUPLICATE] (2.1) Searching object using 'get' method")
                        result_by_tag = await asyncio.to_thread(self.pynetbox_path.get,
                            name=object.get("name"),
                            slug=object.get("slug"),
                            tag=[self.nb.tag.slug]
                        )
                        print(result_by_tag)
                    
                    except Exception as error:
                        
                        try:
                            result_by_tag = await asyncio.to_thread(self.pynetbox_path.filter,
                                name=object.get("name"),
                                slug=object.get("slug"),
                                tag=[self.nb.tag.slug]
                            )
                            
                            if result_by_tag:
                                logger.info("[CHECK DUPLICATE] (2) More than one object found.")
                                
                                for obj in result_by_tag:
                                    print(f"obj.id: {obj.device.id} / device_obj.id: {device_obj.id}")
                                    
                                    if int(obj.device.id) == int(device_obj.id):
                                        logger.info("[CHECK DUPLICATE] (2) More than one object found, but returning with the same ID.")
                                        return obj
                                return None
                            print(f"filter: {result_by_tag}")
                        except Exception as error:
                            logger.error(error)
                            

                        
                    if result_by_tag:
                        logger.info(f"[CHECK DUPLICATE] Object found on Netbox. Returning it.")
                        return result_by_tag
                        
                    
                    logger.info(f"[CHECK DUPLICATE] (3) Checking duplicate object using only NAME and SLUG")
                    result_by_name_and_slug = await asyncio.to_thread(self.pynetbox_path.get,
                        name=object.get("name"),
                        slug=object.get("slug"),
                    )
                    
                    if result_by_name_and_slug:
                        raise ProxboxException(
                            message=f"[CHECK DUPLICATE] '{self.object_name}' with ID '{result_by_name_and_slug.id}' found on Netbox, but without Proxbox tag. Please delete it (or add the tag) and try again.",
                            detail="Netbox does not allow duplicated names and/or slugs."
                        )

                return None
                
            except ProxboxException as error: raise error
                
            #except Exception as error:
            #    raise ProxboxException(
            #        message=f"[CHECK DUPLICATE] Error trying to create {self.object_name} on Netbox.",
            #        detail=f"Payload provided: {object}",
            #        python_exception=f"{error}"
            #    )

        return None
        # name = search_params.get("name")
        # slug = search_params.get("slug")
        
        # logger.info(f"Checking if {name} exists on Netbox.")
        # """
        # Check if object exists on Netbox based on the dict provided.
        # The fields used to distinguish duplicates are:
        # - name
        # - slug
        # - tags
        # """
        
        # try:
        #     print(f"search_params: {search_params}")
        #     # Check if default object exists.
        #     search_result = self.pynetbox_path.get(name = name, slug = slug)
            
        #     print(f"[get] search_result: {search_result}")
            
        #     if search_result:
        #         return search_result
        
        # except ValueError as error:
        #     logger.warning(f"Mutiple objects by get() returned. Proxbox will use filter(), delete duplicate objects and return only the first one.\n   > {error}")
        #     try:

        #         search_result = self.pynetbox_path.filter(name = name, slug = slug)
                
        #         # Create list of all objects returned by filter.
        #         delete_list = [item for item in search_result]
                
        #         # Removes the first object from the list to return it.
        #         single_default = delete_list.pop(0)
                
        #         # Delete all other objects from the list.
        #         self.pynetbox_path.delete(delete_list)

        #         # Returns first element of the list.
        #         print(f"[get] search_result: {search_result}")
        #         return single_default
            
        #     except ProxboxException as error: raise error
            
        #     except Exception as error:
        #         raise ProxboxException(
                    
        #             message=f"Error trying to create default {self.object_name} on Netbox.",
        #             python_exception=f"{error}",
        #             detail=f"Multiple objects returned by filter. Please delete all objects with name '{self.default_dict.get('name')}' and slug '{self.default_dict.get('slug')}' and try again."
        #         )
        
        # return None