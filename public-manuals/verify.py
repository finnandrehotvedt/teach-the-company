#!/usr/bin/env python3
import hashlib
import json
import pathlib
import re
import sys

root = pathlib.Path(__file__).resolve().parent
for line in (root / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
    expected, relative = line.split("  ", 1)
    actual = hashlib.sha256((root / relative).read_bytes()).hexdigest()
    if actual != expected:
        raise SystemExit(f"hash mismatch: {relative}")

catalog = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
if len(catalog["manuals"]) != 5 or len(catalog["lessons"]) != 20:
    raise SystemExit("catalog coverage mismatch")
if len({lesson["id"] for lesson in catalog["lessons"]}) != 20:
    raise SystemExit("lesson IDs are not unique")
covered = [lesson_id for manual in catalog["manuals"] for lesson_id in manual["lesson_ids"]]
if len(covered) != 20 or len(set(covered)) != 20:
    raise SystemExit("manual lesson coverage mismatch")

text = "\n".join(
    path.read_text(encoding="utf-8")
    for path in root.rglob("*")
    if path.is_file() and path.name != "verify.py" and ".git" not in path.parts
)
for pattern in (r"\bCT\d{2,3}\b", r"\bVM\d{2,3}\b", r"/srv/", r"/var/backups/", r"receipt[_ -]?id"):
    if re.search(pattern, text, re.IGNORECASE):
        raise SystemExit(f"private infrastructure marker found: {pattern}")
print("PUBLIC_MANUALS_OK manuals=5 lessons=20 hashes=verified private_markers=0")
