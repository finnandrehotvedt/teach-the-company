# Maintain freshness and run a portable classroom

Check trusted sources on a bounded schedule, keep editorial review separate from detection, and package the agent files so another compatible workspace can inspect them.

Audience: Maintainers operating a long-lived curriculum or a private self-hosted classroom.
Version: 1.0.0 · Last reviewed: 2026-10-03
Author and director: Finn Andre Hotvedt
Developed with assistance from ChatGPT and Codex by OpenAI.
Related lessons: TTC-119, TTC-120

## Separate checking from reviewing

A lightweight scheduled check can use conditional HTTP requests to detect whether an approved source changed. A detected change creates a private editorial task; it does not rewrite a lesson or publish a claim.

Public status should distinguish when a source was last checked, when its teaching was last reviewed and whether an update is pending. A first observation is a baseline, not proof that the content is current.

- Use an allowlist of primary or authoritative sources.
- Apply strict timeouts, size limits and a daily request budget.
- Keep unreviewed summaries private.
- Publish only through an accepted, versioned release.

## Export files, not hidden state

A portable agent package should contain the root instructions, structured rules, reviewed memory, examples, tests and a manifest of versions and sources. Exclude credentials, session tokens and private runtime state.

After import, inspect every file in the destination, confirm its path and status, and run the same acceptance tests before granting tools or sensitive data.


```text
AGENTS.md
rules/training-rules.yaml
memory/README.md
memory/teacher-notes/<reviewed-note>.md
examples/<bounded-example>.md
tests/<acceptance-case>.md
MANIFEST.md
```

## Self-host the classroom generically

Run the web application, database and optional model as separate services. Bind a review installation to loopback by default, store database and private files in named persistent volumes, and route public traffic only through an existing authenticated web boundary.

Pin dependencies, configure secrets outside the repository, keep outbound fetches behind a restricted proxy, back up database and private files together, and prove restore plus stop/start persistence before relying on the installation.

- Copy the example environment file and supply new secrets.
- Start services with a stable Compose project name.
- Apply migrations and collect static assets.
- Run health, authorization and browser acceptance checks.
- Document backup, restore, update and destructive reset separately.

## Public versions

- Canonical HTML: https://teachthecompany.com/manuals/freshness-portability-and-self-hosting/
- Markdown: https://teachthecompany.com/manuals/freshness-portability-and-self-hosting.md
- JSON: https://teachthecompany.com/manuals/freshness-portability-and-self-hosting.json

Licensed under Apache-2.0. See LICENSE and PUBLICATION.md.
