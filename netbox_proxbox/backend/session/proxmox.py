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
    def __init__(
        self,
        cluster_config
    ):
        #proxmox_settings = proxmox_settings.json()
        
        cluster_config = cluster_config.dict()
        print(cluster_config, type(cluster_config))
    
        self.domain = cluster_config["domain"]
        self.http_port = cluster_config["http_port"]
        self.user = cluster_config["user"]
        self.password = cluster_config["password"]
        self.token_name = cluster_config["token"]["name"]
        self.token_value = cluster_config["token"]["value"]
        self.ssl = cluster_config["ssl"]
        
        print(self.token_name)
        print(self.token_value)

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
            
        
class ProxmoxSessions:
    def __init__(
        self,
        proxmox_settings: Annotated[ProxmoxSessionSchema, Depends(proxmox_settings)],
    ):
        self.proxmox_settings = proxmox_settings
    
        
    async def sessions(self):
        proxmox_sessions = []
        
        for cluster in self.proxmox_settings:
            session = await ProxmoxSession(cluster).proxmoxer()
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
            proxmox_sessions.append(
                {   
                    "session": self.session,
                }.update(self.cluster_info)
            )
            """
        
        return proxmox_sessions
        
    
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
    
        
       