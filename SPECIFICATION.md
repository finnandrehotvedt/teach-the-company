# Product specification

## Product promise

Teach the Company gives one AI agent durable, inspectable training. A person
adds links, documents, examples, procedures and corrections; processes them as
a set; answers the agent's uncertainties; approves the resulting knowledge;
and exports the visible cognitive memory for use in Codex.

Primary promise: **Teach one AI agent how you work.**

“Teach” means constructing approved context and reusable rules. The product
does not claim to fine-tune model weights. The first release deliberately has
no organization administration, agent fleet or autonomous external actions.

## Core loop

1. Create one private agent in training mode with no concrete task.
2. Add one or more notes, public links, documents, examples, procedures,
   corrections or tests.
3. Press Process so the agent inspects all unprocessed files together.
4. Answer visible uncertainties with Yes/No quick replies or a free explanation.
5. Review each browser-readable file, then approve and activate it.
6. Optionally test the training, or download the complete Codex ZIP.

## Product journeys

- A visitor can inspect three entirely fictional agent histories without an
  account. Each shows safe files, chronology, outputs and approval state.
- A visitor can request a hosted pilot invitation without creating an account.
- An invite can be used only within its configured expiry/use limit.
- A hosted or self-hosted user can teach one private agent and retain its state
  across visits in the owning browser session. The session lasts up to one year
  while the same browser profile and cookies are retained, and public pages
  show a direct **My classroom** return link.
- The owner can download ordinary files and continue without the web app by
  unpacking the ZIP at the root of a Codex project.
- A self-hoster can start the full stack with Docker Compose and optionally
  connect an OpenAI-compatible model endpoint.

## Agent-file contract

- `AGENTS.md`: Codex-readable training instructions and memory map.
- `rules/training-rules.yaml`: structured learning and approval boundaries.
- `memory/`: cognitive memory and durable teacher explanations.
- `knowledge/`: notes, documents and public links.
- `examples/`: demonstrations of good work.
- `procedures/`: repeatable methods.
- `corrections/*.yaml`: durable corrections.
- `tests/*.yaml`: test cases.
- `outputs/*.md`: generated work waiting for human review.
- `_training/`: proposed/retired files, original uploads, questions, history
  and a checksum manifest in the exported ZIP.

Files have a logical path, revision number, checksum and state. Only `active`
training files enter the agent context. Outputs begin in `review`; approving an
output does not publish, send or execute it.

## Runtime modes

- `evidence` is the safe default. It retrieves relevant active files and
  creates an explicitly grounded test draft without calling a model provider;
  it does not claim semantic document inspection.
- `ollama` uses the private internal model service to inspect new files
  together, generate only relevant structured questions and synthesize durable
  memory and proposed YAML rules from teacher answers.
- `openai-compatible` sends a bounded active-file context to a configured
  chat-completions endpoint. Provider failure falls back to evidence mode.

## Privacy and safety boundaries

- New hosted agents require an invitation and are private by default.
- Browser-session ownership is enforced on every private view, mutation and
  download.
- Uploaded documents live in a private named volume and have no public media
  route.
- Public pages require both `published` and `is_fictional_demo`; only records
  individually marked safe may render there.
- Learner email, source fingerprints, private text and private artifacts never
  render publicly.
- Link ingestion accepts bounded public HTTP(S) text only and blocks local,
  private and reserved network destinations, including redirects.
- No generated output can publish or perform an external action in this MVP.

## Acceptance criteria

- Three fictional demos show versioned files, learning history and outputs.
- One private agent can be created without a job, taught, processed, clarified,
  inspected in the browser, approved and exported.
- A second browser receives no access to the private classroom or downloads.
- One-time invitation reuse is rejected.
- File type/size limits and private-link blocking are enforced.
- Application tests, browser tests and responsive chalk checks pass.
- Database and private files survive stop/start and paired backup/restore.
- The Compose audit reports no errors.
- Production deployment is reversible and does not alter DNS, Caddy or any
  unrelated service.
