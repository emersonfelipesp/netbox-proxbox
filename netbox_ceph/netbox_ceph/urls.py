"""URL routes for netbox-ceph."""

from __future__ import annotations

from django.urls import path

from netbox_ceph import views

app_name = "netbox_ceph"

urlpatterns = [
    path("", views.CephHomeView.as_view(), name="home"),
    path("settings/edit/", views.settings_singleton_redirect, name="cephpluginsettings_singleton_edit"),
]
