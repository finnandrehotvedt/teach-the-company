from __future__ import annotations

import secrets
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from academy.models import AccessInvite, AccessRequest
from academy.notifications import transition_access_request


class Command(BaseCommand):
    help = "Create one bounded private-agent invitation and print its URL once."

    def add_arguments(self, parser):
        parser.add_argument("label")
        parser.add_argument("--email", default="")
        parser.add_argument("--days", type=int, default=14)
        parser.add_argument("--uses", type=int, default=1)

    def handle(self, *args, **options):
        if options["days"] < 1 or options["days"] > 90:
            raise CommandError("--days must be between 1 and 90")
        if options["uses"] < 1 or options["uses"] > 10:
            raise CommandError("--uses must be between 1 and 10")
        token = secrets.token_urlsafe(32)
        invite = AccessInvite.objects.create(
            label=options["label"],
            email=options["email"],
            token_hash=AccessInvite.hash_token(token),
            max_uses=options["uses"],
            expires_at=timezone.now() + timedelta(days=options["days"]),
        )
        if options["email"]:
            requests = AccessRequest.objects.filter(
                email__iexact=options["email"],
                status=AccessRequest.Status.REQUESTED,
            )
            for access_request in requests:
                transition_access_request(access_request, AccessRequest.Status.INVITED)
        origin = settings.AGENT_SITE_ORIGIN if settings.AGENT_SITE_LIVE else settings.SITE_ORIGIN
        self.stdout.write(f"{origin}/join/{token}/")
        self.stderr.write(f"Invite {invite.public_id} created; the URL above will not be recoverable from the database.")
