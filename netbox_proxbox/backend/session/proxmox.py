from fastapi import Depends
from typing import Annotated

# Proxmox
from proxmoxer import ProxmoxAPI
from proxmoxer.core import ResourceException

from netbox_proxbox.backend.routes.proxbox import proxmox_settings
from netbox_proxbox.backend.schemas.proxmox import ProxmoxSessionSchema
from netbox_proxbox.backend.exception import ProxboxException

#from netbox_proxbox.backend.schemas.proxmox import ProxmoxSessionSchema

#
# PROXMOX SESSION
#
class ProxmoxSession:
    """
        (Single-cluster) This class takes user-defined parameters to establish Proxmox connection and returns ProxmoxAPI object (with no further details)
        
        NOTE: As `__init__()` does not support ASYNC methods, I had to create a method to establish Proxmox connection and return ProxmoxAPI object, which is `proxmoxer()` method.
        Which means that only calling ProxmoxSession() will not establish Proxmox connection. You must call `proxmoxer()` method to do so.
        
        INPUT must be:
        - dict
        - pydantic model - will be converted to dict
        - json (string) - will be converted to dict
        
        Example of class instantiation:
        ```python
        ProxmoxSession(
            {
                "domain": "proxmox.domain.com",
                "http_port": 8006,
                "user": "user@pam",
                "password": "password",
                "token": {
                    "name": "token_name",
                    "value": "token_value"
                },
            }
        ).proxmoxer()
        ```
        
        OUTPUT: ProxmoxAPI object (from proxmoxer lib)
    """
    def __init__(
        self,
        cluster_config
    ):
        # Validate cluster_config type
        if isinstance(cluster_config, ProxmoxSessionSchema):
            cluster_config = cluster_config.model_dump(mode="python")
            
        elif isinstance(cluster_config, str):
            try:
                import json
                cluster_config = json.loads(cluster_config)
                
            except Exception as error:
                raise ProxboxException(
                    message = f"Could not proccess the input provided, check if it is correct. Input type provided: {type(cluster_config)}",
                    detail = "ProxmoxSession class tried to convert INPUT to dict, but failed.",
                    python_exception = f"{error}",
                )
        elif isinstance(cluster_config, dict):
            pass
        else:
            raise ProxboxException(
                message = f"INPUT of ProxmoxSession() must be a pydantic model or dict (either one will work). Input type provided: {type(cluster_config)}",
            )       
                
        try:
            # Save cluster_config as class attributes
            self.domain = cluster_config["domain"]
            self.http_port = cluster_config["http_port"]
            self.user = cluster_config["user"]
            self.password = cluster_config["password"]
            self.token_name = cluster_config["token"]["name"]
            self.token_value = cluster_config["token"]["value"]
            self.ssl = cluster_config["ssl"]
        except KeyError:
            raise ProxboxException(
                message = "ProxmoxSession class wasn't able to find all required parameters to establish Proxmox connection. Check if you provided all required parameters.",
                detail = "Python KeyError raised"
            )

    def __repr__(self):
        return f"Proxmox Connection Object. URL: {domain}:{http_port}"

    async def token_auth(self):
        error_message = f"Error trying to initialize Proxmox API connection using TOKEN NAME '{self.token_name}' and TOKEN_VALUE provided",
        
        # Establish Proxmox Session with Token
        try:
            print("Using token to authenticate with Proxmox")
            proxmox_session = ProxmoxAPI(
                self.domain,
                port=self.http_port,
                user=self.user,
                token_name=self.token_name,
                token_value=self.token_value,
                verify_ssl=self.ssl
            )
            
            try:
                
                proxmox_session.version.get()
                
            except Exception as error:
                ProxboxException(
                    message = "Testing Proxmox connection failed.",
                    detail = "Unkown error.",
                    python_exception = f"{error}",
                )
            
            return proxmox_session
        
        except ResourceException as error:
            raise ProxboxException(
                message = error_message,
                detail = "'ResourceException' from proxmoxer lib raised.",
                python_exception = f"{error}"
            )
        except Exception as error:
            raise ProxboxException(
                message = error_message,
                detail = "Unknown error.",
                python_exception = f"{error}"
            )
        


    async def password_auth(self):
        error_message = f'Error trying to initialize Proxmox API connection using USER {self.user} and PASSWORD provided',
        
        try:
            # Start PROXMOX session using USER CREDENTIALS
            print("Using password authenticate with Proxmox")
            proxmox_session = ProxmoxAPI(
                self.domain,
                port=self.http_port,
                user=self.user,
                password=self.password,
                verify_ssl=self.ssl
            )
            
            return proxmox_session
            
        except ResourceException as error:
            raise ProxboxException(
                message = error_message,
                detail = "'ResourceException' from proxmoxer lib raised.",
                python_exception = f"{error}"
            )

        except Exception as error:
            raise ProxboxException(
                message = error_message,
                detail = "Unknown error.",
                python_exception = f"{error}"
            )

    async def proxmoxer(self):
        print("Establish Proxmox connection...")
        
        # DISABLE SSL WARNING
        if self.ssl == False:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # Prefer using token to authenticate
        if self.token_name and self.token_value:
            px = await self.token_auth() 
        
        else:
            px = await self.password_auth()

        return px
            
async def sessions(
    proxmox_settings: Annotated[ProxmoxSessionSchema, Depends(proxmox_settings)]
):
    proxmox_sessions = []
    
    for cluster in proxmox_settings:
        # Convert pydantic mdoel to dict
        cluster = cluster.model_dump()
        
        cluster["object"] = await ProxmoxSession(cluster).proxmoxer()
        
        print(f"CLUSTER: {cluster}")
        proxmox_sessions.append(cluster)
        
    print(proxmox_sessions)
       
class ProxmoxSessions:
    """
    (Multi-cluster) This class takes user-defined parameters to establish Proxmox connection and returns ProxmoxAPI object alongside with cluster details (name and fingerprints)
    
    INPUT must be a list of dicts with the following structure:
    
    ProxmoxSessions(
        [
            {
                'domain': '10.0.30.9',
                'http_port': 8006,
                'user': 'root@pam',
                'password': '@YourStrongProxmoxPassword',
                'token': {
                    'name': 'token_name', # 'proxbox',
                    'value': 'e7fb5ecb-XXXX-YYYY-ZZZZ-ed1059e5772f' #
                },
                'ssl': False
            },
            {
                'domain': '10.0.30.140',
                'http_port': 8006,
                'user': 'root@pam',
                'password': '@YourStrongProxmoxPassword',
                'token': {
                    'name': 'token_name',
                    'value': '2a00665d-XXXX-YYYY-ZZZZ-67852c50c706'
                },
                'ssl': False
            }
        ]
    )

    OUTPUT: [
        {}
    ]ProxmoxAPI object (from proxmoxer lib)
    """
        
    def __init__(
        self,
        proxmox_settings: Annotated[ProxmoxSessionSchema, Depends(proxmox_settings)],
        sessions: Annotated[list, Depends(sessions)]
    ):
        self.proxmox_settings = proxmox_settings
        self.teste = "Teste"
        self.sessions = sessions
        
    
    
        """
            cluster_info = await self.get_cluster(session)
            print(cluster_info)
            proxmox_sessions.append(
                {
                    "session": session,
                    "cluster_name": cluster_info.get("name"),
                    "fingerprints": cluster_info.get("fingerprints"),
                }   
            )
            #self.cluster_info = await self.get_cluster(self.session)
        """
        
    async def fingerprints(self, px):
        """Get Nodes Fingerprints. It is the way I better found to differentiate clusters."""
        join_info = px("cluster/config/join").get()
    
        fingerprints = []        
        for node in join_info.get("nodelist"):
            fingerprints.append(node.get("pve_fp"))
        
        return fingerprints
    

    async def get_cluster(self, px):
        """Get Proxmox Cluster Name"""
        cluster_status_list = px("cluster/status").get()
        
        for item in cluster_status_list:
            if item.get("type") == "cluster":
                return {
                    "name": item.get("name"),
                    "fingerprints": await self.fingerprints(px)
                }
    
        
       