"""
Core/db.py
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def apply_schema(conn: sqlite3.Connection) -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema)
    conn.commit()


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table});").fetchall()
    return any(r["name"] == column for r in rows)


def run_migrations(conn: sqlite3.Connection) -> None:
    """Idempotent migrations — safe to run on every open."""

    # voucher_ledger.consumed_ledger_id
    if not _column_exists(conn, "voucher_ledger", "consumed_ledger_id"):
        conn.execute("ALTER TABLE voucher_ledger ADD COLUMN consumed_ledger_id INTEGER;")
        conn.commit()

    # inventory_items.published_at
    if not _column_exists(conn, "inventory_items", "published_at"):
        conn.execute("ALTER TABLE inventory_items ADD COLUMN published_at TEXT;")
        conn.commit()

    # inventory_items.post_mode
    if not _column_exists(conn, "inventory_items", "post_mode"):
        conn.execute("ALTER TABLE inventory_items ADD COLUMN post_mode TEXT NOT NULL DEFAULT 'claim';")
        conn.commit()


def ensure_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect(db_path)
    try:
        apply_schema(conn)
        run_migrations(conn)
    finally:
        conn.close()


@contextmanager
def db_session(db_path: Path):
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE;")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
