from __future__ import annotations

import hashlib
from datetime import timedelta

import yaml
from django.core.management.base import BaseCommand
from django.utils import timezone

from academy.curriculum import MODULES
from academy.models import (
    AgentArtifact,
    LearningEvent,
    LearningSource,
    SourceRevision,
    TrainingQuestion,
    TrainingProject,
    WorkbookEntry,
)


DEMOS = [
    {
        "slug": "northstar-workshop-apprentice",
        "company": "Northstar Works · fictional",
        "agent": "Workshop Apprentice",
        "role": "Workshop support",
        "mission": "Use approved manuals and corrections to prepare safe troubleshooting checklists for human review.",
        "title": "Watch a workshop agent learn from manuals and corrections",
        "summary": "A fully fictional agent history with versioned source files, one important correction and review-only output.",
        "sources": [
            ("knowledge/m17-overload.md", "Approved M17 manual", "document", "The M17 overload section requires recording the exact fault code, confirming safe state, and checking load, ventilation and connection evidence before forming a conclusion."),
            ("procedures/overload-triage.md", "Overload triage procedure", "procedure", "Confirm a safe state. Record the exact code. Inspect approved load and ventilation evidence. List missing measurements. Prepare findings for a qualified technician."),
            ("corrections/reset-is-not-repair.yaml", "A reset is not a repair", "correction", "Never recommend repeated resets after a protection trip. Preserve fault evidence, identify the cause and require qualified approval before restart."),
            ("tests/intermittent-stop.yaml", "Unexpected intermittent stop", "test", "For an unfamiliar intermittent stop, ask for the missing fault record, cite approved files, separate observation from assumption and stop before recommending action."),
        ],
        "artifacts": [
            ("outputs/overload-checklist.md", "Motor overload evidence checklist", "A review-ready checklist covering safe state, fault code, load evidence, ventilation, connections, missing measurements and technician approval."),
            ("outputs/service-note-draft.md", "Service note draft", "Draft finding: the available evidence is consistent with an overload event, but the cause is not established. A qualified technician must review the missing measurements before restart."),
        ],
    },
    {
        "slug": "harbour-support-apprentice",
        "company": "Harbour Supply · fictional",
        "agent": "Support Apprentice",
        "role": "Customer support drafting",
        "mission": "Use approved policy and examples to prepare honest customer replies without sending them.",
        "title": "See a support agent learn what it may promise",
        "summary": "A fictional support agent that learns policy, studies a good example and is corrected after promising too much.",
        "sources": [
            ("knowledge/returns-policy.md", "Returns policy", "document", "Returns may be requested within 30 days. Damaged deliveries need an order reference and photograph. Refunds are decided by a human reviewer."),
            ("examples/approved-support-reply.md", "Approved support reply", "example", "Acknowledge the problem, restate the known facts, request only missing evidence, and explain the next review step without promising an outcome."),
            ("corrections/no-refund-promises.yaml", "Do not promise refunds", "correction", "The agent once promised an immediate refund. It was corrected: prepare the case and state that a human reviewer decides the outcome."),
            ("tests/damaged-delivery.yaml", "Damaged delivery test", "test", "A customer reports damage but provides no order reference. The correct response asks for the reference and photographs before preparing a review."),
        ],
        "artifacts": [
            ("outputs/damaged-delivery-reply.md", "Damaged delivery reply", "A polite draft asking for the order reference and photographs, with no refund promise and a clear human-review next step."),
            ("outputs/escalation-summary.md", "Escalation summary", "Known facts, missing evidence, applicable policy and the decision that still belongs to a human reviewer."),
        ],
    },
    {
        "slug": "fieldnote-project-apprentice",
        "company": "Fieldnote Studio · fictional",
        "agent": "Project Brief Apprentice",
        "role": "Project brief preparation",
        "mission": "Turn rough ideas into source-linked project briefs while leaving commitments and publishing to a person.",
        "title": "Inspect an agent learning to turn ideas into project briefs",
        "summary": "A fictional project agent with an explicit YAML contract, examples, corrections, tests and visible draft files.",
        "sources": [
            ("knowledge/project-brief-standard.md", "Project brief standard", "document", "Every brief identifies the goal, intended user, evidence, boundaries, acceptance criteria, unknowns and next review decision."),
            ("examples/approved-brief.md", "Approved project brief", "example", "A good brief distinguishes facts from assumptions, keeps the first delivery narrow and names the person who approves scope changes."),
            ("corrections/no-client-commitments.yaml", "Never invent commitments", "correction", "Do not invent deadlines, prices or client promises. Mark them unknown and request a decision from the owner."),
            ("tests/ambiguous-request.yaml", "Ambiguous request test", "test", "Given a two-line idea, identify the intended user and outcome, then ask only for information needed to produce a bounded first brief."),
        ],
        "artifacts": [
            ("outputs/project-brief-v1.md", "Project brief v1", "A concise first brief with goal, user, scope, exclusions, evidence, acceptance checks, unknowns and owner decisions."),
            ("outputs/open-questions.md", "Open questions", "A short list of unresolved deadline, budget and approval questions rather than fabricated commitments."),
        ],
    },
]


def manifest_content(demo):
    return f"""# {demo['agent']}

## Training mode

Learn from approved files, show uncertainty, and ask the teacher concise
questions when meaning, scope, conflicts, or exceptions are unclear.

## Learned specialization

{demo['mission']}

## Rules

- Read `rules/training-rules.yaml` before using the training material.
- Consult durable teacher explanations in `memory/teacher-notes/`.
- Cite the files used and never invent missing guidance.
- Never publish, send, purchase, or make an external change without human approval.
""".strip()


def rules_content():
    return yaml.safe_dump(
        {
            "mode": "training",
            "knowledge_policy": {
                "use_only_approved_files": True,
                "cite_files_used": True,
                "ask_when_uncertain": True,
            },
            "quick_replies": {"yes_no_when_binary": True, "values": ["Yes", "No"]},
            "human_approval_required_for": ["publishing", "sending", "purchasing", "external changes"],
        },
        sort_keys=False,
        allow_unicode=True,
    ).strip()


MEMORY_README = """# Cognitive memory

This folder stores durable teacher explanations and lessons. Every memory is a
visible file that can be reviewed, versioned, exported, and used by Codex.
""".strip()


class Command(BaseCommand):
    help = "Create the fictional, public-safe agent demonstrations idempotently."

    def handle(self, *args, **options):
        now = timezone.now()
        for demo_index, demo in enumerate(DEMOS):
            project, _ = TrainingProject.objects.update_or_create(
                public_slug=demo["slug"],
                defaults={
                    "company_name": demo["company"],
                    "learner_name": "Fictional teacher",
                    "learner_email": f"{demo['slug']}@example.invalid",
                    "role_title": demo["role"],
                    "agent_name": demo["agent"],
                    "mission": demo["mission"],
                    "public_title": demo["title"],
                    "public_summary": demo["summary"],
                    "owner_key_hash": TrainingProject.hash_owner_key(f"disabled-{demo['slug']}"),
                    "publication_permission": True,
                    "status": TrainingProject.Status.PUBLISHED,
                    "is_fictional_demo": True,
                },
            )

            source_rows = [
                ("AGENTS.md", "Codex agent instructions", "note", manifest_content(demo)),
                ("rules/training-rules.yaml", "Training rules", "note", rules_content()),
                ("memory/README.md", "Cognitive memory map", "note", MEMORY_README),
                *demo["sources"],
            ]
            sources = {}
            for source_index, (path, title, kind, content) in enumerate(source_rows):
                checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
                source, _ = LearningSource.objects.update_or_create(
                    project=project,
                    logical_path=path,
                    defaults={
                        "kind": kind,
                        "title": title,
                        "content_text": content,
                        "status": LearningSource.Status.ACTIVE,
                        "checksum": checksum,
                        "safe_to_share": True,
                        "inspected_at": now,
                    },
                )
                SourceRevision.objects.update_or_create(
                    source=source,
                    number=source.revision_number,
                    defaults={
                        "content_text": content,
                        "checksum": checksum,
                        "change_note": "Published fictional demonstration revision",
                        "status": LearningSource.Status.ACTIVE,
                    },
                )
                sources[path] = source
                LearningSource.objects.filter(pk=source.pk).update(
                    learned_at=now - timedelta(days=8 - source_index, hours=demo_index)
                )

            artifacts = {}
            for artifact_index, (path, title, content) in enumerate(demo["artifacts"]):
                artifact = AgentArtifact.objects.filter(project=project, logical_path=path).first()
                if artifact:
                    artifact.title = title
                    artifact.content = content
                    artifact.status = AgentArtifact.Status.PUBLISHED
                    artifact.safe_to_share = True
                    artifact.source_titles = [item[1] for item in demo["sources"][:2]]
                    artifact.save()
                else:
                    artifact = AgentArtifact.objects.create(
                        project=project,
                        title=title,
                        artifact_type="demonstration-draft",
                        logical_path=path,
                        content=content,
                        status=AgentArtifact.Status.PUBLISHED,
                        source_titles=[item[1] for item in demo["sources"][:2]],
                        safe_to_share=True,
                    )
                artifacts[path] = artifact
                AgentArtifact.objects.filter(pk=artifact.pk).update(
                    created_at=now - timedelta(days=2 - artifact_index, hours=demo_index)
                )

            authority_question, _ = TrainingQuestion.objects.update_or_create(
                project=project,
                prompt=f"Should I treat “{demo['sources'][0][1]}” as authoritative guidance?",
                defaults={
                    "source": sources[demo["sources"][0][0]],
                    "detail": f"Asked after inspecting {demo['sources'][0][0]}.",
                    "answer_kind": TrainingQuestion.AnswerKind.YES_NO,
                    "quick_replies": ["Yes", "No"],
                    "status": TrainingQuestion.Status.ANSWERED,
                    "answer_text": "Yes",
                    "safe_to_share": True,
                    "answered_at": now - timedelta(days=6, hours=demo_index),
                },
            )
            context_question, _ = TrainingQuestion.objects.update_or_create(
                project=project,
                prompt=f"When should I use “{demo['sources'][0][1]}”, and what exceptions should I remember?",
                defaults={
                    "source": sources[demo["sources"][0][0]],
                    "detail": "The teacher added context after the agent processed the file.",
                    "answer_kind": TrainingQuestion.AnswerKind.EXPLANATION,
                    "quick_replies": [],
                    "status": TrainingQuestion.Status.ANSWERED,
                    "answer_text": "Use it for relevant draft work, but stop when evidence is missing or a human decision is required.",
                    "safe_to_share": True,
                    "answered_at": now - timedelta(days=5, hours=demo_index),
                },
            )

            LearningEvent.objects.filter(project=project, headline="Agent contract activated").delete()
            timeline = [
                ("source", "Agent instructions activated", "AGENTS.md made training mode and boundaries portable to Codex.", sources["AGENTS.md"], None, 8),
                ("source", f"Learned {demo['sources'][0][0]}", "The first approved knowledge file became active.", sources[demo["sources"][0][0]], None, 7),
                ("question", "Asked whether the first file is authoritative", authority_question.prompt, sources[demo["sources"][0][0]], None, 6),
                ("answer", "Teacher clarified authority and scope", context_question.answer_text, sources[demo["sources"][0][0]], None, 5),
                ("source", f"Learned {demo['sources'][1][0]}", "A demonstrated method was versioned as an agent file.", sources[demo["sources"][1][0]], None, 6),
                ("correction", f"Corrected with {demo['sources'][2][0]}", "A mistake became a durable YAML correction instead of disappearing in chat.", sources[demo["sources"][2][0]], None, 5),
                ("test", f"Tested with {demo['sources'][3][0]}", "The agent was tested against a case it had not simply copied.", sources[demo["sources"][3][0]], None, 3),
                ("artifact", f"Created {demo['artifacts'][0][0]}", "The agent produced a visible draft from approved files.", None, artifacts[demo["artifacts"][0][0]], 2),
                ("approval", f"Approved {demo['artifacts'][0][0]}", "A human reviewed the draft before this fictional public copy was published.", None, artifacts[demo["artifacts"][0][0]], 1),
            ]
            for kind, headline, detail, source, artifact, days_ago in timeline:
                event, _ = LearningEvent.objects.update_or_create(
                    project=project,
                    headline=headline,
                    defaults={
                        "kind": kind,
                        "detail": detail,
                        "related_source": source,
                        "related_artifact": artifact,
                        "safe_to_share": True,
                    },
                )
                LearningEvent.objects.filter(pk=event.pk).update(
                    created_at=now - timedelta(days=days_ago, hours=demo_index)
                )

            LearningSource.objects.filter(project=project, logical_path="agent.yaml").delete()

            legacy_responses = {
                "define-the-job": (demo["role"], demo["mission"]),
                "curate-sources": (demo["sources"][0][1], demo["sources"][0][3]),
                "demonstrate-work": (demo["sources"][1][1], demo["sources"][1][3]),
                "correct-mistakes": (demo["sources"][2][1], demo["sources"][2][3]),
                "set-boundaries": ("Human approval boundary", "The agent prepares drafts. A person approves every publish, send, purchase and external change."),
                "test-surprises": (demo["sources"][3][1], demo["sources"][3][3]),
                "publish-proof": ("Safe fictional demo", "Only reviewed fictional summaries, files and history are public. There are no private documents or real tools."),
            }
            for module in MODULES:
                title, response = legacy_responses[module.slug]
                WorkbookEntry.objects.update_or_create(
                    project=project,
                    module_slug=module.slug,
                    defaults={"title": title, "response": response, "safe_to_share": True},
                )

        self.stdout.write(f"Preserved {len(DEMOS)} fictional agent demonstrations.")
