from fastapi import Depends, Query
from typing import Annotated, Any

# Proxmox
from proxmoxer import ProxmoxAPI

from proxbox_api.schemas.proxmox import ProxmoxSessionSchema, ProxmoxTokenSchema
from proxbox_api.exception import ProxboxException
from proxbox_api.session.netbox import NetboxSessionDep

#
# PROXMOX SESSION
#
class ProxmoxSession:
    """
        (Single-cluster) This class takes user-defined parameters to establish Proxmox connection and returns ProxmoxAPI object (with no further details)
        
        INPUT must be:
        - dict
        - pydantic model - will be converted to dict
        - json (string) - will be converted to dict
        
        Example of class instantiation:
        ```python
        ProxmoxSessionSchema(
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
        )
        ```
    """
    def __init__(
        self,
        cluster_config: Any
    ):
        #
        # Validate cluster_config type
        #
        if isinstance(cluster_config, ProxmoxSessionSchema):
            print("INPUT is Pydantic Model ProxmoxSessionSchema")
            cluster_config = cluster_config.model_dump(mode="python")
          
        # FIXME: This is not working  
        elif isinstance(cluster_config, str):
            print("INPUT is string")
            import json
            cluster_config = json.loads(cluster_config)
            print(f"json_loads: {cluster_config} - type: {type(cluster_config)}""}")
                
                
            """
            except Exception as error:
                raise ProxboxException(
                    message = f"Could not proccess the input provided, check if it is correct. Input type provided: {type(cluster_config)}",
                    detail = "ProxmoxSession class tried to convert INPUT to dict, but failed.",
                    python_exception = f"{error}",
                )
            """
        elif isinstance(cluster_config, dict):
            print("INPUT is dict")
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


        #
        # Establish Proxmox Session
        #
        try:
            # DISABLE SSL WARNING
            if not self.ssl:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            # Prefer using token to authenticate
            if self.token_name and self.token_value:
                self.proxmoxer = self.token_auth() 
            
            else:
                self.proxmoxer = self.password_auth()
                
            self.session = self.proxmoxer

        except Exception as error:
            raise ProxboxException(
                message = f"Could not establish Proxmox connection to '{self.domain}:{self.http_port}' using token name '{self.token_name}'.",
                detail = "Unknown error.",
                python_exception = f"{error}"
            )
         
        #
        # Test Connection and Return Cluster Status if succeeded.
        # 
        try:
            """Test Proxmox Connection and return Cluster Status API response as class attribute"""
            self.cluster_status = self.proxmoxer("cluster/status").get()
        except Exception as error:
            raise ProxboxException(
                message = f"After instatiating object connection, could not make API call to Proxmox '{self.domain}:{self.http_port}' using token name '{self.token_name}'.",
                detail = "Unknown error.",
                python_exception = f"{__name__}: {error}"
            )   
        
        #
        # Add more attributes to class about Proxmox Session
        #
        self.mode = self.get_cluster_mode()
        if self.mode == "cluster":
            cluster_name: str = self.get_cluster_name()
            
            self.cluster_name = cluster_name
            self.name = cluster_name
            self.fingerprints: list = self.get_node_fingerprints(self.proxmoxer)
        
        elif self.mode == "standalone":
            standalone_node_name: str = self.get_standalone_name()
            
            self.node_name = standalone_node_name
            self.name = standalone_node_name
            self.fingerprints = None
        
        

    def __repr__(self):
        return f"Proxmox Connection Object. URL: {self.domain}:{self.http_port}"


    #
    # Proxmox Authentication Modes: TOKEN-BASED & PASSWORD-BASED
    #
    
    def token_auth(self):
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
            
            return proxmox_session
            
        except Exception as error:
            raise ProxboxException(
                message = error_message,
                detail = "Unknown error.",
                python_exception = f"{error}"
            )


    def password_auth(self):
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

        except Exception as error:
            raise ProxboxException(
                message = error_message,
                detail = "Unknown error.",
                python_exception = f"{error}"
            )


    #
    # Get Proxmox Details about Cluster and Nodes
    #
    def get_node_fingerprints(self, px):
        """Get Nodes Fingerprints. It is the way I better found to differentiate clusters."""
        try:
            join_info = px("cluster/config/join").get()
        
            fingerprints = []        
            for node in join_info.get("nodelist"):
                fingerprints.append(node.get("pve_fp"))
            
            return fingerprints
        
        except Exception as error:
            raise ProxboxException(
                message = "Could not get Nodes Fingerprints",
                python_exception = f"{error}"
            )


    def get_cluster_mode(self):
        """Get Proxmox Cluster Mode (Standalone or Cluster)"""
        try:
            if len(self.cluster_status) == 1 and self.cluster_status[0].get("type") == "node":
                return "standalone"
            else:
                return "cluster"
            
        except Exception as error:
            raise ProxboxException(
                message = "Could not get Proxmox Cluster Mode (Standalone or Cluster)",
                python_exception = f"{error}"
            )
        
    
    def get_cluster_name(self):
        """Get Proxmox Cluster Name"""
        try:      
            for item in self.cluster_status:
                if item.get("type") == "cluster":
                    return item.get("name")

        except Exception as error:
            raise ProxboxException(
                message = "Could not get Proxmox Cluster Name and Nodes Fingerprints",
                python_exception = f"{error}"
            )


    def get_standalone_name(self):
        """Get Proxmox Standalone Node Name"""
        try:
            if len(self.cluster_status) == 1 and self.cluster_status[0].get("type") == "node":
                return self.cluster_status[0].get("name")
            
        except Exception as error:
            raise ProxboxException(
                message = "Could not get Proxmox Standalone Node Name",
                python_exception = f"{error}"
            )


async def proxmox_sessions(
    nb: NetboxSessionDep,
    source: str = "netbox",
    name: Annotated[
        str,
        Query(
            title="Proxmox Name",
            description="Name of Proxmox Cluster or Proxmox Node (if standalone)."
        )
    ] = None,
    domain: Annotated[
        str,
        Query(
            title="Proxmox Domain",
            description="Domain of Proxmox Cluster or Proxmox Node (if standalone)."
        )
    ] = None,
    ip_address: Annotated[
        str,
        Query(
            title="Proxmox IP Address",
            description="IP Address of Proxmox Cluster or Proxmox Node (if standalone)."
        )
    ] = None,
    port: Annotated[
        int,
        Query(
            title="Proxmox HTTP Port",
            description="HTTP Port of Proxmox Cluster or Proxmox Node (if standalone)."
        )
    ] = 8006,
):
    """
        Default Behavior: Instantiate Proxmox Sessions and return a list of Proxmox Sessions objects.
        If 'name' is provided, return only the Proxmox Session with that name.
    """
    
    # GET /api/plugins/proxbox/endpoints/proxmox/
    proxmox = nb.session.plugins.proxbox.__getattr__('endpoints/proxmox').all()

    if domain and not ip_address:
        ip_address = domain
        
    if source == "netbox":
        proxmox_schemas = []
        
        for endpoint in proxmox:
            proxmox_schema = ProxmoxSessionSchema(
                domain = endpoint.ip_address.address.split('/')[0],
                http_port = endpoint.port,
                user = endpoint.username,
                password = endpoint.password,
                ssl = endpoint.verify_ssl,
                token = ProxmoxTokenSchema(
                    name = endpoint.token_name,
                    value = endpoint.token_value
                )
            )
            
            if (ip_address == endpoint.ip_address.address.split('/')[0]) and (port == endpoint.port):
                # Instantiate Proxmox Session object from ProxmoxSession class
                px_obj = ProxmoxSession(proxmox_schema)
                return [px_obj]
            
            else:
                proxmox_schemas.append(proxmox_schema)           
        
        # Only if no match was found, return all Proxmox Sessions
        return [ProxmoxSession(px) for px in proxmox_schemas]

ProxmoxSessionsDep = Annotated[list, Depends(proxmox_sessions)]