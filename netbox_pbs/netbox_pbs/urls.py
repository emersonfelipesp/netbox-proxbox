"""URL routes for netbox-pbs.

PR C1 ships a single placeholder ``home`` route. List/detail views land
in PR C2 alongside the domain models.
"""

from django.urls import path

from netbox_pbs.views import PBSHomeView


app_name = "netbox_pbs"

urlpatterns = [
    path("", PBSHomeView.as_view(), name="home"),
]
