from fastapi import Query, Body

from typing import Annotated

from netbox_proxbox.backend.session.netbox import NetboxSessionDep
from netbox_proxbox.backend.exception import ProxboxException

class NetboxBase:
    """
    Class to handle Netbox 'Objects'.
    
    Logic: 
        1. it will use 'id' to get the 'Objects' from Netbox if provided.
            1.1. if object is returned, it will return it.
            1.2. if object is not returned, it will raise an `ProxboxException`.
        2. if 'site_id' is not provided, it will check if there's any Site registered on Netbox.
            2.1. if there's no 'Objects' registered on Netbox, it will create a default one.
            2.2. if there's any 'Objects' registered on Netbox, it will check if is Proxbox one by checking tag and name.
                2.2.1. if it's Proxbox one, it will return it.
                2.2.2. if it's not Proxbox one, it will create a default one.
        3. if 'all' is True, it will return all 'Objects' registered on Netbox.
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
    ):
        self.nb = nb
        self.id = id
        self.all = all
        self.default = default
        self.default_extra_fields = default_extra_fields
        
        self.pynetbox_path = getattr(getattr(self.nb.session, self.app), self.endpoint)
        self.default_dict = {
            "name": self.default_name,
            "slug": self.default_slug,
            "description": self.default_description,
            "tags": [self.nb.tag.id]
        }
    
    # Default Cluster Type Params
    default_name = None
    default_slug = None
    default_description = None
    
    # Parameters to be used as Pynetbox class attributes
    app = None
    endpoint = None
    object_name = None
    
    
    async def get(
        self,
    ):
        # 1. If 'id' provided, use it to get the Cluster Type from Netbox using it.
        if self.id:
            response = None
            
            try:
                response = self.pynetbox_path.get(self.id)
            
            except Exception as error:
                raise ProxboxException(
                    message=f"Error trying to get {self.object_name} from Netbox using the specified ID '{self.id}'.",
                    error=f"{error}"
                )
            
            # 1.1. Return found object.
            if response != None:
                return response
            
            # 1.2. Raise ProxboxException if object is not found.
            else:
                raise ProxboxException(
                    message=f"{self.object_name} with ID '{self.id}' not found on Netbox."
                )
        
        # 2. Check if there's any Cluster Type registered on Netbox.
        else:
            try:
                
                # 2.1. If there's no Cluster Type registered on Netbox, create a default one.
                if self.pynetbox_path.count() == 0:
                    print("2.1. If there's no Cluster Type registered on Netbox, create a default one.")
                    default_cluster_type_obj = await self.post()
                    
                    return default_cluster_type_obj
                
                else:
                    # 3. If Query param 'all' is True, return all Cluster Types registered.
                    if self.all:
                        response_list = []
                        
                        for cluster_type in response:
                            response_list.append(cluster_type)
                        
                        return response_list
                    
                    # 2.2
                    # 2.2.1 If there's any Cluster Type registered on Netbox, check if is Proxbox one by checking tag and name.
                    get_proxbox_cluster_type = self.pynetbox_path.get(
                        name=self.default_name,
                        slug=self.default_slug,
                        tags=[self.nb.tag.id]
                    )

                    if get_proxbox_cluster_type != None:
                        return get_proxbox_cluster_type
                    
                    # 2.2.2. If it's not Proxbox one, create a default one.
                    print("2.2.2. If it's not Proxbox one, create a default one.")
                    default_cluster_type_obj = await self.post()
                    return default_cluster_type_obj
                
            except Exception as error:
                raise ProxboxException(
                    message=f"Error trying to get '{self.object_name}' from Netbox.",
                    python_exception=f"{error}"
                )
                
    async def post(
        self,
        data = None,
    ):
        if self.default:
            try:
                # try:
                #     # Check if default object exists.
                #     check_duplicate = self.pynetbox_path.get(
                #         name = self.default_dict.get("name"),
                #         slug = self.default_dict.get("slug"),
                #         tags = [self.nb.tag.id]
                #     )
                    
                #     if check_duplicate:
                #         return check_duplicate
                
                # except ValueError as error:
                #     print(f"Mutiple objects returned.\n   > {error}")
                #     try:
                #         check_duplicate = self.pynetbox_path.filter(
                #             name = self.default_dict.get("name"),
                #             slug = self.default_dict.get("slug"),
                #             tags = [self.nb.tag.id]
                #         )
                        
                #         # Create list of all objects returned by filter.
                #         delete_list = [item for item in check_duplicate]
                        
                #         # Removes the first object from the list to return it.
                #         single_default = delete_list.pop(0)
                        
                #         # Delete all other objects from the list.
                #         self.pynetbox_path.delete(delete_list)

                #         return single_default
                    
                #     except Exception as error:
                #         raise ProxboxException(
                #             message=f"Error trying to create default {self.object_name} on Netbox.",
                #             python_exception=f"{error}",
                #             detail=f"Multiple objects returned by filter. Please delete all objects with name '{self.default_dict.get('name')}' and slug '{self.default_dict.get('slug')}' and try again."
                #         )
                
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

    async def _check_duplicate(self, object: dict):
        """
        Check if object exists on Netbox based on the dict provided.
        The fields used to distinguish duplicates are:
        - name
        - slug
        - tags
        """
        
        self.search_params = {
            "name": object.get("name"),
            "slug": object.get("slug"),
            #"tags": [self.nb.tag.id]
        }
        
        try:
            print(f"search_params: {self.search_params}")
            # Check if default object exists.
            search_result = self.pynetbox_path.get(self.search_params)
            
            print(f"[get] search_result: {search_result}")
            
            if search_result:
                return search_result
        
        except ValueError as error:
            print(f"Mutiple objects returned.\n   > {error}")
            try:

                search_result = self.pynetbox_path.filter(self.search_params)
                
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