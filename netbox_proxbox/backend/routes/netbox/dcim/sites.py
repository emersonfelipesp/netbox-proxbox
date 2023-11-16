from fastapi import Query

from typing import Annotated

from netbox_proxbox.backend.session.netbox import NetboxSessionDep
from netbox_proxbox.backend.exception import ProxboxException

class Sites:
    """
    Class to handle Netbox Sites.
    
    Logic: 
        1. it will use 'site_id' to get the Site from Netbox if provided.
            1.1. if object is returned, it will return it.
            1.2. if object is not returned, it will raise an ProxboxException.
        2. if 'site_id' is not provided, it will check if there's any Site registered on Netbox.
            2.1. if there's no Site registered on Netbox, it will create a default one.
            2.2. if there's any Site registered on Netbox, it will check if is Proxbox one by checking tag and name.
                2.2.1. if it's Proxbox one, it will return it.
                2.2.2. if it's not Proxbox one, it will create a default one.
    """
    
    def __init__(
        self,
        nb: NetboxSessionDep,
        site_id: Annotated[
            int,
            Query(
                title="Site ID",
                description="Netbox Site ID of Nodes and/or Clusters.")
        ] = None
    ):
        self.nb = nb
        self.site_id = site_id
        self.default_name = "Proxbox Basic Site"
        self.default_slug = "proxbox-basic-site"
        self.default_description = "Proxbox Basic Site (used to identify the items the plugin created)"
        
        
    async def get(self):
        # 1. If 'site_id' provided, use it to get the Site from Netbox.
        if self.site_id:
            response = None
            try: 
                response = self.nb.session.dcim.sites.get(self.site_id)
      
            except Exception as error:
                raise ProxboxException(
                    message=f"Error trying to get Site from Netbox using the specified ID '{self.site_id}''.",
                    python_exception=f"{error}"
                )
            
            # 1.1. Return found object.
            if response != None:
                return response
            
            # 1.2. Raise ProxboxException if object is not found.
            else:
                raise ProxboxException(
                    message=f"Site with ID '{self.site_id}' not found on Netbox.",
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
                    # 2.2. If there's any Site registered on Netbox, check if is Proxbox one by checking tag and name.
                    for site in response:
                        # 2.2.1. If it's Proxbox one, return it.
                        if site.tags == [self.nb.tag.id] and site.name == self.default_name and site.slug == self.default_slug:
                            return site
                    
                    # 2.2.2. If it's not Proxbox one, create a default one.
                    default_site_obj = await self.post(default=True)
                    
                    return default_site_obj


            except Exception as error:
                raise ProxboxException(
                    message="Error trying to get Sites from Netbox.",
                    python_exception=f"{error}"
                )
    
    async def post(self, default: bool = False):
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

    async def put(self):
        pass