from __future__ import annotations

from django.conf import settings
from django.http import HttpResponsePermanentRedirect

from .hosts import is_agent_host, is_private_path


class HostRoutingMiddleware:
    agent_prefixes = ("/control/", "/handoff/", "/healthz/", "/join/", "/request-access/", "/robots.txt", "/start/", "/static/", "/studio/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        agent_host = is_agent_host(request)
        is_agent_route = request.path == "/" or request.path.startswith(self.agent_prefixes)
        if settings.ENFORCE_HOST_ROUTES and agent_host and not is_agent_route:
            target = settings.PUBLIC_SITE_ORIGIN + request.get_full_path()
            return HttpResponsePermanentRedirect(target)
        response = self.get_response(request)
        if agent_host or is_private_path(request.path) or request.path == "/healthz/":
            response["X-Robots-Tag"] = "noindex, nofollow"
        return response
