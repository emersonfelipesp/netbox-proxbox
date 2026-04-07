"""Redirect plugin users to external community and discussion pages."""

from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import redirect


def discussions_redirect(request: HttpRequest) -> HttpResponseRedirect:
    """Redirect to GitHub discussions for the project."""

    external_url = "https://github.com/orgs/emersonfelipesp/discussions"
    return redirect(external_url)


def discord_redirect(request: HttpRequest) -> HttpResponseRedirect:
    """Redirect to the project Discord invite."""

    external_url = "https://discord.com/invite/9N3V4mpMXU"
    return redirect(external_url)


def telegram_redirect(request: HttpRequest) -> HttpResponseRedirect:
    """Redirect to the NetBox Telegram group."""

    external_url = "https://t.me/netboxbr"
    return redirect(external_url)
