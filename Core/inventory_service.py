"""
Core/inventory_service.py
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .db import db_session

UTC = timezone.utc


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def generate_inventory(db_path: Path, count: int) -> dict:
    if count <= 0:
        return {"created": 0}

    with db_session(db_path) as conn:
        last = conn.execute(
            "SELECT item_code FROM inventory_items ORDER BY id DESC LIMIT 1"
        ).fetchone()

        start_number = 1
        if last:
            start_number = int(last["item_code"][1:]) + 1

        created = 0
        for n in range(start_number, start_number + count):
            code = f"N{n:03d}"
            conn.execute(
                "INSERT INTO inventory_items (item_code, status, created_at, updated_at, published_at) VALUES (?, 'available', ?, ?, NULL)",
                (code, _now_iso(), _now_iso()),
            )
            created += 1

        return {"created": created, "from": f"N{start_number:03d}", "to": f"N{(start_number+count-1):03d}"}


def list_inventory(db_path: Path) -> list[dict]:
    with db_session(db_path) as conn:
        rows = conn.execute(
            "SELECT item_code, status, post_mode, created_at, updated_at, published_at FROM inventory_items ORDER BY id ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def remove_item(db_path: Path, item_code: str) -> dict:
    item_code = item_code.strip().upper()

    with db_session(db_path) as conn:
        row = conn.execute(
            "SELECT status FROM inventory_items WHERE item_code = ?", (item_code,)
        ).fetchone()

        if not row:
            return {"ok": False, "code": "NOT_FOUND", "message": f"{item_code} does not exist."}

        status = row["status"]

        if status == "available":
            new_status = "removed"
        elif status == "claimed":
            new_status = "claimed_removed"
        elif status in ("removed", "claimed_removed"):
            return {"ok": True, "item_code": item_code, "status": status, "note": "Already removed."}
        else:
            return {"ok": False, "code": "BAD_STATE", "message": f"Unexpected status: {status}"}

        conn.execute(
            "UPDATE inventory_items SET status = ?, updated_at = ? WHERE item_code = ?",
            (new_status, _now_iso(), item_code),
        )
        return {"ok": True, "item_code": item_code, "status": new_status}


def next_inventory_code(db_path: Path, rating: str, post_mode: str = "claim") -> dict:
    """
    Allocate and insert the next inventory code.
    post_mode: 'claim' (default) or 'display'
    """
    rating    = rating.lower()
    prefix    = "S" if rating == "sfw" else "N"
    post_mode = post_mode if post_mode in ("claim", "display") else "claim"

    with db_session(db_path) as conn:
        last = conn.execute(
            "SELECT item_code FROM inventory_items WHERE item_code LIKE ? ORDER BY id DESC LIMIT 1",
            (f"{prefix}%",),
        ).fetchone()

        start_number = 1
        if last:
            start_number = int(last["item_code"][1:]) + 1

        code = f"{prefix}{start_number:03d}"
        conn.execute(
            "INSERT INTO inventory_items (item_code, status, post_mode, created_at, updated_at, published_at) "
            "VALUES (?, 'available', ?, ?, ?, NULL)",
            (code, post_mode, _now_iso(), _now_iso()),
        )
        return {"ok": True, "item_code": code}
