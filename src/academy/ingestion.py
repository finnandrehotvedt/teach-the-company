from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

import yaml
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.text import slugify
from pypdf import PdfReader

from .models import LearningSource, SourceRevision, TrainingProject


MAX_EXTRACTED_CHARACTERS = 120_000
MAX_REMOTE_BYTES = 1_000_000


@dataclass(frozen=True)
class PublicTextSnapshot:
    text: str
    final_url: str
    etag: str = ""
    last_modified: str = ""
    not_modified: bool = False


class _VisibleTextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden_depth += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self.hidden_depth:
            self.hidden_depth -= 1

    def handle_data(self, data):
        if not self.hidden_depth and data.strip():
            self.parts.append(data.strip())

    def text(self) -> str:
        return "\n".join(self.parts)


def _validate_public_url(value: str, *, resolve: bool = True) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValidationError("Use a public HTTP or HTTPS link without embedded credentials.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValidationError("Use a valid public HTTP or HTTPS link.") from exc
    if port not in {None, 80, 443}:
        raise ValidationError("Public links must use the standard HTTP or HTTPS port.")
    if not resolve:
        return value
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
        }
    except socket.gaierror as exc:
        raise ValidationError("The link hostname could not be resolved.") from exc
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValidationError("Private, local and reserved network addresses cannot be learned from links.")
    return value


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        _validate_public_url(urljoin(request.full_url, new_url))
        return super().redirect_request(request, file_pointer, code, message, headers, new_url)


def _decode_remote_text(body: bytes, content_type: str, charset: str | None) -> str:
    text = body.decode(charset or "utf-8", errors="replace")
    if content_type == "text/html":
        parser = _VisibleTextParser()
        parser.feed(text)
        text = parser.text()
    elif content_type == "application/json":
        try:
            text = json.dumps(json.loads(text), indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            pass
    return text[:MAX_EXTRACTED_CHARACTERS].strip()


def _proxy_result(url: str, *, etag: str = "", last_modified: str = "") -> dict:
    payload = json.dumps(
        {"url": url, "etag": etag[:500], "last_modified": last_modified[:500]}, separators=(",", ":")
    ).encode("utf-8")
    try:
        if settings.FETCH_PROXY_SOCKET:
            connection = _UnixHTTPConnection(settings.FETCH_PROXY_SOCKET, timeout=9)
            try:
                connection.request(
                    "POST",
                    "/fetch",
                    body=payload,
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                )
                response = connection.getresponse()
                if response.headers.get_content_type() != "application/json":
                    raise ValidationError("The safe link reader returned an invalid response.")
                raw_result = response.read(MAX_REMOTE_BYTES * 4 + 1)
                if response.status != 200:
                    raise ValidationError("The link could not be read safely right now.")
            finally:
                connection.close()
        else:
            request = Request(
                settings.FETCH_PROXY_URL,
                data=payload,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                method="POST",
            )
            with build_opener().open(request, timeout=9) as response:
                if response.headers.get_content_type() != "application/json":
                    raise ValidationError("The safe link reader returned an invalid response.")
                raw_result = response.read(MAX_REMOTE_BYTES * 4 + 1)
        return json.loads(raw_result.decode("utf-8"))
    except ValidationError:
        raise
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise ValidationError("The link could not be read safely right now.") from exc


def _fetch_snapshot_through_proxy(url: str, *, etag: str = "", last_modified: str = "") -> PublicTextSnapshot:
    result = _proxy_result(url, etag=etag, last_modified=last_modified)
    try:
        final_url = _validate_public_url(result["final_url"], resolve=False)
        if result.get("not_modified") is True:
            return PublicTextSnapshot(
                "",
                final_url,
                str(result.get("etag", ""))[:500],
                str(result.get("last_modified", ""))[:500],
                True,
            )
        content_type = result["content_type"]
        body = result["body"].encode("utf-8")
    except (KeyError, AttributeError, TypeError) as exc:
        raise ValidationError("The safe link reader returned an invalid response.") from exc
    if content_type not in {"text/html", "text/plain", "text/markdown", "application/json"}:
        raise ValidationError("That link is not a supported text page.")
    return PublicTextSnapshot(
        _decode_remote_text(body, content_type, "utf-8"),
        final_url,
        str(result.get("etag", ""))[:500],
        str(result.get("last_modified", ""))[:500],
        False,
    )


def _fetch_through_proxy(url: str) -> tuple[str, str]:
    snapshot = _fetch_snapshot_through_proxy(url)
    return snapshot.text, snapshot.final_url


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: str, timeout: int):
        self.socket_path = socket_path
        super().__init__("localhost", timeout=timeout)

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.socket_path)


def fetch_public_text(url: str) -> tuple[str, str]:
    use_proxy = bool(settings.FETCH_PROXY_SOCKET or settings.FETCH_PROXY_URL)
    _validate_public_url(url, resolve=not use_proxy)
    if use_proxy:
        return _fetch_through_proxy(url)
    request = Request(
        url,
        headers={
            "User-Agent": "TeachTheCompany/1.0 (+https://teachthecompany.com)",
            "Accept": "text/html,text/plain,application/json,text/markdown;q=0.9",
        },
    )
    try:
        with build_opener(_SafeRedirectHandler()).open(request, timeout=6) as response:
            final_url = response.geturl()
            _validate_public_url(final_url)
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "text/plain", "text/markdown", "application/json"}:
                raise ValidationError("That link is not a supported text page.")
            body = response.read(MAX_REMOTE_BYTES + 1)
            if len(body) > MAX_REMOTE_BYTES:
                raise ValidationError("That page is too large to learn in one lesson.")
            charset = response.headers.get_content_charset() or "utf-8"
            text = body.decode(charset, errors="replace")
    except ValidationError:
        raise
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise ValidationError("The link could not be read safely right now.") from exc

    return _decode_remote_text(text.encode("utf-8"), content_type, "utf-8"), final_url


def fetch_public_snapshot(url: str, *, etag: str = "", last_modified: str = "") -> PublicTextSnapshot:
    """Fetch public text with bounded HTTP validators for recurring review checks."""
    use_proxy = bool(settings.FETCH_PROXY_SOCKET or settings.FETCH_PROXY_URL)
    _validate_public_url(url, resolve=not use_proxy)
    if use_proxy:
        return _fetch_snapshot_through_proxy(url, etag=etag, last_modified=last_modified)
    # The direct-development path retains the same safety checks but does not
    # cache validators; production recurring checks always use the proxy path.
    text, final_url = fetch_public_text(url)
    return PublicTextSnapshot(text, final_url)


def extract_uploaded_text(uploaded) -> str:
    raw = uploaded.read()
    uploaded.seek(0)
    suffix = Path(uploaded.name).suffix.lower()
    try:
        if suffix == ".pdf":
            reader = PdfReader(BytesIO(raw))
            text = "\n\n".join((page.extract_text() or "") for page in reader.pages[:150])
        else:
            text = raw.decode("utf-8", errors="replace")
    except Exception as exc:
        raise ValidationError("The document could not be read. Try exporting it as UTF-8 text or a text-based PDF.") from exc
    text = text[:MAX_EXTRACTED_CHARACTERS].strip()
    if not text:
        raise ValidationError("No readable text was found in the document.")
    return text


def _logical_path(project: TrainingProject, kind: str, title: str) -> str:
    folders = {
        LearningSource.Kind.NOTE: "knowledge",
        LearningSource.Kind.LINK: "knowledge",
        LearningSource.Kind.DOCUMENT: "knowledge",
        LearningSource.Kind.EXAMPLE: "examples",
        LearningSource.Kind.PROCEDURE: "procedures",
        LearningSource.Kind.CORRECTION: "corrections",
        LearningSource.Kind.TEST: "tests",
    }
    suffix = ".yaml" if kind in {LearningSource.Kind.CORRECTION, LearningSource.Kind.TEST} else ".md"
    stem = slugify(title)[:80] or "lesson"
    folder = folders.get(kind, "knowledge")
    candidate = f"{folder}/{stem}{suffix}"
    sequence = 2
    while project.sources.filter(logical_path=candidate).exists():
        candidate = f"{folder}/{stem}-{sequence}{suffix}"
        sequence += 1
    return candidate


def _versioned_content(kind: str, title: str, content: str, source_url: str) -> str:
    if kind in {LearningSource.Kind.CORRECTION, LearningSource.Kind.TEST}:
        return yaml.safe_dump(
            {
                "kind": str(kind),
                "title": title,
                "source": source_url or None,
                "lesson": content,
            },
            sort_keys=False,
            allow_unicode=True,
        ).strip()
    heading = f"# {title}\n\n"
    provenance = f"Source: {source_url}\n\n" if source_url else ""
    return f"{heading}{provenance}{content}".strip()


def prepare_source(source: LearningSource, project: TrainingProject, uploaded=None) -> LearningSource:
    pieces = [source.content_text.strip()] if source.content_text.strip() else []
    if source.source_url:
        fetched, final_url = fetch_public_text(source.source_url)
        source.source_url = final_url
        pieces.append(fetched)
    if uploaded:
        pieces.append(extract_uploaded_text(uploaded))
        source.original_filename = Path(uploaded.name).name[:255]
        source.content_type = getattr(uploaded, "content_type", "")[:120]
        source.byte_size = uploaded.size
    combined = "\n\n---\n\n".join(piece for piece in pieces if piece).strip()
    if not combined:
        raise ValidationError("No readable knowledge was found in this lesson.")
    source.project = project
    source.logical_path = _logical_path(project, source.kind, source.title)
    source.content_text = _versioned_content(source.kind, source.title, combined, source.source_url)
    source.checksum = hashlib.sha256(source.content_text.encode("utf-8")).hexdigest()
    source.status = LearningSource.Status.PROPOSED
    return source


def record_revision(source: LearningSource, note: str) -> SourceRevision:
    return SourceRevision.objects.create(
        source=source,
        number=source.revision_number,
        content_text=source.content_text,
        checksum=source.checksum,
        change_note=note[:240],
        status=source.status,
    )


def _create_framework_source(
    project: TrainingProject,
    *,
    title: str,
    logical_path: str,
    content: str,
) -> LearningSource:
    checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
    source = LearningSource.objects.create(
        project=project,
        kind=LearningSource.Kind.NOTE,
        title=title,
        logical_path=logical_path,
        content_text=content,
        status=LearningSource.Status.ACTIVE,
        checksum=checksum,
        inspected_at=timezone.now(),
    )
    record_revision(source, "Initial training framework")
    return source


def create_agent_framework(project: TrainingProject) -> list[LearningSource]:
    agents_content = f"""# {project.agent_name}

## Current mode

You are in training mode. No concrete role or task has been assigned yet.
Learn from the teacher's approved files and ask concise questions when meaning,
authority, scope, conflicts, exceptions, or missing context are uncertain.

## How to learn

- Read `rules/training-rules.yaml` before using the training material.
- Use only approved files in `knowledge/`, `examples/`, `procedures/`,
  `corrections/`, `tests/`, and `memory/`.
- Treat `memory/teacher-notes/` as durable explanations from the teacher.
- If a question can honestly be answered yes or no, offer those quick replies.
  Always allow the teacher to explain in their own words instead.
- State uncertainty and cite the files used. Never invent a missing rule.
- A draft is not approval. Do not publish, send, purchase, or change an external
  system without an explicit human decision.

## Portability

This file is the root instruction file for a Codex project. The surrounding
folders are the agent's inspectable cognitive memory and training evidence.
""".strip()
    rules_content = yaml.safe_dump(
        {
            "mode": "training",
            "task_assigned": False,
            "knowledge_policy": {
                "use_only_approved_files": True,
                "cite_files_used": True,
                "ask_when_uncertain": True,
                "allow_teacher_explanation": True,
            },
            "quick_replies": {"yes_no_when_binary": True, "values": ["Yes", "No"]},
            "human_approval_required_for": [
                "publishing",
                "sending",
                "purchasing",
                "changing external systems",
            ],
        },
        sort_keys=False,
        allow_unicode=True,
    ).strip()
    memory_content = """# Cognitive memory

This folder contains durable, inspectable memory created during training.

- `teacher-notes/` records answers and explanations from the teacher.
- Corrections belong in `corrections/` as structured YAML rules.
- Open questions and the complete learning history are included in `_training/`
  when the classroom is downloaded.

Memory is evidence, not hidden state: it can be read, versioned, edited, and
moved into another agent project.
""".strip()
    return [
        _create_framework_source(
            project,
            title="Codex agent instructions",
            logical_path="AGENTS.md",
            content=agents_content,
        ),
        _create_framework_source(
            project,
            title="Training rules",
            logical_path="rules/training-rules.yaml",
            content=rules_content,
        ),
        _create_framework_source(
            project,
            title="Cognitive memory map",
            logical_path="memory/README.md",
            content=memory_content,
        ),
    ]
