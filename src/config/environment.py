from __future__ import annotations

import os
from pathlib import Path


def env_or_file(name: str, default: str = "") -> str:
    """Read a setting directly or from NAME_FILE without exposing its value."""

    direct = os.getenv(name)
    if direct is not None:
        return direct

    file_name = os.getenv(f"{name}_FILE", "").strip()
    if not file_name:
        return default

    try:
        return Path(file_name).read_text(encoding="utf-8").rstrip("\r\n")
    except OSError as exc:
        raise RuntimeError(f"Unable to read protected setting {name} from its configured file") from exc
