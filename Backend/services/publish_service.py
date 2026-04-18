"""
Backend/services/publish_service.py

Publishes a watermarked item to the public Discord catalog channel.
Delegates the actual Discord send to the bot's internal API (port 8001)
since the backend process does not have an active Discord connection.
"""

import requests
from datetime import datetime, timezone
from pathlib import Path

from Core.media_service import get_media
from Core.db import db_session

BOT_API = "http://127.0.0.1:8001"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _stamp_published(db_path: Path, item_code: str) -> None:
    with db_session(db_path) as conn:
        conn.execute(
            "UPDATE inventory_items SET published_at = ? WHERE item_code = ?",
            (_now_iso(), item_code.upper()),
        )


def publish_item(item_code: str, active) -> dict:
    """
    Publishes one item to the public catalog channel.
    Sync — callers must run this in a thread (asyncio.to_thread) so the
    blocking HTTP call to the bot API does not stall the backend event loop.
    """
    item_code = item_code.strip().upper()
    db_path   = active.db_path

    # Check item exists and is publishable
    with db_session(db_path) as conn:
        row = conn.execute(
            "SELECT published_at, status, post_mode FROM inventory_items WHERE item_code = ?",
            (item_code,),
        ).fetchone()

    if not row:
        return {"ok": False, "code": "NOT_FOUND", "message": f"{item_code} not found in inventory"}
    if row["published_at"]:
        return {"ok": False, "code": "ALREADY_PUBLISHED", "message": f"{item_code} already published"}
    if row["status"] != "available":
        return {"ok": False, "code": "NOT_AVAILABLE", "message": f"{item_code} is {row['status']}"}

    post_mode = row["post_mode"] if row["post_mode"] else "claim"

    # Verify watermarked media exists before calling bot
    rating = "nsfw" if item_code.startswith("N") else "sfw"
    wm     = get_media(db_path, item_code, "watermarked", rating)
    if not wm:
        return {"ok": False, "code": "NO_MEDIA", "message": f"No watermarked media found for {item_code}"}

    # Delegate Discord send to the bot internal API
    # Pass post_mode so bot knows whether to include the claim button
    try:
        r = requests.post(
            f"{BOT_API}/publish",
            params={"item_code": item_code, "post_mode": post_mode},
            timeout=20,
        )
        result = r.json()
    except Exception as e:
        return {"ok": False, "code": "BOT_ERROR", "message": f"Could not reach bot API: {e}"}

    if not result.get("ok"):
        return {"ok": False, "code": "BOT_ERROR", "message": result.get("error", "Bot failed to publish")}

    # Stamp published_at in DB
    _stamp_published(db_path, item_code)

    return {"ok": True, "message_id": result.get("message_id"), "item_code": item_code}
