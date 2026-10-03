# Teach the Company contributor contract

## Product boundary

- This repository runs one private training classroom for one AI agent.
- Training creates visible, versioned Markdown and YAML files. It does not
  fine-tune model weights.
- Every generated file stays reviewable. Approval does not publish, send or
  execute anything outside the classroom.
- Public demos must remain fictional. Never add real customer, learner or
  employee data to tests, screenshots or fixtures.
- The managed service and self-hosted installations are separate. Repository
  access never grants access to a hosted classroom.

## Security boundary

- Never commit `.env`, credentials, uploaded documents, databases, backups,
  session tokens or provider responses containing private material.
- Keep the web listener on loopback unless the operator deliberately adds a
  trusted HTTPS reverse proxy.
- Preserve browser-session authorization, private-file isolation, SSRF
  restrictions, human approval and the synthetic-only security lab.
- Treat uploaded files, fetched pages and model output as untrusted input.

## Change and verification

1. Keep changes focused and update tests for changed behavior.
2. Run `python manage.py test` in the application container.
3. Run `python manage.py makemigrations --check --dry-run`.
4. Run the security-lab test suite when its source or policy changes.
5. Verify the relevant browser journey at desktop and mobile widths.
6. Document lifecycle or configuration changes in `RUNBOOK.md`.

Use Apache-2.0-compatible contributions and retain `LICENSE` and `NOTICE`.
