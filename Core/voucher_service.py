"""
Core/voucher_service.py

What this file does:
- Implements the voucher ledger system.

Ledger model (important):
- Every voucher change is a row in voucher_ledger.
- We NEVER edit past rows, because audit trail matters.
- Balance is computed from SUM(delta).

delta:
  +1 = earned voucher
  -1 = spent voucher OR staff adjustment (removal / correction)

In Phase 2 we’ll implement FIFO spending for claims.
For Phase 1 we just need:
- award voucher (+1)
- staff remove voucher (-1)
- compute balance
- list ledger (for UI)
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .db import db_session

UTC = timezone.utc


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def award_voucher(
    db_path: Path,
    user_id: int,
    reason: str,
    note: Optional[str] = None,
    winner_slot: Optional[int] = None,
) -> dict:
    """
    Adds +1 voucher.

    reason must be one of:
    WINNER, GIVY, END_GIVY, CUSTOM_CHOICE, FREEBIE, STAFF_ADJUST
    (DB enforces allowed reasons)
    """
    with db_session(db_path) as conn:
        conn.execute(
            """
            INSERT INTO voucher_ledger (user_id, delta, reason, winner_slot, note, created_at)
            VALUES (?, 1, ?, ?, ?, ?)
            """,
            (user_id, reason, winner_slot, note, _now_iso()),
        )
    return {"ok": True}


def staff_adjust(
    db_path: Path,
    user_id: int,
    delta: int,
    note: Optional[str] = None,
) -> dict:
    """
    Staff-only adjustment.

    delta must be +1 or -1 (DB enforces delta in schema).
    This is how we allow negative balances (if staff forces it).
    """
    if delta not in (1, -1):
        raise ValueError("delta must be +1 or -1")

    with db_session(db_path) as conn:
        conn.execute(
            """
            INSERT INTO voucher_ledger (user_id, delta, reason, winner_slot, note, created_at)
            VALUES (?, ?, 'STAFF_ADJUST', NULL, ?, ?)
            """,
            (user_id, delta, note, _now_iso()),
        )
    return {"ok": True}


def get_balance(db_path: Path, user_id: int) -> int:
    """
    Computed balance for one user.
    """
    with db_session(db_path) as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(delta), 0) AS balance FROM voucher_ledger WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return int(row["balance"] if row else 0)


def list_ledger(db_path: Path, user_id: Optional[int] = None) -> list[dict]:
    """
    List ledger rows (all users, or one user if user_id provided).
    """
    with db_session(db_path) as conn:
        if user_id is None:
            rows = conn.execute(
                """
                SELECT id, user_id, delta, reason, winner_slot, note, consumed_ledger_id, created_at
                FROM voucher_ledger
                ORDER BY created_at ASC, id ASC
                """
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, user_id, delta, reason, winner_slot, note, consumed_ledger_id, created_at
                FROM voucher_ledger
                WHERE user_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (user_id,),
            ).fetchall()

        return [dict(r) for r in rows]
def pick_oldest_unconsumed_credit(conn, user_id: int) -> int | None:
    """
    FIFO credit selection:
    - Find the oldest (+1) ledger entry for this user
    - that has NOT already been consumed by a spend row.

    We use consumed_ledger_id on spend rows to mark which credit was used.
    """
    row = conn.execute(
        """
        SELECT id
        FROM voucher_ledger
        WHERE user_id = ?
          AND delta = 1
          AND id NOT IN (
            SELECT COALESCE(consumed_ledger_id, -1)
            FROM voucher_ledger
            WHERE user_id = ?
              AND delta = -1
              AND consumed_ledger_id IS NOT NULL
          )
        ORDER BY created_at ASC, id ASC
        LIMIT 1
        """,
        (user_id, user_id),
    ).fetchone()

    return int(row["id"]) if row else None
