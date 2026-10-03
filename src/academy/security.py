from __future__ import annotations

import hashlib
import hmac

from django.conf import settings


def client_address(request) -> str:
    remote = request.META.get("REMOTE_ADDR", "")
    if settings.TRUST_PROXY_HEADERS and remote in settings.TRUSTED_PROXY_IPS:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",", 1)[0].strip()
    return remote


def source_fingerprint(request, purpose: str) -> str:
    material = "|".join(
        (
            purpose,
            client_address(request),
            request.META.get("HTTP_USER_AGENT", "")[:250],
        )
    )
    return hmac.new(settings.SECRET_KEY.encode(), material.encode(), hashlib.sha256).hexdigest()
