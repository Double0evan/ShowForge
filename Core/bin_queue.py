"""
Core/bin_queue.py

Tiny SQLite queue that bridges the Whatnot screen watcher and the bot's
bin-number listener.

The watcher writes: sale detected (auction_number, username)
The bot reads:      when host types a bin number, pop latest pending sale

Queue lives at DB/bin_queue.sqlite — separate from show DBs so it works
across show boundaries and doesn't need to know which show is active.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_DB_PATH = Path(__file__).resolve().parents[1] / "DB" / "bin_queue.sqlite"


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pending_sales (
            id             INTEGER PRIMARY KEY,
            auction_number INTEGER NOT NULL,
            username       TEXT    NOT NULL,
            detected_at    TEXT    NOT NULL,
            matched        INTEGER NOT NULL DEFAULT 0,
            matched_at     TEXT
        )
    """)
    conn.commit()
    return conn


def push_sale(auction_number: int, username: str) -> int:
    """Called by watcher when a new sale is detected. Returns the row id."""
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO pending_sales (auction_number, username, detected_at) VALUES (?, ?, ?)",
            (auction_number, username, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def pop_latest_sale() -> dict | None:
    """
    Returns the most recent unmatched sale and marks it matched.
    Returns None if nothing is pending.
    """
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM pending_sales WHERE matched = 0 ORDER BY detected_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE pending_sales SET matched = 1, matched_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), row["id"]),
        )
        conn.commit()
        return dict(row)
    finally:
        conn.close()


def peek_latest_sale() -> dict | None:
    """Read latest unmatched sale without consuming it."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM pending_sales WHERE matched = 0 ORDER BY detected_at DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def confirm_sale(row_id: int) -> bool:
    """Mark a peeked sale as matched (consumed). Call only after claim succeeds."""
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE pending_sales SET matched = 1, matched_at = ? WHERE id = ? AND matched = 0",
            (datetime.now(timezone.utc).isoformat(), row_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def clear_queue() -> int:
    """Clear all unmatched pending sales. Returns count cleared."""
    conn = _connect()
    try:
        cur = conn.execute("DELETE FROM pending_sales WHERE matched = 0")
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


# ── Auction Log ───────────────────────────────────────────────────────────────
# Tracks card numbers in the order the host typed them (auction order).

def log_auction(card_number: int) -> int:
    """Append a card number to the auction log. Returns the auction sequence number."""
    conn = _connect()
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS auction_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            card_number INTEGER NOT NULL,
            winner_name TEXT,
            discord_name TEXT,
            claimed     INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )""")
        cur = conn.execute(
            "INSERT INTO auction_log (card_number) VALUES (?)", (card_number,)
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_auction_log() -> list[dict]:
    conn = _connect()
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS auction_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, card_number INTEGER NOT NULL,
            winner_name TEXT, discord_name TEXT, claimed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )""")
        rows = conn.execute(
            "SELECT id, card_number, winner_name, discord_name, claimed, created_at FROM auction_log ORDER BY id ASC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_auction_winner(auction_id: int, winner_name: str, discord_name: str) -> bool:
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE auction_log SET winner_name=?, discord_name=?, claimed=1 WHERE id=?",
            (winner_name, discord_name, auction_id)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def clear_auction_log() -> int:
    conn = _connect()
    try:
        cur = conn.execute("DELETE FROM auction_log")
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
