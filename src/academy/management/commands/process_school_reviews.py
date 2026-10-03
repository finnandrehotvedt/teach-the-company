from __future__ import annotations

import json
import re

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from academy.models import KnowledgeReview


def _editor(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_.@ -]", "", (value or "").strip())[:120]
    if not value:
        raise CommandError("--editor is required and must contain a safe editor identifier.")
    return value


def _lesson_versions(values: list[str]) -> dict[str, str]:
    result = {}
    for value in values:
        lesson_id, separator, version = value.partition("=")
        if not separator or not re.fullmatch(r"TTC-\d{3}", lesson_id.strip()) or not version.strip():
            raise CommandError("Each --lesson-version must use TTC-NNN=VERSION.")
        result[lesson_id.strip()] = version.strip()[:40]
    return result


class Command(BaseCommand):
    help = "Claim, decide and publish the private trusted-source editorial queue with release evidence."

    def add_arguments(self, parser):
        operation = parser.add_mutually_exclusive_group(required=True)
        operation.add_argument("--claim", action="store_true")
        operation.add_argument("--review-id", type=int)
        operation.add_argument("--publish-id", type=int)
        parser.add_argument("--editor", required=True)
        parser.add_argument("--limit", type=int, default=3)
        parser.add_argument("--decision", choices=("accepted", "rejected", "conflict"))
        parser.add_argument("--notes", default="")
        parser.add_argument("--commit", default="")
        parser.add_argument("--release", default="")
        parser.add_argument("--lesson-version", action="append", default=[])

    def handle(self, *args, **options):
        editor = _editor(options["editor"])
        if options["claim"]:
            self._claim(editor, options["limit"])
            return
        if options["review_id"]:
            self._review(editor, options["review_id"], options["decision"], options["notes"])
            return
        self._publish(
            editor,
            options["publish_id"],
            options["commit"],
            options["release"],
            _lesson_versions(options["lesson_version"]),
        )

    def _claim(self, editor, limit):
        claimed = []
        with transaction.atomic():
            rows = list(
                KnowledgeReview.objects.select_for_update(skip_locked=True)
                .filter(status=KnowledgeReview.Status.NEEDS_REVIEW, claimed_at__isnull=True)
                .order_by("detected_at", "id")[: max(1, min(limit, 20))]
            )
            now = timezone.now()
            for review in rows:
                review.status = KnowledgeReview.Status.IN_REVIEW
                review.claimed_by = editor
                review.claimed_at = now
                review.save(update_fields=("status", "claimed_by", "claimed_at"))
                claimed.append(
                    {
                        "id": review.id,
                        "source": review.source.source_key,
                        "lessons": review.source.lesson_ids,
                        "draft_prepared_by": review.draft_prepared_by,
                    }
                )
        self.stdout.write(json.dumps({"claimed": claimed, "count": len(claimed)}, sort_keys=True))

    def _review(self, editor, review_id, decision, notes):
        if not decision or not notes.strip():
            raise CommandError("--decision and non-empty --notes are required with --review-id.")
        with transaction.atomic():
            review = KnowledgeReview.objects.select_for_update().select_related("source").get(pk=review_id)
            if review.status != KnowledgeReview.Status.IN_REVIEW:
                raise CommandError("Only a claimed in-review item can receive an editorial decision.")
            if review.claimed_by != editor:
                raise CommandError("The editorial decision must use the same editor that claimed the item.")
            review.status = decision
            review.reviewed_by = editor
            review.review_notes = notes.strip()[:2000]
            review.reviewed_at = timezone.now()
            review.save()
        self.stdout.write(json.dumps({"id": review.id, "status": review.status, "reviewed_by": editor}, sort_keys=True))

    def _publish(self, editor, review_id, commit, release, lesson_versions):
        commit = commit.strip().lower()
        release = release.strip()
        if not re.fullmatch(r"[0-9a-f]{7,64}", commit):
            raise CommandError("--commit must be a 7-64 character lowercase hexadecimal Git commit.")
        if not release or not lesson_versions:
            raise CommandError("--release and at least one --lesson-version are required with --publish-id.")
        with transaction.atomic():
            review = KnowledgeReview.objects.select_for_update().select_related("source").get(pk=review_id)
            if review.status != KnowledgeReview.Status.ACCEPTED:
                raise CommandError("Only an accepted review can be linked to a published release.")
            if review.reviewed_by != editor:
                raise CommandError("Publication must use the same editor that accepted the review.")
            review.review_commit = commit
            review.publication_reference = release[:200]
            review.approved_lesson_versions = lesson_versions
            review.status = KnowledgeReview.Status.PUBLISHED
            try:
                review.save()
            except ValidationError as exc:
                raise CommandError("; ".join(exc.messages)) from exc
        self.stdout.write(
            json.dumps(
                {
                    "id": review.id,
                    "status": review.status,
                    "commit": review.review_commit,
                    "release": review.publication_reference,
                    "lesson_versions": review.approved_lesson_versions,
                },
                sort_keys=True,
            )
        )
