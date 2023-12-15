from fastapi import Query, Body

from typing import Annotated
from typing_extensions import Doc

from netbox_proxbox.backend.session.netbox import NetboxSessionDep
from netbox_proxbox.backend.exception import ProxboxException

from netbox_proxbox.backend.logging import logger

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
        default_extra_fields: Annotated[
            dict,
            Body(title="Extra Fields", description="Extra fields to be added to the default Object.")
        ] = None,
        ignore_tag: Annotated[
            bool,
            Query(
                title="Ignore Proxbox Tag",
                description="Ignore Proxbox tag filter when searching for objects in Netbox. This will return all Netbox objects, not only Proxbox related ones."
            ),
            Doc(
                "Ignore Proxbox tag filter when searching for objects in Netbox. This will return all Netbox objects, not only Proxbox related ones."
            )
        
        ] = False,
    ):
        self.nb = nb
        self.id = id
        self.all = all
        self.default = default
        self.ignore_tag = ignore_tag
        self.default_extra_fields = default_extra_fields
        
        self.pynetbox_path = getattr(getattr(self.nb.session, self.app), self.endpoint)
        
        self.default_dict = {
            "name": self.default_name,
            "slug": self.default_slug,
            "description": self.default_description,
            "tags": [self.nb.tag.id]
        }
        
        
    # New Implementantion of "default_dict" amd "default_extra_fields".
    base_dict = None
    
    # Default Object Parameters.
    # It should be overwritten by the child class.
    default_name = None
    default_slug = None
    default_description = None
    
    # Parameters to be used as Pynetbox class attributes. 
    # It should be overwritten by the child class.
    app = None
    endpoint = None
    object_name = None
    
        
    async def get(
        self,
        **kwargs
    ):
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
                get_object = self.pynetbox_path.get(
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
            response = self.pynetbox_path.get(**kwargs)
            return response
            
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
                response = self.pynetbox_path.get(self.id)
            
            else:
                response = self.pynetbox_path.get(
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
                return [item for item in self.pynetbox_path.all()]
            except Exception as error:
                raise ProxboxException(
                    message=f"Error trying to get all '{self.object_name}' from Netbox.",
                    python_exception=f"{error}"
                )
            
        try:       
            # If ignore_tag is False, return only objects with Proxbox tag.
            return [item for item in self.pynetbox_path.filter(tag = [self.nb.tag.slug])]
        
        except Exception as error:
            raise ProxboxException(
                message=f"Error trying to get all Proxbox '{self.object_name}' from Netbox.",
                python_exception=f"{error}"
            )
        

        
        
        
              
    async def post(
        self,
        data = None,
    ): 
        if self.default:
 
            logger.info(f"[POST] Creating DEFAULT '{self.object_name}' object on Netbox.")
            try:
                
                # If default object doesn't exist, create it.
                check_duplicate_result = await self._check_duplicate()
                if check_duplicate_result == None:
                    
                    # Create default object
                    response = self.pynetbox_path.create(self.default_dict)
                    return response
                
                # If duplicate object found, return it.
                else:
                    return check_duplicate_result
                
                    
            except ProxboxException as error: raise error
            
            except Exception as error:
                raise ProxboxException(
                    message=f"[POST] Error trying to create DEFAULT '{self.object_name}' on Netbox.",
                    python_exception=f"{error}"
                )
        
        if data:
            try:
                logger.info(f"[POST] Creating '{self.object_name}' object on Netbox.")
                
                if isinstance(data, dict) == False:
                    # Convert Pydantic model to Dict through 'model_dump' Pydantic method.
                    data = data.model_dump(exclude_unset=True)
                
                if self.base_dict:
                
                    # Merge base_dict and data dict.
                    data = self.base_dict | data
                
                check_duplicate_result = await self._check_duplicate(object = data)
                
                if check_duplicate_result == None:
                    
                    # Check if tags field exists on the payload and if true, append the Proxbox tag. If not, create it.
                    if data.get("tags") == None:
                        data["tags"] = [self.nb.tag.id]
                    else:
                        data["tags"].append(self.nb.tag.id)
                        
                    response = self.pynetbox_path.create(data)
                    
                    if response:
                        logger.info(f"[POST] '{self.object_name}' object created successfully. {self.object_name} ID: {response.id}")
                        return response
                    
                    else:
                        logger.error(f"[POST] '{self.object_name}' object could not be created.")
                else:
                    logger.info(f"[POST] '{self.object_name}' object already exists on Netbox. Returning it.")
                    return check_duplicate_result
            
            except ProxboxException as error: raise error
            
            except Exception as error:
                raise ProxboxException(
                    message=f"Error trying to create {self.object_name} on Netbox.",
                    detail=f"Payload provided: {data}",
                    python_exception=f"{error}"
                )
        
        raise ProxboxException(
            message=f"[POST] No data provided to create '{self.object_name}' on Netbox.",
            detail=f"Please provide a JSON payload to create the '{self.object_name}' on Netbox or set 'default' to 'Trsue' on Query Parameter to create a default one."
        )






    async def _check_duplicate(self, search_params: dict = None, object: dict = None):
        
        logger.info(f"[CHECK DUPLICATE] Checking if '{self.object_name}' exists on Netbox before creating it.")
        
        if self.default:
            logger.info("[CHECK DUPLICATE] Checking default object.")
            try:
                result = self.pynetbox_path.get(
                    name=self.default_name,
                    slug=self.default_slug,
                    tag=[self.nb.tag.slug]
                )
                
                
                if result:
                    return result
                
                else:
                    # If no object found searching using tag, try to find without it, using just name and slug.
                    result = self.pynetbox_path.get(
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
                logger.info("[CHECK DUPLICATE] (1) First attempt: Checking object making EXACT MATCH with the Payload provided...")
                result = self.pynetbox_path.get(object)
                
                if result:
                    logger.info(f"[CHECK DUPLICATE] Object found on Netbox. Returning it.")
                    return result
                
                else:
                    logger.info("[CHECK DUPLICATE] (2) Checking object using only NAME and SLUG provided by the Payload and also the PROXBOX TAG). If found, return it.")
                    result_by_tag = self.pynetbox_path.get(
                        name=object.get("name"),
                        slug=object.get("slug"),
                        tag=[self.nb.tag.slug]
                    )
                    
                    if result_by_tag:
                        logger.info(f"[CHECK DUPLICATE] Object found on Netbox. Returning it.")
                        return result_by_tag
                    
                    else:
                        result_by_name_and_slug = self.pynetbox_path.get(
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
                
            except Exception as error:
                raise ProxboxException(
                    message=f"[CHECK DUPLICATE] Error trying to create {self.object_name} on Netbox.",
                    detail=f"Payload provided: {object}",
                    python_exception=f"{error}"
                )

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