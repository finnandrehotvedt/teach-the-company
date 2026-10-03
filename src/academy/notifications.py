from __future__ import annotations

import hashlib
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.utils import timezone

from .models import AccessRequest, TransactionalEmail


def _recipient_fingerprint(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


def _enqueue(access_request: AccessRequest, kind: str, outcome: str = "") -> None:
    if not settings.TRANSACTIONAL_NOTIFICATIONS_ENABLED or not access_request.notification_eligible:
        return
    TransactionalEmail.objects.get_or_create(
        access_request=access_request,
        kind=kind,
        defaults={"outcome": outcome, "recipient": access_request.email,
                  "recipient_fingerprint": _recipient_fingerprint(access_request.email),
                  "source_fingerprint": access_request.source_fingerprint},
    )


def enqueue_receipt(access_request: AccessRequest) -> None:
    _enqueue(access_request, TransactionalEmail.Kind.RECEIPT)


def enqueue_outcome(access_request: AccessRequest) -> None:
    if access_request.status != AccessRequest.Status.REQUESTED:
        _enqueue(access_request, TransactionalEmail.Kind.OUTCOME, access_request.status)


def transition_access_request(access_request: AccessRequest, status: str) -> AccessRequest:
    with transaction.atomic():
        locked = AccessRequest.objects.select_for_update().get(pk=access_request.pk)
        if locked.status != status:
            locked.status = status
            locked.save(update_fields=("status",))
            enqueue_outcome(locked)
        return locked


def _content(item: TransactionalEmail) -> tuple[str, str]:
    privacy = ("This address is used only for the request receipt and manual-review outcome. "
               "It is never sold, used for ads, or disclosed for unrelated purposes.")
    if item.kind == TransactionalEmail.Kind.RECEIPT:
        return "We received your Teach the Company access request", "We received your access request. It is stored privately and will be reviewed manually. " + privacy
    outcome = ("Your access request was approved. Your invitation will be delivered separately by the reviewer."
               if item.outcome == AccessRequest.Status.INVITED else
               "The manual review of your access request is complete, and access was not opened.")
    return "Teach the Company access request outcome", outcome + " " + privacy


def deliver_one(item_id: int) -> bool:
    if not settings.TRANSACTIONAL_EMAIL_DELIVERY_ENABLED:
        return False
    now, day = timezone.now(), timezone.now() - timedelta(days=1)
    with transaction.atomic():
        item = TransactionalEmail.objects.select_for_update(skip_locked=True).filter(pk=item_id, status="pending", available_at__lte=now).first()
        if not item or not item.access_request.notification_eligible:
            return False
        sent = TransactionalEmail.objects.filter(status="sent", sent_at__gte=day)
        if (sent.count() >= settings.TRANSACTIONAL_EMAIL_DAILY_CAP or
            sent.filter(recipient_fingerprint=item.recipient_fingerprint).count() >= settings.TRANSACTIONAL_EMAIL_RECIPIENT_DAILY_CAP or
            sent.filter(source_fingerprint=item.source_fingerprint).count() >= settings.TRANSACTIONAL_EMAIL_SOURCE_DAILY_CAP):
            return False
        item.status, item.attempts = "sending", item.attempts + 1
        item.save(update_fields=("status", "attempts", "updated_at"))
    subject, body = _content(item)
    try:
        message = EmailMultiAlternatives(subject, body, settings.TRANSACTIONAL_EMAIL_FROM, [item.recipient])
        if len(message.to) != 1 or message.cc or message.bcc or message.reply_to:
            raise RuntimeError("recipient policy rejected")
        message.send(fail_silently=False)
    except Exception:
        with transaction.atomic():
            failed = TransactionalEmail.objects.select_for_update().get(pk=item.pk)
            failed.status = "failed" if failed.attempts >= settings.TRANSACTIONAL_EMAIL_MAX_ATTEMPTS else "pending"
            failed.available_at = timezone.now() + timedelta(minutes=2 ** failed.attempts)
            failed.last_error = "delivery failed"
            failed.save(update_fields=("status", "available_at", "last_error", "updated_at"))
        return False
    TransactionalEmail.objects.filter(pk=item.pk).update(status="sent", sent_at=timezone.now(), last_error="")
    return True
