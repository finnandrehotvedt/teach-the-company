from django.contrib import admin
from django.utils import timezone

from .models import (
    AccessInvite,
    AccessRequest,
    AgentArtifact,
    ChallengeAttempt,
    LearningEvent,
    LearningSource,
    KnowledgeReview,
    ProjectAccessKey,
    ProjectHandoff,
    PublicInputEvent,
    PublicSuggestion,
    SourceRevision,
    TrustedKnowledgeSource,
    TrainingQuestion,
    TrainingProject,
    TransactionalEmail,
    WorkbookEntry,
)


class WorkbookEntryInline(admin.StackedInline):
    model = WorkbookEntry
    extra = 0
    fields = ("module_slug", "title", "response", "safe_to_share", "completed_at")
    readonly_fields = ("completed_at",)


class LearningSourceInline(admin.TabularInline):
    model = LearningSource
    extra = 0
    fields = ("logical_path", "kind", "status", "revision_number", "safe_to_share", "updated_at")
    readonly_fields = ("updated_at",)


class AgentArtifactInline(admin.TabularInline):
    model = AgentArtifact
    extra = 0
    fields = ("logical_path", "status", "revision_number", "safe_to_share", "updated_at")
    readonly_fields = ("updated_at",)


class TrainingQuestionInline(admin.TabularInline):
    model = TrainingQuestion
    extra = 0
    fields = ("prompt", "answer_kind", "status", "source", "answered_at")
    readonly_fields = ("answered_at",)


@admin.register(TrainingProject)
class TrainingProjectAdmin(admin.ModelAdmin):
    list_display = ("company_name", "role_title", "learner_name", "status", "publication_permission", "updated_at")
    list_filter = ("status", "publication_permission", "is_fictional_demo")
    search_fields = ("company_name", "role_title", "learner_name", "learner_email", "agent_name")
    readonly_fields = ("public_id", "owner_key_hash", "created_at", "updated_at")
    inlines = (LearningSourceInline, TrainingQuestionInline, AgentArtifactInline, WorkbookEntryInline)


@admin.register(ChallengeAttempt)
class ChallengeAttemptAdmin(admin.ModelAdmin):
    list_display = ("project", "outcome", "is_private_preview", "created_at")
    list_filter = ("outcome", "is_private_preview")
    search_fields = ("project__company_name", "prompt", "response")
    readonly_fields = ("source_fingerprint", "created_at")


@admin.register(WorkbookEntry)
class WorkbookEntryAdmin(admin.ModelAdmin):
    list_display = ("project", "module_slug", "title", "safe_to_share", "updated_at")
    list_filter = ("module_slug", "safe_to_share")
    search_fields = ("project__company_name", "title", "response")


@admin.register(LearningSource)
class LearningSourceAdmin(admin.ModelAdmin):
    list_display = ("logical_path", "project", "kind", "status", "revision_number", "safe_to_share", "updated_at")
    list_filter = ("kind", "status", "safe_to_share")
    search_fields = ("project__agent_name", "logical_path", "title", "content_text")
    readonly_fields = ("public_id", "checksum", "learned_at", "updated_at")


@admin.register(SourceRevision)
class SourceRevisionAdmin(admin.ModelAdmin):
    list_display = ("source", "number", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("source__logical_path", "change_note", "content_text")
    readonly_fields = ("checksum", "created_at")


@admin.register(AgentArtifact)
class AgentArtifactAdmin(admin.ModelAdmin):
    list_display = ("logical_path", "project", "status", "revision_number", "safe_to_share", "updated_at")
    list_filter = ("status", "safe_to_share")
    search_fields = ("project__agent_name", "logical_path", "title", "content")
    readonly_fields = ("public_id", "created_at", "updated_at")


@admin.register(LearningEvent)
class LearningEventAdmin(admin.ModelAdmin):
    list_display = ("project", "kind", "headline", "safe_to_share", "created_at")
    list_filter = ("kind", "safe_to_share")
    search_fields = ("project__agent_name", "headline", "detail")
    readonly_fields = ("created_at",)


@admin.register(TrainingQuestion)
class TrainingQuestionAdmin(admin.ModelAdmin):
    list_display = ("project", "prompt", "answer_kind", "status", "answered_at")
    list_filter = ("answer_kind", "status", "safe_to_share")
    search_fields = ("project__agent_name", "prompt", "answer_text")
    readonly_fields = ("public_id", "created_at", "answered_at")


@admin.register(AccessRequest)
class AccessRequestAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("name", "email", "use_case")
    readonly_fields = ("public_id", "source_fingerprint", "notification_eligible", "created_at")

    def save_model(self, request, obj, form, change):
        previous = AccessRequest.objects.filter(pk=obj.pk).values_list("status", flat=True).first() if change else None
        super().save_model(request, obj, form, change)
        if previous == AccessRequest.Status.REQUESTED and obj.status in {AccessRequest.Status.INVITED, AccessRequest.Status.CLOSED}:
            from .notifications import enqueue_outcome
            enqueue_outcome(obj)


@admin.register(PublicSuggestion)
class PublicSuggestionAdmin(admin.ModelAdmin):
    list_display = ("kind", "title", "status", "created_at", "reviewed_at")
    list_filter = ("kind", "status")
    search_fields = ("title", "detail", "source_url")
    readonly_fields = ("public_id", "source_fingerprint", "created_at", "updated_at")

    def save_model(self, request, obj, form, change):
        if change and "status" in form.changed_data:
            obj.reviewed_at = timezone.now()
        super().save_model(request, obj, form, change)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PublicInputEvent)
class PublicInputEventAdmin(admin.ModelAdmin):
    list_display = ("action", "created_at")
    list_filter = ("action",)
    readonly_fields = tuple(field.name for field in PublicInputEvent._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TrustedKnowledgeSource)
class TrustedKnowledgeSourceAdmin(admin.ModelAdmin):
    list_display = ("source_key", "publisher", "last_status", "last_checked_at", "active")
    list_filter = ("last_status", "active", "publisher")
    search_fields = ("source_key", "title", "publisher", "url")
    readonly_fields = ("source_key", "title", "publisher", "url", "lesson_ids", "last_checked_at", "last_content_hash", "last_final_url", "last_etag", "last_modified_header", "last_error_code", "created_at", "updated_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(KnowledgeReview)
class KnowledgeReviewAdmin(admin.ModelAdmin):
    list_display = ("source", "status", "draft_prepared_by", "claimed_by", "detected_at", "reviewed_at", "published_at")
    list_filter = ("status", "source__publisher")
    search_fields = (
        "source__source_key", "change_summary", "proposed_update", "claimed_by", "reviewed_by",
        "review_commit", "publication_reference",
    )
    readonly_fields = (
        "source", "previous_hash", "observed_hash", "evidence_excerpt", "draft_prepared_by",
        "draft_prepared_at", "claimed_at", "reviewed_at", "published_at", "detected_at",
    )

    def save_model(self, request, obj, form, change):
        previous = KnowledgeReview.objects.filter(pk=obj.pk).values_list("status", flat=True).first() if change else None
        if change and "status" in form.changed_data:
            editor = request.user.get_username()[:120] or "django-editor"
            if previous == KnowledgeReview.Status.NEEDS_REVIEW and not obj.claimed_at:
                obj.claimed_by = editor
                obj.claimed_at = timezone.now()
            if obj.status in {
                KnowledgeReview.Status.CONFLICT,
                KnowledgeReview.Status.ACCEPTED,
                KnowledgeReview.Status.REJECTED,
                KnowledgeReview.Status.PUBLISHED,
            }:
                obj.reviewed_by = editor
                obj.reviewed_at = timezone.now()
                if not obj.review_notes.strip():
                    obj.review_notes = "Decision recorded by the authenticated editorial owner in Django admin."
            if obj.status == KnowledgeReview.Status.PUBLISHED:
                obj.published_at = timezone.now()
        super().save_model(request, obj, form, change)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ProjectAccessKey)
class ProjectAccessKeyAdmin(admin.ModelAdmin):
    list_display = ("project", "purpose", "active", "created_at", "last_used_at")
    list_filter = ("purpose", "active")
    search_fields = ("project__agent_name", "project__learner_email")
    readonly_fields = ("token_hash", "created_at", "last_used_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ProjectHandoff)
class ProjectHandoffAdmin(admin.ModelAdmin):
    list_display = ("project", "expires_at", "used_at", "created_at")
    search_fields = ("project__agent_name", "project__learner_email")
    readonly_fields = ("project", "access_key", "token_hash", "expires_at", "used_at", "created_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TransactionalEmail)
class TransactionalEmailAdmin(admin.ModelAdmin):
    list_display = ("kind", "status", "attempts", "created_at", "sent_at")
    list_filter = ("kind", "status")
    readonly_fields = tuple(field.name for field in TransactionalEmail._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AccessInvite)
class AccessInviteAdmin(admin.ModelAdmin):
    list_display = ("label", "email", "active", "use_count", "max_uses", "expires_at", "created_at")
    list_filter = ("active",)
    search_fields = ("label", "email")
    readonly_fields = ("public_id", "token_hash", "use_count", "created_at")

    def has_add_permission(self, request):
        # Plain invitation tokens are intentionally generated and shown once by
        # the create_invite command; the admin stores only their hashes.
        return False
