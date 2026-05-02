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

    # trade_offer_requested_cards — added in v2.1 to track what sender wants
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS trade_offer_requested_cards (
                offer_id  TEXT NOT NULL,
                item_code TEXT NOT NULL,
                PRIMARY KEY (offer_id, item_code)
            );
        """)
        conn.commit()
    except Exception:
        pass

    # claims.auction_number -- Whatnot auction # matched during bin shows
    if not _column_exists(conn, "claims", "auction_number"):
        conn.execute("ALTER TABLE claims ADD COLUMN auction_number TEXT;")
        conn.commit()

    # inventory_items.post_mode
    if not _column_exists(conn, "inventory_items", "post_mode"):
        conn.execute("ALTER TABLE inventory_items ADD COLUMN post_mode TEXT NOT NULL DEFAULT 'claim';")
        conn.commit()

    # claims.source CHECK — add 'bin' source for bin show claims
    add_source_bin_migration(conn)


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


def add_source_bin_migration(conn: sqlite3.Connection) -> None:
    """
    SQLite can't ALTER a CHECK constraint, so we recreate the claims table
    with 'bin' added to the source CHECK. Safe to run multiple times.
    """
    # Check if 'bin' is already allowed by inspecting existing rows or just
    # try inserting — easiest is to check the schema string directly.
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='claims'"
    ).fetchone()
    if row and "'bin'" in row["sql"]:
        return  # already migrated

    conn.executescript("""
        PRAGMA foreign_keys = OFF;

        CREATE TABLE IF NOT EXISTS claims_new (
          id                  INTEGER PRIMARY KEY,
          item_code           TEXT NOT NULL REFERENCES inventory_items(item_code),
          user_id             INTEGER NOT NULL REFERENCES users(id),
          voucher_spend_id    INTEGER REFERENCES voucher_ledger(id),
          source              TEXT NOT NULL CHECK(source IN ('reaction','staff','button','bin')),
          reaction_message_id TEXT,
          reaction_emoji      TEXT,
          auction_number      TEXT,
          created_at          TEXT NOT NULL,
          removed_at          TEXT,
          removed_reason      TEXT
        );

        INSERT INTO claims_new
          SELECT id, item_code, user_id, voucher_spend_id, source,
                 reaction_message_id, reaction_emoji,
                 NULL as auction_number,
                 created_at, removed_at, removed_reason
          FROM claims;

        DROP TABLE claims;
        ALTER TABLE claims_new RENAME TO claims;

        CREATE UNIQUE INDEX IF NOT EXISTS idx_claims_item_active
          ON claims(item_code)
          WHERE removed_at IS NULL;

        PRAGMA foreign_keys = ON;
    """)
    conn.commit()
