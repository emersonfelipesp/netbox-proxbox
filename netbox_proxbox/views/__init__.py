import subprocess
import json

from django.shortcuts import render
from django.views import View

try:
    from netbox import configuration
except Exception as error:
    print(error)
    
from netbox_proxbox import ProxboxConfig
from netbox_proxbox import github

# Import other proxbox views
from .external_pages import *
from .proxbox_backend import *
from .endpoints import  *
from .keepalive_status import *

from netbox_proxbox.models import ProxmoxEndpoint, NetBoxEndpoint, FastAPIEndpoint

class HomeView(View):
    """
    ## HomeView class-based view to handle incoming GET HTTP requests.
    
    ### Attributes:
    - **template_name (str):** The path to the HTML template used for rendering the view.
    
    ### Methods:
    - **get(request):**
            Handles GET requests to the view.
            Retrieves plugin configuration and default settings.
            Constructs the FastAPI endpoint URL.
            Renders the template with the configuration and default settings.
            
            **Args:**
            - **request (HttpRequest):** The HTTP request object.
            
            **Returns:**
            - **HttpResponse:** The rendered HTML response.
    """
    
    template_name = 'netbox_proxbox/home.html'

    # service incoming GET HTTP requests
    def get(self, request):
        """Get request."""
        
        default_config = dict =  getattr(ProxboxConfig, 'default_settings', {})
        
        proxmox_endpoint_obj = ProxmoxEndpoint.objects.all()
        netbox_endpoint_obj = NetBoxEndpoint.objects.all()
        fastapi_endpoint_obj = FastAPIEndpoint.objects.all()

        return render(
            request,
            self.template_name,
            {
                "default_config": default_config,
                'proxmox_endpoint_list': proxmox_endpoint_obj,
                'netbox_endpoint_list': netbox_endpoint_obj,
                'fastapi_endpoint_list': fastapi_endpoint_obj,
            }
        )


class NodesView(View):
    template = 'netbox_proxbox/nodes.html'

    def get(self, request):
        plugin_configuration: dict = getattr(configuration, "PLUGINS_CONFIG", {})

        return render(
            request, 
            self.template,
            {
                "configuration": plugin_configuration
            }
        )


class VirtualMachinesView(View):
    template = 'netbox_proxbox/virtual_machines.html'

    def get(self, request):
        plugin_configuration: dict = getattr(configuration, "PLUGINS_CONFIG", {})

        return render(
            request, 
            self.template,
            {
                "configuration": plugin_configuration
            }
        )

class ContributingView(View):
    """
    **ContributingView** handles the rendering of the contributing page for the Proxbox project.
    
    **Attributes:**
    - **template_name (str):** The path to the HTML template for the contributing page.
    
    **Methods:**
    - **get(request):** Handles GET HTTP requests and renders the contributing page with the content
    of the 'CONTRIBUTING.md' file and a title.
    """
    
    template_name = 'netbox_proxbox/contributing.html'

    # service incoming GET HTTP requests
    def get(self, request):
        """Get request."""

        title = "Contributing to Proxbox Project"
        
        return render(
            request,
            self.template_name,
            {
                "html": github.get(filename = "CONTRIBUTING.md"),
                "title": title,
            }
        )


class CommunityView(View):
    """
    CommunityView handles the rendering of the community page.
    
    **Attributes:**
    - **template_name (str):** The path to the HTML template for the community page.
    
    **Methods:**
    - **get(request):** Handles GET HTTP requests and renders the community page with a title.
    """
    
    
    template_name = 'netbox_proxbox/community.html'

    # service incoming GET HTTP requests
    def get(self, request):
        """Get request."""

        title = "Join our Community!"
        
        return render(
            request,
            self.template_name,
            {
                "title": title,
            }
        )