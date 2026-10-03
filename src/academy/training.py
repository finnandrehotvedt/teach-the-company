from __future__ import annotations

import hashlib
import json

from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from .agent_runtime import (
    AgentUnavailable,
    MemorySynthesis,
    connected_backend,
    inspect_training_material,
    synthesize_teacher_memory,
)
from .ingestion import record_revision
from .models import LearningEvent, LearningSource, TrainingProject, TrainingQuestion


def _questions_for_source(source: LearningSource) -> list[TrainingQuestion]:
    if source.kind == LearningSource.Kind.CORRECTION:
        binary_prompt = f"Should I treat “{source.title}” as a rule that overrides conflicting guidance?"
        explanation_prompt = f"What mistake should “{source.title}” prevent, and are there exceptions?"
    elif source.kind == LearningSource.Kind.TEST:
        binary_prompt = f"Should “{source.title}” be used as an acceptance test for future work?"
        explanation_prompt = f"What would count as passing “{source.title}”?"
    else:
        binary_prompt = f"Should I treat “{source.title}” as authoritative guidance?"
        explanation_prompt = f"When should I use “{source.title}”, and what important exceptions should I remember?"
    return [
        TrainingQuestion.objects.create(
            project=source.project,
            source=source,
            prompt=binary_prompt,
            detail=f"Asked after inspecting {source.logical_path}.",
            answer_kind=TrainingQuestion.AnswerKind.YES_NO,
            quick_replies=["Yes", "No"],
        ),
        TrainingQuestion.objects.create(
            project=source.project,
            source=source,
            prompt=explanation_prompt,
            detail="Optional context helps the agent avoid applying a file too broadly.",
            answer_kind=TrainingQuestion.AnswerKind.EXPLANATION,
        ),
    ]


@transaction.atomic
def inspect_unprocessed_files(project: TrainingProject) -> tuple[int, int]:
    sources = list(
        project.sources.select_for_update()
        .filter(inspected_at__isnull=True)
        .order_by("learned_at", "id")
    )
    question_count = 0
    if sources and connected_backend():
        source_by_path = {source.logical_path: source for source in sources}
        for suggestion in inspect_training_material(project, sources):
            TrainingQuestion.objects.create(
                project=project,
                source=source_by_path.get(suggestion.source_path),
                prompt=suggestion.prompt,
                detail=suggestion.detail,
                answer_kind=suggestion.answer_kind,
                quick_replies=suggestion.quick_replies,
            )
            question_count += 1
    else:
        for source in sources:
            if not source.training_questions.exists():
                question_count += len(_questions_for_source(source))
    for source in sources:
        source.inspected_at = timezone.now()
        source.save(update_fields=("inspected_at", "updated_at"))
    if sources:
        LearningEvent.objects.create(
            project=project,
            kind=LearningEvent.Kind.QUESTION,
            headline=f"Inspected {len(sources)} new file{'s' if len(sources) != 1 else ''}",
            detail=(
                f"The agent compared the new material with its visible file set and asked "
                f"{question_count} clarification question{'s' if question_count != 1 else ''}. "
                f"Processing mode: {'connected model' if connected_backend() else 'evidence fallback'}."
            ),
        )
    return len(sources), question_count


@transaction.atomic
def answer_training_question(question: TrainingQuestion, answer: str) -> LearningSource:
    answer = answer.strip()
    if not answer:
        raise ValueError("An answer is required.")
    if len(answer) > 3000:
        raise ValueError("Keep the explanation under 3000 characters.")

    locked = TrainingQuestion.objects.select_for_update().select_related("project").get(pk=question.pk)
    if locked.status == TrainingQuestion.Status.ANSWERED:
        existing = locked.project.sources.filter(
            logical_path__contains=f"-{str(locked.public_id)[:8]}.md"
        ).first()
        if existing:
            return existing
        raise ValueError("This question has already been answered.")

    try:
        synthesis = synthesize_teacher_memory(locked, answer)
    except AgentUnavailable:
        synthesis = MemorySynthesis(
            title=f"Teacher answer: {locked.prompt[:100]}",
            content="The connected model was unavailable, so preserve and apply the teacher's exact answer without adding an interpretation.",
        )

    stem = slugify(synthesis.title)[:58] or "teacher-answer"
    logical_path = f"memory/teacher-notes/{stem}-{str(locked.public_id)[:8]}.md"
    related = locked.source.logical_path if locked.source else "Classroom setup"
    content = (
        f"# {synthesis.title}\n\n"
        f"Related material: `{related}`\n\n"
        f"## Agent question\n\n{locked.prompt}\n\n"
        f"## Teacher answer\n\n{answer}\n\n"
        f"## Agent interpretation\n\n{synthesis.content}\n"
    )
    source = LearningSource.objects.create(
        project=locked.project,
        kind=LearningSource.Kind.NOTE,
        title=synthesis.title,
        logical_path=logical_path,
        content_text=content,
        status=LearningSource.Status.ACTIVE,
        checksum=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        inspected_at=timezone.now(),
        safe_to_share=locked.safe_to_share,
    )
    record_revision(source, "Teacher answered an agent question")
    if synthesis.rule_name and synthesis.rule_statement:
        rule_path = f"rules/proposals/{slugify(synthesis.rule_name)[:55] or 'learned-rule'}-{str(locked.public_id)[:8]}.yaml"
        rule_content = (
            "kind: learned-rule\n"
            f"name: {json.dumps(synthesis.rule_name, ensure_ascii=False)}\n"
            f"statement: {json.dumps(synthesis.rule_statement, ensure_ascii=False)}\n"
            f"learned_from: {json.dumps(logical_path)}\n"
            "status: proposed\n"
        )
        rule = LearningSource.objects.create(
            project=locked.project,
            kind=LearningSource.Kind.CORRECTION,
            title=synthesis.rule_name,
            logical_path=rule_path,
            content_text=rule_content,
            status=LearningSource.Status.PROPOSED,
            checksum=hashlib.sha256(rule_content.encode("utf-8")).hexdigest(),
            inspected_at=timezone.now(),
            safe_to_share=locked.safe_to_share,
        )
        record_revision(rule, "Agent proposed a structured rule from the teacher's answer")
    locked.answer_text = answer
    locked.status = TrainingQuestion.Status.ANSWERED
    locked.answered_at = timezone.now()
    locked.save(update_fields=("answer_text", "status", "answered_at"))
    LearningEvent.objects.create(
        project=locked.project,
        kind=LearningEvent.Kind.ANSWER,
        headline=f"Answered: {locked.prompt[:150]}",
        detail=f"The teacher's answer became active cognitive memory at {logical_path}.",
        related_source=source,
        safe_to_share=locked.safe_to_share,
    )
    return source
