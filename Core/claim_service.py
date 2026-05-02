"""
Core/claim_service.py

Creates and manages claims against inventory items.

Claim flow:
  1. Check user has balance >= 1
  2. Verify item exists and is available
  3. Spend voucher (FIFO — links spend row to exact credit used)
  4. Insert claim row
  5. Mark item as 'claimed'

Remove flow:
  1. Mark claim as removed (audit trail kept)
  2. Return item to 'available'
  3. Optionally refund the credit
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .db import db_session
from .voucher_service import get_balance, pick_oldest_unconsumed_credit

UTC = timezone.utc


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


class ClaimError(Exception):
    """
    Expected claim failure with a machine-readable code.
    Usage: raise ClaimError("NO_VOUCHER", "User has no credits.")
    """
    def __init__(self, code: str, message: str | None = None):
        if message is None:
            message = code
            code    = "ERROR"
        super().__init__(message)
        self.code    = code
        self.message = message


def fail(code: str, message: str):
    raise ClaimError(code, message)


def create_claim(
    db_path: Path,
    item_code: str,
    user_id: int,
    source: str = "staff",
    reaction_message_id: Optional[str] = None,
    reaction_emoji: Optional[str] = None,
    auction_number: Optional[str] = None,
) -> dict:
    item_code = item_code.strip().upper()

    # Quick balance check before opening transaction
    if get_balance(db_path, user_id) < 1:
        fail("NO_VOUCHER", "User does not have a voucher to spend.")

    with db_session(db_path) as conn:
        # 1) Item must exist
        item = conn.execute(
            "SELECT item_code, status FROM inventory_items WHERE item_code = ?",
            (item_code,),
        ).fetchone()
        if not item:
            fail("ITEM_NOT_FOUND", f"Item {item_code} does not exist.")

        # 2) Item must not already be actively claimed
        existing = conn.execute(
            "SELECT id FROM claims WHERE item_code = ? AND removed_at IS NULL",
            (item_code,),
        ).fetchone()
        if existing:
            fail("ALREADY_CLAIMED", f"Item {item_code} is already claimed.")

        # 3) Item must be claimable
        if item["status"] in ("removed", "claimed_removed"):
            fail("ITEM_REMOVED", f"Item {item_code} is removed and cannot be claimed.")

        # 4) Re-check balance inside transaction (race condition guard)
        bal_row = conn.execute(
            "SELECT COALESCE(SUM(delta), 0) AS bal FROM voucher_ledger WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if int(bal_row["bal"] if bal_row else 0) < 1:
            fail("NO_VOUCHER", "User does not have a voucher to spend.")

        # 5) FIFO credit selection
        credit_id = pick_oldest_unconsumed_credit(conn, user_id)
        if credit_id is None:
            fail("NO_CREDIT_FOUND", "No unconsumed credit found (contact staff).")

        # 6) Insert spend row linked to the credit it consumed
        cur_spend = conn.execute(
            """
            INSERT INTO voucher_ledger
              (user_id, delta, reason, winner_slot, note, consumed_ledger_id, created_at)
            VALUES (?, -1, 'STAFF_ADJUST', NULL, ?, ?, ?)
            """,
            (user_id, f"Claim spend for {item_code}", credit_id, _now_iso()),
        )
        spend_id = cur_spend.lastrowid

        # 7) Insert claim row
        try:
            cur_claim = conn.execute(
                """
                INSERT INTO claims
                  (item_code, user_id, voucher_spend_id, source,
                   reaction_message_id, reaction_emoji,
                   auction_number,
                   created_at, removed_at, removed_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
                """,
                (item_code, user_id, spend_id, source,
                 reaction_message_id, reaction_emoji,
                 auction_number, _now_iso()),
            )
        except sqlite3.IntegrityError:
            # Race condition — another request claimed it first.
            # Refund the credit so user doesn't lose it.
            conn.execute(
                """
                INSERT INTO voucher_ledger
                  (user_id, delta, reason, winner_slot, note, consumed_ledger_id, created_at)
                VALUES (?, 1, 'STAFF_ADJUST', NULL, ?, NULL, ?)
                """,
                (user_id, f"Refund — race condition on {item_code}", _now_iso()),
            )
            fail("ALREADY_CLAIMED", f"Item {item_code} is already claimed.")

        # 8) Mark item claimed
        conn.execute(
            "UPDATE inventory_items SET status = 'claimed', updated_at = ? WHERE item_code = ?",
            (_now_iso(), item_code),
        )

        return {"ok": True, "claim_id": cur_claim.lastrowid, "item_code": item_code, "user_id": user_id}


def remove_claim(
    db_path: Path,
    item_code: str,
    refund: bool,
    reason: str = "Removed by staff",
) -> dict:
    item_code = item_code.strip().upper()

    with db_session(db_path) as conn:
        claim = conn.execute(
            "SELECT id, user_id FROM claims WHERE item_code = ? AND removed_at IS NULL",
            (item_code,),
        ).fetchone()
        if not claim:
            fail("NO_ACTIVE_CLAIM", f"No active claim found for {item_code}.")

        user_id = claim["user_id"]

        # Mark claim removed
        conn.execute(
            "UPDATE claims SET removed_at = ?, removed_reason = ? WHERE id = ?",
            (_now_iso(), reason, claim["id"]),
        )

        # Return item to available
        conn.execute(
            "UPDATE inventory_items SET status = 'available', updated_at = ? WHERE item_code = ?",
            (_now_iso(), item_code),
        )

        # Optional refund
        if refund:
            conn.execute(
                """
                INSERT INTO voucher_ledger
                  (user_id, delta, reason, winner_slot, note, created_at)
                VALUES (?, 1, 'STAFF_ADJUST', NULL, ?, ?)
                """,
                (user_id, f"Refund for removed claim {item_code}", _now_iso()),
            )

        return {"ok": True, "item_code": item_code, "refunded": refund}


def list_claims(db_path: Path, include_removed: bool = False) -> list[dict]:
    with db_session(db_path) as conn:
        where = "" if include_removed else "WHERE c.removed_at IS NULL"
        rows  = conn.execute(
            f"""
            SELECT
              c.id, c.item_code, c.user_id,
              u.display_name AS user_display_name,
              c.source, c.reaction_message_id, c.reaction_emoji,
              c.created_at, c.removed_at, c.removed_reason
            FROM claims c
            JOIN users u ON u.id = c.user_id
            {where}
            ORDER BY c.created_at ASC, c.id ASC
            """
        ).fetchall()
        return [dict(r) for r in rows]
