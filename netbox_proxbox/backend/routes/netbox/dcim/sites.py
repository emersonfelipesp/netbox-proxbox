from fastapi import Query

from typing import Annotated

from netbox_proxbox.backend.session.netbox import NetboxSessionDep
from netbox_proxbox.backend.exception import ProxboxException

from netbox_proxbox.backend.schemas.netbox.dcim import SitesSchema

class Sites:
    """
    Class to handle Netbox Sites.
    
    Logic: 
        1. it will use 'id' to get the Site from Netbox if provided.
            1.1. if object is returned, it will return it.
            1.2. if object is not returned, it will raise an `ProxboxException`.
        2. if 'id' is not provided, it will check if there's any Site registered on Netbox.
            2.1. if there's no `Site` registered on Netbox, it will create a default one.
            2.2. if there's any `Site` registered on Netbox, it will check if is Proxbox one by checking tag and name.
                2.2.1. if it's Proxbox one, it will return it.
                2.2.2. if it's not Proxbox one, it will create a default one.
        3. if 'all' is True, it will return all `Sites` registered on Netbox.
    """
    
    def __init__(
        self,
        nb: NetboxSessionDep,
        id: Annotated[
            int,
            Query(
                title="Site ID", description="Netbox Site ID of Nodes and/or Clusters.")
        ] = None,
        all: Annotated[
            bool,
            Query(title="List All Sites", description="List all Sites registered on Netbox.")
        ] = False

    ):
        self.nb = nb
        self.id = id
        self.default_name = "Proxbox Basic Site"
        self.default_slug = "proxbox-basic-site"
        self.default_description = "Proxbox Basic Site (used to identify the items the plugin created)"
        self.all = all
        
    async def get(self):
        # 1. If 'id' provided, use it to get the Site from Netbox using it.
        if self.id:
            response = None
            try: 
                response = self.nb.session.dcim.sites.get(self.id)
      
            except Exception as error:
                raise ProxboxException(
                    message=f"Error trying to get Site from Netbox using the specified ID '{self.id}'.",
                    python_exception=f"{error}"
                )
            
            # 1.1. Return found object.
            if response != None:
                return response
            
            # 1.2. Raise ProxboxException if object is not found.
            else:
                raise ProxboxException(
                    message=f"Site with ID '{self.id}' not found on Netbox.",
                )
                
        # 2. Check if there's any Site registered on Netbox.
        else:
            try:
                response = self.nb.session.dcim.sites.all()
                
                # 2.1. If there's no Site registered on Netbox, create a default one.
                if len(response) == 0:
                    default_site_obj = await self.post(default=True)
                    
                    return default_site_obj

                else:
                    # 3. If Query param 'all' is True, return all Sites registered on Netbox.
                    if self.all:
                        response_list = []
                        
                        for site in response:
                            response_list.append(site)
                            
                        return response_list
                
                    # 2.2
                    # 2.2.1. If there's any 'Site' registered on Netbox, check if is Proxbox one by checking tag and name.
                    get_proxbox_site = self.nb.session.dcim.sites.get(
                        name=self.default_name,
                        slug=self.default_slug,
                        tags=[self.nb.tag.id]
                    )
                    
                    if get_proxbox_site != None:
                        return get_proxbox_site

                    # 2.2.2. If it's not Proxbox one, create a default one.
                    default_site_obj = await self.post(default=True)
                    return default_site_obj

            except Exception as error:
                raise ProxboxException(
                    message="Error trying to get 'Sites' from Netbox.",
                    python_exception=f"{error}"
                )
    
    async def post(self, default: bool = False, data: SitesSchema = None):
        if default:
            try: 
                response = self.nb.session.dcim.sites.create(
                    name = self.default_name,
                    slug = self.default_slug,
                    description = self.default_description,
                    status = 'active',
                    tags = [self.nb.tag.id]
                )
                return response
            
            except Exception as error:
                raise ProxboxException(
                    message=f"Error trying to create the default Proxbox Site on Netbox.",
                    python_exception=f"{error}"
                )

        if data:
            try: 
                data_dict = data.model_dump(exclude_unset=True)
        
                print(data_dict)
                response = self.nb.session.dcim.sites.create(data_dict)
                return response

            except Exception as error:
                raise ProxboxException(
                    message=f"Error trying to create the Proxbox Site on Netbox.",
                    detail=f"Payload provided: {data_dict}",
                    python_exception=f"{error}"
                )
    
    async def put(self):
        pass