from __future__ import annotations

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create the initial moderator without resetting an existing password."

    def handle(self, *args, **options):
        username = os.getenv("DJANGO_ADMIN_USERNAME", "").strip()
        password = os.getenv("DJANGO_ADMIN_PASSWORD", "")
        email = os.getenv("DJANGO_ADMIN_EMAIL", "").strip()
        if not username or not password:
            self.stdout.write("Moderator bootstrap skipped: protected settings are absent.")
            return
        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(
            username=username,
            defaults={"email": email, "is_staff": True, "is_superuser": True},
        )
        if created:
            user.set_password(password)
            user.save(update_fields=("password",))
            self.stdout.write("Protected moderator account created.")
        else:
            self.stdout.write("Moderator already exists; credentials preserved.")
