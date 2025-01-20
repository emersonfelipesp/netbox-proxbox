from django.views import View
from django.shortcuts import redirect

def DiscussionsView(request):
    """
    ### Redirects the user to the external discussions URL.
    
    **Args:**
    - **request:** The HTTP request object.
        
    **Returns:**
    - **HttpResponseRedirect:** A redirect response to the external discussions URL.
    """
    
    external_url = "https://github.com/orgs/netdevopsbr/discussions"
    return redirect(external_url)


def DiscordView(request):
    """
    ### Redirects the user to the specified Discord invite URL.
    
    **Args:**
    - **request:** The HTTP request object.
    
    **Returns:**
    - **HttpResponseRedirect:** A redirection response to the Discord invite URL.
    """
    
    
    external_url = "https://discord.com/invite/9N3V4mpMXU"
    return redirect(external_url)


def TelegramView(request):
    """
    ### Redirects the user to the NetBox Telegram group.
    
    **Args:**
    - **request:** The HTTP request object.
    
    **Returns:**
    - **HttpResponseRedirect:** A redirect response to the specified external URL.
    """
    
    external_url = "https://t.me/netboxbr"
    return redirect(external_url)