from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .application import _connect, _database_path


BACKUP_ROOT = Path("/var/lib/security-lab/backups")


def backup(destination: Path | None = None) -> Path:
    database = _database_path()
    with _connect() as connection:
        connection.execute("SELECT 1").fetchone()
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = (destination or BACKUP_ROOT / f"security-lab-{stamp}.sqlite3").resolve()
    if BACKUP_ROOT.resolve() not in target.parents:
        raise SystemExit("Backup destination must be inside /var/lib/security-lab/backups")
    with sqlite3.connect(database) as source, sqlite3.connect(target) as output:
        source.backup(output)
    print(target)
    return target


def restore(source: Path) -> None:
    if os.getenv("ALLOW_SECURITY_LAB_RESTORE") != "yes":
        raise SystemExit("Set ALLOW_SECURITY_LAB_RESTORE=yes for an explicit restore")
    source = source.resolve()
    if BACKUP_ROOT.resolve() not in source.parents or not source.is_file():
        raise SystemExit("Restore source must be an existing file inside the backup directory")
    recovery = backup()
    with sqlite3.connect(source) as incoming, sqlite3.connect(_database_path()) as current:
        incoming.backup(current)
    print(f"restored={source} recovery={recovery}")


def reset() -> None:
    if os.getenv("ALLOW_SECURITY_LAB_RESET") != "yes":
        raise SystemExit("Set ALLOW_SECURITY_LAB_RESET=yes for an explicit destructive reset")
    recovery = backup()
    database = _database_path()
    if database.is_file():
        database.unlink()
    _connect().close()
    print(f"reset_complete recovery={recovery}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("backup", "restore", "reset"))
    parser.add_argument("path", nargs="?")
    args = parser.parse_args()
    if args.command == "backup":
        backup(Path(args.path) if args.path else None)
    elif args.command == "restore":
        if not args.path:
            raise SystemExit("restore requires a backup path")
        restore(Path(args.path))
    else:
        reset()


if __name__ == "__main__":
    main()
