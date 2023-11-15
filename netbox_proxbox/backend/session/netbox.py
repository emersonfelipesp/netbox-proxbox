import aiohttp
import requests

# Netbox
import pynetbox

try:
    from netbox.settings import BASE_PATH
    DEFAULT_BASE_PATH = '/' + BASE_PATH
except ImportError:
    DEFAULT_BASE_PATH = ''
    
#
# NETBOX SESSION 
#
# TODO: CREATES SSL VERIFICATION - Issue #32
class NetboxSession:
    def __init__(self, netbox_settings):
        self.domain = netbox_settings.domain
        self.http_port = netbox_settings.http_port
        self.token = netbox_settings.token
        self.ssl = netbox_settings.ssl
        self.settings = netbox_settings.settings
        
    async def pynetbox(self):
        print("Establish Netbox connection...")
        try:
            # CHANGE SSL VERIFICATION TO FALSE
            session = requests.Session()
            session.verify = False
            
            netbox_session = pynetbox.api(
                    f'http://{self.domain}:{self.http_port}{DEFAULT_BASE_PATH}',
                    token=self.token,
                    threading=True,
            )
            # DISABLES SSL VERIFICATION
            netbox_session.http_session = session
            
            return netbox_session
        
        except Exception as error:
            raise RuntimeError(f"Error trying to initialize Netbox Session using TOKEN {self.token} provided.\nPython Error: {error}")
        
    async def aiohttp(self):
        # Future Development. We're currently use pynetbox.
        pass
    