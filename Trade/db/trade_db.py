"""
Trade/db/trade_db.py

All SQLite schema creation and repository functions for the trade system.
Uses Core.db.db_session — the same connection pattern as the rest of V3.

NOTE: Queries against inventory_items (item_code, status, owner_discord_user_id,
card_name, auction_number, image_url, is_nsfw) assume those columns exist in
your show DB. Adjust column names here if your schema differs.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional, Any


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

TRADE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS trade_user_channels (
    guild_id    TEXT NOT NULL,
    user_id     TEXT NOT NULL,
    channel_id  TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS trade_ui_messages (
    guild_id     TEXT NOT NULL,
    user_id      TEXT NOT NULL,
    channel_id   TEXT NOT NULL,
    message_type TEXT NOT NULL,
    message_id   TEXT NOT NULL,
    updated_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (guild_id, user_id, message_type)
);

CREATE TABLE IF NOT EXISTS trade_listings (
    listing_id    TEXT PRIMARY KEY,
    guild_id      TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    looking_for   TEXT,
    status        TEXT NOT NULL DEFAULT 'active',
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at     TEXT
);

CREATE TABLE IF NOT EXISTS trade_listing_cards (
    listing_id TEXT NOT NULL,
    item_code  TEXT NOT NULL,
    PRIMARY KEY (listing_id, item_code),
    FOREIGN KEY (listing_id) REFERENCES trade_listings(listing_id)
);

CREATE TABLE IF NOT EXISTS trade_offers (
    offer_id         TEXT PRIMARY KEY,
    guild_id         TEXT NOT NULL,
    listing_id       TEXT,
    sender_user_id   TEXT NOT NULL,
    receiver_user_id TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pending',
    created_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at      TEXT,
    FOREIGN KEY (listing_id) REFERENCES trade_listings(listing_id)
);

CREATE TABLE IF NOT EXISTS trade_offer_cards (
    offer_id  TEXT NOT NULL,
    item_code TEXT NOT NULL,
    PRIMARY KEY (offer_id, item_code),
    FOREIGN KEY (offer_id) REFERENCES trade_offers(offer_id)
);
"""


def ensure_trade_tables(conn: sqlite3.Connection) -> None:
    """
    Create all trade tables. Call once per bot session with an open connection
    from Core.db.db_session or _connect.
    """
    conn.executescript(TRADE_SCHEMA_SQL)
    conn.commit()


# ---------------------------------------------------------------------------
# Channel repo
# ---------------------------------------------------------------------------

def get_trade_channel_id(
    conn: sqlite3.Connection,
    guild_id: int,
    user_id: int,
) -> Optional[int]:
    row = conn.execute(
        "SELECT channel_id FROM trade_user_channels WHERE guild_id = ? AND user_id = ?",
        (str(guild_id), str(user_id)),
    ).fetchone()
    return int(row["channel_id"]) if row else None


def save_trade_channel_id(
    conn: sqlite3.Connection,
    guild_id: int,
    user_id: int,
    channel_id: int,
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO trade_user_channels (guild_id, user_id, channel_id) VALUES (?, ?, ?)",
        (str(guild_id), str(user_id), str(channel_id)),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# UI message repo
# ---------------------------------------------------------------------------

def get_trade_ui_message_id(
    conn: sqlite3.Connection,
    guild_id: int,
    user_id: int,
    message_type: str,
) -> Optional[int]:
    row = conn.execute(
        "SELECT message_id FROM trade_ui_messages WHERE guild_id = ? AND user_id = ? AND message_type = ?",
        (str(guild_id), str(user_id), message_type),
    ).fetchone()
    return int(row["message_id"]) if row else None


def save_trade_ui_message_id(
    conn: sqlite3.Connection,
    guild_id: int,
    user_id: int,
    channel_id: int,
    message_type: str,
    message_id: int,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO trade_ui_messages
        (guild_id, user_id, channel_id, message_type, message_id, updated_at)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (str(guild_id), str(user_id), str(channel_id), message_type, str(message_id)),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Inventory item repo
# Queries against inventory_items — V3's existing table.
# ---------------------------------------------------------------------------

def get_user_card_count(conn: sqlite3.Connection, discord_user_id: int) -> int:
    """Count items currently claimed/owned by this Discord user."""
    row = conn.execute(
        """
        SELECT COUNT(*) FROM claims c
        JOIN users u ON c.user_id = u.id
        WHERE u.discord_user_id = ? AND c.removed_at IS NULL
        """,
        (str(discord_user_id),),
    ).fetchone()
    return int(row[0]) if row else 0


def get_user_cards_page(
    conn: sqlite3.Connection,
    discord_user_id: int,
    page: int,
    page_size: int = 3,
) -> list[Any]:
    """Return one page (0-indexed) of a user's claimed cards."""
    offset = page * page_size
    rows = conn.execute(
        """
        SELECT i.item_code, i.post_mode,
               ma_wm.attachment_url AS image_url
        FROM claims c
        JOIN users u ON c.user_id = u.id
        JOIN inventory_items i ON c.item_code = i.item_code
        LEFT JOIN media_assets ma_wm
            ON ma_wm.item_code = i.item_code AND ma_wm.variant = 'watermarked'
        WHERE u.discord_user_id = ? AND c.removed_at IS NULL
        ORDER BY c.id
        LIMIT ? OFFSET ?
        """,
        (str(discord_user_id), page_size, offset),
    ).fetchall()
    return rows


def search_card_by_item_code(conn: sqlite3.Connection, item_code: str) -> Optional[Any]:
    """
    Look up a card and its current owner's Discord user ID.
    Returns None if not found or not currently claimed.
    """
    row = conn.execute(
        """
        SELECT i.item_code, i.status,
               u.discord_user_id AS owner_discord_user_id,
               u.display_name    AS owner_display_name,
               ma_wm.attachment_url AS image_url
        FROM inventory_items i
        LEFT JOIN claims c ON c.item_code = i.item_code AND c.removed_at IS NULL
        LEFT JOIN users u  ON c.user_id = u.id
        LEFT JOIN media_assets ma_wm
            ON ma_wm.item_code = i.item_code AND ma_wm.variant = 'watermarked'
        WHERE i.item_code = ?
        """,
        (item_code.strip().upper(),),
    ).fetchone()
    return row


# ---------------------------------------------------------------------------
# Listing repo
# ---------------------------------------------------------------------------

def get_user_active_listing_count(conn: sqlite3.Connection, discord_user_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM trade_listings WHERE owner_user_id = ? AND status = 'active'",
        (str(discord_user_id),),
    ).fetchone()
    return int(row[0]) if row else 0


def save_listing(
    conn: sqlite3.Connection,
    listing_id: str,
    guild_id: int,
    owner_discord_user_id: int,
    item_codes: list[str],
    looking_for: Optional[str],
) -> None:
    conn.execute(
        "INSERT INTO trade_listings (listing_id, guild_id, owner_user_id, looking_for) VALUES (?, ?, ?, ?)",
        (listing_id, str(guild_id), str(owner_discord_user_id), looking_for),
    )
    for code in item_codes:
        conn.execute(
            "INSERT INTO trade_listing_cards (listing_id, item_code) VALUES (?, ?)",
            (listing_id, code),
        )
    conn.commit()


def close_listing(conn: sqlite3.Connection, listing_id: str) -> None:
    conn.execute(
        "UPDATE trade_listings SET status = 'closed', closed_at = CURRENT_TIMESTAMP WHERE listing_id = ?",
        (listing_id,),
    )
    conn.commit()


def get_listing_item_codes(conn: sqlite3.Connection, listing_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT item_code FROM trade_listing_cards WHERE listing_id = ?",
        (listing_id,),
    ).fetchall()
    return [r["item_code"] for r in rows]


# ---------------------------------------------------------------------------
# Offer repo
# ---------------------------------------------------------------------------

def get_user_incoming_offer_count(conn: sqlite3.Connection, discord_user_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM trade_offers WHERE receiver_user_id = ? AND status = 'pending'",
        (str(discord_user_id),),
    ).fetchone()
    return int(row[0]) if row else 0


def save_offer(
    conn: sqlite3.Connection,
    offer_id: str,
    guild_id: int,
    sender_discord_user_id: int,
    receiver_discord_user_id: int,
    item_codes: list[str],
    listing_id: Optional[str] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO trade_offers (offer_id, guild_id, listing_id, sender_user_id, receiver_user_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        (offer_id, str(guild_id), listing_id, str(sender_discord_user_id), str(receiver_discord_user_id)),
    )
    for code in item_codes:
        conn.execute(
            "INSERT INTO trade_offer_cards (offer_id, item_code) VALUES (?, ?)",
            (offer_id, code),
        )
    conn.commit()


def get_offer_row(conn: sqlite3.Connection, offer_id: str) -> Optional[Any]:
    return conn.execute(
        "SELECT * FROM trade_offers WHERE offer_id = ?",
        (offer_id,),
    ).fetchone()


def get_offer_item_codes(conn: sqlite3.Connection, offer_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT item_code FROM trade_offer_cards WHERE offer_id = ?",
        (offer_id,),
    ).fetchall()
    return [r["item_code"] for r in rows]


def resolve_offer(conn: sqlite3.Connection, offer_id: str, status: str) -> None:
    """status: 'accepted' or 'declined'"""
    conn.execute(
        "UPDATE trade_offers SET status = ?, resolved_at = CURRENT_TIMESTAMP WHERE offer_id = ?",
        (status, offer_id),
    )
    conn.commit()


def swap_card_ownership_for_offer(conn: sqlite3.Connection, offer_id: str) -> None:
    """
    Transfer claim ownership for an accepted offer.
    Sender's offered cards → receiver. Listing cards (if any) → sender.

    TODO: Implement once the full trade ownership model is decided.
    V3 uses the claims table for ownership — swapping means updating
    claims.user_id to the new owner's internal user id (not discord_user_id).
    Stub: resolve_offer() is called first; add the UPDATE claims logic here.
    """
    pass
