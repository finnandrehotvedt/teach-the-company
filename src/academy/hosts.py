from __future__ import annotations

from django.conf import settings


PRIVATE_PREFIXES = (
    "/control/",
    "/handoff/",
    "/join/",
    "/request-access/",
    "/start/",
    "/studio/",
)


def request_host(request) -> str:
    return request.get_host().split(":", 1)[0].lower()


def is_agent_host(request) -> bool:
    return request_host(request) in settings.AGENT_HOSTS


def is_private_path(path: str) -> bool:
    return path.startswith(PRIVATE_PREFIXES)
