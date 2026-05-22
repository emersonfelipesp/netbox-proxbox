"""Redirect plugin users to external discussion pages."""

from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import redirect


def discussions_redirect(request: HttpRequest) -> HttpResponseRedirect:
    """Redirect to GitHub discussions for the project."""

    external_url = "https://github.com/orgs/emersonfelipesp/discussions"
    return redirect(external_url)
