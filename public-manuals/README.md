# Teach the Company public manuals

This repository is the public, versioned source trail for the safe manuals at
<https://teachthecompany.com/manuals/>. It contains the generic learning and agent-training
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
