"""
Core/user_service.py

Guest merge utilities:
- find_pending_by_name: find a guest user by Whatnot display name
- transfer_credits: move credits from pending -> discord user on merge
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .db import db_session
from .normalize import normalize_name
from .voucher_service import get_balance

UTC = timezone.utc


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def find_pending_by_name(db_path: Path, display_name: str) -> Optional[dict]:
    normalized = normalize_name(display_name)
    with db_session(db_path) as conn:
        row = conn.execute(
            "SELECT id, display_name, normalized_name, kind FROM users WHERE kind = 'pending' AND normalized_name = ? LIMIT 1",
            (normalized,),
        ).fetchone()
        if not row:
            return None
        user_id = row["id"]

    balance = get_balance(db_path, user_id)
    return {"found": True, "user_id": user_id, "display_name": row["display_name"], "balance": balance}


def transfer_credits(db_path: Path, from_user_id: int, to_user_id: int, amount: int) -> dict:
    if amount <= 0:
        return {"ok": False, "message": "Amount must be > 0"}

    balance = get_balance(db_path, from_user_id)
    amount  = min(amount, balance)

    if amount == 0:
        return {"ok": True, "transferred": 0, "note": "No credits to transfer"}

    with db_session(db_path) as conn:
        for _ in range(amount):
            conn.execute(
                "INSERT INTO voucher_ledger (user_id, delta, reason, note, created_at) VALUES (?, -1, 'STAFF_ADJUST', ?, ?)",
                (from_user_id, f"Guest merge transfer to user#{to_user_id}", _now_iso()),
            )
            conn.execute(
                "INSERT INTO voucher_ledger (user_id, delta, reason, note, created_at) VALUES (?, 1, 'STAFF_ADJUST', ?, ?)",
                (to_user_id, f"Guest merge transfer from pending#{from_user_id}", _now_iso()),
            )
        conn.execute(
            "UPDATE users SET display_name = display_name || ' [merged]' WHERE id = ?",
            (from_user_id,),
        )

    return {"ok": True, "transferred": amount, "from": from_user_id, "to": to_user_id}
