from fastapi import Query, WebSocket

from typing import Annotated
from typing_extensions import Doc

from netbox_proxbox.backend.session.netbox import NetboxSessionDep
from netbox_proxbox.backend.exception import ProxboxException

from netbox_proxbox.backend.logging import log

from netbox_proxbox.backend.cache import cache

from netbox_proxbox.backend.routes.netbox.generic.check_duplicate import _check_duplicate
from netbox_proxbox.backend.routes.netbox.generic.get import (
    _get_by_id,
    _get_all,
    _get_by_kwargs,
)
from netbox_proxbox.backend.routes.netbox.generic.post import _post

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
        websocket: WebSocket = None,
    ):
        
        self.nb = nb
        self.websocket = websocket
        self.id = id
        self.all = all
        self.default = default
        self.ignore_tag = ignore_tag
        self.primary_field_value = primary_field_value
        self.pynetbox_path = getattr(getattr(self.nb.session, self.app), self.endpoint)

        
    # New Implementantion of "default_dict" and "default_extra_fields".
    async def get_base_dict(self):
        "This method MUST be overwritten by the child class."
        pass
    
    # Parameters to be used as Pynetbox class attributes. 
    # It should be overwritten by the child class.
    app: str = ""
    endpoint: str = ""
    object_name: str = ""
    primary_field: str = ""
    

    async def get(
        self,
        **kwargs
    )
        self.base_dict = cache.get(self.endpoint)
        if self.base_dict is None:
            self.base_dict = await self.get_base_dict()
            cache.set(self.endpoint, self.base_dict)
    
        if self.id:
            return await _get_by_id(
                websocket=self.websocket,
                nb=self.nb,
                pynetbox_path=self.pynetbox_path,
                ignore_tag=self.ignore_tag,
                object_name=self.object_name,
                id=self.id
            )
        
        if kwargs:
            return await _get_by_kwargs(
                weboscket=self.websocket,
                pynetbox_path=self.pynetbox_path,
                endpoint=self.endpoint,
                primary_field=self.primary_field,
                primary_field_value=self.primary_field_value,
                object_name=self.object_name,
                **kwargs
            )
            
        if self.all:
            return await _get_all(
                websocket=self.websocket,
                nb=self.nb,
                pynetbox_path=self.pynetbox_path,
                ignore_tag=self.ignore_tag,
                object_name=self.object_name,
            )
        
    post = _post
    _check_duplicate = _check_duplicate
    

    
    