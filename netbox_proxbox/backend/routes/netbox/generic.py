from fastapi import Query, Body

from typing import Annotated
from typing_extensions import Doc

from netbox_proxbox.backend.session.netbox import NetboxSessionDep
from netbox_proxbox.backend.exception import ProxboxException

from netbox_proxbox import logger

class NetboxBase:
    """
    ## Class to handle Netbox Objects.
    
    Warning: Deprecated
        Stop using this class
    
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
            Query(title="Create Default Object", description="Create a default Object if there's no Object registered on Netbox.")
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
        print("Inside NetboxBase.__init__")
        print(f"hasHandlers: {logger.hasHandlers()}")
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
    ):
        if self.id: return await self._get_by_id()
        if self.all: return await self._get_all()
        
        
        
        
        # 2.1. If there's no Object registered on Netbox, create a default one.
        if self.pynetbox_path.count() == 0:
            print(f"2.1. If there's no {self.object_name} registered on Netbox, create a default one.")
                
            create_default_object = await self.post()
                
            if create_default_object != None:
                logger.info(f"No objects found. Default '{self.object_name}' created successfully. {self.object_name} ID: {create_default_object.id}")
                return create_default_object
                
            else:
                print('teste')
                logger.info("teste")
                raise ProxboxException(
                    message=f"Error trying to create default {self.object_name} on Netbox.",
                    detail=f"No objects found. Default '{self.object_name}' could not be created."
                )
            
        
                    

        
        

        
        
        # 2. Check if there's any 'Object' registered on Netbox.
        try:
            
            # 2.2
            # 2.2.1 If there's any Cluster Type registered on Netbox, check if is Proxbox one by checking tag and name.
            try:
                get_object = self.pynetbox_path.get(
                    name=self.default_name,
                    slug=self.default_slug,
                    tags=[self.nb.tag.id]
                )
            except ValueError as error:
                get_object = await self._check_duplicate(
                    search_params = {
                        "name": self.default_name,
                        "slug": self.default_slug,
                        "tags": [self.nb.tag.id],
                    }
                )

            if get_object != None:
                return get_object
            
            # 2.2.2. If it's not Proxbox one, create a default one.
            print("2.2.2. If it's not Proxbox one, create a default one.")
            default_object = await self.post()
            return default_object
            
        except Exception as error:
            raise ProxboxException(
                message=f"Error trying to get '{self.object_name}' from Netbox.",
                python_exception=f"{error}"
            )
    
    
    
    async def _get_by_id(self):
        """
        If Query Parameter 'id' provided, use it to get the object from Netbox.
        """
        logger.info(f"Searching {self.object_name} by ID {self.id}.")
        
        if self.id:
            logger.info(f"Searching object by ID {self.id}.")
            response = None
            
            try:
                response = self.pynetbox_path.get(self.id)
            
            except Exception as error:
                raise ProxboxException(
                    message=f"Error trying to get '{self.object_name}' from Netbox using the specified ID '{self.id}'.",
                    error=f"{error}"
                )
            
            # 1.1. Return found object.
            if response != None:
                logger.info(f"{self.object_name} with ID '{self.id}' found on Netbox.")
                return response
            
            # 1.2. Raise ProxboxException if object is not found.
            else:
                raise ProxboxException(
                    message=f"{self.object_name} with ID '{self.id}' not found on Netbox."
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
            try:
                
                # If default object doesn't exist, create it.
                check_duplicate_result = await self._check_duplicate(object = self.default_dict)
                if check_duplicate_result == None:
                    
                    # Create default object
                    response = self.pynetbox_path.create(self.default_dict)
                    return response
                
                # If duplicate object found, return it.
                else:
                    return check_duplicate_result
                
                    
                
            except Exception as error:
                raise ProxboxException(
                    message=f"Error trying to create default {self.object_name} on Netbox.",
                    python_exception=f"{error}"
                )
        
        if data:
            print(data)
            try:
                # Parse Pydantic model to Dict
                data_dict = data.model_dump(exclude_unset=True)
                
                check_duplicate_result = await self._check_duplicate(object = data_dict)
                print(f"\n\ncheck_duplicate_result: {check_duplicate_result}\n\n")
                if check_duplicate_result == None:
                    response = self.pynetbox_path.create(data_dict)
                    return response
                else:
                    return check_duplicate_result
            
            except Exception as error:
                raise ProxboxException(
                    message=f"Error trying to create {self.object_name} on Netbox.",
                    detail=f"Payload provided: {data_dict}",
                    python_exception=f"{error}"
                )

    async def _check_duplicate(self, search_params: dict = None):
        name = search_params.get("name")
        slug = search_params.get("slug")
        
        logger.info(f"Checking if {name} exists on Netbox.")
        """
        Check if object exists on Netbox based on the dict provided.
        The fields used to distinguish duplicates are:
        - name
        - slug
        - tags
        """
        
        try:
            print(f"search_params: {search_params}")
            # Check if default object exists.
            search_result = self.pynetbox_path.get(name = name, slug = slug)
            
            print(f"[get] search_result: {search_result}")
            
            if search_result:
                return search_result
        
        except ValueError as error:
            logger.warning(f"Mutiple objects by get() returned. Proxbox will use filter(), delete duplicate objects and return only the first one.\n   > {error}")
            try:

                search_result = self.pynetbox_path.filter(name = name, slug = slug)
                
                # Create list of all objects returned by filter.
                delete_list = [item for item in search_result]
                
                # Removes the first object from the list to return it.
                single_default = delete_list.pop(0)
                
                # Delete all other objects from the list.
                self.pynetbox_path.delete(delete_list)

                # Returns first element of the list.
                print(f"[get] search_result: {search_result}")
                return single_default
            
            except Exception as error:
                raise ProxboxException(
                    
                    message=f"Error trying to create default {self.object_name} on Netbox.",
                    python_exception=f"{error}",
                    detail=f"Multiple objects returned by filter. Please delete all objects with name '{self.default_dict.get('name')}' and slug '{self.default_dict.get('slug')}' and try again."
                )
        
        return None