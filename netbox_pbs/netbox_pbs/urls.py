"""URL routes for netbox-pbs."""

from __future__ import annotations

from django.urls import include, path
from utilities.urls import get_model_urls

from netbox_pbs import views

app_name = "netbox_pbs"

_MODEL_ROUTES = (
    ("pbsserver", "servers"),
    ("pbsdatastore", "datastores"),
    ("pbssnapshot", "snapshots"),
    ("pbsjob", "jobs"),
    ("pbspluginsettings", "settings"),
)

urlpatterns = [
    path("", views.PBSHomeView.as_view(), name="home"),
    path(
        "settings/edit/",
        views.settings_singleton_redirect,
        name="pbspluginsettings_singleton_edit",
    ),
]

for _model_name, _slug in _MODEL_ROUTES:
    urlpatterns += [
        path(
            f"{_slug}/<int:pk>/",
            include(get_model_urls("netbox_pbs", _model_name)),
        ),
        path(
            f"{_slug}/",
            include(get_model_urls("netbox_pbs", _model_name, detail=False)),
        ),
    ]
