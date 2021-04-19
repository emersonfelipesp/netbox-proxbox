#from django.<a href="http" target="_blank">http</a> import HttpResponse
from django.http import HttpResponse
from django.urls import path

from .views import VmResourcesView, VmResourcesListView, VmResourcesCreateView

'''
def dummy_view(request):
    html = "<html><body>Proxbox Plugin.</body></html>"
    return HttpResponse(html)
'''

urlpatterns = [
    path("", VmResourcesListView.as_view(), name="proxbox_list"),
    
    # <int:pk> = plugins/netbox_proxbox/<pk> | example: plugins/netbox_proxbox/1/
    # VmResourcesView.as_view() - as.view() is need so that our view class can process requests.
    # as_view() takes request and returns well-formed response, that is a class based view.
    path("<int:pk>/", VmResourcesView.as_view(), name="proxbox"),
    path("add/", VmResourcesCreateView.as_view(), name="proxbox_add")
]
