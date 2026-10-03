from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Module:
    day: int
    slug: str
    title: str
    verb: str
    summary: str
    lesson: str
    artifact: str
    prompt: str
    example_title: str
    example_response: str


MODULES = (
    Module(
        1,
        "define-the-job",
        "Define one job",
        "Focus",
        "Turn a vague wish into one observable responsibility.",
        "An agent learns faster when its job has a clear start, finish, and standard of success. Avoid ‘know everything’. Name the decisions it may support and the work it must not do.",
        "A narrow job contract",
        "Describe the one job, what good work looks like, and what remains outside the agent's role.",
        "Workshop support",
        "Help a technician locate approved troubleshooting information and prepare a safe diagnostic checklist. Never control equipment or approve a repair.",
    ),
    Module(
        2,
        "curate-sources",
        "Curate trusted sources",
        "Ground",
        "Teach from approved material with a visible origin.",
        "More documents do not automatically mean better learning. Prefer current, authoritative sources; label conflicts; record ownership and revision dates; and remove material the agent must not use.",
        "A source policy",
        "List the sources the agent may trust, how their origin is recorded, and what material is excluded.",
        "Approved machine knowledge",
        "Use the current M17 service manual, the signed electrical drawing, and reviewed maintenance notes. Exclude forum posts and superseded manuals.",
    ),
    Module(
        3,
        "demonstrate-work",
        "Demonstrate the work",
        "Show",
        "Convert expert habit into a procedure someone else can follow.",
        "A source explains facts; a demonstration explains sequence. Show the trigger, checks, decision points, expected output, and how the result is verified.",
        "One explicit procedure",
        "Write one representative procedure with its trigger, ordered steps, decision points, and verification.",
        "Motor overload triage",
        "Confirm the equipment is in a safe state, record the fault code, inspect the approved manual section, check load and ventilation evidence, then prepare findings for a qualified technician.",
    ),
    Module(
        4,
        "correct-mistakes",
        "Correct mistakes",
        "Refine",
        "Turn feedback into a rule that survives the conversation.",
        "‘Wrong’ is weak feedback. Record the situation, the incorrect behaviour, the corrected behaviour, and why the correction matters. Retest the same rule in a different case.",
        "A reusable correction",
        "Describe a likely mistake, the corrected behaviour, and the general rule the agent should preserve.",
        "Never treat a reset as a repair",
        "If a protection device trips, do not recommend repeated resets. Preserve the fault evidence, identify the cause, and require qualified review before restart.",
    ),
    Module(
        5,
        "set-boundaries",
        "Set boundaries",
        "Protect",
        "Teach the agent when to stop and ask a person.",
        "Separate reading, drafting, recommending, approving, and executing. Give the agent the smallest permission needed and make escalation a successful outcome—not a failure.",
        "An approval boundary",
        "List actions the agent may prepare and the actions that always require a named human role.",
        "Human approval before action",
        "The agent may prepare a checklist and draft a service note. A qualified technician must approve isolation, reset, repair, ordering, customer communication, and every real system change.",
    ),
    Module(
        6,
        "test-surprises",
        "Test surprise cases",
        "Prove",
        "Check learning with cases the agent has not already seen.",
        "Do not grade only the final answer. Inspect sources, assumptions, procedure, uncertainty, and whether approval was requested at the right moment.",
        "An unseen evaluation",
        "Write a new test case, its expected behaviour, and the evidence you will inspect before accepting the result.",
        "Unexpected intermittent stop",
        "Present a stop with incomplete evidence. Passing means the agent asks for the missing fault record, cites only approved sources, avoids guessing, and does not suggest a restart.",
    ),
    Module(
        7,
        "publish-proof",
        "Publish safe proof",
        "Share",
        "Make the result challengeable without exposing the company.",
        "A public sandbox should contain only reviewed examples and simulated tasks. Remove private files, personal data, credentials, customer records, and every real action path.",
        "A sanitized challenge",
        "Describe what strangers may test, what evidence may be shown, and what remains private.",
        "Challenge the workshop apprentice",
        "Visitors may submit simulated troubleshooting questions. The demo may reveal only the seven reviewed summaries and cannot access files, customers, equipment, or real tools.",
    ),
)

MODULE_BY_SLUG = {module.slug: module for module in MODULES}
