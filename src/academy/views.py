from __future__ import annotations

import json
import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.db.models import Count
from django.http import FileResponse, Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.utils.text import get_valid_filename, slugify
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from xml.sax.saxutils import escape as xml_escape

from .agent_runtime import AgentUnavailable, answer_agent, connected_backend
from .curriculum import MODULES, MODULE_BY_SLUG
from .evaluator import evaluate
from .forms import (
    AccessRequestForm,
    AgentQuestionForm,
    ChallengeForm,
    LearningSourceForm,
    PublicSuggestionForm,
    SchoolCompositionForm,
    StartProjectForm,
    TrainingAnswerForm,
    WorkbookEntryForm,
)
from .exporter import build_training_zip
from .ingestion import create_agent_framework, prepare_source, record_revision
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
    TrustedKnowledgeSource,
    TrainingQuestion,
    TrainingProject,
    WorkbookEntry,
)
from .security import source_fingerprint
from .training import answer_training_question, inspect_unprocessed_files
from .hosts import is_agent_host
from .public_content import GUIDES
from .composer import PRESETS, compose
from .school_content import LESSONS, LESSON_BY_ID, LESSON_BY_SLUG
from .manual_content import MANUALS, MANUAL_BY_SLUG
from .project_library import PUBLISHED_PROJECTS, PUBLISHED_PROJECT_BY_SLUG


@require_GET
def favicon(request, filename):
    response = redirect(static(f"img/{filename}"), permanent=True)
    response["Cache-Control"] = "public, max-age=86400"
    return response


@require_GET
def mobile_icon(request, filename):
    icon_path = settings.BASE_DIR / "static" / "img" / filename
    response = FileResponse(icon_path.open("rb"), content_type="image/png")
    response["Cache-Control"] = "public, max-age=86400"
    return response


@require_GET
def site_manifest(request):
    response = JsonResponse(
        {
            "name": "Teach the Company",
            "short_name": "Teach",
            "description": "A practical school and private training center for one AI agent.",
            "start_url": "/",
            "scope": "/",
            "display": "standalone",
            "background_color": "#171c36",
            "theme_color": "#171c36",
            "icons": [
                {
                    "src": static("img/icon-192.png"),
                    "sizes": "192x192",
                    "type": "image/png",
                    "purpose": "any",
                },
                {
                    "src": static("img/icon-512.png"),
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "any",
                },
            ],
        },
        content_type="application/manifest+json",
    )
    response["Cache-Control"] = "public, max-age=86400"
    return response


def _owned_tokens(request) -> dict[str, str]:
    value = request.session.get(settings.STUDIO_SESSION_KEY, {})
    return value if isinstance(value, dict) else {}


def _remember_project(request, project: TrainingProject, token: str) -> None:
    owned = _owned_tokens(request).copy()
    owned[str(project.public_id)] = token
    request.session[settings.STUDIO_SESSION_KEY] = owned
    request.session.modified = True


def _owned_project(request, public_id) -> TrainingProject:
    project = get_object_or_404(TrainingProject, public_id=public_id)
    token = _owned_tokens(request).get(str(project.public_id), "")
    token_hash = TrainingProject.hash_owner_key(token) if token else ""
    has_access_keys = project.access_keys.exists()
    legacy_match = token and not has_access_keys and secrets.compare_digest(token_hash, project.owner_key_hash)
    key_match = token and ProjectAccessKey.objects.filter(
        project=project, token_hash=token_hash, active=True
    ).exists()
    if not legacy_match and not key_match:
        raise PermissionDenied("This private agent belongs to another browser session.")
    return project


def _module_rows(project: TrainingProject):
    entries = {entry.module_slug: entry for entry in project.entries.all()}
    return [(module, entries.get(module.slug)) for module in MODULES]


def _studio_context(project, *, source_form=None, question_form=None, latest_artifact=None):
    return {
        "project": project,
        "sources": project.sources.prefetch_related("revisions").all(),
        "open_questions": project.training_questions.select_related("source").filter(
            status=TrainingQuestion.Status.OPEN
        ),
        "answered_questions": project.training_questions.select_related("source").filter(
            status=TrainingQuestion.Status.ANSWERED
        ).order_by("-answered_at")[:8],
        "unprocessed_count": project.sources.filter(inspected_at__isnull=True).count(),
        "events": project.learning_events.select_related("related_source", "related_artifact")[:30],
        "artifacts": project.artifacts.all()[:20],
        "source_form": source_form or LearningSourceForm(),
        "question_form": question_form or AgentQuestionForm(),
        "latest_artifact": latest_artifact,
        "agent_backend": settings.AGENT_BACKEND,
        "agent_connected": connected_backend(),
    }


@require_GET
def home(request):
    if is_agent_host(request):
        return render(request, "academy/agent_home.html")
    public_projects = TrainingProject.objects.filter(
        status=TrainingProject.Status.PUBLISHED,
        is_fictional_demo=True,
    ).order_by("created_at")[:6]
    return render(request, "academy/home.html", {"public_projects": public_projects})


@require_GET
def demos(request):
    projects = TrainingProject.objects.filter(
        status=TrainingProject.Status.PUBLISHED,
        is_fictional_demo=True,
    ).order_by("created_at")
    return render(request, "academy/demos.html", {"projects": projects})


@require_GET
def curriculum(request):
    return render(request, "academy/curriculum.html")


@require_GET
def self_host(request):
    return render(
        request,
        "academy/self_host.html",
        {
            "source_repository_url": settings.SOURCE_REPOSITORY_URL,
            "github_source_repository_url": settings.GITHUB_SOURCE_REPOSITORY_URL,
            "manuals_repository_url": settings.PUBLIC_MANUALS_REPOSITORY_URL,
        },
    )


@require_http_methods(["GET", "POST"])
def request_access(request):
    form = AccessRequestForm(request.POST or None)
    rate_limited = False
    if request.method == "POST" and form.is_valid():
        fingerprint = source_fingerprint(request, "access-request")
        since = timezone.now() - timedelta(hours=1)
        recent = AccessRequest.objects.filter(source_fingerprint=fingerprint, created_at__gte=since).count()
        recipient_since = timezone.now() - timedelta(days=1)
        recipient_recent = AccessRequest.objects.filter(email__iexact=form.cleaned_data["email"], created_at__gte=recipient_since).count()
        if recent >= settings.ACCESS_REQUEST_LIMIT_PER_HOUR or recipient_recent >= settings.ACCESS_REQUEST_LIMIT_PER_RECIPIENT_PER_DAY:
            rate_limited = True
            messages.error(request, "This browser has reached the hourly request limit. Try again later.")
        else:
            from .notifications import enqueue_receipt
            with transaction.atomic():
                access_request = form.save(commit=False)
                access_request.company_name = ""
                access_request.source_fingerprint = fingerprint
                access_request.notification_eligible = settings.TRANSACTIONAL_NOTIFICATIONS_ENABLED
                access_request.save()
                enqueue_receipt(access_request)
            return render(request, "academy/access_requested.html", {"access_request": access_request})
    return render(
        request,
        "academy/request_access.html",
        {"form": form},
        status=429 if rate_limited else 200,
    )


def _create_private_agent(request, invite_token: str | None = None):
    invite = None
    if invite_token:
        invite = AccessInvite.objects.filter(token_hash=AccessInvite.hash_token(invite_token)).first()
        if not invite or not invite.can_use():
            raise Http404("This invitation is unavailable.")
    elif not settings.OPEN_SIGNUP:
        return redirect("academy:request_access")

    initial = {"learner_email": invite.email} if invite and invite.email else None
    form = StartProjectForm(request.POST or None, initial=initial)
    rate_limited = False
    if request.method == "POST" and form.is_valid():
        fingerprint = source_fingerprint(request, "start")
        since = timezone.now() - timedelta(hours=1)
        recent = TrainingProject.objects.filter(creator_fingerprint=fingerprint, created_at__gte=since).count()
        if recent >= settings.START_LIMIT_PER_HOUR:
            rate_limited = True
            messages.error(request, "This browser has reached the hourly agent limit. Try again later.")
        else:
            with transaction.atomic():
                if invite_token:
                    invite = AccessInvite.objects.select_for_update().get(
                        token_hash=AccessInvite.hash_token(invite_token)
                    )
                    if not invite.can_use():
                        raise Http404("This invitation is unavailable.")
                owner_token = secrets.token_urlsafe(32)
                project = form.save(commit=False)
                project.company_name = f"{project.learner_name}'s private agent"
                project.role_title = "Privately taught agent"
                project.mission = "Training mode. No concrete task has been assigned."
                project.owner_key_hash = TrainingProject.hash_owner_key(owner_token)
                project.creator_fingerprint = fingerprint
                project.status = TrainingProject.Status.TRAINING
                project.save()
                ProjectAccessKey.objects.create(
                    project=project,
                    token_hash=TrainingProject.hash_owner_key(owner_token),
                    purpose=ProjectAccessKey.Purpose.INITIAL,
                )
                framework_files = create_agent_framework(project)
                LearningEvent.objects.create(
                    project=project,
                    kind=LearningEvent.Kind.SOURCE,
                    headline="Training framework created",
                    detail="AGENTS.md, structured YAML rules, and the cognitive-memory map are ready to inspect.",
                    related_source=framework_files[0],
                )
                if invite:
                    invite.use_count += 1
                    invite.save(update_fields=("use_count",))
            _remember_project(request, project, owner_token)
            messages.success(request, "Training mode is ready. Add files, then process them when you want the agent to inspect them.")
            return redirect("academy:studio", public_id=project.public_id)
    return render(
        request,
        "academy/start.html",
        {"form": form, "invite": invite, "open_signup": settings.OPEN_SIGNUP},
        status=429 if rate_limited else 200,
    )


@require_http_methods(["GET", "POST"])
def start(request):
    return _create_private_agent(request)


@require_http_methods(["GET", "POST"])
def join(request, token):
    return _create_private_agent(request, token)


@require_POST
def create_handoff(request, public_id):
    project = _owned_project(request, public_id)
    if not settings.AGENT_SITE_LIVE:
        messages.info(request, "The agent-domain handoff is not live yet.")
        return redirect("academy:studio", public_id=project.public_id)
    token = secrets.token_urlsafe(32)
    token_hash = ProjectAccessKey.hash_token(token)
    with transaction.atomic():
        access_key = ProjectAccessKey.objects.create(
            project=project,
            token_hash=token_hash,
            purpose=ProjectAccessKey.Purpose.HANDOFF,
        )
        ProjectHandoff.objects.create(
            project=project,
            access_key=access_key,
            token_hash=token_hash,
            expires_at=timezone.now() + timedelta(minutes=10),
        )
    target = settings.AGENT_SITE_ORIGIN + reverse("academy:accept_handoff", kwargs={"token": token})
    return redirect(target)


@require_GET
def accept_handoff(request, token):
    token_hash = ProjectAccessKey.hash_token(token)
    with transaction.atomic():
        handoff = ProjectHandoff.objects.select_for_update().select_related("project", "access_key").filter(
            token_hash=token_hash
        ).first()
        if not handoff or not handoff.can_use():
            raise Http404("This handoff is unavailable.")
        handoff.used_at = timezone.now()
        handoff.save(update_fields=("used_at",))
        handoff.access_key.last_used_at = handoff.used_at
        handoff.access_key.save(update_fields=("last_used_at",))
        project = handoff.project
    _remember_project(request, project, token)
    messages.success(request, "This browser now owns the same private classroom on the agent domain.")
    return redirect("academy:studio", public_id=project.public_id)


@require_GET
def studio(request, public_id):
    project = _owned_project(request, public_id)
    return render(request, "academy/studio.html", _studio_context(project))


@require_POST
def teach_agent(request, public_id):
    project = _owned_project(request, public_id)
    form = LearningSourceForm(request.POST, request.FILES)
    if form.is_valid():
        source = form.save(commit=False)
        try:
            prepare_source(source, project, form.cleaned_data.get("uploaded_file"))
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            source.save()
            record_revision(source, "Lesson proposed")
            LearningEvent.objects.create(
                project=project,
                kind=LearningEvent.Kind.CORRECTION if source.kind == LearningSource.Kind.CORRECTION else LearningEvent.Kind.SOURCE,
                headline=f"Proposed {source.logical_path}",
                detail="The file is versioned and waiting for teacher approval before the agent may use it.",
                related_source=source,
            )
            messages.success(request, f"{source.logical_path} was added. Process the files when you are ready for questions.")
            return redirect("academy:studio", public_id=project.public_id)
    return render(request, "academy/studio.html", _studio_context(project, source_form=form), status=400)


@require_POST
def source_action(request, public_id, source_id):
    project = _owned_project(request, public_id)
    source = get_object_or_404(LearningSource, public_id=source_id, project=project)
    action = request.POST.get("action")
    if action == "approve" and source.status == LearningSource.Status.PROPOSED:
        source.status = LearningSource.Status.ACTIVE
        source.revision_number += 1
        source.save(update_fields=("status", "revision_number", "updated_at"))
        record_revision(source, "Teacher approved and activated this file")
        LearningEvent.objects.create(
            project=project,
            kind=LearningEvent.Kind.APPROVAL,
            headline=f"Approved {source.logical_path}",
            detail=f"Version {source.revision_number} is now active training for the agent.",
            related_source=source,
        )
        messages.success(request, f"{source.logical_path} is now active.")
    elif action == "retire" and source.logical_path != "AGENTS.md":
        source.status = LearningSource.Status.RETIRED
        source.revision_number += 1
        source.save(update_fields=("status", "revision_number", "updated_at"))
        record_revision(source, "Teacher retired this file")
        LearningEvent.objects.create(
            project=project,
            kind=LearningEvent.Kind.APPROVAL,
            headline=f"Retired {source.logical_path}",
            detail="The agent will no longer use this file.",
            related_source=source,
        )
        messages.success(request, f"{source.logical_path} was retired.")
    return redirect("academy:studio", public_id=project.public_id)


@require_POST
def process_training(request, public_id):
    project = _owned_project(request, public_id)
    try:
        file_count, question_count = inspect_unprocessed_files(project)
    except AgentUnavailable as exc:
        messages.error(request, str(exc))
        return HttpResponseRedirect(reverse("academy:studio", kwargs={"public_id": project.public_id}) + "#agent-questions")
    if not file_count:
        messages.info(request, "All current files have already been processed.")
    elif question_count:
        messages.success(
            request,
            f"Inspected {file_count} file{'s' if file_count != 1 else ''} and found {question_count} point{'s' if question_count != 1 else ''} to clarify.",
        )
    else:
        messages.success(request, f"Inspected {file_count} file{'s' if file_count != 1 else ''}; no new questions were needed.")
    return HttpResponseRedirect(reverse("academy:studio", kwargs={"public_id": project.public_id}) + "#agent-questions")


@require_POST
def answer_training(request, public_id, question_id):
    project = _owned_project(request, public_id)
    question = get_object_or_404(TrainingQuestion, public_id=question_id, project=project)
    form = TrainingAnswerForm(request.POST)
    if form.is_valid():
        try:
            memory_file = answer_training_question(question, form.cleaned_data["answer"])
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"Your answer is now visible memory in {memory_file.logical_path}.")
    else:
        messages.error(request, "Write an explanation or choose a quick answer.")
    return HttpResponseRedirect(reverse("academy:studio", kwargs={"public_id": project.public_id}) + "#agent-questions")


@require_POST
def ask_agent(request, public_id):
    project = _owned_project(request, public_id)
    form = AgentQuestionForm(request.POST)
    if form.is_valid():
        answer = answer_agent(form.cleaned_data["prompt"], project.sources)
        path_stem = slugify(form.cleaned_data["prompt"])[:55] or "agent-draft"
        artifact = AgentArtifact.objects.create(
            project=project,
            title=form.cleaned_data["prompt"][:180],
            artifact_type="agent-draft",
            logical_path=f"outputs/{path_stem}-{secrets.token_hex(3)}.md",
            content=answer.text,
            status=AgentArtifact.Status.REVIEW,
            source_titles=answer.source_titles,
        )
        LearningEvent.objects.create(
            project=project,
            kind=LearningEvent.Kind.ARTIFACT,
            headline=f"Created {artifact.logical_path}",
            detail=f"Generated in {answer.mode} mode from {len(answer.source_titles)} approved file(s); waiting for review.",
            related_artifact=artifact,
        )
        return HttpResponseRedirect(reverse("academy:studio", kwargs={"public_id": project.public_id}) + "#agent-desk")
    return render(request, "academy/studio.html", _studio_context(project, question_form=form), status=400)


@require_POST
def artifact_action(request, public_id, artifact_id):
    project = _owned_project(request, public_id)
    artifact = get_object_or_404(AgentArtifact, public_id=artifact_id, project=project)
    if request.POST.get("action") == "approve" and artifact.status in {
        AgentArtifact.Status.DRAFT,
        AgentArtifact.Status.REVIEW,
    }:
        artifact.status = AgentArtifact.Status.APPROVED
        artifact.revision_number += 1
        artifact.save(update_fields=("status", "revision_number", "updated_at"))
        LearningEvent.objects.create(
            project=project,
            kind=LearningEvent.Kind.APPROVAL,
            headline=f"Approved {artifact.logical_path}",
            detail=f"Version {artifact.revision_number} was approved by the teacher. It was not published or sent.",
            related_artifact=artifact,
        )
        messages.success(request, "Draft approved. Nothing was published or sent.")
    return HttpResponseRedirect(reverse("academy:studio", kwargs={"public_id": project.public_id}) + "#agent-desk")


@require_GET
def source_download(request, public_id, source_id):
    project = _owned_project(request, public_id)
    source = get_object_or_404(LearningSource, public_id=source_id, project=project)
    response = HttpResponse(source.content_text, content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{get_valid_filename(source.logical_path.replace("/", "-"))}"'
    return response


@require_GET
def source_original_download(request, public_id, source_id):
    project = _owned_project(request, public_id)
    source = get_object_or_404(LearningSource, public_id=source_id, project=project)
    if not source.uploaded_file:
        raise Http404("This source has no original upload.")
    return FileResponse(
        source.uploaded_file.open("rb"),
        as_attachment=True,
        filename=source.original_filename or get_valid_filename(source.title),
    )


@require_GET
def source_view(request, public_id, source_id):
    project = _owned_project(request, public_id)
    source = get_object_or_404(
        LearningSource.objects.prefetch_related("revisions", "training_questions"),
        public_id=source_id,
        project=project,
    )
    return render(request, "academy/source_detail.html", {"project": project, "source": source})


@require_GET
def export_training(request, public_id):
    project = _owned_project(request, public_id)
    archive, filename = build_training_zip(project)
    return FileResponse(archive, as_attachment=True, filename=filename, content_type="application/zip")


@require_GET
def artifact_download(request, public_id, artifact_id):
    project = _owned_project(request, public_id)
    artifact = get_object_or_404(AgentArtifact, public_id=artifact_id, project=project)
    response = HttpResponse(artifact.content, content_type="text/markdown; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{get_valid_filename(artifact.logical_path.replace("/", "-"))}"'
    return response


@require_http_methods(["GET", "POST"])
def module(request, public_id, module_slug):
    """Legacy course route retained while old private records remain recoverable."""
    project = _owned_project(request, public_id)
    lesson = MODULE_BY_SLUG.get(module_slug)
    if lesson is None:
        raise Http404("Unknown lesson")
    entry = WorkbookEntry.objects.filter(project=project, module_slug=module_slug).first()
    form = WorkbookEntryForm(request.POST or None, instance=entry)
    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False)
        saved.project = project
        saved.module_slug = lesson.slug
        saved.completed_at = timezone.now()
        saved.save()
        messages.success(request, "Legacy workbook entry saved.")
        return redirect("academy:studio", public_id=project.public_id)
    return render(request, "academy/module.html", {"project": project, "lesson": lesson, "form": form, "is_complete": entry is not None})


@require_http_methods(["GET", "POST"])
def preview(request, public_id):
    project = _owned_project(request, public_id)
    form = ChallengeForm(request.POST or None)
    result = None
    if request.method == "POST" and form.is_valid():
        result = evaluate(form.cleaned_data["prompt"], project.entries.all())
        ChallengeAttempt.objects.create(
            project=project,
            prompt=form.cleaned_data["prompt"],
            outcome=result.outcome,
            response=result.response,
            evidence_titles=result.evidence_titles,
            source_fingerprint=source_fingerprint(request, f"preview:{project.public_id}"),
            is_private_preview=True,
        )
    return render(request, "academy/preview.html", {"project": project, "form": form, "result": result, "module_rows": _module_rows(project)})


@require_http_methods(["GET", "POST"])
def challenge(request, slug):
    project = get_object_or_404(
        TrainingProject.objects.prefetch_related("entries", "sources", "artifacts", "learning_events"),
        public_slug=slug,
        status=TrainingProject.Status.PUBLISHED,
        is_fictional_demo=True,
    )
    form = ChallengeForm(request.POST or None)
    result = None
    rate_limited = False
    if request.method == "POST" and form.is_valid():
        fingerprint = source_fingerprint(request, f"challenge:{project.public_id}")
        since = timezone.now() - timedelta(hours=1)
        recent = ChallengeAttempt.objects.filter(
            source_fingerprint=fingerprint,
            is_private_preview=False,
            created_at__gte=since,
        ).count()
        if recent >= settings.CHALLENGE_LIMIT_PER_HOUR:
            rate_limited = True
            messages.error(request, "This browser has reached the hourly challenge limit. Try again later.")
        else:
            public_entries = project.entries.filter(safe_to_share=True)
            result = evaluate(form.cleaned_data["prompt"], public_entries)
            ChallengeAttempt.objects.create(
                project=project,
                prompt=form.cleaned_data["prompt"],
                outcome=result.outcome,
                response=result.response,
                evidence_titles=result.evidence_titles,
                source_fingerprint=fingerprint,
                is_private_preview=False,
            )
    outcome_counts = {
        row["outcome"]: row["total"]
        for row in project.challenges.filter(is_private_preview=False).values("outcome").annotate(total=Count("id"))
    }
    return render(
        request,
        "academy/challenge.html",
        {
            "project": project,
            "entries": project.entries.filter(safe_to_share=True),
            "sources": project.sources.filter(safe_to_share=True),
            "events": project.learning_events.filter(safe_to_share=True)[:20],
            "questions": project.training_questions.filter(safe_to_share=True).select_related("source"),
            "artifacts": project.artifacts.filter(safe_to_share=True, status=AgentArtifact.Status.PUBLISHED),
            "form": form,
            "result": result,
            "rate_limited": rate_limited,
            "outcome_counts": outcome_counts,
        },
        status=429 if rate_limited else 200,
    )


@require_GET
def principles(request):
    return render(request, "academy/principles.html")


@require_GET
def guide(request, slug):
    page = GUIDES.get(slug)
    if not page:
        raise Http404("Guide not found.")
    related = []
    for label, target in page["related"]:
        if target == "SECURITY_LAB":
            target = settings.SECURITY_LAB_ORIGIN if settings.SECURITY_LAB_LIVE else "/ai-agent-security/"
        related.append((label, target))
    structured_data = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "TechArticle",
            "headline": page["title"],
            "description": page["meta"],
            "url": settings.PUBLIC_SITE_ORIGIN + page["path"],
            "publisher": {"@type": "Organization", "name": "Teach the Company"},
        },
        separators=(",", ":"),
    )
    return render(request, "academy/guide.html", {"guide": page, "related": related, "structured_data": structured_data})


def _lesson_value(lesson, name, default=""):
    if isinstance(lesson, dict):
        return lesson.get(name, default)
    return getattr(lesson, name, default)


def _source_payload(source):
    if isinstance(source, dict):
        return source
    if isinstance(source, str):
        return {"title": source, "publisher": "", "url": source}
    if isinstance(source, (tuple, list)):
        if len(source) == 3:
            return {"publisher": source[0], "title": source[1], "url": source[2]}
        return {"title": source[0], "publisher": "", "url": source[-1]}
    return {
        "title": getattr(source, "title", "Primary source"),
        "publisher": getattr(source, "publisher", ""),
        "url": getattr(source, "url", ""),
    }


def _lesson_payload(lesson):
    return {
        "id": _lesson_value(lesson, "lesson_id"),
        "slug": _lesson_value(lesson, "slug"),
        "title": _lesson_value(lesson, "title"),
        "level": _lesson_value(lesson, "level"),
        "summary": _lesson_value(lesson, "answer_first_summary", _lesson_value(lesson, "summary")),
        "learning_outcome": _lesson_value(lesson, "learning_outcome", _lesson_value(lesson, "outcome")),
        "explanation": _lesson_value(lesson, "explanation"),
        "worked_example": _lesson_value(lesson, "worked_example", _lesson_value(lesson, "example")),
        "exercise": _lesson_value(lesson, "exercise"),
        "success_criteria": list(_lesson_value(lesson, "success_criteria", ())),
        "limitations": list(_lesson_value(lesson, "limitations", ())),
        "prerequisites": list(_lesson_value(lesson, "prerequisite_ids", _lesson_value(lesson, "prerequisites", ()))),
        "next_lessons": list(_lesson_value(lesson, "next_lessons", _lesson_value(lesson, "next_lesson_ids", ()))),
        "copyable_material": _lesson_value(lesson, "copyable_material"),
        "sources": [_source_payload(source) for source in _lesson_value(lesson, "sources", ())],
        "version": _lesson_value(lesson, "content_version", _lesson_value(lesson, "version", "1.0")),
        "reviewed_on": str(_lesson_value(lesson, "reviewed_on", "2026-10-03")),
        "review_status": _lesson_value(lesson, "review_status", "editorially reviewed"),
        "next_review_criteria": "; ".join(
            _lesson_value(
                lesson,
                "next_review_criteria",
                ("Review when a cited primary source or relevant product behavior changes.",),
            )
        ),
        "canonical_aliases": list(
            _lesson_value(lesson, "canonical_guide_paths", _lesson_value(lesson, "canonical_aliases", ()))
        ),
    }


@require_GET
def school(request):
    level = request.GET.get("level", "").lower()
    allowed_levels = {"beginner", "practitioner", "advanced"}
    if level not in allowed_levels:
        level = ""
    lessons = [_lesson_payload(item) for item in LESSONS]
    if level:
        lessons = [item for item in lessons if item["level"] == level]
    structured_data = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "ItemList",
            "name": "Teach the Company English AI School",
            "numberOfItems": len(LESSONS),
            "itemListElement": [
                {"@type": "ListItem", "position": index, "url": f"{settings.PUBLIC_SITE_ORIGIN}/school/{item.slug}/"}
                for index, item in enumerate(LESSONS, 1)
            ],
        },
        separators=(",", ":"),
    )
    preset_rows = []
    for key, preset in PRESETS.items():
        values = {**preset["choices"], "subjects": preset["lesson_ids"]}
        preset_rows.append({**preset, "key": key, "url": f"{reverse('academy:compose')}?{urlencode(values, doseq=True)}"})
    return render(
        request,
        "academy/school.html",
        {"lessons": lessons, "level": level, "presets": preset_rows, "structured_data": structured_data},
    )


def _lesson_markdown(payload):
    def block(value):
        if isinstance(value, (list, tuple)):
            return "\n".join(str(item) for item in value)
        return str(value or "")

    lines = [
        f"# {payload['id']} — {payload['title']}",
        "",
        payload["summary"],
        "",
        f"Level: {payload['level']} · Version: {payload['version']} · Last reviewed: {payload['reviewed_on']}",
        f"Review status: {payload['review_status']}",
        "",
        "## Learning outcome",
        payload["learning_outcome"],
        "",
        "## Explanation",
        block(payload["explanation"]),
        "",
        "## Worked fictional example",
        block(payload["worked_example"]),
        "",
        "## Reusable exercise",
        block(payload["exercise"]),
        "",
        "## Observable success criteria",
        *[f"- {item}" for item in payload["success_criteria"]],
        "",
        "## Limitations",
        *[f"- {item}" for item in payload["limitations"]],
        "",
        "## Next review",
        str(payload["next_review_criteria"]),
        "",
        "## Copyable material",
        "```text",
        block(payload["copyable_material"]),
        "```",
        "",
        "## Primary sources",
        *[f"- {item['publisher']}: {item['title']} — {item['url']}" for item in payload["sources"]],
        "",
        f"Canonical URL: {settings.PUBLIC_SITE_ORIGIN}/school/{payload['slug']}/",
        *[f"Related established guide: {settings.PUBLIC_SITE_ORIGIN}{path}" for path in payload["canonical_aliases"]],
    ]
    return "\n".join(lines)


@require_GET
def lesson(request, slug, format="html"):
    if format not in {"html", "md", "json"}:
        raise Http404("Lesson format not found.")
    item = LESSON_BY_SLUG.get(slug)
    if not item:
        raise Http404("Lesson not found.")
    payload = _lesson_payload(item)
    if format == "md":
        return HttpResponse(_lesson_markdown(payload), content_type="text/markdown; charset=utf-8")
    if format == "json":
        payload["canonical_url"] = f"{settings.PUBLIC_SITE_ORIGIN}/school/{slug}/"
        return JsonResponse(payload)
    prerequisites = [_lesson_payload(LESSON_BY_ID[item]) for item in payload["prerequisites"] if item in LESSON_BY_ID]
    next_lessons = [_lesson_payload(LESSON_BY_ID[item]) for item in payload["next_lessons"] if item in LESSON_BY_ID]
    structured_data = json.dumps(
        {
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": "LearningResource",
                    "name": payload["title"],
                    "description": payload["summary"],
                    "educationalLevel": payload["level"],
                    "learningResourceType": "lesson",
                    "inLanguage": "en",
                    "url": f"{settings.PUBLIC_SITE_ORIGIN}/school/{slug}/",
                    "dateModified": payload["reviewed_on"],
                    "publisher": {"@type": "Organization", "name": "Teach the Company"},
                    "isAccessibleForFree": True,
                },
                {
                    "@type": "BreadcrumbList",
                    "itemListElement": [
                        {"@type": "ListItem", "position": 1, "name": "Home", "item": settings.PUBLIC_SITE_ORIGIN + "/"},
                        {"@type": "ListItem", "position": 2, "name": "English AI School", "item": settings.PUBLIC_SITE_ORIGIN + "/school/"},
                        {"@type": "ListItem", "position": 3, "name": payload["title"], "item": f"{settings.PUBLIC_SITE_ORIGIN}/school/{slug}/"},
                    ],
                },
            ],
        },
        separators=(",", ":"),
    )
    return render(
        request,
        "academy/school_lesson.html",
        {
            "lesson": payload,
            "prerequisites": prerequisites,
            "next_lessons": next_lessons,
            "lesson_markdown": _lesson_markdown(payload),
            "structured_data": structured_data,
        },
    )


@require_GET
def school_index(request, format):
    if format not in {"md", "json"}:
        raise Http404("School index format not found.")
    lessons = [_lesson_payload(item) for item in LESSONS]
    if format == "json":
        return JsonResponse(
            {
                "name": "Teach the Company English AI School",
                "version": "1.0",
                "lessons": [
                    {
                        "id": item["id"],
                        "title": item["title"],
                        "level": item["level"],
                        "dependencies": item["prerequisites"],
                        "url": f"{settings.PUBLIC_SITE_ORIGIN}/school/{item['slug']}/",
                        "markdown": f"{settings.PUBLIC_SITE_ORIGIN}/school/{item['slug']}.md",
                    }
                    for item in lessons
                ],
            }
        )
    lines = ["# Teach the Company English AI School", "", "20 free lessons. The agent is the student; people retain judgment.", ""]
    lines.extend(
        f"- [{item['id']} — {item['title']}]({settings.PUBLIC_SITE_ORIGIN}/school/{item['slug']}/) "
        f"({item['level']}; prerequisites: {', '.join(item['prerequisites']) or 'none'})"
        for item in lessons
    )
    return HttpResponse("\n".join(lines), content_type="text/markdown; charset=utf-8")


def _manual_payload(item):
    return {
        "slug": item.slug,
        "title": item.title,
        "summary": item.summary,
        "audience": item.audience,
        "version": item.version,
        "reviewed_on": item.reviewed_on,
        "author": "Finn Andre Hotvedt",
        "assistance": "Developed with assistance from ChatGPT and Codex by OpenAI.",
        "lesson_ids": list(item.lesson_ids),
        "sections": [
            {
                "title": section.title,
                "paragraphs": list(section.paragraphs),
                "checklist": list(section.checklist),
                "copyable": section.copyable,
            }
            for section in item.sections
        ],
    }


def _manual_markdown(payload):
    lines = [
        f"# {payload['title']}",
        "",
        payload["summary"],
        "",
        f"Audience: {payload['audience']}",
        f"Version: {payload['version']} · Last reviewed: {payload['reviewed_on']}",
        f"Author: {payload['author']}",
        payload["assistance"],
        f"Related lessons: {', '.join(payload['lesson_ids'])}",
    ]
    for section in payload["sections"]:
        lines.extend(("", f"## {section['title']}", ""))
        for paragraph in section["paragraphs"]:
            lines.extend((paragraph, ""))
        if section["checklist"]:
            lines.extend(f"- {entry}" for entry in section["checklist"])
        if section["copyable"]:
            lines.extend(("", "```text", section["copyable"], "```"))
    lines.extend(
        (
            "",
            "## Source trail",
            "",
            "Manual versions are available as HTML, Markdown and JSON on Teach the Company.",
            "The linked GitLab project contains these public manuals and their real version history; the complete application source is linked from the self-host page.",
            f"Public manuals repository: {settings.PUBLIC_MANUALS_REPOSITORY_URL}",
            "License: Apache-2.0.",
            "",
            f"Canonical URL: {settings.PUBLIC_SITE_ORIGIN}/manuals/{payload['slug']}/",
        )
    )
    return "\n".join(lines)


@require_GET
def manuals(request):
    manual_rows = [_manual_payload(item) for item in MANUALS]
    lesson_rows = [_lesson_payload(item) for item in LESSONS]
    covered = {lesson_id for item in MANUALS for lesson_id in item.lesson_ids}
    structured_data = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "name": "Teach the Company public manuals",
            "description": "Versioned manuals for learning, teaching, reviewing and safely operating one useful AI agent.",
            "url": settings.PUBLIC_SITE_ORIGIN + "/manuals/",
            "author": {"@type": "Person", "name": "Finn Andre Hotvedt"},
            "hasPart": [
                {"@type": "TechArticle", "name": item["title"], "url": f"{settings.PUBLIC_SITE_ORIGIN}/manuals/{item['slug']}/"}
                for item in manual_rows
            ],
        },
        separators=(",", ":"),
    )
    return render(
        request,
        "academy/manuals.html",
        {
            "manuals": manual_rows,
            "lessons": lesson_rows,
            "covered_lesson_count": len(covered),
            "repository_url": settings.PUBLIC_MANUALS_REPOSITORY_URL,
            "structured_data": structured_data,
        },
    )


@require_GET
def manual(request, slug, format="html"):
    if format not in {"html", "md", "json"}:
        raise Http404("Manual format not found.")
    item = MANUAL_BY_SLUG.get(slug)
    if not item:
        raise Http404("Manual not found.")
    payload = _manual_payload(item)
    payload["canonical_url"] = f"{settings.PUBLIC_SITE_ORIGIN}/manuals/{slug}/"
    payload["public_manuals_repository"] = settings.PUBLIC_MANUALS_REPOSITORY_URL
    payload["repository_scope"] = "Dedicated public manuals and version history; complete application source is linked from the self-host page."
    payload["license"] = "Apache-2.0"
    if format == "md":
        return HttpResponse(_manual_markdown(payload), content_type="text/markdown; charset=utf-8")
    if format == "json":
        return JsonResponse(payload)
    lessons = [_lesson_payload(LESSON_BY_ID[lesson_id]) for lesson_id in item.lesson_ids if lesson_id in LESSON_BY_ID]
    structured_data = json.dumps(
        {
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": "TechArticle",
                    "headline": payload["title"],
                    "description": payload["summary"],
                    "url": payload["canonical_url"],
                    "dateModified": payload["reviewed_on"],
                    "version": payload["version"],
                    "author": {"@type": "Person", "name": payload["author"]},
                    "publisher": {"@type": "Organization", "name": "Teach the Company"},
                    "isAccessibleForFree": True,
                    "inLanguage": "en",
                },
                {
                    "@type": "BreadcrumbList",
                    "itemListElement": [
                        {"@type": "ListItem", "position": 1, "name": "Home", "item": settings.PUBLIC_SITE_ORIGIN + "/"},
                        {"@type": "ListItem", "position": 2, "name": "Manuals", "item": settings.PUBLIC_SITE_ORIGIN + "/manuals/"},
                        {"@type": "ListItem", "position": 3, "name": payload["title"], "item": payload["canonical_url"]},
                    ],
                },
            ],
        },
        separators=(",", ":"),
    )
    return render(
        request,
        "academy/manual.html",
        {
            "manual": payload,
            "lessons": lessons,
            "repository_url": settings.PUBLIC_MANUALS_REPOSITORY_URL,
            "structured_data": structured_data,
        },
    )


@require_GET
def manual_index(request, format):
    if format not in {"md", "json"}:
        raise Http404("Manual index format not found.")
    manual_rows = [_manual_payload(item) for item in MANUALS]
    lessons = [_lesson_payload(item) for item in LESSONS]
    if format == "json":
        return JsonResponse(
            {
                "name": "Teach the Company public manuals",
                "version": "1.0.0",
                "author": "Finn Andre Hotvedt",
                "assistance": "Developed with assistance from ChatGPT and Codex by OpenAI.",
                "license": "Apache-2.0",
                "public_manuals_repository": settings.PUBLIC_MANUALS_REPOSITORY_URL,
                "repository_scope": "Dedicated sanitized public manuals and version history; not the private classroom source tree.",
                "manuals": [
                    {
                        "title": item["title"],
                        "version": item["version"],
                        "lesson_ids": item["lesson_ids"],
                        "url": f"{settings.PUBLIC_SITE_ORIGIN}/manuals/{item['slug']}/",
                        "markdown": f"{settings.PUBLIC_SITE_ORIGIN}/manuals/{item['slug']}.md",
                        "json": f"{settings.PUBLIC_SITE_ORIGIN}/manuals/{item['slug']}.json",
                    }
                    for item in manual_rows
                ],
                "lessons": [
                    {"id": item["id"], "title": item["title"], "url": f"{settings.PUBLIC_SITE_ORIGIN}/school/{item['slug']}/"}
                    for item in lessons
                ],
            }
        )
    lines = [
        "# Teach the Company public manuals",
        "",
        "Versioned manuals for learning, teaching, reviewing and safely operating one useful AI agent.",
        "",
        "Author: Finn Andre Hotvedt. Developed with assistance from ChatGPT and Codex by OpenAI.",
        "License: Apache-2.0.",
        "",
        "## Manuals",
    ]
    lines.extend(
        f"- [{item['title']}]({settings.PUBLIC_SITE_ORIGIN}/manuals/{item['slug']}/) — version {item['version']}; lessons {', '.join(item['lesson_ids'])}"
        for item in manual_rows
    )
    lines.extend(("", "## Complete twenty-lesson map"))
    lines.extend(f"- [{item['id']} — {item['title']}]({settings.PUBLIC_SITE_ORIGIN}/school/{item['slug']}/)" for item in lessons)
    lines.extend(
        (
            "",
            "## Public source trail",
            "",
            "The repository below contains these sanitized public manuals and their real Git history. It is not the private classroom source tree:",
            settings.PUBLIC_MANUALS_REPOSITORY_URL,
        )
    )
    return HttpResponse("\n".join(lines), content_type="text/markdown; charset=utf-8")


def _project_payload(item):
    return {
        "id": item.project_id,
        "slug": item.slug,
        "title": item.title,
        "outcome": item.outcome,
        "summary": item.summary,
        "publication_status": item.publication_status,
        "published_on": item.published_on,
        "updated_on": item.updated_on,
        "author": item.author,
        "language": item.language,
        "board": item.board,
        "board_revision": item.board_revision,
        "toolchain": item.toolchain,
        "logic_level": item.logic_level,
        "power_requirement": item.power_requirement,
        "hardware": [
            {
                "quantity": part.quantity,
                "item": part.item,
                "model": part.model,
                "revision": part.revision,
                "purpose": part.purpose,
            }
            for part in item.hardware
        ],
        "wiring": [
            {
                "board_pin": wire.board_pin,
                "module_pin": wire.module_pin,
                "signal": wire.signal,
                "electrical_note": wire.electrical_note,
            }
            for wire in item.wiring
        ],
        "wiring_diagram_alt": item.wiring_diagram_alt,
        "wiring_note": item.wiring_note,
        "prompt_version": item.prompt_version,
        "prompt_sha256": hashlib.sha256(item.finished_prompt.encode("utf-8")).hexdigest(),
        "finished_prompt": item.finished_prompt,
        "usage_steps": list(item.usage_steps),
        "observed_results": list(item.observed_results),
        "limitations": list(item.limitations),
        "related_lesson_ids": list(item.related_lesson_ids),
        "references": [
            {"label": reference.label, "url": reference.url, "scope": reference.scope}
            for reference in item.references
        ],
        "verification": {
            "prompt_review": item.verification.prompt_review,
            "build": item.verification.build,
            "upload": item.verification.upload,
            "wiring": item.verification.wiring,
            "physical_test": item.verification.physical_test,
        },
        "verification_labels": {
            "prompt_review": "Editorially reviewed",
            "build": "Not tested" if item.verification.build == "not-tested" else item.verification.build,
            "upload": "Not observed" if item.verification.upload == "not-tested" else item.verification.upload,
            "wiring": "Reference-reviewed; not hardware-verified" if item.verification.wiring == "reference-reviewed" else item.verification.wiring,
            "physical_test": "Not hardware-verified" if item.verification.physical_test == "not-hardware-verified" else item.verification.physical_test,
        },
        "video": (
            {
                "name": item.video.name,
                "url": item.video.url,
                "thumbnail_url": item.video.thumbnail_url,
                "upload_date": item.video.upload_date,
                "duration": item.video.duration,
                "transcript": item.video.transcript,
            }
            if item.video
            else None
        ),
    }


def _project_markdown(payload):
    verification = payload["verification"]
    labels = payload["verification_labels"]
    lines = [
        f"# {payload['id']} — {payload['title']}",
        "",
        payload["outcome"],
        "",
        payload["summary"],
        "",
        f"Published: {payload['published_on']} · Updated: {payload['updated_on']}",
        f"Author: {payload['author']}",
        "",
        "## Verification status",
        "",
        f"- Finished prompt: {labels['prompt_review']}",
        f"- Firmware build: {labels['build']}",
        f"- Upload: {labels['upload']}",
        f"- Wiring: {labels['wiring']}",
        f"- Physical test: {labels['physical_test']}",
        "",
        "## Video",
        "",
    ]
    if payload["video"]:
        lines.append(f"[{payload['video']['name']}]({payload['video']['url']})")
    else:
        lines.append("No real, accessible project video is published for this entry yet.")
    lines.extend(
        (
            "",
            "## Board, toolchain and electrical boundary",
            "",
            f"- Board: {payload['board']}",
            f"- Board revision: {payload['board_revision']}",
            f"- Toolchain: {payload['toolchain']}",
            f"- Logic level: {payload['logic_level']}",
            f"- Power: {payload['power_requirement']}",
            "",
            "## Hardware / BOM",
            "",
            "| Qty | Item | Model | Revision | Purpose |",
            "| --- | --- | --- | --- | --- |",
        )
    )
    lines.extend(
        f"| {part['quantity']} | {part['item']} | {part['model']} | {part['revision']} | {part['purpose']} |"
        for part in payload["hardware"]
    )
    lines.extend(("", "## Wiring", "", f"**Status:** {labels['wiring']}", "", payload["wiring_note"], ""))
    lines.extend(("| Board pin | Module pin | Signal | Electrical note |", "| --- | --- | --- | --- |"))
    lines.extend(
        f"| {wire['board_pin']} | {wire['module_pin']} | {wire['signal']} | {wire['electrical_note']} |"
        for wire in payload["wiring"]
    )
    lines.extend(
        (
            "",
            f"Diagram description: {payload['wiring_diagram_alt']}",
            "",
            f"## Finished prompt — version {payload['prompt_version']}",
            "",
            f"SHA-256: `{payload['prompt_sha256']}`",
            "",
            "```text",
            payload["finished_prompt"],
            "```",
            "",
            "## How to use it",
            "",
        )
    )
    lines.extend(f"{index}. {step}" for index, step in enumerate(payload["usage_steps"], 1))
    lines.extend(("", "## Actual results", ""))
    lines.extend(f"- {result}" for result in payload["observed_results"])
    lines.extend(("", "## Limits", ""))
    lines.extend(f"- {limit}" for limit in payload["limitations"])
    lines.extend(("", "## Sources and evidence", ""))
    lines.extend(f"- [{reference['label']}]({reference['url']}) — {reference['scope']}" for reference in payload["references"])
    lines.extend(
        (
            "",
            f"Related lessons: {', '.join(payload['related_lesson_ids'])}",
            "",
            f"Canonical URL: {settings.PUBLIC_SITE_ORIGIN}/projects/{payload['slug']}/",
            f"Machine-readable JSON: {settings.PUBLIC_SITE_ORIGIN}/projects/{payload['slug']}.json",
        )
    )
    return "\n".join(lines)


@require_GET
def projects(request):
    project_rows = [_project_payload(item) for item in PUBLISHED_PROJECTS]
    structured_data = json.dumps(
        {
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": "CollectionPage",
                    "name": "Microcontroller Project Library",
                    "description": "Finished prompts, exact hardware boundaries, wiring status and honest test evidence for adaptable microcontroller projects.",
                    "url": settings.PUBLIC_SITE_ORIGIN + "/projects/",
                    "isAccessibleForFree": True,
                },
                {
                    "@type": "ItemList",
                    "numberOfItems": len(project_rows),
                    "itemListElement": [
                        {
                            "@type": "ListItem",
                            "position": index,
                            "name": project["title"],
                            "url": f"{settings.PUBLIC_SITE_ORIGIN}/projects/{project['slug']}/",
                        }
                        for index, project in enumerate(project_rows, 1)
                    ],
                },
            ],
        },
        separators=(",", ":"),
    )
    return render(
        request,
        "academy/projects.html",
        {"projects": project_rows, "structured_data": structured_data},
    )


@require_GET
def project(request, slug, format="html"):
    if format not in {"html", "md", "json"}:
        raise Http404("Project format not found.")
    item = PUBLISHED_PROJECT_BY_SLUG.get(slug)
    if not item:
        raise Http404("Project not found.")
    payload = _project_payload(item)
    payload["canonical_url"] = f"{settings.PUBLIC_SITE_ORIGIN}/projects/{slug}/"
    payload["prompt_download_url"] = f"{settings.PUBLIC_SITE_ORIGIN}/projects/{slug}/prompt.txt"
    if format == "md":
        return HttpResponse(_project_markdown(payload), content_type="text/markdown; charset=utf-8")
    if format == "json":
        return JsonResponse(payload)
    lessons = [_lesson_payload(LESSON_BY_ID[lesson_id]) for lesson_id in item.related_lesson_ids if lesson_id in LESSON_BY_ID]
    graph = [
        {
            "@type": "WebPage",
            "name": payload["title"],
            "description": payload["summary"],
            "url": payload["canonical_url"],
            "datePublished": payload["published_on"],
            "dateModified": payload["updated_on"],
            "inLanguage": payload["language"],
        },
        {
            "@type": "CreativeWork",
            "name": payload["title"],
            "description": payload["summary"],
            "url": payload["canonical_url"],
            "author": {"@type": "Person", "name": payload["author"]},
            "publisher": {"@type": "Organization", "name": "Teach the Company"},
            "datePublished": payload["published_on"],
            "dateModified": payload["updated_on"],
            "isAccessibleForFree": True,
            "learningResourceType": "finished microcontroller project prompt",
        },
        {
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Home", "item": settings.PUBLIC_SITE_ORIGIN + "/"},
                {"@type": "ListItem", "position": 2, "name": "Projects", "item": settings.PUBLIC_SITE_ORIGIN + "/projects/"},
                {"@type": "ListItem", "position": 3, "name": payload["title"], "item": payload["canonical_url"]},
            ],
        },
    ]
    if payload["video"]:
        graph.append(
            {
                "@type": "VideoObject",
                "name": payload["video"]["name"],
                "description": payload["summary"],
                "thumbnailUrl": [payload["video"]["thumbnail_url"]],
                "uploadDate": payload["video"]["upload_date"],
                "duration": payload["video"]["duration"],
                "contentUrl": payload["video"]["url"],
                "transcript": payload["video"]["transcript"],
            }
        )
    structured_data = json.dumps({"@context": "https://schema.org", "@graph": graph}, separators=(",", ":"))
    return render(
        request,
        "academy/project.html",
        {"project": payload, "lessons": lessons, "structured_data": structured_data},
    )


@require_GET
def project_prompt(request, slug):
    item = PUBLISHED_PROJECT_BY_SLUG.get(slug)
    if not item:
        raise Http404("Project not found.")
    response = HttpResponse(item.finished_prompt + "\n", content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{item.slug}-prompt-v{item.prompt_version}.txt"'
    return response


@require_GET
def project_index(request, format):
    if format not in {"md", "json"}:
        raise Http404("Project index format not found.")
    projects_payload = [_project_payload(item) for item in PUBLISHED_PROJECTS]
    if format == "json":
        return JsonResponse(
            {
                "name": "Microcontroller Project Library",
                "version": "1.0.0",
                "canonical_url": settings.PUBLIC_SITE_ORIGIN + "/projects/",
                "publication_rule": "Only published records appear. Verification states remain separate.",
                "projects": [
                    {
                        **project_payload,
                        "canonical_url": f"{settings.PUBLIC_SITE_ORIGIN}/projects/{project_payload['slug']}/",
                        "markdown_url": f"{settings.PUBLIC_SITE_ORIGIN}/projects/{project_payload['slug']}.md",
                        "json_url": f"{settings.PUBLIC_SITE_ORIGIN}/projects/{project_payload['slug']}.json",
                        "prompt_download_url": f"{settings.PUBLIC_SITE_ORIGIN}/projects/{project_payload['slug']}/prompt.txt",
                    }
                    for project_payload in projects_payload
                ],
            }
        )
    lines = [
        "# Microcontroller Project Library",
        "",
        "Finished public prompts, hardware boundaries, wiring status and test evidence. Only published records appear.",
        "",
    ]
    lines.extend(
        f"- [{project_payload['id']} — {project_payload['title']}]({settings.PUBLIC_SITE_ORIGIN}/projects/{project_payload['slug']}/) "
        f"— physical test: {project_payload['verification']['physical_test']}; updated {project_payload['updated_on']}"
        for project_payload in projects_payload
    )
    return HttpResponse("\n".join(lines), content_type="text/markdown; charset=utf-8")


def _composition_share_url(cleaned):
    public = {
        "goal": cleaned["goal"],
        "experience_level": cleaned["experience_level"],
        "provider": cleaned["provider"],
        "hosting": cleaned["hosting"],
        "privacy": cleaned["privacy"],
        "autonomy": cleaned["autonomy"],
        "subjects": cleaned.get("subjects", []),
    }
    return f"{settings.PUBLIC_SITE_ORIGIN}{reverse('academy:compose')}?{urlencode(public, doseq=True)}"


@require_http_methods(["GET", "POST"])
def compose_school(request):
    initial = None
    if request.method == "GET" and request.GET:
        initial = request.GET.copy()
        initial.pop("use_case", None)
        initial.pop("tools", None)
    form = SchoolCompositionForm(request.POST or initial)
    result = None
    share_url = ""
    if form.is_bound and form.is_valid():
        result = compose(form.cleaned_data, origin=settings.PUBLIC_SITE_ORIGIN)
        share_url = _composition_share_url(form.cleaned_data)
    preset_rows = []
    for key, preset in PRESETS.items():
        values = {**preset["choices"], "subjects": preset["lesson_ids"]}
        preset_rows.append({**preset, "key": key, "url": f"{reverse('academy:compose')}?{urlencode(values, doseq=True)}"})
    return render(
        request,
        "academy/compose.html",
        {"form": form, "result": result, "share_url": share_url, "presets": preset_rows},
    )


@require_POST
def composition_download(request):
    form = SchoolCompositionForm(request.POST)
    if not form.is_valid():
        return render(request, "academy/compose.html", {"form": form, "result": None, "presets": PRESETS}, status=400)
    result = compose(form.cleaned_data, origin=settings.PUBLIC_SITE_ORIGIN)
    response = HttpResponse(result.markdown, content_type="text/markdown; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="teach-the-company-agent-pack.md"'
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_http_methods(["GET", "POST"])
def suggest(request):
    form = PublicSuggestionForm(request.POST or None)
    rate_limited = False
    if request.method == "POST":
        fingerprint = source_fingerprint(request, "public-suggestion")
        PublicInputEvent.objects.create(action="suggestion-post", actor_hash=fingerprint)
        since = timezone.now() - timedelta(hours=1)
        recent = PublicInputEvent.objects.filter(
            action="suggestion-post", actor_hash=fingerprint, created_at__gte=since
        ).count()
        rate_limited = recent > settings.PUBLIC_SUGGESTION_LIMIT_PER_HOUR
        if not rate_limited and form.is_valid():
            suggestion = form.save(commit=False)
            suggestion.source_fingerprint = fingerprint
            suggestion.save()
            request.session["public_suggestion_receipt"] = str(suggestion.public_id)
            return redirect("academy:suggest_thanks")
    return render(request, "academy/suggest.html", {"form": form, "rate_limited": rate_limited}, status=429 if rate_limited else 200)


@require_GET
def suggest_thanks(request):
    receipt = request.session.get("public_suggestion_receipt", "")
    return render(request, "academy/suggest_thanks.html", {"receipt": receipt})


@require_GET
def freshness(request):
    sources = TrustedKnowledgeSource.objects.prefetch_related("reviews").filter(active=True)
    source_rows = []
    for source in sources:
        source_reviews = list(source.reviews.all())
        published = next((item for item in source_reviews if item.status == KnowledgeReview.Status.PUBLISHED), None)
        source_rows.append(
            {
                "source": source,
                "last_reviewed": published.published_at if published else None,
                "update_pending": any(
                    item.status in {
                        KnowledgeReview.Status.NEEDS_REVIEW,
                        KnowledgeReview.Status.IN_REVIEW,
                        KnowledgeReview.Status.CONFLICT,
                        KnowledgeReview.Status.ACCEPTED,
                    }
                    for item in source_reviews
                ),
            }
        )
    reviews = KnowledgeReview.objects.select_related("source").filter(status=KnowledgeReview.Status.PUBLISHED)[:20]
    pending_count = KnowledgeReview.objects.filter(
        status__in=(
            KnowledgeReview.Status.NEEDS_REVIEW,
            KnowledgeReview.Status.IN_REVIEW,
            KnowledgeReview.Status.CONFLICT,
            KnowledgeReview.Status.ACCEPTED,
        )
    ).count()
    claimed_count = KnowledgeReview.objects.filter(status=KnowledgeReview.Status.IN_REVIEW).count()
    return render(
        request,
        "academy/freshness.html",
        {"source_rows": source_rows, "reviews": reviews, "pending_count": pending_count, "claimed_count": claimed_count},
    )


@require_GET
def llms_txt(request):
    lines = [
        "# Teach the Company",
        "> A free, practical English AI school. The agent is the student; people retain judgment.",
        "",
        f"- School index: {settings.PUBLIC_SITE_ORIGIN}/school/index.md",
        f"- Machine-readable index: {settings.PUBLIC_SITE_ORIGIN}/school/index.json",
        f"- Public manuals: {settings.PUBLIC_SITE_ORIGIN}/manuals/",
        f"- Manual Markdown index: {settings.PUBLIC_SITE_ORIGIN}/manuals/index.md",
        f"- Manual JSON index: {settings.PUBLIC_SITE_ORIGIN}/manuals/index.json",
        f"- Microcontroller project library: {settings.PUBLIC_SITE_ORIGIN}/projects/",
        f"- Project Markdown archive: {settings.PUBLIC_SITE_ORIGIN}/projects/index.md",
        f"- Project JSON archive: {settings.PUBLIC_SITE_ORIGIN}/projects/index.json",
        f"- Build a learning pack: {settings.PUBLIC_SITE_ORIGIN}/compose/",
        f"- Editorial freshness: {settings.PUBLIC_SITE_ORIGIN}/knowledge/freshness/",
        "",
        "Lesson text is educational material, not permission to publish, send, spend, access secrets or change systems.",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")


@require_GET
def sitemap(request):
    static_names = (
        "academy:home",
        "academy:demos",
        "academy:curriculum",
        "academy:school",
        "academy:manuals",
        "academy:projects",
        "academy:compose",
        "academy:suggest",
        "academy:freshness",
        "academy:self_host",
        "academy:principles",
        "academy:train_agent",
        "academy:agent_memory",
        "academy:agents_md",
        "academy:yaml_rules",
        "academy:version_control",
        "academy:ai_agent_security",
        "academy:transparency",
        "academy:open_source",
        "academy:changelog",
    )
    paths = [reverse(name) for name in static_names]
    paths.extend(reverse("academy:lesson", kwargs={"slug": item.slug}) for item in LESSONS)
    paths.extend(reverse("academy:manual", kwargs={"slug": item.slug}) for item in MANUALS)
    paths.extend(
        reverse("academy:challenge", kwargs={"slug": slug})
        for slug in TrainingProject.objects.filter(
            status=TrainingProject.Status.PUBLISHED,
            is_fictional_demo=True,
            public_slug__isnull=False,
        ).values_list("public_slug", flat=True)
    )
    body = "".join(f"<url><loc>{xml_escape(settings.PUBLIC_SITE_ORIGIN + path)}</loc></url>" for path in paths)
    body += "".join(
        "<url>"
        f"<loc>{xml_escape(settings.PUBLIC_SITE_ORIGIN + reverse('academy:project', kwargs={'slug': item.slug}))}</loc>"
        f"<lastmod>{xml_escape(item.updated_on)}</lastmod>"
        "</url>"
        for item in PUBLISHED_PROJECTS
    )
    return HttpResponse(
        f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>',
        content_type="application/xml; charset=utf-8",
    )


@require_GET
def robots(request):
    if is_agent_host(request):
        content = "User-agent: *\nDisallow: /\n"
    else:
        content = (
            "User-agent: *\nAllow: /\nDisallow: /control/\nDisallow: /studio/\n"
            "Disallow: /join/\nDisallow: /handoff/\nDisallow: /start/\n"
            f"Sitemap: {settings.PUBLIC_SITE_ORIGIN}/sitemap.xml\n"
        )
    return HttpResponse(content, content_type="text/plain")


@require_GET
def health(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    return JsonResponse({"status": "ok", "service": "teach-the-company"})
