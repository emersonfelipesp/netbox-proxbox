import requests

from typing import Annotated, Any
from fastapi import Depends

from proxbox_api.routes.proxbox import netbox_settings
from proxbox_api.schemas.netbox import NetboxSessionSchema
from proxbox_api.exception import ProxboxException

from pynetbox_api.database import SessionDep, NetBoxEndpoint


# Netbox
import pynetbox

try:
    from netbox.settings import BASE_PATH
    DEFAULT_BASE_PATH = '/' + BASE_PATH
except ImportError:
    DEFAULT_BASE_PATH = ''

async def netbox_settings(session: SessionDep) -> NetboxSessionSchema:
    """
    Get NetBox settings.

    **Returns:**
    - **`NetboxSessionSchema`**
    """
    
    try:
        # Return the first NetBoxEndpoint from the database.
        netbox: list = session.exec(select(NetBoxEndpoint).limit(1)).all()
        for nb in netbox:
            return NetboxSessionSchema(
                domain = nb.ip_address,
                http_port = nb.port,
                token = nb.token
            )
            
    except Exception as e:
        raise ProxboxException(
            message = "Error trying to get Netbox settings from database.",
            python_exception = f"{str(e)}"
        )
    
    return None

NetboxConfigDep = Annotated[NetboxSessionSchema, Depends(netbox_settings)] 


#
# NETBOX SESSION 
#
# TODO: CREATES SSL VERIFICATION - Issue #32
'''
This is the old NetboxSession class.
It is not used anymore.
It is kept here for reference.

The new NetboxSession class is in the pynetbox-api/pynetbox_api/session.py file on pynetbox-api project/package.


class NetboxSession:
    def __init__(self, netbox_settings):
        self.domain = netbox_settings.domain
        self.http_port = netbox_settings.http_port
        self.token = netbox_settings.token
        self.settings = netbox_settings.settings
        self.session = self.pynetbox_session()
        self.tag = self.proxbox_tag()
        
        
    def pynetbox_session(self):
        print("🔃 Establishing Netbox connection...")
        
        netbox_session = None
        try:
            # CHANGE SSL VERIFICATION TO FALSE
            # Default certificate is self signed. Future versions will use a valid certificate and enable verify (or make it optional)
            session = requests.Session()
            session.verify = False
            
            # Default Netbox URL
            netbox_url: str = f'https://{self.domain}:{self.http_port}{DEFAULT_BASE_PATH}'
            
            # If port is 8000, use HTTP (insecure).
            # This hardcoded exception maybe changed to a dynamic identification of the protocol in the future.
            if int(self.http_port) == 8000:
                netbox_url = f'http://{self.domain}:{self.http_port}{DEFAULT_BASE_PATH}'
                
            netbox_session = pynetbox.api(
                    netbox_url,
                    token=self.token,
                    threading=True,
            )
            # DISABLES SSL VERIFICATION
            netbox_session.http_session = session
            
            
            if netbox_session is not None:
                print("✅ Netbox connection established.")
                return netbox_session
        
        except Exception as error:
            raise RuntimeError(f"Error trying to initialize Netbox Session using TOKEN {self.token} provided.\nPython Error: {error}")
        
        if netbox_session is None:
            raise RuntimeError(f"Error trying to initialize Netbox Session using TOKEN and HOST provided.")
        
    def proxbox_tag(self):
            proxbox_tag_name = 'Proxbox'
            proxbox_tag_slug = 'proxbox'

            proxbox_tag = None

            try:
                # Check if Proxbox tag already exists.
                proxbox_tag = self.session.extras.tags.get(
                    name = proxbox_tag_name,
                    slug = proxbox_tag_slug
                )
            except Exception as error:
                raise ProxboxException(
                    message = f"Error trying to get the '{proxbox_tag_name}' tag. Possible errors: the name '{proxbox_tag_name}' or slug '{proxbox_tag_slug}' is not found.",
                    python_exception=f"{error}"
                )

            if proxbox_tag is None:
                try:
                    # If Proxbox tag does not exist, create one.
                    tag = self.session.extras.tags.create(
                        name = proxbox_tag_name,
                        slug = proxbox_tag_slug,
                        color = 'ff5722',
                        description = "Proxbox Identifier (used to identify the items the plugin created)"
                    )
                except Exception as error:
                    raise ProxboxException(
                        message = f"Error creating the '{proxbox_tag_name}' tag. Possible errors: the name '{proxbox_tag_name}' or slug '{proxbox_tag_slug}' is already used.",
                        python_exception=f"{error}"
                    ) 
            else:
                tag = proxbox_tag

            return tag
'''


'''
NetBox Session function used in the old NetboxSession class to Dependency Injection.
async def netbox_session(
    netbox_settings: Annotated[NetboxSessionSchema, Depends(netbox_settings)],
) -> NetboxSession:
    """Instantiate 'NetboxSession' class with user parameters and return Netbox  HTTP connection to make API calls"""
    if netbox_settings is None:
        raise ProxboxException(
            message = "Netbox settings not found.",
            detail = "Netbox settings are required to establish a connection with the Netbox API. Verify if plugin's backend (FastAPI) is correctly configured on NetBox GUI or API."
        )
        
    return NetboxSession(netbox_settings)

# Make Session reusable
NetboxSessionDep = Annotated[NetboxSession, Depends(netbox_session)]
'''