# Build context, rules, examples and visible memory

Separate temporary context, retrieved evidence, durable reviewed memory and model fine-tuning, then express reusable teaching as inspectable files.

Audience: Teachers preparing agent files and maintainers reviewing what an agent may remember.
Version: 1.0.0 · Last reviewed: 2026-10-03
Author and director: Finn Andre Hotvedt
Developed with assistance from ChatGPT and Codex by OpenAI.
Related lessons: TTC-108, TTC-109, TTC-110, TTC-111, TTC-112

## Keep four mechanisms distinct

Context is the material available during one run. Retrieval selects relevant passages from an approved collection. Visible memory is durable, reviewable project material. Fine-tuning changes model behavior through training and is not what this classroom claims to do.

A useful agent can be taught without changing model weights. Clear files, bounded retrieval, examples, tests and explicit approval often provide a more inspectable first step.


## Use a small portable file contract

AGENTS.md states purpose, scope, working rules and stop conditions. Structured YAML stores narrowly defined reusable rules. Teacher notes preserve grounded explanations. Examples demonstrate desired and rejected behavior. Every file should have a clear owner and revision history.

Do not hide the entire operating method in one long prompt. Split stable policy from changing knowledge and task-specific context so each part can be reviewed and replaced independently.

- Keep instructions separate from untrusted source text.
- Record the source and reason for every durable rule.
- Use examples that include boundaries and counterexamples.
- Retire superseded files instead of silently overwriting history.

```text
# Agent purpose
<what this agent helps with>

# Allowed evidence
<named files or collections>

# Rules
<short, testable instructions>

# Stop and ask
<uncertainty, conflict, permission or consequence triggers>
```

## Turn corrections into reviewed memory

When a teacher corrects an answer, retain the exact explanation and a grounded interpretation. A proposed reusable rule remains a draft until a person approves it. Approval makes the rule available to the agent; it does not publish or execute anything.

Memory should reduce repeated clarification without erasing uncertainty. If two approved sources conflict, preserve both and ask the named decision owner.


## Public versions

- Canonical HTML: https://teachthecompany.com/manuals/context-rules-and-memory/
- Markdown: https://teachthecompany.com/manuals/context-rules-and-memory.md
- JSON: https://teachthecompany.com/manuals/context-rules-and-memory.json

Licensed under Apache-2.0. See LICENSE and PUBLICATION.md.
