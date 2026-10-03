import secrets

from django.conf import settings

from .hosts import is_agent_host, is_private_path
from .models import ProjectAccessKey, TrainingProject


def site_context(request):
    owned = []
    tokens = request.session.get(settings.STUDIO_SESSION_KEY, {}) if hasattr(request, "session") else {}
    if isinstance(tokens, dict) and tokens:
        projects = TrainingProject.objects.filter(public_id__in=tokens.keys()).order_by("created_at")
        for project in projects:
            token = tokens.get(str(project.public_id), "")
            token_hash = TrainingProject.hash_owner_key(token) if token else ""
            has_access_keys = project.access_keys.exists()
            legacy_match = token and not has_access_keys and secrets.compare_digest(token_hash, project.owner_key_hash)
            key_match = token and ProjectAccessKey.objects.filter(
                project=project, token_hash=token_hash, active=True
            ).exists()
            if legacy_match or key_match:
                owned.append(project)
    agent_host = is_agent_host(request)
    private_page = is_private_path(request.path)
    canonical_url = "" if agent_host or private_page else settings.PUBLIC_SITE_ORIGIN + request.path
    classroom_origin = settings.AGENT_SITE_ORIGIN if settings.AGENT_SITE_LIVE else settings.PUBLIC_SITE_ORIGIN
    security_url = settings.SECURITY_LAB_ORIGIN if settings.SECURITY_LAB_LIVE else settings.PUBLIC_SITE_ORIGIN + "/ai-agent-security/"
    return {
        "site_origin": settings.SITE_ORIGIN,
        "public_site_origin": settings.PUBLIC_SITE_ORIGIN,
        "agent_site_origin": settings.AGENT_SITE_ORIGIN,
        "classroom_origin": classroom_origin,
        "security_lab_url": security_url,
        "agent_site_live": settings.AGENT_SITE_LIVE,
        "security_lab_live": settings.SECURITY_LAB_LIVE,
        "is_agent_host": agent_host,
        "canonical_url": canonical_url,
        "page_noindex": agent_host or private_page or request.path == "/healthz/",
        "default_meta_description": "A free practical English AI school: understand AI, teach one useful agent, verify evidence and keep people in control.",
        "owned_projects": owned,
        "owned_project": owned[0] if owned else None,
    }
