from __future__ import annotations

from io import StringIO
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .composer import compose, expand_prerequisites
from .ingestion import PublicTextSnapshot
from .models import KnowledgeReview, PublicInputEvent, PublicSuggestion, TrustedKnowledgeSource
from .manual_content import MANUALS
from .school_content import CANONICAL_GUIDE_ALIASES, LESSONS, LESSON_BY_ID
from config.fetch_proxy import FetchError, fetch as safe_proxy_fetch


class SchoolContentTests(TestCase):
    def test_curriculum_contract_is_complete_and_acyclic(self):
        self.assertEqual(len(LESSONS), 20)
        self.assertEqual({item.lesson_id for item in LESSONS}, {f"TTC-{number}" for number in range(101, 121)})
        self.assertEqual(len({item.slug for item in LESSONS}), 20)
        self.assertEqual(
            set(CANONICAL_GUIDE_ALIASES),
            {
                "/train-an-ai-agent/", "/agent-memory/", "/agents-md/",
                "/yaml-rules-for-ai-agents/", "/version-control-for-ai-agents/", "/ai-agent-security/",
            },
        )
        for lesson in LESSONS:
            expanded = expand_prerequisites([lesson.lesson_id])
            self.assertEqual(expanded[-1], lesson.lesson_id)
            self.assertTrue(lesson.sources)
            self.assertTrue(lesson.success_criteria)
            self.assertTrue(lesson.limitations)
            self.assertTrue(lesson.copyable_material)

    def test_school_and_every_lesson_format_render(self):
        response = self.client.get(reverse("academy:school"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "20 lessons")
        for lesson in LESSONS:
            html = self.client.get(reverse("academy:lesson", kwargs={"slug": lesson.slug}))
            markdown = self.client.get(reverse("academy:lesson_format", kwargs={"slug": lesson.slug, "format": "md"}))
            payload = self.client.get(reverse("academy:lesson_format", kwargs={"slug": lesson.slug, "format": "json"}))
            self.assertEqual((html.status_code, markdown.status_code, payload.status_code), (200, 200, 200))
            self.assertContains(html, lesson.title)
            self.assertIn(lesson.lesson_id, markdown.content.decode())
            self.assertEqual(payload.json()["id"], lesson.lesson_id)

    def test_machine_indexes_and_sitemap_include_public_lessons_only(self):
        markdown = self.client.get(reverse("academy:school_index", kwargs={"format": "md"}))
        payload = self.client.get(reverse("academy:school_index", kwargs={"format": "json"})).json()
        sitemap = self.client.get(reverse("academy:sitemap")).content.decode()
        self.assertEqual(len(payload["lessons"]), 20)
        self.assertIn("TTC-101", markdown.content.decode())
        for lesson in LESSONS:
            self.assertIn(f"/school/{lesson.slug}/", sitemap)
        self.assertNotIn("/studio/", sitemap)
        self.assertNotIn("/request-access/", sitemap)


class PublicManualTests(TestCase):
    def test_manuals_partition_all_twenty_subjects(self):
        lesson_ids = [lesson_id for manual in MANUALS for lesson_id in manual.lesson_ids]
        self.assertEqual(len(MANUALS), 5)
        self.assertEqual(len(lesson_ids), 20)
        self.assertEqual(set(lesson_ids), {item.lesson_id for item in LESSONS})
        self.assertEqual(len(lesson_ids), len(set(lesson_ids)))

    def test_manual_index_and_every_stable_format_render(self):
        index = self.client.get(reverse("academy:manuals"))
        markdown_index = self.client.get(reverse("academy:manual_index", kwargs={"format": "md"}))
        json_index = self.client.get(reverse("academy:manual_index", kwargs={"format": "json"}))
        self.assertEqual((index.status_code, markdown_index.status_code, json_index.status_code), (200, 200, 200))
        self.assertContains(index, "20 of 20 lessons mapped")
        self.assertEqual(len(json_index.json()["manuals"]), 5)
        self.assertEqual(len(json_index.json()["lessons"]), 20)
        for manual in MANUALS:
            html = self.client.get(reverse("academy:manual", kwargs={"slug": manual.slug}))
            markdown = self.client.get(reverse("academy:manual_format", kwargs={"slug": manual.slug, "format": "md"}))
            payload = self.client.get(reverse("academy:manual_format", kwargs={"slug": manual.slug, "format": "json"}))
            self.assertEqual((html.status_code, markdown.status_code, payload.status_code), (200, 200, 200))
            self.assertContains(html, manual.title)
            self.assertIn("Finn Andre Hotvedt", markdown.content.decode())
            self.assertEqual(payload.json()["version"], manual.version)
            self.assertIn("dedicated public manuals", payload.json()["repository_scope"].lower())
            self.assertEqual(payload.json()["license"], "Apache-2.0")

    def test_manuals_are_in_discovery_surfaces_and_exclude_private_infrastructure(self):
        sitemap = self.client.get(reverse("academy:sitemap")).content.decode()
        llms = self.client.get(reverse("academy:llms_txt")).content.decode()
        all_public_text = [self.client.get(reverse("academy:manuals")).content.decode()]
        for manual in MANUALS:
            self.assertIn(f"/manuals/{manual.slug}/", sitemap)
            all_public_text.append(
                self.client.get(reverse("academy:manual_format", kwargs={"slug": manual.slug, "format": "md"})).content.decode()
            )
        self.assertIn("/manuals/index.json", llms)
        combined = "\n".join(all_public_text)
        self.assertNotRegex(combined, r"\b(?:CT|VM)\d{2,3}\b")
        self.assertNotRegex(combined, r"/(?:srv|var/backups)/")
        self.assertNotRegex(combined, r"\b(?:10|172|185|192)\.\d{1,3}\.")
        self.assertNotIn("receipt_id", combined)

    def test_manual_repository_and_complete_source_are_truthfully_scoped(self):
        response = self.client.get(reverse("academy:manuals"))
        self.assertContains(response, "dedicated Teach manuals repository")
        self.assertContains(response, "complete Apache-2.0 application and Docker source")
        self.assertContains(response, "linked from the self-host page")


class CompositionTests(TestCase):
    data = {
        "goal": "teach-agent",
        "experience_level": "practitioner",
        "subjects": ["TTC-108", "TTC-117"],
        "use_case": "Summarize approved fictional workshop notes.",
        "provider": "neutral",
        "hosting": "self-hosted",
        "privacy": "standard",
        "autonomy": "approval",
        "tools": "Django and a local model",
    }

    def test_pack_expands_dependencies_and_preserves_boundaries(self):
        result = compose(self.data, origin="https://teachthecompany.com")
        self.assertIn("TTC-101", result.lesson_ids)
        self.assertIn("TTC-108", result.lesson_ids)
        self.assertIn("Drafts are not permission to publish", result.markdown)
        self.assertIn("https://teachthecompany.com/school/", result.markdown)

    def test_compose_share_url_excludes_free_text(self):
        response = self.client.post(reverse("academy:compose"), self.data)
        self.assertEqual(response.status_code, 200)
        share_url = response.context["share_url"]
        query = parse_qs(urlparse(share_url).query)
        self.assertNotIn("use_case", query)
        self.assertNotIn("tools", query)
        self.assertNotIn("fictional", share_url)
        self.assertEqual(query["subjects"], ["TTC-108", "TTC-117"])

    def test_download_is_markdown_post_response(self):
        response = self.client.post(reverse("academy:composition_download"), self.data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/markdown; charset=utf-8")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(b"Non-negotiable authority boundaries", response.content)

    def test_free_text_is_ignored_on_get_share_links(self):
        response = self.client.get(reverse("academy:compose"), {**self.data, "use_case": "PRIVATE QUERY TEXT", "tools": "secret tool"})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "PRIVATE QUERY TEXT")
        self.assertNotContains(response, "secret tool")

    def test_contradictory_privacy_and_hosting_is_visible(self):
        data = {**self.data, "privacy": "local-sensitive", "hosting": "hosted"}
        response = self.client.post(reverse("academy:compose"), data)
        self.assertContains(response, "Conflict: sensitive material must stay local")

    @override_settings(PUBLIC_SITE_ORIGIN="https://teachthecompany.com", SITE_ORIGIN="https://teachthecompany.com")
    def test_production_pack_uses_only_canonical_public_information_urls(self):
        response = self.client.post(reverse("academy:compose"), self.data)
        self.assertEqual(response.status_code, 200)
        markdown = response.context["result"].markdown
        self.assertIn("https://teachthecompany.com/school/", markdown)
        self.assertNotIn("127.0.0.1", markdown)
        self.assertNotIn("localhost", markdown)


class PublicSuggestionTests(TestCase):
    data = {
        "kind": "correction",
        "title": "Clarify the example",
        "detail": "The fictional example should separate evidence from inference more explicitly.",
        "source_url": "https://www.nist.gov/itl/ai-risk-management-framework",
        "website": "",
    }

    def test_valid_suggestion_is_private_and_acknowledged(self):
        response = self.client.post(reverse("academy:suggest"), self.data, REMOTE_ADDR="198.51.100.10")
        self.assertRedirects(response, reverse("academy:suggest_thanks"))
        self.assertEqual(PublicSuggestion.objects.count(), 1)
        self.assertEqual(PublicSuggestion.objects.get().status, PublicSuggestion.Status.PENDING)
        self.assertNotContains(self.client.get(reverse("academy:suggest_thanks")), self.data["detail"])

    def test_every_post_is_counted_before_validation_and_fourth_is_limited(self):
        invalid = {**self.data, "title": ""}
        for _ in range(3):
            self.client.post(reverse("academy:suggest"), invalid, REMOTE_ADDR="198.51.100.11")
        response = self.client.post(reverse("academy:suggest"), self.data, REMOTE_ADDR="198.51.100.11")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(PublicInputEvent.objects.count(), 4)
        self.assertEqual(PublicSuggestion.objects.count(), 0)

    def test_honeypot_does_not_save(self):
        response = self.client.post(
            reverse("academy:suggest"), {**self.data, "website": "spam.invalid"}, REMOTE_ADDR="198.51.100.12"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PublicSuggestion.objects.count(), 0)
        self.assertEqual(PublicInputEvent.objects.count(), 1)

    def test_post_requires_csrf(self):
        response = Client(enforce_csrf_checks=True).post(reverse("academy:suggest"), self.data)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(PublicSuggestion.objects.count(), 0)


class FreshnessWorkflowTests(TestCase):
    @patch("academy.management.commands.monitor_school_sources.fetch_public_snapshot")
    def test_monitor_baselines_then_prepares_nonpublishing_review(self, fetch):
        fetch.return_value = PublicTextSnapshot(
            "First reviewed primary-source text", "https://example.test/final", '"v1"', "Wed, 01 Oct 2026 00:00:00 GMT"
        )
        output = StringIO()
        call_command("monitor_school_sources", all=True, limit=100, stdout=output)
        self.assertGreater(TrustedKnowledgeSource.objects.count(), 0)
        self.assertEqual(KnowledgeReview.objects.count(), 0)

        fetch.return_value = PublicTextSnapshot(
            "Changed reviewed primary-source text", "https://example.test/final", '"v2"', "Thu, 02 Oct 2026 00:00:00 GMT"
        )
        call_command("monitor_school_sources", all=True, limit=100, stdout=output)
        review = KnowledgeReview.objects.first()
        self.assertIsNotNone(review)
        self.assertEqual(review.status, KnowledgeReview.Status.NEEDS_REVIEW)
        self.assertIn("Changed reviewed", review.evidence_excerpt)
        self.assertEqual(review.draft_prepared_by, "deterministic")
        self.assertIsNotNone(review.draft_prepared_at)
        self.assertFalse(review.published_at)

    @patch("academy.management.commands.monitor_school_sources.fetch_public_snapshot")
    def test_conditional_not_modified_updates_check_without_review(self, fetch):
        source = TrustedKnowledgeSource.objects.create(
            source_key="conditional", title="Conditional", publisher="NIST", url="https://example.test/conditional",
            last_content_hash="c" * 64, last_etag='"v1"', last_modified_header="Wed, 01 Oct 2026 00:00:00 GMT",
        )
        fetch.return_value = PublicTextSnapshot("", source.url, '"v1"', source.last_modified_header, True)
        call_command("monitor_school_sources", all=True, limit=100, stdout=StringIO())
        source.refresh_from_db()
        self.assertEqual(source.last_status, TrustedKnowledgeSource.CheckStatus.OK)
        self.assertEqual(KnowledgeReview.objects.count(), 0)
        fetch.assert_any_call(source.url, etag='"v1"', last_modified=source.last_modified_header)

    def test_publication_requires_accepted_state_and_release_reference(self):
        source = TrustedKnowledgeSource.objects.create(
            source_key="nist-test", title="Test", publisher="NIST", url="https://example.test/source"
        )
        review = KnowledgeReview.objects.create(source=source, observed_hash="a" * 64)
        review.status = KnowledgeReview.Status.PUBLISHED
        with self.assertRaises(ValidationError):
            review.save()
        review.status = KnowledgeReview.Status.IN_REVIEW
        review.claimed_by = "resident-editor"
        review.claimed_at = timezone.now()
        review.save()
        review.status = KnowledgeReview.Status.ACCEPTED
        review.reviewed_by = "resident-editor"
        review.review_notes = "Compared the source evidence with the affected lesson."
        review.reviewed_at = timezone.now()
        review.save()
        review.status = KnowledgeReview.Status.PUBLISHED
        with self.assertRaises(ValidationError):
            review.save()
        review.publication_reference = "release abc123 reviewed by editor"
        review.review_commit = "a" * 40
        source.lesson_ids = ["TTC-101"]
        source.save(update_fields=("lesson_ids",))
        review.approved_lesson_versions = {"TTC-101": "1.1.0"}
        review.save()
        self.assertEqual(review.status, KnowledgeReview.Status.PUBLISHED)
        source.refresh_from_db()
        self.assertEqual(source.last_content_hash, "a" * 64)
        self.assertEqual(source.last_status, TrustedKnowledgeSource.CheckStatus.OK)

    def test_unreviewed_change_draft_is_not_public(self):
        source = TrustedKnowledgeSource.objects.create(
            source_key="private-review", title="Test", publisher="NIST", url="https://example.test/review"
        )
        KnowledgeReview.objects.create(
            source=source,
            observed_hash="b" * 64,
            change_summary="UNREVIEWED DRAFT MUST STAY PRIVATE",
        )
        response = self.client.get(reverse("academy:freshness"))
        self.assertNotContains(response, "UNREVIEWED DRAFT MUST STAY PRIVATE")
        self.assertContains(response, "1 detected change")

    def test_private_queue_claim_review_and_publish_is_release_linked(self):
        source = TrustedKnowledgeSource.objects.create(
            source_key="queue-test",
            title="Queue source",
            publisher="NIST",
            url="https://example.test/queue",
            lesson_ids=["TTC-101"],
            last_content_hash="1" * 64,
        )
        review = KnowledgeReview.objects.create(
            source=source,
            previous_hash="1" * 64,
            observed_hash="2" * 64,
            evidence_excerpt="PRIVATE SOURCE EVIDENCE",
            change_summary="Reviewed source wording changed.",
            proposed_update="Verify the bounded claim in TTC-101.",
            draft_prepared_by="local-agent",
            draft_prepared_at=timezone.now(),
        )
        output = StringIO()
        call_command("process_school_reviews", claim=True, editor="resident-editor", limit=3, stdout=output)
        review.refresh_from_db()
        self.assertEqual(review.status, KnowledgeReview.Status.IN_REVIEW)
        self.assertEqual(review.claimed_by, "resident-editor")

        call_command(
            "process_school_reviews",
            review_id=review.id,
            editor="resident-editor",
            decision="accepted",
            notes="Compared the cited evidence and approved the bounded lesson update.",
            stdout=output,
        )
        review.refresh_from_db()
        self.assertEqual(review.status, KnowledgeReview.Status.ACCEPTED)

        call_command(
            "process_school_reviews",
            publish_id=review.id,
            editor="resident-editor",
            commit="abcdef1234567890",
            release="release school-1.1.0",
            lesson_version=["TTC-101=1.1.0"],
            stdout=output,
        )
        review.refresh_from_db()
        self.assertEqual(review.status, KnowledgeReview.Status.PUBLISHED)
        self.assertEqual(review.review_commit, "abcdef1234567890")
        self.assertEqual(review.approved_lesson_versions, {"TTC-101": "1.1.0"})
        public = self.client.get(reverse("academy:freshness"))
        self.assertContains(public, "release school-1.1.0")
        self.assertContains(public, "TTC-101 1.1.0")
        self.assertNotContains(public, "PRIVATE SOURCE EVIDENCE")

    @patch("academy.management.commands.monitor_school_sources._model_chat")
    @patch("academy.management.commands.monitor_school_sources.connected_backend", return_value=True)
    def test_connected_local_agent_prepares_bounded_private_draft(self, connected, model_chat):
        from academy.management.commands.monitor_school_sources import prepare_draft

        source = TrustedKnowledgeSource(
            source_key="agent-draft",
            title="Agent draft source",
            publisher="NIST",
            url="https://example.test/agent-draft",
            lesson_ids=["TTC-101"],
        )
        model_chat.return_value = (
            '{"change_summary":"A bounded wording change was detected.",'
            '"conflict_flags":["verify_definition"],'
            '"proposed_update":"Compare the definition before editing TTC-101."}'
        )
        draft, mode = prepare_draft(source, "UNTRUSTED EXCERPT")
        self.assertEqual(mode, "local-agent")
        self.assertIn("bounded wording change", draft["change_summary"])
        sent_prompt = model_chat.call_args.args[0][1]["content"]
        self.assertIn("UNTRUSTED CURRENT EXCERPT", sent_prompt)
        self.assertIn("UNTRUSTED EXCERPT", sent_prompt)


class ConditionalFetchProxyTests(TestCase):
    @patch("config.fetch_proxy.PinnedHTTPSConnection")
    @patch("config.fetch_proxy.resolve_public_target")
    def test_proxy_sends_validators_and_accepts_304(self, resolve, connection_class):
        resolve.return_value = (urlparse("https://example.test/source"), "93.184.216.34")
        response = connection_class.return_value.getresponse.return_value
        response.status = 304
        response.getheader.side_effect = lambda name, default=None: {
            "ETag": '"v1"',
            "Last-Modified": "Wed, 01 Oct 2026 00:00:00 GMT",
        }.get(name, default)
        result = safe_proxy_fetch(
            "https://example.test/source",
            etag='"v1"',
            last_modified="Wed, 01 Oct 2026 00:00:00 GMT",
        )
        self.assertTrue(result["not_modified"])
        headers = connection_class.return_value.request.call_args.kwargs["headers"]
        self.assertEqual(headers["If-None-Match"], '"v1"')
        self.assertIn("If-Modified-Since", headers)

    def test_proxy_rejects_header_injection_in_validator(self):
        with self.assertRaises(FetchError):
            safe_proxy_fetch("https://example.test/source", etag='"v1"\r\nX-Evil: yes')


class PublicPrivateBoundaryTests(TestCase):
    @override_settings(ENFORCE_HOST_ROUTES=True, AGENT_HOSTS={"agent.teachthecompany.com"})
    def test_school_on_agent_host_redirects_to_public_origin(self):
        response = self.client.get(reverse("academy:school"), HTTP_HOST="agent.teachthecompany.com")
        self.assertEqual(response.status_code, 301)
        self.assertTrue(response["Location"].startswith("http://127.0.0.1:18574/school/"))

    def test_llms_file_is_truthful_convenience_index(self):
        response = self.client.get(reverse("academy:llms_txt"))
        self.assertContains(response, "Machine-readable index")
        self.assertContains(response, "not permission to publish")
