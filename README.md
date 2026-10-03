# Teach the Company

**An open-source Docker training center for one AI agent.**

Teach the Company is a private training center for one AI agent. Add links,
documents, examples, procedures and YAML corrections; choose when the agent
processes all new files; answer its uncertainties; and approve the knowledge it
may use. The cognitive memory is visible, versioned and portable—not a
forgotten chat or a database you can never leave.

The complete self-hosting source is open under Apache-2.0 so individuals and
companies can run agent training on infrastructure they control. The managed
service at `teachthecompany.com` is a separate invitation-based offering.

The repository contains:

- a Django/PostgreSQL application with private session-owned classrooms;
- three clearly fictional public agent histories;
- bounded text, document, PDF and public-link ingestion;
- browser-readable files, agent-generated clarification questions and quick
  Yes/No replies;
- a portable ZIP with root `AGENTS.md`, YAML rules, cognitive memory, original
  uploads, questions and learning history for use in Codex;
- a model-driven training runtime with structured questions, local Ollama and
  OpenAI-compatible options, plus an explicit evidence fallback;
- one-time hosted invitations and private access requests;
- paired database/private-file backup and restore; and
- a reusable Docker Compose environment with a loopback-only ingress proxy for self-hosting;
- a restricted public-link reader that leaves the classroom without general
  internet access; and
- an isolated synthetic Agent Security Lab with deterministic privacy receipts.

Quick start:

```bash
python3 scripts/init_env.py
docker compose up -d --build
```

Open `http://127.0.0.1:18574`. See [RUNBOOK.md](RUNBOOK.md) for operations and
[SPECIFICATION.md](SPECIFICATION.md) for product and privacy boundaries.
If your Docker installation provides the standalone Compose command, use
`docker-compose` in place of `docker compose`.
Security reporting is documented in [SECURITY.md](SECURITY.md), the exact
public-source boundary is in
[PUBLIC-SOURCE-MANIFEST.md](PUBLIC-SOURCE-MANIFEST.md), and contributions are
covered by [CONTRIBUTING.md](CONTRIBUTING.md).

Public mirrors:

- GitLab: `https://gitlab.finnandre.no/finnandrehotvedt/teach-the-company`
- GitHub: `https://github.com/finnandrehotvedt/teach-the-company`

The repository contains all application, Docker, migration, test, model-adapter
and synthetic security-lab source needed for self-hosting. Production secrets,
private user data, backups and internal deployment receipts are intentionally
excluded because they are runtime state, not source code.

Created independently by Finn Andre Hotvedt with ChatGPT and Codex from OpenAI.
This is not sponsored, endorsed or operated by OpenAI.
