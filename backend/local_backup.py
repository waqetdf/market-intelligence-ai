"""Consistent snapshots of the desktop database, including live writes."""

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from tempfile import NamedTemporaryFile


def backup_database(directory: Path, automatic=False):
    backups = directory / "backups"
    backups.mkdir(mode=0o700, exist_ok=True)
    source = (directory / "market.db").resolve().as_uri() + "?mode=ro"
    now = datetime.now(timezone.utc)
    daily = backups / f"auto-{now:%Y-%m-%d}.sqlite3"
    if automatic and daily.exists():
        return daily
    destination = daily if automatic else backups / f"manual-{now:%Y%m%d-%H%M%S-%f}.sqlite3"
    with NamedTemporaryFile(dir=backups, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        with closing(sqlite3.connect(source, uri=True)) as live, closing(sqlite3.connect(temporary)) as copy:
            live.backup(copy, pages=128)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    for obsolete in sorted(backups.glob("auto-*.sqlite3"), reverse=True)[14:]:
        obsolete.unlink(missing_ok=True)
    return destination
