# Contributing

Teach the Company is built around one person teaching one agent through visible
files, explicit processing and human approval. Contributions should preserve
that product contract and keep public examples entirely fictional.

Before proposing a change:

1. describe the user-visible problem;
2. keep private routes, files and tokens out of logs and fixtures;
3. add or update focused tests;
4. run the Django and security-lab suites plus migration drift checks; and
5. update the runbook when lifecycle, networking, backup or rollback changes.

Use pinned container dependencies. Do not commit `.env`, database files,
uploaded documents, credentials, production backups or generated session
tokens. Public-link ingestion must continue through the restricted reader, and
the synthetic security lab must remain disconnected from classroom state,
model, SMTP and secrets.

Contributions intentionally submitted for inclusion are accepted under the
repository's Apache-2.0 license. By contributing, you confirm that you have the
right to submit the work under those terms.
