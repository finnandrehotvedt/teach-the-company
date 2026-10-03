from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from academy.models import TransactionalEmail
from academy.notifications import deliver_one


class Command(BaseCommand):
    help = "Send a bounded batch of fixed transactional messages from the outbox."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=10)

    def handle(self, *args, **options):
        if not settings.TRANSACTIONAL_EMAIL_DELIVERY_ENABLED:
            raise CommandError("transactional email delivery is disabled")
        limit = max(1, min(options["limit"], 50))
        ids = list(TransactionalEmail.objects.filter(status="pending", available_at__lte=timezone.now()).values_list("id", flat=True)[:limit])
        delivered = sum(deliver_one(item_id) for item_id in ids)
        self.stdout.write(f"delivered={delivered}")
