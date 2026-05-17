"""URL routes for netbox-packer."""

from __future__ import annotations

from django.urls import include, path
from utilities.urls import get_model_urls

from netbox_packer import views

app_name = "netbox_packer"

_MODEL_ROUTES = (
    ("packerimagedefinition", "image-definitions"),
    ("packerimagebuild", "image-builds"),
    ("packerpluginsettings", "settings"),
)

urlpatterns = [
    path("", views.PackerHomeView.as_view(), name="home"),
    path(
        "settings/edit/",
        views.settings_singleton_redirect,
        name="packerpluginsettings_singleton_edit",
    ),
]

for _model_name, _slug in _MODEL_ROUTES:
    urlpatterns += [
        path(
            f"{_slug}/<int:pk>/",
            include(get_model_urls("netbox_packer", _model_name)),
        ),
        path(
            f"{_slug}/",
            include(get_model_urls("netbox_packer", _model_name, detail=False)),
        ),
    ]
