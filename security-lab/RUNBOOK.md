# Agent Security Lab runbook

The lab runs a synthetic **Only What It Needs** experiment in a separate
Compose project. It has no classroom database, uploads, model endpoint, SMTP
identity or credentials. The policy app is reached through a private Unix
socket; only the secret-free preview service binds to loopback.

Use `docker-compose` instead of `docker compose` below when your host provides
the standalone command.

## Start and verify

```bash
docker compose --project-name teach-security-lab \
  -f security-lab/compose.yaml up -d --build
docker compose --project-name teach-security-lab \
  -f security-lab/compose.yaml ps
curl --fail --silent http://127.0.0.1:18575/healthz/
PYTHONPATH=security-lab/app python3 -m unittest discover \
  -s security-lab/tests -v
```

If port `18575` or either small Docker subnet overlaps your environment, set
`TTC_SECURITY_LAB_PORT`, `TTC_SECURITY_LAB_INTERNAL_SUBNET` or
`TTC_SECURITY_LAB_PREVIEW_SUBNET` before starting the project.

## Stop and resume

```bash
docker compose --project-name teach-security-lab \
  -f security-lab/compose.yaml stop
docker compose --project-name teach-security-lab \
  -f security-lab/compose.yaml start
```

The synthetic receipt volume is retained.

## Backup and restore

```bash
docker compose --project-name teach-security-lab \
  -f security-lab/compose.yaml exec -T lab \
  python -m security_lab.manage backup
```

Restore creates a fresh recovery backup first and requires an explicit gate:

```bash
docker compose --project-name teach-security-lab \
  -f security-lab/compose.yaml exec -T \
  -e ALLOW_SECURITY_LAB_RESTORE=yes lab \
  python -m security_lab.manage restore \
  /var/lib/security-lab/backups/<exact-file>.sqlite3
```

## Destructive reset

Reset affects only synthetic receipts but still requires an explicit gate:

```bash
docker compose --project-name teach-security-lab \
  -f security-lab/compose.yaml exec -T \
  -e ALLOW_SECURITY_LAB_RESET=yes lab \
  python -m security_lab.manage reset
```

Do not connect this lab to real customer data or treat its receipt as external
certification.
