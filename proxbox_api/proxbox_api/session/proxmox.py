from fastapi import Depends, Query
from typing import Annotated, Any

# Proxmox
from proxmoxer import ProxmoxAPI

from proxbox_api.schemas.proxmox import ProxmoxSessionSchema, ProxmoxTokenSchema
from proxbox_api.exception import ProxboxException
#from proxbox_api.session.netbox import NetboxSessionDep


# Pynetbox-api Imports
from pynetbox_api.session import RawNetBoxSession

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
        self.CONNECTED = False  
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
            self.ip_address = cluster_config["ip_address"]
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
            
            self.proxmoxer = self._auth(auth_method="token") if self.token_name and self.token_value else self._auth(auth_method="password")
            if self.proxmoxer:
                self.session = self.proxmoxer
                self.CONNECTED = True

        except ProxboxException as error:
            raise error
        
        except Exception as error:
            raise ProxboxException(
                message = f"Could not establish Proxmox connection to '{self.domain}:{self.http_port}' using token name '{self.token_name}'.",
                detail = "Unknown error.",
                python_exception = f"{error}"
            )
         
        #
        # Test Connection and Return Cluster Status if succeeded.
        # 
        if self.CONNECTED:
            try:
                """Test Proxmox Connection and return Cluster Status API response as class attribute"""
                self.cluster_status = self.session("cluster/status").get()
            except ProxboxException as error:
                raise error
            
            except Exception as error:
                raise ProxboxException(
                    message = f"After instatiating object connection, could not make API call to Proxmox '{self.domain}:{self.http_port}' using token name '{self.token_name}'.",
                    detail = "Unknown error.",
                    python_exception = f"{__name__}: {error}"
                )   
        
        #
        # Add more attributes to class about Proxmox Session
        #
        self.mode = None
        self.cluster_name = None
        self.node_name = None
        self.fingerprints = None
        
        if self.CONNECTED:
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
    
    def _auth(self, auth_method: str):
        if auth_method != "token" and auth_method != "password":
            raise ProxboxException(
                message = f"Invalid authentication method provided: {auth_method}",
                detail = "ProxmoxSession class only accepts 'token' or 'password' as authentication method"
            )
        
        error_message = f"Error trying to initialize Proxmox API connection using TOKEN NAME '{self.token_name}' and TOKEN_VALUE provided",
        
        # Establish Proxmox Session with Token
        USE_IP_ADDRESS = False
        try:
            print(f"Using {auth_method} to authenticate with Proxmox")
            kwargs = {
                'port': self.http_port,
                'user': self.user,
                'token_name': self.token_name,
                'token_value': self.token_value,
                'verify_ssl': self.ssl
            } if auth_method == "token" else {
                'port': self.http_port,
                'user': self.user,
                'password': self.password,
                'verify_ssl': self.ssl
            }
            
            # Initialize Proxmox Session using Token or Password
            if self.domain:
                print(f'Using domain {self.domain} to authenticate with Proxmox')
                proxmox_session = ProxmoxAPI(
                    self.domain,
                    **kwargs
                )
                
                # Get Proxmox Version to test connection.
                # Object instatiation does not actually connect to Proxmox, need to make an API call to test connection.
                self.version = proxmox_session.version.get()
                return proxmox_session
            else:
                print(f'Using IP {self.ip_address} address to authenticate with Proxmox as domain is not provided')
                proxmox_session = ProxmoxAPI(
                    self.ip_address,
                    **kwargs
                )
                
                # Get Proxmox Version to test connection.
                # Object instatiation does not actually connect to Proxmox, need to make an API call to test connection.
                self.version = proxmox_session.version.get()
                return proxmox_session
                
        except Exception as error:
            print(f'Proxmox connection using domain failed, trying to connect using IP address {self.ip_address}')
            USE_IP_ADDRESS = True
                
        if USE_IP_ADDRESS:
            # If domain connection failed, try to connect using IP address.
            try:
                proxmox_session = ProxmoxAPI(
                    self.ip_address,
                    **kwargs
                )
                
                # Get Proxmox Version to test connection.
                # Object instatiation does not actually connect to Proxmox, need to make an API call to test connection.
                self.version = proxmox_session.version.get()
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
        if self.CONNECTED:
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
        else:
            print('Proxmox Session is not connected, so not able to get Cluster Mode')
            
    
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
    nb = RawNetBoxSession
    

    def parse_to_schema(endpoint):
        ip = None
        ip_address_object = getattr(endpoint, 'ip_address', None)
        if ip_address_object:
            ip_address_with_mask = getattr(ip_address_object, 'address', None)
            ip = ip_address_with_mask.split('/')[0]
        
        return ProxmoxSessionSchema(
            ip_address = ip,
            domain = getattr(endpoint, 'domain', None),
            http_port = getattr(endpoint, 'port', None),
            user = getattr(endpoint, 'username', None),
            password = getattr(endpoint, 'password', None),
            ssl = getattr(endpoint, 'verify_ssl', None),
            token = ProxmoxTokenSchema(
                name = getattr(endpoint, 'token_name', None),
                value = getattr(endpoint, 'token_value', None)
            )
        )
        

    # GET /api/plugins/proxbox/endpoints/proxmox/ and parse the JSON result to schemas.
    proxmox_schemas = [parse_to_schema(endpoint) for endpoint in nb.plugins.proxbox.__getattr__('endpoints/proxmox').all()]
    print(f"proxmox_schemas: {proxmox_schemas}")
    
    def return_single_session(field, value):
        for proxmox_schema in proxmox_schemas:
            if value == getattr(proxmox_schema, field, None):
                return [ProxmoxSession(proxmox_schema)]
        
        raise ProxboxException(
            message = f"No result found for Proxmox Sessions based on the provided {field}",
            detail = "Check if the provided parameters are correct"
        )
                
    try:
        if ip_address is not None:
            return return_single_session("ip_address", ip_address)
        
        if domain is not None:
            return return_single_session("domain", domain)
        
        if name is not None:
            return return_single_session("name", name)
    except ProxboxException as error:
        raise error
    
    try:
        return [ProxmoxSession(px_schema) for px_schema in proxmox_schemas]
    except Exception as error:
        raise ProxboxException(
            message = "Could not return Proxmox Sessions",
            python_exception = f"{error}"
        )

ProxmoxSessionsDep = Annotated[list, Depends(proxmox_sessions)]