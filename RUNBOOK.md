# Self-hosting runbook

Teach the Company runs as a loopback-only ingress, Django and PostgreSQL Docker
Compose stack. The application and database remain on an internal network;
only the small ingress service joins the publishing network. PostgreSQL stores
metadata and history, while a separate named volume stores private uploaded
files. Back up and restore both together.

## Requirements

- Docker Engine
- Docker Compose v2 (`docker compose`) or standalone Compose
  (`docker-compose`)
- Python 3 for the local environment generator

The examples below use `docker compose`. Substitute `docker-compose` if that
is the command available on your host.

## First start

```bash
python3 scripts/init_env.py
docker compose config --quiet
docker compose up -d --build
docker compose ps
curl --fail --silent http://127.0.0.1:18574/healthz/
```

Open `http://127.0.0.1:18574`. The generated `.env` is mode `0600`, contains
random local secrets and is ignored by Git. Local signup is enabled by default.

If a configured subnet overlaps your network, change only the matching
`TTC_*_SUBNET` value in `.env`. Change `TTC_HTTP_PORT` if port `18574` is in
use. The application stays bound to `127.0.0.1`.

## Model modes

The default `TTC_AGENT_BACKEND=evidence` mode is deterministic and does not
call a model. It is useful for evaluating the workflow without sending content
to a provider.

For a local Ollama-compatible endpoint:

```text
TTC_AGENT_BACKEND=ollama
TTC_AGENT_API_URL=http://your-model-host:11434/api/chat
TTC_AGENT_MODEL=your-model
```

For an OpenAI-compatible chat-completions endpoint:

```text
TTC_AGENT_BACKEND=openai-compatible
TTC_AGENT_API_URL=https://your-provider.example/v1/chat/completions
TTC_AGENT_MODEL=your-model
TTC_AGENT_API_KEY=your-private-key
```

Store provider credentials only in `.env`. Review the provider's data policy
before sending private training material.

## Status, logs and tests

```bash
docker compose ps
docker compose logs --tail 100 app
docker compose exec -T app python manage.py test
docker compose exec -T app python manage.py check --deploy
docker compose exec -T app python manage.py makemigrations --check --dry-run
```

Install the pinned browser-test dependency and Chromium once, then run the
journey relevant to your change while the stack is running:

```bash
npm ci
npx playwright install chromium
node scripts/browser_acceptance.js
node scripts/chalk_visual_acceptance.js
BASE_URL=http://127.0.0.1:18574 node scripts/favicon_browser_acceptance.js
node security-lab/scripts/browser_acceptance.js
```

Generated screenshots and reports are written below the ignored `evidence/`
directory.

## Backup and restore

Create a paired database/private-file backup:

```bash
scripts/backup.sh
```

The script verifies both archives and writes a checksum manifest below the
ignored, mode-`0700` `backups/` directory.

Restore only after preserving the current state. Restore replaces the
application database schema and private-file volume:

```bash
ALLOW_DATABASE_REPLACE=yes scripts/restore.sh \
  /absolute/path/to/teach-the-company-YYYYMMDDTHHMMSSZ.sql.gz
```

The matching `-private-data.tar.gz` file must be beside the SQL archive.

## Stop, resume and update

An ordinary stop preserves all named volumes:

```bash
docker compose stop
docker compose start
```

For an update, create a verified backup first, retain the previous image, then
rebuild and run the checks above:

```bash
scripts/backup.sh
docker compose build --pull app fetch-proxy
docker compose up -d
```

## HTTPS publication

The provided Compose file intentionally publishes only on loopback. For remote
use, keep that boundary and place a maintained HTTPS reverse proxy in front of
it. Set the public origin, allowed hosts, CSRF trusted origins, secure-cookie,
proxy-header and HSTS settings in `.env`. Do not expose PostgreSQL or the
fetch-proxy socket.

Hosted use should set `TTC_OPEN_SIGNUP=false` and distribute bounded invitations
through the application command instead of enabling public classroom creation.

## Synthetic Agent Security Lab

The optional lab is isolated from classroom state, model credentials and SMTP:

```bash
docker compose --project-name teach-security-lab \
  -f security-lab/compose.yaml up -d --build
curl --fail --silent http://127.0.0.1:18575/healthz/
```

See `security-lab/RUNBOOK.md` for its lifecycle and test commands.

## Destructive reset

Deleting Compose volumes permanently removes the database and private files.
It is intentionally not automated here. Inspect exact volume names and keep a
verified paired backup before performing any reset.
