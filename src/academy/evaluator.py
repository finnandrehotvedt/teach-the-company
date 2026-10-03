from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from .models import ChallengeAttempt, WorkbookEntry


STOP_WORDS = {
    "a", "about", "an", "and", "are", "as", "at", "be", "before", "can", "do",
    "for", "from", "how", "i", "if", "in", "is", "it", "my", "of", "on", "or",
    "should", "the", "this", "to", "we", "what", "when", "with", "you", "your",
}
APPROVAL_WORDS = {
    "approve", "buy", "change", "control", "delete", "email", "execute", "isolate",
    "operate", "order", "publish", "repair", "reset", "restart", "send", "switch",
}


@dataclass(frozen=True)
class Evaluation:
    outcome: str
    label: str
    response: str
    evidence_titles: list[str]


def tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) > 2 and token not in STOP_WORDS
    }


def _rank(prompt: str, entries: Iterable[WorkbookEntry]) -> list[tuple[float, WorkbookEntry]]:
    prompt_tokens = tokens(prompt)
    ranked = []
    for entry in entries:
        title_tokens = tokens(entry.title)
        body_tokens = tokens(entry.response)
        title_matches = len(prompt_tokens & title_tokens)
        body_matches = len(prompt_tokens & body_tokens)
        score = title_matches * 2.0 + body_matches
        if prompt_tokens:
            score /= len(prompt_tokens)
        ranked.append((score, entry))
    return sorted(ranked, key=lambda item: (item[0], item[1].updated_at), reverse=True)


def evaluate(prompt: str, entries: Iterable[WorkbookEntry]) -> Evaluation:
    entries = list(entries)
    prompt_tokens = tokens(prompt)
    boundary = next((item for item in entries if item.module_slug == "set-boundaries"), None)

    if prompt_tokens & APPROVAL_WORDS:
        response = (
            "This request crosses an action boundary. The apprentice can prepare information, "
            "but a responsible person must review and approve the real action."
        )
        evidence = []
        if boundary:
            response += f" The taught boundary says: {boundary.response[:420]}"
            evidence.append(boundary.title)
        return Evaluation(ChallengeAttempt.Outcome.APPROVAL, "Human approval required", response, evidence)

    ranked = _rank(prompt, entries)
    best = ranked[0] if ranked else (0.0, None)
    if best[1] is not None and best[0] >= 0.55:
        entry = best[1]
        evidence = [entry.title]
        source = next((item for item in entries if item.module_slug == "curate-sources"), None)
        if source and source.pk != entry.pk:
            evidence.append(source.title)
        response = (
            f"The apprentice found a taught method in “{entry.title}”. "
            f"Its next step would be: {entry.response[:520]}"
        )
        return Evaluation(ChallengeAttempt.Outcome.LEARNED, "A taught method was found", response, evidence)

    return Evaluation(
        ChallengeAttempt.Outcome.NOT_LEARNED,
        "Not learned yet",
        "The apprentice cannot connect this challenge to a sufficiently specific taught method. "
        "A good agent should say that plainly, ask for missing context, and send the gap back to its teacher.",
        [],
    )
