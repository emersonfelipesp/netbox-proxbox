# Proxmox
from proxmoxer import ProxmoxAPI

#
# PROXMOX SESSION
#
class ProxmoxSession:
    def __init__(self, proxmox_settings):
        self.domain = proxmox_settings.domain
        self.http_port = proxmox_settings.http_port
        self.user = proxmox_settings.user
        self.password = proxmox_settings.password
        self.token_name = proxmox_settings.token.name
        self.token_value = proxmox_settings.token.value
        self.ssl = proxmox_settings.ssl
        
    async def proxmoxer(self):
        print("Establish Proxmox connection...")
        
        # Check if token was provided
        if self.ssl == False:
            # DISABLE SSL WARNING
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                    
        if self.token_name and self.token_value:
            # Establish Proxmox Session with Token
            try:
                proxmox_session = ProxmoxAPI(
                    self.domain,
                    port=self.http_port,
                    token_name=self.token_name,
                    token_value=self.token_value,
                    verify_ssl=self.ssl
                )
                
                return proxmox_session
        
            except Exception as error:
                raise RuntimeError(f'Error trying to initialize Proxmox Session using TOKEN (token_name: {self.token_name} and token_value: {self.token_value} provided')       
        else:
            try:
                # Start PROXMOX session using USER CREDENTIALS
                PROXMOX_SESSION = ProxmoxAPI(
                    self.domain,
                    port=self.http_port,
                    user=self.user,
                    password=self.password,
                    verify_ssl=self.ssl
                )
                
                return proxmox_session
            except Exception as error:
                raise RuntimeError(f'Error trying to initialize Proxmox Session using USER {self.user} and PASSWORD provided')