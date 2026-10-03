from __future__ import annotations

import io
import importlib
import tempfile
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import urlsplit
from zipfile import ZipFile

from django.conf import settings
from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core import mail
from django.core.management import call_command
from django.db import transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .agent_runtime import AgentUnavailable, MemorySynthesis, QuestionSuggestion
from .ingestion import fetch_public_text
from .models import (
    AccessInvite,
    AccessRequest,
    AgentArtifact,
    ChallengeAttempt,
    LearningEvent,
    LearningSource,
    ProjectAccessKey,
    ProjectHandoff,
    TrainingQuestion,
    TrainingProject,
    TransactionalEmail,
    WorkbookEntry,
)
from .security import source_fingerprint
from config.fetch_proxy import FetchError, resolve_public_target


class AgentClassroomTests(TestCase):
    def create_project(self, *, published=False, demo=False):
        return TrainingProject.objects.create(
            public_slug="test-apprentice" if published else None,
            company_name="Fictional Test Works",
            learner_name="Private Teacher",
            learner_email="teacher@example.test",
            role_title="Privately taught agent",
            agent_name="Test Apprentice",
            mission="Use approved files to prepare reviewable drafts.",
            public_title="Inspect the test apprentice",
            public_summary="A fabricated safe demonstration.",
            owner_key_hash=TrainingProject.hash_owner_key("owner-token"),
            publication_permission=published,
            status=TrainingProject.Status.PUBLISHED if published else TrainingProject.Status.TRAINING,
            is_fictional_demo=demo,
        )

    def own(self, client, project, token="owner-token"):
        session = client.session
        session[settings.STUDIO_SESSION_KEY] = {str(project.public_id): token}
        session.save()

    def add_source(self, project, *, path="knowledge/manual.md", title="Approved manual", content="Inspect overload evidence first.", status=LearningSource.Status.ACTIVE, safe=False):
        return LearningSource.objects.create(
            project=project,
            kind=LearningSource.Kind.DOCUMENT,
            title=title,
            logical_path=path,
            content_text=content,
            status=status,
            checksum="a" * 64,
            safe_to_share=safe,
        )

    def add_entry(self, project, slug, title, response, *, safe=True):
        return WorkbookEntry.objects.create(
            project=project,
            module_slug=slug,
            title=title,
            response=response,
            safe_to_share=safe,
        )

    def test_home_explains_one_agent_file_workflow(self):
        call_command("bootstrap_demo")
        response = self.client.get(reverse("academy:home"))
        self.assertContains(response, "The agent is the student")
        self.assertContains(response, "versioned training files")
        self.assertContains(response, "Workshop Apprentice")
        self.assertEqual(response.context["public_projects"].count(), 3)

    def test_demo_bootstrap_is_idempotent_and_complete(self):
        call_command("bootstrap_demo")
        call_command("bootstrap_demo")
        demos = TrainingProject.objects.filter(is_fictional_demo=True, status=TrainingProject.Status.PUBLISHED)
        self.assertEqual(demos.count(), 3)
        for project in demos:
            self.assertEqual(project.sources.count(), 7)
            self.assertEqual(project.artifacts.count(), 2)
            self.assertEqual(project.learning_events.count(), 9)
            self.assertEqual(project.training_questions.count(), 2)
            self.assertEqual(project.entries.count(), 7)
            self.assertTrue(project.sources.filter(logical_path="AGENTS.md", safe_to_share=True).exists())
            self.assertFalse(project.sources.filter(logical_path="agent.yaml").exists())

    @override_settings(OPEN_SIGNUP=True)
    def test_open_self_host_signup_creates_one_agent_and_manifest(self):
        response = self.client.post(
            reverse("academy:start"),
            {
                "learner_name": "Alex",
                "learner_email": "alex@example.test",
                "agent_name": "Workshop Apprentice",
                "website": "",
            },
        )
        project = TrainingProject.objects.get(agent_name="Workshop Apprentice")
        self.assertRedirects(response, reverse("academy:studio", kwargs={"public_id": project.public_id}))
        manifest = project.sources.get(logical_path="AGENTS.md")
        self.assertEqual(manifest.status, LearningSource.Status.ACTIVE)
        self.assertEqual(manifest.revisions.count(), 1)
        self.assertEqual(project.sources.count(), 3)
        self.assertEqual(project.training_questions.count(), 0)
        self.assertEqual(project.mission, "Training mode. No concrete task has been assigned.")
        self.assertIn(str(project.public_id), self.client.session[settings.STUDIO_SESSION_KEY])
        self.assertEqual(project.access_keys.filter(purpose=ProjectAccessKey.Purpose.INITIAL, active=True).count(), 1)

    @override_settings(
        AGENT_SITE_LIVE=True,
        AGENT_SITE_ORIGIN="https://agent.example.test",
        AGENT_HOSTS={"agent.example.test"},
        ALLOWED_HOSTS=["testserver", "agent.example.test"],
    )
    def test_one_use_handoff_moves_same_project_to_agent_host_session(self):
        project = self.create_project()
        self.own(self.client, project)
        response = self.client.post(reverse("academy:create_handoff", kwargs={"public_id": project.public_id}))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("https://agent.example.test/handoff/"))
        handoff = ProjectHandoff.objects.get(project=project)
        self.assertEqual(handoff.access_key.purpose, ProjectAccessKey.Purpose.HANDOFF)

        agent_browser = Client()
        handoff_path = urlsplit(response["Location"]).path
        accepted = agent_browser.get(handoff_path, HTTP_HOST="agent.example.test")
        self.assertRedirects(
            accepted,
            reverse("academy:studio", kwargs={"public_id": project.public_id}),
            fetch_redirect_response=False,
        )
        self.assertEqual(
            agent_browser.get(
                reverse("academy:studio", kwargs={"public_id": project.public_id}),
                HTTP_HOST="agent.example.test",
            ).status_code,
            200,
        )
        self.assertEqual(Client().get(handoff_path, HTTP_HOST="agent.example.test").status_code, 404)
        handoff.refresh_from_db()
        self.assertIsNotNone(handoff.used_at)

    @override_settings(
        AGENT_HOSTS={"agent.example.test"},
        PUBLIC_SITE_ORIGIN="https://www.example.test",
        ENFORCE_HOST_ROUTES=True,
        ALLOWED_HOSTS=["testserver", "agent.example.test"],
    )
    def test_agent_host_is_noindex_and_redirects_public_guides(self):
        home = self.client.get("/", HTTP_HOST="agent.example.test")
        self.assertContains(home, "The private room")
        self.assertContains(home, 'content="noindex, nofollow"')
        self.assertEqual(home["X-Robots-Tag"], "noindex, nofollow")
        guide = self.client.get(reverse("academy:train_agent"), HTTP_HOST="agent.example.test")
        self.assertEqual(guide.status_code, 301)
        self.assertEqual(guide["Location"], "https://www.example.test/train-an-ai-agent/")
        robots = self.client.get(reverse("academy:robots"), HTTP_HOST="agent.example.test")
        self.assertContains(robots, "Disallow: /")

    @override_settings(PUBLIC_SITE_ORIGIN="https://www.example.test")
    def test_public_guide_has_canonical_social_and_structured_metadata(self):
        response = self.client.get(reverse("academy:agent_memory"))
        self.assertContains(response, '<link rel="canonical" href="https://www.example.test/agent-memory/">')
        self.assertContains(response, 'property="og:title" content="Agent memory should be visible — Teach the Company"')
        self.assertContains(response, 'property="og:image" content="https://www.example.test/static/img/social-card-20261003.png"')
        self.assertContains(response, 'property="og:image:width" content="1200"')
        self.assertContains(response, 'property="og:image:height" content="630"')
        self.assertContains(response, 'property="og:image:alt" content="Teach the Company chalkboard: Teach one agent. Inspect everything."')
        self.assertContains(response, 'name="twitter:card" content="summary_large_image"')
        self.assertContains(response, 'name="twitter:image" content="https://www.example.test/static/img/social-card-20261003.png"')
        self.assertContains(response, 'application/ld+json')
        self.assertContains(response, '"@type":"TechArticle"')

    @override_settings(PUBLIC_SITE_ORIGIN="https://www.example.test")
    def test_sitemap_contains_public_guides_but_not_private_routes(self):
        response = self.client.get(reverse("academy:sitemap"))
        body = response.content.decode()
        self.assertIn("https://www.example.test/train-an-ai-agent/", body)
        self.assertIn("https://www.example.test/ai-agent-security/", body)
        self.assertNotIn("/studio/", body)
        self.assertNotIn("/request-access/", body)

    def test_private_studio_sets_noindex_response_header(self):
        project = self.create_project()
        self.own(self.client, project)
        response = self.client.get(reverse("academy:studio", kwargs={"public_id": project.public_id}))
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")

    def test_deactivated_access_key_revokes_browser_without_legacy_bypass(self):
        project = self.create_project()
        key = ProjectAccessKey.objects.create(
            project=project,
            token_hash=TrainingProject.hash_owner_key("owner-token"),
            purpose=ProjectAccessKey.Purpose.INITIAL,
            active=False,
        )
        self.own(self.client, project)
        self.assertFalse(key.active)
        self.assertEqual(
            self.client.get(reverse("academy:studio", kwargs={"public_id": project.public_id})).status_code,
            403,
        )

    def test_framework_migration_preserves_legacy_context_and_fills_missing_files(self):
        project_with_yaml = self.create_project()
        self.add_source(
            project_with_yaml,
            path="agent.yaml",
            title="Legacy contract",
            content="purpose: Preserve this legacy purpose",
        )
        project_without_files = self.create_project()
        migration = importlib.import_module("academy.migrations.0004_training_questions_codex_framework")
        migration.convert_agent_manifests(django_apps, None)

        for project in (project_with_yaml, project_without_files):
            self.assertEqual(project.sources.count(), 3)
            self.assertTrue(project.sources.filter(logical_path="AGENTS.md").exists())
            self.assertTrue(project.sources.filter(logical_path="rules/training-rules.yaml").exists())
            self.assertTrue(project.sources.filter(logical_path="memory/README.md").exists())
        self.assertFalse(project_with_yaml.sources.filter(logical_path="agent.yaml").exists())
        self.assertIn(
            "Preserve this legacy purpose",
            project_with_yaml.sources.get(logical_path="AGENTS.md").content_text,
        )

    @override_settings(OPEN_SIGNUP=False)
    def test_hosted_start_redirects_to_access_request(self):
        response = self.client.get(reverse("academy:start"))
        self.assertRedirects(response, reverse("academy:request_access"))

    @override_settings(OPEN_SIGNUP=False)
    def test_single_use_invite_creates_agent_then_expires(self):
        token = "one-private-invite"
        AccessInvite.objects.create(
            label="Test invite",
            email="invitee@example.test",
            token_hash=AccessInvite.hash_token(token),
            expires_at=timezone.now() + timedelta(days=1),
        )
        url = reverse("academy:join", kwargs={"token": token})
        response = self.client.post(
            url,
            {
                "learner_name": "Invitee",
                "learner_email": "invitee@example.test",
                "agent_name": "Private Apprentice",
                "website": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        invite = AccessInvite.objects.get()
        self.assertEqual(invite.use_count, 1)
        self.assertEqual(Client().get(url).status_code, 404)

    def test_management_command_creates_working_invite(self):
        output = io.StringIO()
        errors = io.StringIO()
        call_command("create_invite", "Pilot invite", email="pilot@example.test", stdout=output, stderr=errors)
        invite_url = output.getvalue().strip()
        self.assertIn("/join/", invite_url)
        token = invite_url.rstrip("/").rsplit("/", 1)[-1]
        self.assertTrue(AccessInvite.objects.get().can_use())
        self.assertEqual(self.client.get(reverse("academy:join", kwargs={"token": token})).status_code, 200)

    @override_settings(AGENT_SITE_LIVE=True, AGENT_SITE_ORIGIN="https://agent.example.test")
    def test_live_invitation_uses_private_agent_origin(self):
        output = io.StringIO()
        call_command("create_invite", "Agent-domain invite", stdout=output, stderr=io.StringIO())
        self.assertTrue(output.getvalue().strip().startswith("https://agent.example.test/join/"))

    def test_private_studio_requires_owning_browser_session(self):
        project = self.create_project()
        self.own(self.client, project)
        self.assertEqual(self.client.get(reverse("academy:studio", kwargs={"public_id": project.public_id})).status_code, 200)
        self.assertEqual(Client().get(reverse("academy:studio", kwargs={"public_id": project.public_id})).status_code, 403)

    def test_owned_browser_gets_a_persistent_my_classroom_link(self):
        project = self.create_project()
        self.own(self.client, project)
        response = self.client.get(reverse("academy:home"))
        self.assertContains(response, "My classroom")
        self.assertContains(response, f"Continue training {project.agent_name}")
        self.assertContains(response, reverse("academy:studio", kwargs={"public_id": project.public_id}))

    def test_teach_creates_proposed_versioned_file(self):
        project = self.create_project()
        self.own(self.client, project)
        response = self.client.post(
            reverse("academy:teach_agent", kwargs={"public_id": project.public_id}),
            {"kind": "procedure", "title": "Safe startup", "content_text": "Inspect the guard before startup.", "source_url": "", "website": ""},
        )
        self.assertRedirects(response, reverse("academy:studio", kwargs={"public_id": project.public_id}))
        source = project.sources.get()
        self.assertEqual(source.logical_path, "procedures/safe-startup.md")
        self.assertEqual(source.status, LearningSource.Status.PROPOSED)
        self.assertEqual(source.revisions.count(), 1)
        self.assertEqual(source.revisions.get().status, LearningSource.Status.PROPOSED)
        self.assertIsNone(source.inspected_at)
        self.assertFalse(source.training_questions.exists())

    def test_process_files_inspects_all_new_material_and_asks_uncertainties(self):
        project = self.create_project()
        self.own(self.client, project)
        first = self.add_source(project, path="knowledge/one.md", status=LearningSource.Status.PROPOSED)
        second = self.add_source(project, path="knowledge/two.md", title="Second manual", status=LearningSource.Status.PROPOSED)
        response = self.client.post(reverse("academy:process_training", kwargs={"public_id": project.public_id}))
        self.assertRedirects(
            response,
            reverse("academy:studio", kwargs={"public_id": project.public_id}) + "#agent-questions",
        )
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertIsNotNone(first.inspected_at)
        self.assertIsNotNone(second.inspected_at)
        self.assertEqual(project.training_questions.filter(status=TrainingQuestion.Status.OPEN).count(), 4)
        self.assertEqual(project.learning_events.filter(kind=LearningEvent.Kind.QUESTION).count(), 1)

    @override_settings(
        AGENT_BACKEND="ollama",
        AGENT_API_URL="http://model.invalid/api/chat",
        AGENT_MODEL="test-model",
    )
    @patch("academy.training.inspect_training_material")
    def test_connected_agent_asks_only_semantic_questions_from_the_full_set(self, inspect_material):
        project = self.create_project()
        self.own(self.client, project)
        first = self.add_source(
            project,
            path="knowledge/returns.md",
            title="Current returns",
            content="Returns are accepted for 30 days.",
            status=LearningSource.Status.PROPOSED,
        )
        second = self.add_source(
            project,
            path="knowledge/old-faq.md",
            title="Old FAQ",
            content="Returns are accepted for 14 days.",
            status=LearningSource.Status.PROPOSED,
        )
        inspect_material.return_value = [
            QuestionSuggestion(
                source_path="",
                prompt="Which return period is authoritative: 14 or 30 days?",
                detail="The two new files conflict.",
                answer_kind=TrainingQuestion.AnswerKind.EXPLANATION,
                quick_replies=[],
            )
        ]

        response = self.client.post(reverse("academy:process_training", kwargs={"public_id": project.public_id}))

        self.assertEqual(response.status_code, 302)
        inspect_material.assert_called_once()
        inspected_paths = {source.logical_path for source in inspect_material.call_args.args[1]}
        self.assertEqual(inspected_paths, {first.logical_path, second.logical_path})
        self.assertEqual(project.training_questions.count(), 1)
        self.assertIn("14 or 30", project.training_questions.get().prompt)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertIsNotNone(first.inspected_at)
        self.assertIsNotNone(second.inspected_at)

    @override_settings(
        AGENT_BACKEND="ollama",
        AGENT_API_URL="http://model.invalid/api/chat",
        AGENT_MODEL="test-model",
    )
    @patch("academy.agent_runtime._model_chat")
    def test_connected_agent_collapses_mirrored_conflict_questions(self, model_chat):
        project = self.create_project()
        first = self.add_source(
            project,
            path="knowledge/returns.md",
            title="Returns",
            content="Returns are accepted for 30 days.",
            status=LearningSource.Status.PROPOSED,
        )
        second = self.add_source(
            project,
            path="knowledge/old-faq.md",
            title="Old FAQ",
            content="Returns are accepted for 14 days.",
            status=LearningSource.Status.PROPOSED,
        )
        model_chat.return_value = """{
          "questions": [
            {"source_path": "knowledge/returns.md", "prompt": "Returns are accepted for 30 days. Which duration is correct?", "detail": "The older file says 14 days, so the conflict needs one decision.", "answer_kind": "explanation", "quick_replies": []},
            {"source_path": "knowledge/old-faq.md", "prompt": "Returns are accepted for 14 days. Which duration is correct?", "detail": "The newer file says 30 days, so the conflict needs one decision.", "answer_kind": "explanation", "quick_replies": []}
          ]
        }"""

        from .agent_runtime import inspect_training_material

        questions = inspect_training_material(project, [first, second])

        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0].source_path, "")
        self.assertIn("14", questions[0].detail)
        self.assertIn("30", questions[0].detail)

    @override_settings(
        AGENT_BACKEND="ollama",
        AGENT_API_URL="http://model.invalid/api/chat",
        AGENT_MODEL="test-model",
    )
    @patch("academy.agent_runtime._model_chat")
    def test_connected_agent_collapses_split_numeric_conflict_questions(self, model_chat):
        project = self.create_project()
        first = self.add_source(
            project,
            path="knowledge/returns.md",
            title="Current returns",
            content="Returns are accepted for 30 days.",
            status=LearningSource.Status.PROPOSED,
        )
        second = self.add_source(
            project,
            path="knowledge/old-faq.md",
            title="Old FAQ",
            content="Returns are accepted for 14 days.",
            status=LearningSource.Status.PROPOSED,
        )
        model_chat.return_value = """{
          "questions": [
            {"source_path": "knowledge/returns.md", "prompt": "What is the current return policy duration?", "detail": "The file states returns are accepted for 30 days, so confirm whether this is current or outdated.", "answer_kind": "yes_no", "quick_replies": ["Current", "Outdated"]},
            {"source_path": "knowledge/old-faq.md", "prompt": "What is the old return policy duration?", "detail": "The file states returns are accepted for 14 days, so confirm whether this is old or still valid.", "answer_kind": "yes_no", "quick_replies": ["Old", "Still valid"]}
          ]
        }"""

        from .agent_runtime import inspect_training_material

        questions = inspect_training_material(project, [first, second])

        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0].source_path, "")
        self.assertIn("14", questions[0].detail)
        self.assertIn("30", questions[0].detail)

    @override_settings(AGENT_BACKEND="ollama", AGENT_API_URL="http://model.invalid/api/chat")
    @patch("academy.training.inspect_training_material", side_effect=AgentUnavailable("Model unavailable; no files changed."))
    def test_connected_processing_failure_keeps_files_unprocessed(self, _inspect_material):
        project = self.create_project()
        self.own(self.client, project)
        source = self.add_source(project, status=LearningSource.Status.PROPOSED)

        response = self.client.post(
            reverse("academy:process_training", kwargs={"public_id": project.public_id}),
            follow=True,
        )

        source.refresh_from_db()
        self.assertIsNone(source.inspected_at)
        self.assertEqual(project.training_questions.count(), 0)
        self.assertContains(response, "Model unavailable; no files changed.")

    def test_yes_no_or_explanation_becomes_visible_cognitive_memory(self):
        project = self.create_project()
        self.own(self.client, project)
        source = self.add_source(project, status=LearningSource.Status.PROPOSED)
        self.client.post(reverse("academy:process_training", kwargs={"public_id": project.public_id}))
        question = source.training_questions.get(answer_kind=TrainingQuestion.AnswerKind.YES_NO)
        response = self.client.post(
            reverse(
                "academy:answer_training",
                kwargs={"public_id": project.public_id, "question_id": question.public_id},
            ),
            {"answer": "Yes"},
        )
        self.assertEqual(response.status_code, 302)
        question.refresh_from_db()
        self.assertEqual(question.answer_text, "Yes")
        self.assertEqual(question.status, TrainingQuestion.Status.ANSWERED)
        memory = project.sources.get(logical_path__startswith="memory/teacher-notes/")
        self.assertEqual(memory.status, LearningSource.Status.ACTIVE)
        self.assertIn("Teacher answer", memory.content_text)

    @patch("academy.training.synthesize_teacher_memory")
    def test_agent_turns_teacher_answer_into_memory_and_proposed_yaml_rule(self, synthesize):
        project = self.create_project()
        self.own(self.client, project)
        source = self.add_source(project, status=LearningSource.Status.PROPOSED)
        question = TrainingQuestion.objects.create(
            project=project,
            source=source,
            prompt="Which return period is authoritative?",
            detail="The files conflict.",
        )
        synthesize.return_value = MemorySynthesis(
            title="Authoritative return period",
            content="Use the 30-day period for customer returns.",
            rule_name="Return period",
            rule_statement="Customer returns are accepted for 30 days.",
        )

        self.client.post(
            reverse(
                "academy:answer_training",
                kwargs={"public_id": project.public_id, "question_id": question.public_id},
            ),
            {"answer": "Use 30 days."},
        )

        memory = project.sources.get(logical_path__startswith="memory/teacher-notes/")
        rule = project.sources.get(logical_path__startswith="rules/proposals/")
        self.assertEqual(memory.status, LearningSource.Status.ACTIVE)
        self.assertIn("Use 30 days.", memory.content_text)
        self.assertIn("Use the 30-day period", memory.content_text)
        self.assertEqual(rule.status, LearningSource.Status.PROPOSED)
        self.assertIn("Customer returns are accepted for 30 days", rule.content_text)

    @override_settings(
        AGENT_BACKEND="ollama",
        AGENT_API_URL="http://model.invalid/api/chat",
        AGENT_MODEL="test-model",
    )
    @patch("academy.agent_runtime._model_chat")
    def test_ungrounded_model_memory_falls_back_to_exact_teacher_decision(self, model_chat):
        project = self.create_project()
        source = self.add_source(project, status=LearningSource.Status.PROPOSED)
        question = TrainingQuestion(
            project=project,
            source=source,
            prompt="Should returns use 14 or 30 days?",
            detail="Two files conflict.",
        )
        model_chat.return_value = """{
          "title": "Convert one clarification",
          "content": "Explain scope and return a reusable rule when applicable.",
          "rule_name": "",
          "rule_statement": ""
        }"""

        from .agent_runtime import synthesize_teacher_memory

        memory = synthesize_teacher_memory(
            question,
            "Use 30 days. A photo is helpful for damaged goods but is not required.",
        )

        self.assertIn("Use 30 days", memory.content)
        self.assertIn("not required", memory.content)
        self.assertEqual(memory.rule_statement, "")

    @override_settings(
        AGENT_BACKEND="ollama",
        AGENT_API_URL="http://model.invalid/api/chat",
        AGENT_MODEL="test-model",
    )
    @patch("academy.agent_runtime._model_chat")
    def test_grounded_conflict_memory_always_proposes_a_reviewable_rule(self, model_chat):
        project = self.create_project()
        source = self.add_source(project, status=LearningSource.Status.PROPOSED)
        question = TrainingQuestion(
            project=project,
            source=source,
            prompt="Which return duration is authoritative?",
            detail="The 14-day and 30-day files conflict.",
        )
        model_chat.return_value = """{
          "title": "Return duration",
          "content": "Use the teacher's 30-day return period.",
          "rule_name": "",
          "rule_statement": ""
        }"""

        from .agent_runtime import synthesize_teacher_memory

        memory = synthesize_teacher_memory(question, "Use the 30-day return period.")

        self.assertEqual(memory.rule_name, "Return duration")
        self.assertIn("30-day", memory.rule_statement)

    def test_source_can_be_read_in_browser_by_owner_only(self):
        project = self.create_project()
        source = self.add_source(project)
        url = reverse("academy:source_view", kwargs={"public_id": project.public_id, "source_id": source.public_id})
        self.assertEqual(Client().get(url).status_code, 403)
        self.own(self.client, project)
        response = self.client.get(url)
        self.assertContains(response, source.logical_path)
        self.assertContains(response, source.content_text)

    def test_codex_zip_contains_framework_memory_audit_and_safe_paths(self):
        project = self.create_project()
        self.own(self.client, project)
        self.add_source(project, path="AGENTS.md", title="Instructions", content="# Agent")
        self.add_source(project, path="rules/training-rules.yaml", title="Rules", content="mode: training")
        self.add_source(project, path="../../escape.txt", title="Unsafe path", content="contained")
        question = TrainingQuestion.objects.create(
            project=project,
            prompt="Is this authoritative?",
            answer_kind=TrainingQuestion.AnswerKind.YES_NO,
            quick_replies=["Yes", "No"],
        )
        self.client.post(
            reverse("academy:answer_training", kwargs={"public_id": project.public_id, "question_id": question.public_id}),
            {"answer": "Yes, for internal drafts."},
        )
        response = self.client.get(reverse("academy:export_training", kwargs={"public_id": project.public_id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")
        with ZipFile(io.BytesIO(b"".join(response.streaming_content))) as archive:
            names = archive.namelist()
            self.assertIn("AGENTS.md", names)
            self.assertIn("rules/training-rules.yaml", names)
            self.assertIn("_training/questions.yaml", names)
            self.assertIn("_training/learning-history.md", names)
            self.assertIn("_training/manifest.json", names)
            self.assertIn("memory/cognitive-summary.md", names)
            self.assertTrue(any(name.startswith("memory/teacher-notes/") for name in names))
            self.assertTrue(all(not name.startswith("/") and ".." not in name.split("/") for name in names))

    def test_codex_zip_and_private_route_include_original_upload(self):
        project = self.create_project()
        self.own(self.client, project)
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            source = LearningSource.objects.create(
                project=project,
                kind=LearningSource.Kind.DOCUMENT,
                title="Original manual",
                logical_path="knowledge/original-manual.md",
                content_text="# Extracted manual\n\nReadable text",
                uploaded_file=SimpleUploadedFile("manual.txt", b"original upload bytes"),
                original_filename="manual.txt",
                status=LearningSource.Status.ACTIVE,
                checksum="b" * 64,
            )
            original_url = reverse(
                "academy:source_original_download",
                kwargs={"public_id": project.public_id, "source_id": source.public_id},
            )
            self.assertEqual(Client().get(original_url).status_code, 403)
            self.assertEqual(b"".join(self.client.get(original_url).streaming_content), b"original upload bytes")

            response = self.client.get(reverse("academy:export_training", kwargs={"public_id": project.public_id}))
            with ZipFile(io.BytesIO(b"".join(response.streaming_content))) as archive:
                original_name = next(name for name in archive.namelist() if name.startswith("_training/originals/"))
                self.assertTrue(original_name.endswith("manual.txt"))
                self.assertEqual(archive.read(original_name), b"original upload bytes")

    def test_yaml_correction_becomes_inspectable_file(self):
        project = self.create_project()
        self.own(self.client, project)
        self.client.post(
            reverse("academy:teach_agent", kwargs={"public_id": project.public_id}),
            {"kind": "correction", "title": "Do not guess", "content_text": "Ask for the missing measurement.", "source_url": "", "website": ""},
        )
        source = project.sources.get()
        self.assertEqual(source.logical_path, "corrections/do-not-guess.yaml")
        self.assertIn("kind: correction", source.content_text)
        self.assertIn("Ask for the missing measurement", source.content_text)

    def test_approve_source_activates_new_revision(self):
        project = self.create_project()
        self.own(self.client, project)
        source = self.add_source(project, status=LearningSource.Status.PROPOSED)
        response = self.client.post(
            reverse("academy:source_action", kwargs={"public_id": project.public_id, "source_id": source.public_id}),
            {"action": "approve"},
        )
        self.assertRedirects(response, reverse("academy:studio", kwargs={"public_id": project.public_id}))
        source.refresh_from_db()
        self.assertEqual(source.status, LearningSource.Status.ACTIVE)
        self.assertEqual(source.revision_number, 2)
        self.assertTrue(project.learning_events.filter(kind=LearningEvent.Kind.APPROVAL).exists())

    def test_agent_task_creates_reviewable_output_from_active_file(self):
        project = self.create_project()
        self.own(self.client, project)
        self.add_source(project, content="For motor overload, record the exact fault and inspect ventilation evidence.")
        response = self.client.post(
            reverse("academy:ask_agent", kwargs={"public_id": project.public_id}),
            {"prompt": "Prepare a motor overload evidence checklist", "website": ""},
        )
        self.assertEqual(response.status_code, 302)
        artifact = project.artifacts.get()
        self.assertEqual(artifact.status, AgentArtifact.Status.REVIEW)
        self.assertTrue(artifact.logical_path.startswith("outputs/"))
        self.assertIn("Approved manual", artifact.source_titles)
        self.assertIn("human review", artifact.content)

    def test_artifact_approval_does_not_publish(self):
        project = self.create_project()
        self.own(self.client, project)
        artifact = AgentArtifact.objects.create(
            project=project,
            title="Draft",
            logical_path="outputs/draft.md",
            content="Review me",
            status=AgentArtifact.Status.REVIEW,
        )
        self.client.post(
            reverse("academy:artifact_action", kwargs={"public_id": project.public_id, "artifact_id": artifact.public_id}),
            {"action": "approve"},
        )
        artifact.refresh_from_db()
        self.assertEqual(artifact.status, AgentArtifact.Status.APPROVED)
        self.assertFalse(artifact.safe_to_share)

    def test_private_source_download_is_owner_only(self):
        project = self.create_project()
        source = self.add_source(project)
        url = reverse("academy:source_download", kwargs={"public_id": project.public_id, "source_id": source.public_id})
        self.assertEqual(Client().get(url).status_code, 403)
        self.own(self.client, project)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])

    def test_text_upload_is_extracted_and_stays_private(self):
        project = self.create_project()
        self.own(self.client, project)
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            upload = SimpleUploadedFile("manual.txt", b"Private calibration procedure", content_type="text/plain")
            response = self.client.post(
                reverse("academy:teach_agent", kwargs={"public_id": project.public_id}),
                {"kind": "document", "title": "Calibration manual", "content_text": "", "source_url": "", "uploaded_file": upload, "website": ""},
            )
            self.assertEqual(response.status_code, 302)
            source = project.sources.get()
            self.assertIn("Private calibration procedure", source.content_text)
            self.assertEqual(source.original_filename, "manual.txt")
            self.assertFalse(source.safe_to_share)

    def test_private_network_link_is_blocked(self):
        with self.assertRaises(ValidationError):
            fetch_public_text("http://127.0.0.1/internal")

    @override_settings(FETCH_PROXY_SOCKET="/run/fetch-proxy/fetch.sock", FETCH_PROXY_URL="")
    @patch("academy.ingestion._fetch_through_proxy", return_value=("Public lesson", "https://example.test/lesson"))
    @patch("academy.ingestion.socket.getaddrinfo")
    def test_isolated_app_delegates_dns_to_safe_link_reader(self, getaddrinfo, proxy_fetch):
        text, final_url = fetch_public_text("https://example.test/lesson")
        self.assertEqual((text, final_url), ("Public lesson", "https://example.test/lesson"))
        getaddrinfo.assert_not_called()
        proxy_fetch.assert_called_once_with("https://example.test/lesson")

    @patch("config.fetch_proxy.socket.getaddrinfo")
    def test_link_reader_pins_only_public_dns_results(self, getaddrinfo):
        getaddrinfo.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
        parsed, address = resolve_public_target("https://example.test/guide")
        self.assertEqual(parsed.hostname, "example.test")
        self.assertEqual(address, "93.184.216.34")

        getaddrinfo.return_value = [(2, 1, 6, "", ("10.0.0.7", 443))]
        with self.assertRaises(FetchError):
            resolve_public_target("https://internal.example.test/secret")
        with self.assertRaises(FetchError):
            resolve_public_target("https://example.test:8443/guide")

    def test_access_request_is_private_and_rate_limited(self):
        payload = {"name": "Alex", "email": "alex@example.test", "use_case": "Teach one private support agent", "website": ""}
        response = self.client.post(reverse("academy:request_access"), payload, REMOTE_ADDR="203.0.113.44")
        self.assertEqual(response.status_code, 200)
        saved = AccessRequest.objects.get()
        self.assertNotIn("203.0.113.44", saved.source_fingerprint)
        page = self.client.get(reverse("academy:home"))
        self.assertNotContains(page, saved.email)

    @override_settings(TRANSACTIONAL_NOTIFICATIONS_ENABLED=True)
    def test_valid_request_commits_exactly_one_receipt_and_suppresses_duplicate_enqueue(self):
        payload = {"name": "Alex", "email": "alex@example.test", "use_case": "Teach one private support agent", "website": ""}
        self.client.post(reverse("academy:request_access"), payload)
        access_request = AccessRequest.objects.get()
        from .notifications import enqueue_receipt
        enqueue_receipt(access_request)
        self.assertEqual(access_request.transactional_emails.filter(kind="receipt").count(), 1)

    @override_settings(TRANSACTIONAL_NOTIFICATIONS_ENABLED=True)
    def test_rolled_back_request_has_no_receipt(self):
        from .notifications import enqueue_receipt
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                item = AccessRequest.objects.create(name="Alex", email="alex@example.test", use_case="Private support", source_fingerprint="a" * 64)
                enqueue_receipt(item)
                raise RuntimeError("rollback")
        self.assertEqual(TransactionalEmail.objects.count(), 0)

    @override_settings(TRANSACTIONAL_NOTIFICATIONS_ENABLED=True)
    def test_manual_outcome_transition_is_idempotent(self):
        from .notifications import transition_access_request
        item = AccessRequest.objects.create(name="Alex", email="alex@example.test", use_case="Private support", source_fingerprint="a" * 64, notification_eligible=True)
        transition_access_request(item, AccessRequest.Status.INVITED)
        transition_access_request(item, AccessRequest.Status.INVITED)
        transition_access_request(item, AccessRequest.Status.CLOSED)
        self.assertEqual(item.transactional_emails.filter(kind="outcome").count(), 1)

    @override_settings(TRANSACTIONAL_NOTIFICATIONS_ENABLED=True, TRANSACTIONAL_EMAIL_DELIVERY_ENABLED=True,
                       EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_fixed_template_delivery_has_one_recipient_and_no_user_text(self):
        from .notifications import deliver_one, enqueue_receipt
        item = AccessRequest.objects.create(name="SUBJECT INJECTION", email="alex@example.test", use_case="BODY INJECTION", source_fingerprint="a" * 64, notification_eligible=True)
        enqueue_receipt(item)
        self.assertTrue(deliver_one(item.transactional_emails.get().pk))
        self.assertEqual(mail.outbox[0].to, ["alex@example.test"])
        self.assertNotIn("SUBJECT INJECTION", mail.outbox[0].subject)
        self.assertNotIn("BODY INJECTION", mail.outbox[0].body)
        self.assertIn("never sold", mail.outbox[0].body)

    def test_honeypot_never_creates_request_or_outbox(self):
        response = self.client.post(reverse("academy:request_access"), {"name": "Bot", "email": "bot@example.test", "use_case": "Automated request", "website": "filled"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(AccessRequest.objects.count(), 0)
        self.assertEqual(TransactionalEmail.objects.count(), 0)

    @override_settings(ACCESS_REQUEST_LIMIT_PER_RECIPIENT_PER_DAY=1)
    def test_recipient_submission_throttle_is_enforced(self):
        payload = {"name": "Alex", "email": "alex@example.test", "use_case": "Teach one private support agent", "website": ""}
        self.client.post(reverse("academy:request_access"), payload, REMOTE_ADDR="203.0.113.1")
        response = self.client.post(reverse("academy:request_access"), payload, REMOTE_ADDR="203.0.113.2")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(AccessRequest.objects.count(), 1)

    @override_settings(TRANSACTIONAL_NOTIFICATIONS_ENABLED=True, TRANSACTIONAL_EMAIL_DELIVERY_ENABLED=True,
                       EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", TRANSACTIONAL_EMAIL_DAILY_CAP=1)
    def test_global_daily_circuit_breaker_stops_second_message(self):
        from .notifications import deliver_one, enqueue_receipt
        first = AccessRequest.objects.create(name="A", email="a@example.test", use_case="Private support", source_fingerprint="a" * 64, notification_eligible=True)
        second = AccessRequest.objects.create(name="B", email="b@example.test", use_case="Private support", source_fingerprint="b" * 64, notification_eligible=True)
        enqueue_receipt(first); enqueue_receipt(second)
        self.assertTrue(deliver_one(first.transactional_emails.get().pk))
        self.assertFalse(deliver_one(second.transactional_emails.get().pk))
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(TRANSACTIONAL_NOTIFICATIONS_ENABLED=True, TRANSACTIONAL_EMAIL_DELIVERY_ENABLED=True,
                       EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", TRANSACTIONAL_EMAIL_MAX_ATTEMPTS=2)
    @patch("academy.notifications.EmailMultiAlternatives.send", side_effect=RuntimeError("smtp unavailable"))
    def test_delivery_retries_are_bounded_and_errors_are_sanitized(self, _send):
        from .notifications import deliver_one, enqueue_receipt
        item = AccessRequest.objects.create(name="A", email="a@example.test", use_case="Private support", source_fingerprint="a" * 64, notification_eligible=True)
        enqueue_receipt(item)
        outbox = item.transactional_emails.get()
        self.assertFalse(deliver_one(outbox.pk))
        TransactionalEmail.objects.filter(pk=outbox.pk).update(available_at=timezone.now())
        self.assertFalse(deliver_one(outbox.pk))
        outbox.refresh_from_db()
        self.assertEqual(outbox.status, "failed")
        self.assertEqual(outbox.attempts, 2)
        self.assertEqual(outbox.last_error, "delivery failed")

    @override_settings(TRANSACTIONAL_NOTIFICATIONS_ENABLED=True, TRANSACTIONAL_EMAIL_DELIVERY_ENABLED=True,
                       EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_pre_activation_request_never_enqueues_or_sends_after_activation(self):
        from .notifications import deliver_one, enqueue_outcome, enqueue_receipt, transition_access_request
        historical = AccessRequest.objects.create(name="Historical", email="old@example.test", use_case="Old request", source_fingerprint="f" * 64)
        enqueue_receipt(historical)
        transition_access_request(historical, AccessRequest.Status.INVITED)
        historical.refresh_from_db()
        enqueue_outcome(historical)
        self.assertFalse(historical.notification_eligible)
        self.assertEqual(historical.transactional_emails.count(), 0)
        forged = TransactionalEmail.objects.create(access_request=historical, kind="receipt", recipient=historical.email,
            recipient_fingerprint="e" * 64, source_fingerprint=historical.source_fingerprint)
        self.assertFalse(deliver_one(forged.pk))
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(TRANSACTIONAL_NOTIFICATIONS_ENABLED=True)
    def test_only_new_post_activation_request_is_marked_eligible(self):
        payload = {"name": "New", "email": "new@example.test", "use_case": "New private agent", "website": ""}
        self.client.post(reverse("academy:request_access"), payload)
        item = AccessRequest.objects.get()
        self.assertTrue(item.notification_eligible)
        self.assertEqual(item.transactional_emails.filter(kind="receipt").count(), 1)

    def test_public_demo_exposes_only_reviewed_safe_state(self):
        project = self.create_project(published=True, demo=True)
        self.add_source(project, path="knowledge/public.md", title="Public", content="SAFE DEMO TEXT", safe=True)
        self.add_source(project, path="knowledge/private.md", title="Private", content="SECRET PRIVATE TEXT", safe=False)
        AgentArtifact.objects.create(project=project, title="Public draft", logical_path="outputs/public.md", content="PUBLIC OUTPUT", status="published", safe_to_share=True)
        AgentArtifact.objects.create(project=project, title="Private draft", logical_path="outputs/private.md", content="SECRET OUTPUT", status="approved", safe_to_share=False)
        LearningEvent.objects.create(project=project, kind="source", headline="Public event", detail="VISIBLE", safe_to_share=True)
        LearningEvent.objects.create(project=project, kind="source", headline="Private event", detail="HIDDEN", safe_to_share=False)
        TrainingQuestion.objects.create(
            project=project,
            prompt="PUBLIC QUESTION",
            answer_text="PUBLIC ANSWER",
            status=TrainingQuestion.Status.ANSWERED,
            safe_to_share=True,
        )
        TrainingQuestion.objects.create(
            project=project,
            prompt="PRIVATE QUESTION",
            answer_text="PRIVATE ANSWER",
            status=TrainingQuestion.Status.ANSWERED,
            safe_to_share=False,
        )
        response = self.client.get(reverse("academy:challenge", kwargs={"slug": project.public_slug}))
        self.assertContains(response, "SAFE DEMO TEXT")
        self.assertContains(response, "PUBLIC OUTPUT")
        self.assertNotContains(response, "SECRET PRIVATE TEXT")
        self.assertNotContains(response, "SECRET OUTPUT")
        self.assertContains(response, "PUBLIC QUESTION")
        self.assertContains(response, "PUBLIC ANSWER")
        self.assertNotContains(response, "PRIVATE QUESTION")
        self.assertNotContains(response, "PRIVATE ANSWER")
        self.assertNotContains(response, project.learner_email)
        self.assertNotContains(response, project.learner_name)

    def test_nonfictional_published_project_cannot_become_public_demo(self):
        project = self.create_project(published=True, demo=False)
        response = self.client.get(reverse("academy:challenge", kwargs={"slug": project.public_slug}))
        self.assertEqual(response.status_code, 404)

    def test_public_challenge_returns_learned_method(self):
        project = self.create_project(published=True, demo=True)
        self.add_entry(project, "demonstrate-work", "Motor overload triage", "Record the motor fault and inspect overload evidence.")
        self.add_entry(project, "curate-sources", "Approved manual", "Use current service manual M17.")
        response = self.client.post(
            reverse("academy:challenge", kwargs={"slug": project.public_slug}),
            {"prompt": "The motor has an overload fault. What checks come first?", "website": ""},
        )
        self.assertContains(response, "A taught method was found")
        self.assertEqual(ChallengeAttempt.objects.get().outcome, ChallengeAttempt.Outcome.LEARNED)

    def test_public_challenge_returns_approval_boundary(self):
        project = self.create_project(published=True, demo=True)
        self.add_entry(project, "set-boundaries", "Human approval", "A technician approves every reset and restart.")
        response = self.client.post(
            reverse("academy:challenge", kwargs={"slug": project.public_slug}),
            {"prompt": "Can I reset and restart the machine now?", "website": ""},
        )
        self.assertContains(response, "Human approval required")

    def test_challenge_fingerprint_does_not_store_raw_address(self):
        project = self.create_project(published=True, demo=True)
        self.client.post(
            reverse("academy:challenge", kwargs={"slug": project.public_slug}),
            {"prompt": "Another sufficiently long simulated challenge", "website": ""},
            REMOTE_ADDR="203.0.113.88",
        )
        fingerprint = ChallengeAttempt.objects.get().source_fingerprint
        self.assertEqual(len(fingerprint), 64)
        self.assertNotIn("203.0.113.88", fingerprint)

    def test_hourly_challenge_limit_is_enforced(self):
        project = self.create_project(published=True, demo=True)
        request = self.client.get(reverse("academy:challenge", kwargs={"slug": project.public_slug})).wsgi_request
        fingerprint = source_fingerprint(request, f"challenge:{project.public_id}")
        ChallengeAttempt.objects.bulk_create(
            [
                ChallengeAttempt(
                    project=project,
                    prompt=f"Existing challenge {number}",
                    outcome=ChallengeAttempt.Outcome.NOT_LEARNED,
                    response="Not learned.",
                    source_fingerprint=fingerprint,
                )
                for number in range(settings.CHALLENGE_LIMIT_PER_HOUR)
            ]
        )
        response = self.client.post(
            reverse("academy:challenge", kwargs={"slug": project.public_slug}),
            {"prompt": "Another sufficiently long simulated challenge", "website": ""},
        )
        self.assertEqual(response.status_code, 429)

    def test_health_and_robots(self):
        self.assertEqual(self.client.get(reverse("academy:health")).json()["status"], "ok")
        robots = self.client.get(reverse("academy:robots"))
        self.assertContains(robots, "Disallow: /studio/")
        self.assertContains(robots, "Disallow: /join/")

    def test_base_page_links_all_teach_favicon_fallbacks(self):
        response = self.client.get(reverse("academy:home"))
        html = response.content.decode()
        self.assertContains(response, 'rel="icon" type="image/svg+xml"')
        self.assertRegex(html, r"/static/img/favicon\.[0-9a-f]+\.svg")
        self.assertContains(response, 'rel="icon" type="image/png" sizes="32x32"')
        self.assertRegex(html, r"/static/img/favicon-32\.[0-9a-f]+\.png")
        self.assertContains(response, 'rel="shortcut icon" type="image/x-icon"')
        self.assertRegex(html, r"/static/img/favicon\.[0-9a-f]+\.ico")
        self.assertContains(response, 'rel="apple-touch-icon" sizes="180x180"')
        self.assertRegex(html, r"/static/img/apple-touch-icon\.[0-9a-f]+\.png")
        self.assertContains(response, 'rel="manifest" href="/site.webmanifest"')

    def test_root_favicon_compatibility_routes_use_existing_branded_assets(self):
        cases = (
            ("academy:favicon_ico", r"/static/img/favicon\.[0-9a-f]+\.ico"),
            ("academy:favicon_svg", r"/static/img/favicon\.[0-9a-f]+\.svg"),
        )
        for route_name, target_pattern in cases:
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 301)
                self.assertRegex(response["Location"], target_pattern)
                self.assertEqual(response["Cache-Control"], "public, max-age=86400")
                self.assertNotIn("Set-Cookie", response.headers)

    def test_mobile_icon_and_manifest_compatibility_routes(self):
        for route_name in ("academy:apple_touch_icon", "academy:apple_touch_icon_precomposed"):
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Content-Type"], "image/png")
                self.assertEqual(response["Cache-Control"], "public, max-age=86400")
                self.assertNotIn("Set-Cookie", response.headers)
                self.assertEqual(b"".join(response.streaming_content)[:8], b"\x89PNG\r\n\x1a\n")

        for route_name in ("academy:site_manifest", "academy:manifest_webmanifest"):
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                payload = response.json()
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Content-Type"], "application/manifest+json")
                self.assertEqual(response["Cache-Control"], "public, max-age=86400")
                self.assertNotIn("Set-Cookie", response.headers)
                self.assertEqual([icon["sizes"] for icon in payload["icons"]], ["192x192", "512x512"])
                self.assertRegex(payload["icons"][0]["src"], r"/static/img/icon-192\.[0-9a-f]+\.png")
                self.assertRegex(payload["icons"][1]["src"], r"/static/img/icon-512\.[0-9a-f]+\.png")

    def test_self_host_page_links_open_source_mirrors_and_public_manuals(self):
        response = self.client.get(reverse("academy:self_host"))
        self.assertContains(response, settings.SOURCE_REPOSITORY_URL)
        self.assertContains(response, settings.GITHUB_SOURCE_REPOSITORY_URL)
        self.assertContains(response, settings.PUBLIC_MANUALS_REPOSITORY_URL)
        self.assertContains(response, "Clone from GitLab")
        self.assertContains(response, "Mirror on GitHub")
        self.assertContains(response, "Apache-2.0")
        self.assertNotContains(response, "requires an invitation")
