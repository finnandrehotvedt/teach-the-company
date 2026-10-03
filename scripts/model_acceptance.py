#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import time
from urllib.request import Request, urlopen


endpoint = os.getenv("MODEL_URL", "http://teach-agent-model:11434/api/chat")
model = os.getenv("MODEL_NAME", "qwen3:4b")
schema = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "detail": {"type": "string"},
                },
                "required": ["prompt", "detail"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["questions"],
    "additionalProperties": False,
}
payload = {
    "model": model,
    "stream": False,
    "think": False,
    "format": schema,
    "options": {"temperature": 0, "num_ctx": 4096},
    "messages": [
        {
            "role": "system",
            "content": (
                "Inspect all supplied files together. Ask only questions needed to resolve a real conflict. "
                "Do not ask generic questions when the files are clear."
            ),
        },
        {
            "role": "user",
            "content": (
                "FILE: knowledge/returns.md\nReturns are accepted for 30 days.\n\n"
                "FILE: knowledge/old-faq.md\nReturns are accepted for 14 days."
            ),
        },
    ],
}

started = time.monotonic()
request = Request(
    endpoint,
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urlopen(request, timeout=240) as response:
    result = json.loads(response.read(2_000_000))
content = json.loads(result["message"]["content"])
questions = content.get("questions", [])
combined = " ".join(
    f"{question.get('prompt', '')} {question.get('detail', '')}" for question in questions
)
if len(questions) != 1 or "14" not in combined or "30" not in combined:
    raise SystemExit("MODEL_ACCEPTANCE_FAILED model did not reduce the 14/30-day conflict to one question")
elapsed = time.monotonic() - started
print(f"MODEL_ACCEPTANCE_OK model={model} questions={len(questions)} elapsed_seconds={elapsed:.2f}")
