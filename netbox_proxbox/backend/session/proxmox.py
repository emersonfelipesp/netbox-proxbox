# Proxmox
from proxmoxer import ProxmoxAPI
from proxmoxer.core import ResourceException

from netbox_proxbox.backend.exception import ProxboxException

#from netbox_proxbox.backend.schemas.proxmox import ProxmoxSessionSchema

#
# PROXMOX SESSION
#
class ProxmoxSession:
    def __init__(self, proxmox_settings):
        #proxmox_settings = proxmox_settings.json()
        
        proxmox_settings = proxmox_settings.dict()
        print(proxmox_settings, type(proxmox_settings))
    
        self.domain = proxmox_settings["domain"]
        self.http_port = proxmox_settings["http_port"]
        self.user = proxmox_settings["user"]
        self.password = proxmox_settings["password"]
        self.token_name = proxmox_settings["token"]["name"]
        self.token_value = proxmox_settings["token"]["value"]
        self.ssl = proxmox_settings["ssl"]
        
        print(self.token_name)
        print(self.token_value)


    async def token_auth(self):
        error_message = f"Error trying to initialize Proxmox API connection using TOKEN NAME '{self.token_name}' and TOKEN_VALUE provided",
        
        # Establish Proxmox Session with Token
        try:
            print("Using token to authenticate with Proxmox")
            proxmox_session = ProxmoxAPI(
                self.domain,
                port=self.http_port,
                token_name=self.token_name,
                token_value=self.token_value,
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
        


    async def password_auth(self):
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
            
        except Exception as error:
            raise RuntimeError()
        except Exception as error:
            return {
                "error": {
                    "message": f'Error trying to initialize Proxmox Session using USER {self.user} and PASSWORD provided',
                    "detail": "Not able to establish Proxmox API connection using password provided by the user.",
                    "python_exception": f"{error}",
                }
            }

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
        
        try:
            px.version.get()
        except ResourceException as error:
            raise ProxboxException(
                message = "Testing Proxmox connection failed. Proxmoxer 'ResourceException' raised.",
                detail = "After instianting connection from 'ProxmoxAPI', testing the communication failed.",
                python_exception = f"{error}",
            )

        except Exception as error:
            return {
                "error": {
                    "message": "Testing Proxmox connection failed.",
                    "detail": "Unkown error.",
                    "python_exception": f"{error}",
            }
        }
        
        return px
            
        
            