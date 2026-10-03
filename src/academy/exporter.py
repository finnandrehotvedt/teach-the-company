from __future__ import annotations

import json
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile

import yaml
from django.utils import timezone
from django.utils.text import slugify

from .models import AgentArtifact, LearningSource, TrainingProject, TrainingQuestion


def _safe_path(value: str, fallback: str) -> str:
    path = PurePosixPath(value.replace("\\", "/").lstrip("/"))
    clean = [part for part in path.parts if part not in {"", ".", ".."}]
    return "/".join(clean) or fallback


def _unique_path(path: str, used: set[str]) -> str:
    candidate = path
    stem = str(PurePosixPath(path).with_suffix(""))
    suffix = PurePosixPath(path).suffix
    number = 2
    while candidate in used:
        candidate = f"{stem}-{number}{suffix}"
        number += 1
    used.add(candidate)
    return candidate


def build_training_zip(project: TrainingProject) -> tuple[BytesIO, str]:
    output = BytesIO()
    used: set[str] = set()
    exported_sources = []
    now = timezone.now()

    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for source in project.sources.order_by("learned_at", "id"):
            source_path = _safe_path(source.logical_path, f"source-{source.public_id}.txt")
            if source.status == LearningSource.Status.PROPOSED:
                source_path = f"_training/proposed/{source_path}"
            elif source.status == LearningSource.Status.RETIRED:
                source_path = f"_training/retired/{source_path}"
            archive_path = _unique_path(source_path, used)
            archive.writestr(archive_path, source.content_text)
            exported_sources.append(
                {
                    "path": archive_path,
                    "classroom_path": source.logical_path,
                    "status": source.status,
                    "revision": source.revision_number,
                    "checksum": source.checksum,
                    "kind": source.kind,
                }
            )
            if source.uploaded_file:
                original_name = _safe_path(source.original_filename, f"original-{source.public_id}")
                original_path = _unique_path(
                    f"_training/originals/{str(source.public_id)[:8]}-{original_name}", used
                )
                try:
                    with source.uploaded_file.open("rb") as uploaded:
                        archive.writestr(original_path, uploaded.read())
                except FileNotFoundError:
                    pass

        for artifact in project.artifacts.order_by("created_at", "id"):
            artifact_path = _safe_path(artifact.logical_path, f"output-{artifact.public_id}.md")
            if artifact.status not in {AgentArtifact.Status.APPROVED, AgentArtifact.Status.PUBLISHED}:
                artifact_path = f"_training/drafts/{artifact_path}"
            archive.writestr(_unique_path(artifact_path, used), artifact.content)

        questions = [
            {
                "question": question.prompt,
                "kind": question.answer_kind,
                "status": question.status,
                "related_file": question.source.logical_path if question.source else None,
                "answer": question.answer_text or None,
            }
            for question in project.training_questions.select_related("source").order_by("created_at", "id")
        ]
        archive.writestr(
            _unique_path("_training/questions.yaml", used),
            yaml.safe_dump({"questions": questions}, sort_keys=False, allow_unicode=True),
        )

        events = ["# Learning history", ""]
        for event in project.learning_events.order_by("created_at", "id"):
            events.extend(
                [
                    f"## {event.created_at.isoformat()} — {event.headline}",
                    "",
                    event.detail or f"Event type: {event.kind}",
                    "",
                ]
            )
        archive.writestr(_unique_path("_training/learning-history.md", used), "\n".join(events))

        answered = project.training_questions.filter(status=TrainingQuestion.Status.ANSWERED).count()
        open_count = project.training_questions.filter(status=TrainingQuestion.Status.OPEN).count()
        memory_summary = (
            "# Cognitive memory summary\n\n"
            f"- Active files: {project.sources.filter(status=LearningSource.Status.ACTIVE).count()}\n"
            f"- Teacher answers: {answered}\n"
            f"- Open questions: {open_count}\n"
            f"- Exported: {now.isoformat()}\n\n"
            "The actual memory is stored in the readable files beside this summary.\n"
        )
        archive.writestr(_unique_path("memory/cognitive-summary.md", used), memory_summary)

        guide = """# Teach the Company export

Unpack this ZIP at the root of the repository where the agent should work.
Codex reads the root `AGENTS.md` before doing work and then follows the visible
rules and memory files referenced by it.

Folders under `_training/` are audit material: pending files, retired files,
original uploads, open questions, and the learning history. Review proposed
material before moving it into the active folders.

Official Codex documentation:
https://developers.openai.com/codex/guides/agents-md/
"""
        archive.writestr(_unique_path("TEACH-THE-COMPANY-EXPORT.md", used), guide)
        manifest = {
            "format": "teach-the-company-codex-training-v1",
            "agent": project.agent_name,
            "mode": "training",
            "task_assigned": False,
            "exported_at": now.isoformat(),
            "sources": exported_sources,
            "question_count": len(questions),
            "event_count": project.learning_events.count(),
        }
        archive.writestr(
            _unique_path("_training/manifest.json", used),
            json.dumps(manifest, indent=2, ensure_ascii=False),
        )

    output.seek(0)
    filename = f"{slugify(project.agent_name) or 'agent'}-codex-training.zip"
    return output, filename
