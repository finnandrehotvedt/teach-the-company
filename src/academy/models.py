from __future__ import annotations

import hashlib
import re
import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.text import get_valid_filename
from django.utils import timezone

from .curriculum import MODULES


class TrainingProject(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        TRAINING = "training", "Training"
        REVIEW = "review", "Ready for review"
        PUBLISHED = "published", "Published"
        RETIRED = "retired", "Retired"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    public_slug = models.SlugField(max_length=150, unique=True, null=True, blank=True)
    company_name = models.CharField(max_length=120)
    learner_name = models.CharField(max_length=100)
    learner_email = models.EmailField(help_text="Private. Never rendered publicly.")
    role_title = models.CharField(max_length=140)
    agent_name = models.CharField(max_length=100)
    mission = models.TextField(max_length=700)
    public_title = models.CharField(max_length=160, blank=True)
    public_summary = models.TextField(max_length=500, blank=True)
    owner_key_hash = models.CharField(max_length=64, editable=False)
    creator_fingerprint = models.CharField(max_length=64, db_index=True, blank=True, editable=False)
    publication_permission = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    is_fictional_demo = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.company_name} — {self.role_title}"

    @staticmethod
    def hash_owner_key(key: str) -> str:
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    @property
    def completed_count(self) -> int:
        return self.entries.count()

    @property
    def progress_percent(self) -> int:
        return round((self.completed_count / len(MODULES)) * 100)

    @property
    def public_url(self) -> str:
        if not self.public_slug:
            return ""
        return reverse("academy:challenge", kwargs={"slug": self.public_slug})

    @property
    def source_count(self) -> int:
        return self.sources.count()

    @property
    def artifact_count(self) -> int:
        return self.artifacts.count()

    @property
    def open_question_count(self) -> int:
        return self.training_questions.filter(status=TrainingQuestion.Status.OPEN).count()


def private_source_path(instance, filename: str) -> str:
    safe_name = get_valid_filename(filename)[:120] or "source"
    return f"workspace-sources/{instance.project.public_id}/{uuid.uuid4().hex}-{safe_name}"


class LearningSource(models.Model):
    class Kind(models.TextChoices):
        NOTE = "note", "Note"
        LINK = "link", "Link"
        DOCUMENT = "document", "Document"
        EXAMPLE = "example", "Example"
        PROCEDURE = "procedure", "Procedure"
        CORRECTION = "correction", "Correction"
        TEST = "test", "Test"

    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        APPROVED = "approved", "Approved"
        ACTIVE = "active", "Active"
        RETIRED = "retired", "Retired"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    project = models.ForeignKey(TrainingProject, on_delete=models.CASCADE, related_name="sources")
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.NOTE)
    title = models.CharField(max_length=160)
    logical_path = models.CharField(max_length=240)
    source_url = models.URLField(max_length=1000, blank=True)
    content_text = models.TextField(blank=True)
    uploaded_file = models.FileField(upload_to=private_source_path, blank=True)
    original_filename = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=120, blank=True)
    byte_size = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROPOSED)
    revision_number = models.PositiveIntegerField(default=1)
    checksum = models.CharField(max_length=64, blank=True, editable=False)
    safe_to_share = models.BooleanField(default=False)
    learned_at = models.DateTimeField(default=timezone.now)
    inspected_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("learned_at", "id")
        constraints = [
            models.UniqueConstraint(fields=("project", "logical_path"), name="unique_project_learning_path")
        ]

    def __str__(self) -> str:
        return f"{self.project.agent_name}: {self.title}"


class SourceRevision(models.Model):
    source = models.ForeignKey(LearningSource, on_delete=models.CASCADE, related_name="revisions")
    number = models.PositiveIntegerField()
    content_text = models.TextField(blank=True)
    checksum = models.CharField(max_length=64)
    change_note = models.CharField(max_length=240, blank=True)
    status = models.CharField(max_length=20, choices=LearningSource.Status.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-number",)
        constraints = [
            models.UniqueConstraint(fields=("source", "number"), name="unique_source_revision")
        ]

    def __str__(self) -> str:
        return f"{self.source.logical_path} @ v{self.number}"


class TrainingQuestion(models.Model):
    class AnswerKind(models.TextChoices):
        YES_NO = "yes_no", "Yes or no"
        EXPLANATION = "explanation", "Explanation"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ANSWERED = "answered", "Answered"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    project = models.ForeignKey(
        TrainingProject,
        on_delete=models.CASCADE,
        related_name="training_questions",
    )
    source = models.ForeignKey(
        LearningSource,
        on_delete=models.SET_NULL,
        related_name="training_questions",
        null=True,
        blank=True,
    )
    prompt = models.CharField(max_length=500)
    detail = models.TextField(max_length=1200, blank=True)
    answer_kind = models.CharField(
        max_length=20,
        choices=AnswerKind.choices,
        default=AnswerKind.EXPLANATION,
    )
    quick_replies = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    answer_text = models.TextField(max_length=3000, blank=True)
    safe_to_share = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    answered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("created_at", "id")

    def __str__(self) -> str:
        return f"{self.project.agent_name}: {self.prompt}"


class AgentArtifact(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        REVIEW = "review", "Needs approval"
        APPROVED = "approved", "Approved"
        PUBLISHED = "published", "Published"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    project = models.ForeignKey(TrainingProject, on_delete=models.CASCADE, related_name="artifacts")
    title = models.CharField(max_length=180)
    artifact_type = models.CharField(max_length=60, default="answer")
    logical_path = models.CharField(max_length=240)
    revision_number = models.PositiveIntegerField(default=1)
    content = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    source_titles = models.JSONField(default=list, blank=True)
    safe_to_share = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.project.agent_name}: {self.title}"


class LearningEvent(models.Model):
    class Kind(models.TextChoices):
        SOURCE = "source", "Source learned"
        CORRECTION = "correction", "Correction learned"
        TEST = "test", "Test completed"
        ARTIFACT = "artifact", "Artifact created"
        APPROVAL = "approval", "Human approval"
        PUBLICATION = "publication", "Published"
        QUESTION = "question", "Agent asked"
        ANSWER = "answer", "Teacher answered"

    project = models.ForeignKey(TrainingProject, on_delete=models.CASCADE, related_name="learning_events")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    headline = models.CharField(max_length=180)
    detail = models.TextField(max_length=1200, blank=True)
    related_source = models.ForeignKey(
        LearningSource,
        on_delete=models.SET_NULL,
        related_name="events",
        null=True,
        blank=True,
    )
    related_artifact = models.ForeignKey(
        AgentArtifact,
        on_delete=models.SET_NULL,
        related_name="events",
        null=True,
        blank=True,
    )
    safe_to_share = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")

    def __str__(self) -> str:
        return f"{self.project.agent_name}: {self.headline}"


class AccessRequest(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        INVITED = "invited", "Invited"
        CLOSED = "closed", "Closed"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=100)
    email = models.EmailField()
    company_name = models.CharField(max_length=120, blank=True)
    use_case = models.TextField(max_length=700)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUESTED)
    source_fingerprint = models.CharField(max_length=64, db_index=True, editable=False)
    notification_eligible = models.BooleanField(default=False, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.name} — {self.email}"


class PublicInputEvent(models.Model):
    action = models.CharField(max_length=32)
    actor_hash = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=("action", "actor_hash", "created_at"), name="public_input_actor_time")]


class PublicSuggestion(models.Model):
    class Kind(models.TextChoices):
        MISSING_TOPIC = "missing_topic", "Missing topic"
        CORRECTION = "correction", "Correction"
        EXPERIENCE = "experience", "Practical experience"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        IN_REVIEW = "in_review", "In review"
        ACCEPTED = "accepted", "Accepted for editorial work"
        DECLINED = "declined", "Declined"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    kind = models.CharField(max_length=24, choices=Kind.choices)
    title = models.CharField(max_length=160)
    detail = models.TextField(max_length=2000)
    source_url = models.URLField(max_length=1000, blank=True)
    source_fingerprint = models.CharField(max_length=64, db_index=True, editable=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    moderator_note = models.TextField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")

    def __str__(self) -> str:
        return f"{self.get_kind_display()}: {self.title}"


class TrustedKnowledgeSource(models.Model):
    class CheckStatus(models.TextChoices):
        NEVER = "never", "Not checked"
        BASELINE = "baseline", "Baseline recorded"
        OK = "ok", "No change detected"
        CHANGED = "changed", "Change needs review"
        ERROR = "error", "Check failed"

    source_key = models.SlugField(max_length=120, unique=True)
    title = models.CharField(max_length=240)
    publisher = models.CharField(max_length=160)
    url = models.URLField(max_length=1000, unique=True)
    lesson_ids = models.JSONField(default=list, blank=True)
    active = models.BooleanField(default=True)
    review_interval_days = models.PositiveSmallIntegerField(default=1)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_content_hash = models.CharField(max_length=64, blank=True)
    last_final_url = models.URLField(max_length=1000, blank=True)
    last_etag = models.CharField(max_length=500, blank=True)
    last_modified_header = models.CharField(max_length=500, blank=True)
    last_status = models.CharField(max_length=16, choices=CheckStatus.choices, default=CheckStatus.NEVER)
    last_error_code = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("publisher", "title")

    def __str__(self) -> str:
        return f"{self.publisher}: {self.title}"


class KnowledgeReview(models.Model):
    class Status(models.TextChoices):
        NEEDS_REVIEW = "needs_review", "Needs editorial review"
        IN_REVIEW = "in_review", "Claimed for editorial review"
        CONFLICT = "conflict", "Conflicting evidence"
        ACCEPTED = "accepted", "Accepted for source update"
        REJECTED = "rejected", "Rejected"
        PUBLISHED = "published", "Published in a reviewed release"

    source = models.ForeignKey(TrustedKnowledgeSource, on_delete=models.PROTECT, related_name="reviews")
    previous_hash = models.CharField(max_length=64, blank=True)
    observed_hash = models.CharField(max_length=64)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEEDS_REVIEW, db_index=True)
    evidence_excerpt = models.TextField(max_length=4000, blank=True)
    change_summary = models.TextField(max_length=1000, blank=True)
    conflict_flags = models.JSONField(default=list, blank=True)
    proposed_update = models.TextField(max_length=6000, blank=True)
    draft_prepared_by = models.CharField(max_length=24, blank=True)
    draft_prepared_at = models.DateTimeField(null=True, blank=True)
    claimed_by = models.CharField(max_length=120, blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.CharField(max_length=120, blank=True)
    review_notes = models.TextField(max_length=2000, blank=True)
    review_commit = models.CharField(max_length=64, blank=True)
    approved_lesson_versions = models.JSONField(default=dict, blank=True)
    publication_reference = models.CharField(max_length=200, blank=True)
    detected_at = models.DateTimeField(auto_now_add=True, db_index=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-detected_at", "-id")
        constraints = [
            models.UniqueConstraint(fields=("source", "observed_hash"), name="unique_source_observed_hash")
        ]

    def __str__(self) -> str:
        return f"{self.source.source_key}: {self.get_status_display()}"

    def clean(self):
        super().clean()
        if self.status == self.Status.IN_REVIEW and (not self.claimed_by.strip() or not self.claimed_at):
            raise ValidationError("A claimed review requires an editor and claim time.")
        if self.status in {self.Status.CONFLICT, self.Status.ACCEPTED, self.Status.REJECTED, self.Status.PUBLISHED}:
            if not self.claimed_by.strip() or not self.claimed_at:
                raise ValidationError("Review decisions require a prior editorial claim.")
            if not self.reviewed_by.strip() or not self.reviewed_at or not self.review_notes.strip():
                raise ValidationError("Review decisions require a named editor, review time and notes.")
        if self.status != self.Status.PUBLISHED:
            return
        if not self.pk:
            raise ValidationError("A review must be accepted before it can be published.")
        previous = type(self).objects.filter(pk=self.pk).values_list("status", flat=True).first()
        if previous != self.Status.ACCEPTED:
            raise ValidationError("Only an accepted editorial review can be marked published.")
        if not self.publication_reference.strip():
            raise ValidationError("Record the reviewed release or commit before publication.")
        if not re.fullmatch(r"[0-9a-f]{7,64}", self.review_commit.strip().lower()):
            raise ValidationError("Record the Git commit containing the reviewed lesson update.")
        if not isinstance(self.approved_lesson_versions, dict) or not self.approved_lesson_versions:
            raise ValidationError("Record at least one approved lesson version before publication.")
        allowed_lessons = set(self.source.lesson_ids or ())
        if not set(self.approved_lesson_versions).issubset(allowed_lessons):
            raise ValidationError("Approved lesson versions must belong to the changed source.")
        if not all(str(value).strip() for value in self.approved_lesson_versions.values()):
            raise ValidationError("Every approved lesson must include its released version.")

    def save(self, *args, **kwargs):
        self.full_clean()
        if self.status in {self.Status.ACCEPTED, self.Status.REJECTED, self.Status.PUBLISHED} and not self.reviewed_at:
            self.reviewed_at = timezone.now()
        if self.status == self.Status.PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        result = super().save(*args, **kwargs)
        if self.status == self.Status.PUBLISHED:
            TrustedKnowledgeSource.objects.filter(pk=self.source_id).update(
                last_content_hash=self.observed_hash,
                last_status=TrustedKnowledgeSource.CheckStatus.OK,
            )
        return result


class TransactionalEmail(models.Model):
    class Kind(models.TextChoices):
        RECEIPT = "receipt", "Request receipt"
        OUTCOME = "outcome", "Manual-review outcome"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    access_request = models.ForeignKey(AccessRequest, on_delete=models.CASCADE, related_name="transactional_emails")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    outcome = models.CharField(max_length=20, blank=True)
    recipient = models.EmailField()
    recipient_fingerprint = models.CharField(max_length=64, db_index=True, editable=False)
    source_fingerprint = models.CharField(max_length=64, db_index=True, editable=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    available_at = models.DateTimeField(default=timezone.now, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at", "id")
        constraints = [models.UniqueConstraint(fields=("access_request", "kind"), name="unique_transactional_email_kind")]


class AccessInvite(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    label = models.CharField(max_length=120)
    email = models.EmailField(blank=True)
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    max_uses = models.PositiveSmallIntegerField(default=1)
    use_count = models.PositiveSmallIntegerField(default=0)
    active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def can_use(self) -> bool:
        if not self.active or self.use_count >= self.max_uses:
            return False
        return not self.expires_at or self.expires_at > timezone.now()

    def __str__(self) -> str:
        return self.label


class ProjectAccessKey(models.Model):
    class Purpose(models.TextChoices):
        INITIAL = "initial", "Initial browser"
        HANDOFF = "handoff", "Domain handoff"
        RECOVERY = "recovery", "Owner recovery"

    project = models.ForeignKey(TrainingProject, on_delete=models.CASCADE, related_name="access_keys")
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    purpose = models.CharField(max_length=20, choices=Purpose.choices, default=Purpose.INITIAL)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def __str__(self) -> str:
        return f"{self.project.agent_name} — {self.get_purpose_display()}"


class ProjectHandoff(models.Model):
    project = models.ForeignKey(TrainingProject, on_delete=models.CASCADE, related_name="handoffs")
    access_key = models.OneToOneField(ProjectAccessKey, on_delete=models.CASCADE, related_name="handoff")
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def can_use(self) -> bool:
        return self.used_at is None and self.access_key.active and self.expires_at > timezone.now()

    def __str__(self) -> str:
        return f"{self.project.agent_name} — domain handoff"


class WorkbookEntry(models.Model):
    project = models.ForeignKey(TrainingProject, on_delete=models.CASCADE, related_name="entries")
    module_slug = models.SlugField(max_length=80)
    title = models.CharField(max_length=150)
    response = models.TextField(max_length=3000)
    safe_to_share = models.BooleanField(
        default=False,
        help_text="Only reviewed entries with this flag may appear in a public challenge.",
    )
    completed_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("completed_at",)
        constraints = [
            models.UniqueConstraint(fields=("project", "module_slug"), name="unique_project_module")
        ]

    def __str__(self) -> str:
        return f"{self.project.company_name}: {self.module_slug}"


class ChallengeAttempt(models.Model):
    class Outcome(models.TextChoices):
        LEARNED = "learned", "Learned procedure"
        APPROVAL = "approval", "Human approval required"
        NOT_LEARNED = "not_learned", "Not learned yet"

    project = models.ForeignKey(TrainingProject, on_delete=models.CASCADE, related_name="challenges")
    prompt = models.TextField(max_length=600)
    outcome = models.CharField(max_length=20, choices=Outcome.choices)
    response = models.TextField(max_length=1200)
    evidence_titles = models.JSONField(default=list, blank=True)
    source_fingerprint = models.CharField(max_length=64, db_index=True)
    is_private_preview = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.project.agent_name}: {self.get_outcome_display()}"
