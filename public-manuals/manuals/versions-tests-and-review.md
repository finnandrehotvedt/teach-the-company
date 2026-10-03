# Version, test and review agent behavior

Treat changes to agent instructions and memory like changes to software: small revisions, visible diffs, reproducible tests and explicit acceptance.

Audience: People maintaining an agent after its first useful result.
Version: 1.0.0 · Last reviewed: 2026-10-03
Author and director: Finn Andre Hotvedt
Developed with assistance from ChatGPT and Codex by OpenAI.
Related lessons: TTC-113, TTC-114, TTC-115

## Make every meaningful change explainable

A revision should say what changed, why it changed, who reviewed it and how to test it. Git provides durable history and comparison, but a commit alone does not prove the behavior is correct.

Keep changes narrow enough to revert. Preserve the previous accepted version until the new version passes its tests and can be restored without losing unrelated work.

- Review the diff for accidental scope expansion.
- Run positive, negative and uncertainty cases.
- Record the evidence used to accept the revision.
- Confirm the rollback restores the previous behavior.

## Test decisions, not writing style

A useful evaluation asks whether the agent selected the right evidence, respected permissions, surfaced uncertainty and produced the required artifact. Avoid grading only tone or similarity to one preferred sentence.

Include a normal case, a missing-evidence case, a conflicting-source case and a request outside authority. A passing test should be observable and repeatable by another reviewer.


```text
Case: <short name>
Given: <approved evidence and permissions>
When: <user request>
Then: <observable result>
Must not: <unsafe or unsupported behavior>
Evidence: <files, citations or event record>
```

## Keep people accountable for acceptance

The agent can prepare a proposal, test result or draft. A named person accepts consequential changes. The record should distinguish proposed, reviewed, accepted, published and executed states.

A review is strongest when it can explain both the accepted result and the rejected alternatives. Confidence language cannot replace that evidence.


## Public versions

- Canonical HTML: https://teachthecompany.com/manuals/versions-tests-and-review/
- Markdown: https://teachthecompany.com/manuals/versions-tests-and-review.md
- JSON: https://teachthecompany.com/manuals/versions-tests-and-review.json

Licensed under Apache-2.0. See LICENSE and PUBLICATION.md.
