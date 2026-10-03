#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from academy.manual_content import MANUALS  # noqa: E402
from academy.school_content import LESSONS  # noqa: E402


PUBLIC_REPOSITORY = "https://gitlab.finnandre.no/finnandrehotvedt/teach-the-company-public-manuals"
PUBLIC_SITE = "https://teachthecompany.com"
FORBIDDEN = (
    re.compile(r"\bCT\d{2,3}\b", re.IGNORECASE),
    re.compile(r"\bVM\d{2,3}\b", re.IGNORECASE),
    re.compile(r"/srv/|/var/backups/", re.IGNORECASE),
    re.compile(r"\b(?:10|127|172|185|192)\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
    re.compile(r"receipt[_ -]?id", re.IGNORECASE),
)


def manual_markdown(manual) -> str:
    lines = [
        f"# {manual.title}",
        "",
        manual.summary,
        "",
        f"Audience: {manual.audience}",
        f"Version: {manual.version} · Last reviewed: {manual.reviewed_on}",
        "Author and director: Finn Andre Hotvedt",
        "Developed with assistance from ChatGPT and Codex by OpenAI.",
        f"Related lessons: {', '.join(manual.lesson_ids)}",
    ]
    for section in manual.sections:
        lines.extend(("", f"## {section.title}", ""))
        for paragraph in section.paragraphs:
            lines.extend((paragraph, ""))
        lines.extend(f"- {item}" for item in section.checklist)
        if section.copyable:
            lines.extend(("", "```text", section.copyable, "```"))
    lines.extend(
        (
            "",
            "## Public versions",
            "",
            f"- Canonical HTML: {PUBLIC_SITE}/manuals/{manual.slug}/",
            f"- Markdown: {PUBLIC_SITE}/manuals/{manual.slug}.md",
            f"- JSON: {PUBLIC_SITE}/manuals/{manual.slug}.json",
            "",
            "Licensed under Apache-2.0. See LICENSE and PUBLICATION.md.",
        )
    )
    return "\n".join(lines).strip() + "\n"


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    catalog = {
        "name": "Teach the Company public manuals",
        "version": "1.0.1",
        "reviewed_on": "2026-10-03",
        "author": "Finn Andre Hotvedt",
        "assistance": "Developed with assistance from ChatGPT and Codex by OpenAI.",
        "canonical_site": f"{PUBLIC_SITE}/manuals/",
        "canonical_repository": PUBLIC_REPOSITORY,
        "license": "Apache-2.0",
        "manuals": [
            {
                "slug": manual.slug,
                "title": manual.title,
                "version": manual.version,
                "reviewed_on": manual.reviewed_on,
                "lesson_ids": list(manual.lesson_ids),
                "file": f"manuals/{manual.slug}.md",
                "canonical_url": f"{PUBLIC_SITE}/manuals/{manual.slug}/",
            }
            for manual in MANUALS
        ],
        "lessons": [
            {
                "id": lesson.lesson_id,
                "title": lesson.title,
                "level": lesson.level,
                "canonical_url": f"{PUBLIC_SITE}/school/{lesson.slug}/",
            }
            for lesson in LESSONS
        ],
    }
    readme = f"""# Teach the Company public manuals

This repository is the public, versioned source trail for the safe manuals at
<{PUBLIC_SITE}/manuals/>. It contains the generic learning and agent-training
methods only. It does not contain the private Teach the Company application,
classroom data, customer material, credentials, deployment details or private
infrastructure.

## What is published

- five working manuals covering all twenty stable school subjects;
- an exact machine-readable catalog with canonical website URLs;
- authorship, review date and version metadata; and
- a deterministic verifier plus file hashes.

The manuals cover learning paths and the composer; context, rules, examples
and visible memory; versioning, tests and review; permissions and safe action;
and freshness, portability and generic self-hosting.

## Authorship

Authored and directed by **Finn Andre Hotvedt**. Developed with assistance
from ChatGPT and Codex by OpenAI. Finn retains editorial judgment and accepts
the public versions.

## Verify

```bash
python3 verify.py
```

The website remains canonical for rendered manuals and live reviewed dates.
This repository provides public Git history and reproducible provenance. The
complete application and Docker source is linked from the website's self-host
page.

## Rights

The manuals are available under Apache-2.0. See `LICENSE` and
`PUBLICATION.md`.
"""
    publication = """# Publication notice

Copyright 2026 Finn Andre Hotvedt.

These files are licensed under the Apache License, Version 2.0. You may use,
modify and redistribute them under that license while retaining the required
license and attribution notices.

The materials are educational and do not grant an AI agent permission to
publish, send, purchase, reveal protected data or change systems.
"""
    authors = """# Authors and assistance

- Author, product direction and editorial acceptance: Finn Andre Hotvedt
- AI-assisted drafting and implementation: ChatGPT and Codex by OpenAI

AI assistance does not transfer authorship, responsibility or editorial
judgment. Public examples are fictional and methods are intentionally generic.
"""
    write_text(output / "README.md", readme)
    write_text(output / "PUBLICATION.md", publication)
    write_text(output / "AUTHORS.md", authors)
    write_text(output / "LICENSE", (PROJECT_ROOT / "LICENSE").read_text(encoding="utf-8"))
    write_text(output / "catalog.json", json.dumps(catalog, indent=2, ensure_ascii=False) + "\n")
    for manual in MANUALS:
        write_text(output / "manuals" / f"{manual.slug}.md", manual_markdown(manual))

    tracked = sorted(
        path
        for path in output.rglob("*")
        if path.is_file() and path.name not in {"SHA256SUMS", "verify.py"} and ".git" not in path.parts
    )
    sums = "\n".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(output).as_posix()}" for path in tracked) + "\n"
    write_text(output / "SHA256SUMS", sums)
    verifier = r'''#!/usr/bin/env python3
import hashlib
import json
import pathlib
import re
import sys

root = pathlib.Path(__file__).resolve().parent
for line in (root / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
    expected, relative = line.split("  ", 1)
    actual = hashlib.sha256((root / relative).read_bytes()).hexdigest()
    if actual != expected:
        raise SystemExit(f"hash mismatch: {relative}")

catalog = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
if len(catalog["manuals"]) != 5 or len(catalog["lessons"]) != 20:
    raise SystemExit("catalog coverage mismatch")
if len({lesson["id"] for lesson in catalog["lessons"]}) != 20:
    raise SystemExit("lesson IDs are not unique")
covered = [lesson_id for manual in catalog["manuals"] for lesson_id in manual["lesson_ids"]]
if len(covered) != 20 or len(set(covered)) != 20:
    raise SystemExit("manual lesson coverage mismatch")

text = "\n".join(
    path.read_text(encoding="utf-8")
    for path in root.rglob("*")
    if path.is_file() and path.name != "verify.py" and ".git" not in path.parts
)
for pattern in (r"\bCT\d{2,3}\b", r"\bVM\d{2,3}\b", r"/srv/", r"/var/backups/", r"receipt[_ -]?id"):
    if re.search(pattern, text, re.IGNORECASE):
        raise SystemExit(f"private infrastructure marker found: {pattern}")
print("PUBLIC_MANUALS_OK manuals=5 lessons=20 hashes=verified private_markers=0")
'''
    write_text(output / "verify.py", verifier)
    (output / "verify.py").chmod(0o755)

    complete_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in output.rglob("*")
        if path.is_file() and path.name != "verify.py" and ".git" not in path.parts
    )
    for pattern in FORBIDDEN:
        if pattern.search(complete_text):
            raise SystemExit(f"forbidden private marker in export: {pattern.pattern}")
    print(f"EXPORTED_PUBLIC_MANUALS output={output} manuals={len(MANUALS)} lessons={len(LESSONS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
