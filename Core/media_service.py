"""
Core/media_service.py

Stores and retrieves where item images live on Discord.

We store:
- RAW asset location (private RAW upload channel)
- Watermarked asset location (private WM upload channel OR catalog post)

Bot uses this on claim to fetch RAW and re-upload it into the show's archival thread.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .db import db_session

UTC = timezone.utc


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def upsert_media(
    db_path: Path,
    item_code: str,
    variant: str,   # 'raw' | 'watermarked'
    rating: str,    # 'sfw' | 'nsfw'
    source_channel_id: str,
    source_message_id: str,
    attachment_url: str,
    filename: Optional[str] = None,
    content_type: Optional[str] = None,
) -> dict:
    item_code = item_code.strip().upper()
    variant = variant.strip().lower()
    rating = rating.strip().lower()

    with db_session(db_path) as conn:
        existing = conn.execute(
            """
            SELECT id FROM media_assets
            WHERE item_code = ? AND variant = ? AND rating = ?
            """,
            (item_code, variant, rating),
        ).fetchone()

        if existing:
            conn.execute(
                """
                UPDATE media_assets
                SET source_channel_id = ?, source_message_id = ?, attachment_url = ?,
                    filename = ?, content_type = ?
                WHERE id = ?
                """,
                (source_channel_id, source_message_id, attachment_url, filename, content_type, existing["id"]),
            )
            return {"ok": True, "updated": True}

        conn.execute(
            """
            INSERT INTO media_assets (
              item_code, variant, rating,
              source_channel_id, source_message_id,
              attachment_url, filename, content_type,
              created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (item_code, variant, rating, source_channel_id, source_message_id, attachment_url, filename, content_type, _now_iso()),
        )
        return {"ok": True, "created": True}


def get_media(db_path: Path, item_code: str, variant: str, rating: str) -> Optional[dict]:
    item_code = item_code.strip().upper()
    variant = variant.strip().lower()
    rating = rating.strip().lower()

    with db_session(db_path) as conn:
        row = conn.execute(
            """
            SELECT item_code, variant, rating,
                   source_channel_id, source_message_id,
                   attachment_url, filename, content_type,
                   created_at
            FROM media_assets
            WHERE item_code = ? AND variant = ? AND rating = ?
            """,
            (item_code, variant, rating),
        ).fetchone()

        return dict(row) if row else None