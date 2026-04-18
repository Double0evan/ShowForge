"""
Core/show_settings_service.py

Stores per-show settings INSIDE the active show's database.
We use this for Discord archival thread IDs so claims always post to the right show thread.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .db import db_session

UTC = timezone.utc


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def set_setting(db_path: Path, key: str, value: str) -> None:
    with db_session(db_path) as conn:
        existing = conn.execute("SELECT key FROM show_settings WHERE key = ?", (key,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE show_settings SET value = ?, updated_at = ? WHERE key = ?",
                (value, _now_iso(), key),
            )
        else:
            conn.execute(
                "INSERT INTO show_settings (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, _now_iso()),
            )


def get_setting(db_path: Path, key: str) -> str | None:
    with db_session(db_path) as conn:
        row = conn.execute("SELECT value FROM show_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None