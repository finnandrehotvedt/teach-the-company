# Public source boundary

This repository contains the complete source needed to run the Teach the
Company agent-training center on infrastructure you control:

- Django application source, templates, migrations and static assets;
- Dockerfile and loopback-only Docker Compose environment;
- PostgreSQL metadata and private-file volume wiring;
- evidence, Ollama and OpenAI-compatible agent backends;
- document, PDF and restricted public-link processing;
- visible agent files, revisions, questions, approvals and Codex ZIP export;
- application, browser and model acceptance tests; and
- the isolated synthetic Agent Security Lab source and tests.

The public repository deliberately does not contain production credentials,
private classroom data, uploaded documents, databases, backups, operational
receipts, internal station memory or server-specific deployment configuration.
Those are runtime records, not missing application source.

Self-hosting is open under Apache-2.0. The managed service at
`teachthecompany.com` remains a separate invitation-based offering operated by
Finn Andre Hotvedt.

## Exact public path allowlist

- `.dockerignore`, `.env.example`, `.gitignore`
- `AGENTS.md`, `CONTRIBUTING.md`, `Dockerfile`, `LICENSE`, `NOTICE`
- `PUBLIC-SOURCE-MANIFEST.md`, `README.md`, `RUNBOOK.md`, `SECURITY.md`,
  `SPECIFICATION.md`
- `compose.yaml`, `requirements.txt`, `package.json`, `package-lock.json`
- `docker/**`
- `src/**`, excluding caches and local databases
- `scripts/**`, excluding caches
- `security-lab/**`, excluding server-specific production overlays and local
  base-image Dockerfiles
- `public-manuals/**`

The public repository starts with a new clean Git history. Private project
history, deployment directories, evidence, handoffs, plans, working memory,
backups, databases, uploads, credentials and runtime volumes are not in this
allowlist.
