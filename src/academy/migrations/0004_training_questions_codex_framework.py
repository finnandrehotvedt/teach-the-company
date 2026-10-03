import hashlib
import uuid

import django.db.models.deletion
from django.db import migrations, models
from django.utils import timezone


def convert_agent_manifests(apps, schema_editor):
    LearningSource = apps.get_model("academy", "LearningSource")
    SourceRevision = apps.get_model("academy", "SourceRevision")
    TrainingProject = apps.get_model("academy", "TrainingProject")
    for source in LearningSource.objects.filter(logical_path="agent.yaml").select_related("project"):
        project = source.project
        if LearningSource.objects.filter(project=project, logical_path="AGENTS.md").exclude(pk=source.pk).exists():
            source.logical_path = f"_training/legacy-agent-yaml-{source.pk}.txt"
            source.title = "Legacy agent.yaml"
        else:
            legacy = source.content_text.strip()
            source.logical_path = "AGENTS.md"
            source.title = "Codex agent instructions"
            source.content_text = (
                f"# {project.agent_name}\n\n"
                "## Current mode\n\n"
                "You are in training mode. No concrete task has been assigned yet. "
                "Learn from approved files, ask concise questions when uncertain, "
                "and offer Yes/No quick replies when a question is genuinely binary.\n\n"
                "Use only approved training files, cite what you used, and never "
                "publish, send, purchase, or change external systems without human approval.\n\n"
                "## Imported legacy contract\n\n"
                "```yaml\n"
                f"{legacy}\n"
                "```\n"
            )
        source.checksum = hashlib.sha256(source.content_text.encode("utf-8")).hexdigest()
        source.revision_number += 1
        source.inspected_at = timezone.now()
        source.save(
            update_fields=(
                "logical_path",
                "title",
                "content_text",
                "checksum",
                "revision_number",
                "inspected_at",
                "updated_at",
            )
        )
        SourceRevision.objects.create(
            source=source,
            number=source.revision_number,
            content_text=source.content_text,
            checksum=source.checksum,
            change_note="Converted legacy agent.yaml to the Codex AGENTS.md format",
            status=source.status,
        )

    rules_content = """mode: training
task_assigned: false
knowledge_policy:
  use_only_approved_files: true
  cite_files_used: true
  ask_when_uncertain: true
  allow_teacher_explanation: true
quick_replies:
  yes_no_when_binary: true
  values:
  - Yes
  - No
human_approval_required_for:
- publishing
- sending
- purchasing
- changing external systems
""".strip()
    memory_content = """# Cognitive memory

This folder contains durable, inspectable memory created during training.

- `teacher-notes/` records answers and explanations from the teacher.
- Corrections belong in `corrections/` as structured YAML rules.
- Open questions and the complete learning history are included in `_training/`
  when the classroom is downloaded.

Memory is evidence, not hidden state: it can be read, versioned, edited, and
moved into another agent project.
""".strip()

    for project in TrainingProject.objects.all():
        safe_to_share = bool(project.is_fictional_demo)
        if not LearningSource.objects.filter(project=project, logical_path="AGENTS.md").exists():
            mission = project.mission.strip() or "No concrete task has been assigned."
            agents_content = (
                f"# {project.agent_name}\n\n"
                "## Current mode\n\n"
                "You are in training mode. Learn from approved files, ask concise "
                "questions when uncertain, and offer Yes/No quick replies when a "
                "question is genuinely binary.\n\n"
                "Read `rules/training-rules.yaml` and the visible files under "
                "`memory/`. Never invent missing guidance or take an external action "
                "without human approval.\n\n"
                "## Imported project context\n\n"
                f"{mission}\n"
            )
            source = LearningSource.objects.create(
                project=project,
                kind="note",
                title="Codex agent instructions",
                logical_path="AGENTS.md",
                content_text=agents_content,
                status="active",
                checksum=hashlib.sha256(agents_content.encode("utf-8")).hexdigest(),
                safe_to_share=safe_to_share,
                inspected_at=timezone.now(),
            )
            SourceRevision.objects.create(
                source=source,
                number=1,
                content_text=agents_content,
                checksum=source.checksum,
                change_note="Created Codex AGENTS.md during framework migration",
                status="active",
            )

        for path, title, content in (
            ("rules/training-rules.yaml", "Training rules", rules_content),
            ("memory/README.md", "Cognitive memory map", memory_content),
        ):
            if LearningSource.objects.filter(project=project, logical_path=path).exists():
                continue
            source = LearningSource.objects.create(
                project=project,
                kind="note",
                title=title,
                logical_path=path,
                content_text=content,
                status="active",
                checksum=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                safe_to_share=safe_to_share,
                inspected_at=timezone.now(),
            )
            SourceRevision.objects.create(
                source=source,
                number=1,
                content_text=content,
                checksum=source.checksum,
                change_note="Created portable training framework during migration",
                status="active",
            )


class Migration(migrations.Migration):

    dependencies = [("academy", "0003_accessinvite_accessrequest_agentartifact_and_more")]

    operations = [
        migrations.AddField(
            model_name="learningsource",
            name="inspected_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="learningevent",
            name="kind",
            field=models.CharField(
                choices=[
                    ("source", "Source learned"),
                    ("correction", "Correction learned"),
                    ("test", "Test completed"),
                    ("artifact", "Artifact created"),
                    ("approval", "Human approval"),
                    ("publication", "Published"),
                    ("question", "Agent asked"),
                    ("answer", "Teacher answered"),
                ],
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="TrainingQuestion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                (
                    "prompt",
                    models.CharField(max_length=500),
                ),
                ("detail", models.TextField(blank=True, max_length=1200)),
                (
                    "answer_kind",
                    models.CharField(
                        choices=[("yes_no", "Yes or no"), ("explanation", "Explanation")],
                        default="explanation",
                        max_length=20,
                    ),
                ),
                ("quick_replies", models.JSONField(blank=True, default=list)),
                (
                    "status",
                    models.CharField(
                        choices=[("open", "Open"), ("answered", "Answered")],
                        default="open",
                        max_length=20,
                    ),
                ),
                ("answer_text", models.TextField(blank=True, max_length=3000)),
                ("safe_to_share", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("answered_at", models.DateTimeField(blank=True, null=True)),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="training_questions",
                        to="academy.trainingproject",
                    ),
                ),
                (
                    "source",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="training_questions",
                        to="academy.learningsource",
                    ),
                ),
            ],
            options={"ordering": ("created_at", "id")},
        ),
        migrations.RunPython(convert_agent_manifests, migrations.RunPython.noop),
    ]
