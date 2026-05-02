"""Trade/db/trade_db.py - stable rebuild."""
from __future__ import annotations
import sqlite3
from typing import Optional, Any

TRADE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS trade_user_channels (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (guild_id, user_id)
);
CREATE TABLE IF NOT EXISTS trade_ui_messages (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    message_type TEXT NOT NULL,
    message_id TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (guild_id, user_id, message_type)
);
CREATE TABLE IF NOT EXISTS trade_listings (
    listing_id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    looking_for TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at TEXT
);
CREATE TABLE IF NOT EXISTS trade_listing_cards (
    listing_id TEXT NOT NULL,
    item_code TEXT NOT NULL,
    PRIMARY KEY (listing_id, item_code),
    FOREIGN KEY (listing_id) REFERENCES trade_listings(listing_id)
);
CREATE TABLE IF NOT EXISTS trade_offers (
    offer_id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    listing_id TEXT,
    sender_user_id TEXT NOT NULL,
    receiver_user_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT,
    FOREIGN KEY (listing_id) REFERENCES trade_listings(listing_id)
);
CREATE TABLE IF NOT EXISTS trade_offer_cards (
    offer_id TEXT NOT NULL,
    item_code TEXT NOT NULL,
    PRIMARY KEY (offer_id, item_code),
    FOREIGN KEY (offer_id) REFERENCES trade_offers(offer_id)
);
CREATE TABLE IF NOT EXISTS trade_offer_requested_cards (
    offer_id TEXT NOT NULL,
    item_code TEXT NOT NULL,
    PRIMARY KEY (offer_id, item_code),
    FOREIGN KEY (offer_id) REFERENCES trade_offers(offer_id)
);
CREATE TABLE IF NOT EXISTS trade_listing_public_messages (
    listing_id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (listing_id) REFERENCES trade_listings(listing_id)
);
"""

def ensure_trade_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(TRADE_SCHEMA_SQL)
    conn.commit()

def get_trade_channel_id(conn, guild_id:int, user_id:int)->Optional[int]:
    row=conn.execute("SELECT channel_id FROM trade_user_channels WHERE guild_id=? AND user_id=?",(str(guild_id),str(user_id))).fetchone()
    return int(row["channel_id"]) if row else None

def save_trade_channel_id(conn,guild_id:int,user_id:int,channel_id:int)->None:
    conn.execute("INSERT OR REPLACE INTO trade_user_channels (guild_id,user_id,channel_id) VALUES (?,?,?)",(str(guild_id),str(user_id),str(channel_id)))
    conn.commit()

def get_trade_ui_message_id(conn,guild_id:int,user_id:int,message_type:str)->Optional[int]:
    row=conn.execute("SELECT message_id FROM trade_ui_messages WHERE guild_id=? AND user_id=? AND message_type=?",(str(guild_id),str(user_id),message_type)).fetchone()
    if not row: return None
    try: return int(row["message_id"])
    except (TypeError,ValueError): return None

def save_trade_ui_message_id(conn,guild_id:int,user_id:int,channel_id:int,message_type:str,message_id:int)->None:
    conn.execute("""INSERT OR REPLACE INTO trade_ui_messages
    (guild_id,user_id,channel_id,message_type,message_id,updated_at)
    VALUES (?,?,?,?,?,CURRENT_TIMESTAMP)""",(str(guild_id),str(user_id),str(channel_id),message_type,str(message_id)))
    conn.commit()

def delete_trade_ui_message_id(conn,guild_id:int,user_id:int,message_type:str)->None:
    conn.execute("DELETE FROM trade_ui_messages WHERE guild_id=? AND user_id=? AND message_type=?",(str(guild_id),str(user_id),message_type))
    conn.commit()

def get_user_card_count(conn, discord_user_id:int)->int:
    row=conn.execute("""SELECT COUNT(*) FROM claims c JOIN users u ON c.user_id=u.id
    WHERE u.discord_user_id=? AND c.removed_at IS NULL""",(str(discord_user_id),)).fetchone()
    return int(row[0]) if row else 0

def get_user_cards_page(conn, discord_user_id:int, page:int, page_size:int=3)->list[Any]:
    return conn.execute("""SELECT i.item_code, i.post_mode, ma_wm.attachment_url AS image_url
    FROM claims c JOIN users u ON c.user_id=u.id JOIN inventory_items i ON c.item_code=i.item_code
    LEFT JOIN media_assets ma_wm ON ma_wm.item_code=i.item_code AND ma_wm.variant='watermarked'
    WHERE u.discord_user_id=? AND c.removed_at IS NULL ORDER BY c.id LIMIT ? OFFSET ?""",(str(discord_user_id),page_size,page*page_size)).fetchall()

def get_user_cards_all(conn, discord_user_id:int)->list[Any]:
    return conn.execute("""SELECT i.item_code, i.post_mode, ma_wm.attachment_url AS image_url
    FROM claims c JOIN users u ON c.user_id=u.id JOIN inventory_items i ON c.item_code=i.item_code
    LEFT JOIN media_assets ma_wm ON ma_wm.item_code=i.item_code AND ma_wm.variant='watermarked'
    WHERE u.discord_user_id=? AND c.removed_at IS NULL ORDER BY c.id""",(str(discord_user_id),)).fetchall()

def search_card_by_item_code(conn,item_code:str)->Optional[Any]:
    return conn.execute("""SELECT i.item_code, i.status, u.discord_user_id AS owner_discord_user_id,
    u.display_name AS owner_display_name, ma_wm.attachment_url AS image_url
    FROM inventory_items i
    LEFT JOIN claims c ON c.item_code=i.item_code AND c.removed_at IS NULL
    LEFT JOIN users u ON c.user_id=u.id
    LEFT JOIN media_assets ma_wm ON ma_wm.item_code=i.item_code AND ma_wm.variant='watermarked'
    WHERE i.item_code=?""",(item_code.strip().upper(),)).fetchone()

def get_user_active_listing_count(conn, discord_user_id:int)->int:
    row=conn.execute("SELECT COUNT(*) FROM trade_listings WHERE owner_user_id=? AND status='active'",(str(discord_user_id),)).fetchone()
    return int(row[0]) if row else 0

def save_listing(conn,listing_id:str,guild_id:int,owner_discord_user_id:int,item_codes:list[str],looking_for:Optional[str])->None:
    conn.execute("INSERT INTO trade_listings (listing_id,guild_id,owner_user_id,looking_for) VALUES (?,?,?,?)",(listing_id,str(guild_id),str(owner_discord_user_id),looking_for))
    for code in item_codes:
        conn.execute("INSERT INTO trade_listing_cards (listing_id,item_code) VALUES (?,?)",(listing_id,code))
    conn.commit()

def close_listing(conn,listing_id:str)->None:
    conn.execute("UPDATE trade_listings SET status='closed', closed_at=CURRENT_TIMESTAMP WHERE listing_id=?",(listing_id,))

def get_listing_item_codes(conn,listing_id:str)->list[str]:
    rows=conn.execute("SELECT item_code FROM trade_listing_cards WHERE listing_id=?",(listing_id,)).fetchall()
    return [r["item_code"] for r in rows]

def save_listing_public_message(conn,listing_id:str,channel_id:int,message_id:int)->None:
    conn.execute("""INSERT OR REPLACE INTO trade_listing_public_messages
    (listing_id,channel_id,message_id,created_at) VALUES (?,?,?,CURRENT_TIMESTAMP)""",(listing_id,str(channel_id),str(message_id)))
    conn.commit()

def get_listing_public_message(conn,listing_id:str)->Optional[Any]:
    return conn.execute("SELECT * FROM trade_listing_public_messages WHERE listing_id=?",(listing_id,)).fetchone()

def delete_listing_public_message(conn,listing_id:str)->None:
    conn.execute("DELETE FROM trade_listing_public_messages WHERE listing_id=?",(listing_id,))

def get_user_incoming_offer_count(conn, discord_user_id:int)->int:
    row=conn.execute("SELECT COUNT(*) FROM trade_offers WHERE receiver_user_id=? AND status='pending'",(str(discord_user_id),)).fetchone()
    return int(row[0]) if row else 0

def get_user_sent_offer_count(conn, discord_user_id:int)->int:
    row=conn.execute("SELECT COUNT(*) FROM trade_offers WHERE sender_user_id=? AND status='pending'",(str(discord_user_id),)).fetchone()
    return int(row[0]) if row else 0

def save_offer(conn,offer_id:str,guild_id:int,sender_discord_user_id:int,receiver_discord_user_id:int,item_codes:list[str],listing_id:Optional[str]=None,requested_codes:Optional[list[str]]=None)->None:
    conn.execute("INSERT INTO trade_offers (offer_id,guild_id,listing_id,sender_user_id,receiver_user_id) VALUES (?,?,?,?,?)",(offer_id,str(guild_id),listing_id,str(sender_discord_user_id),str(receiver_discord_user_id)))
    for code in item_codes:
        conn.execute("INSERT INTO trade_offer_cards (offer_id,item_code) VALUES (?,?)",(offer_id,code))
    for code in (requested_codes or []):
        conn.execute("INSERT INTO trade_offer_requested_cards (offer_id,item_code) VALUES (?,?)",(offer_id,code))
    conn.commit()

def get_offer_row(conn,offer_id:str)->Optional[Any]:
    return conn.execute("SELECT * FROM trade_offers WHERE offer_id=?",(offer_id,)).fetchone()

def get_offer_item_codes(conn,offer_id:str)->list[str]:
    rows=conn.execute("SELECT item_code FROM trade_offer_cards WHERE offer_id=?",(offer_id,)).fetchall()
    return [r["item_code"] for r in rows]

def get_offer_requested_codes(conn,offer_id:str)->list[str]:
    rows=conn.execute("SELECT item_code FROM trade_offer_requested_cards WHERE offer_id=?",(offer_id,)).fetchall()
    return [r["item_code"] for r in rows]

def resolve_offer(conn,offer_id:str,status:str)->int:
    cur=conn.execute("UPDATE trade_offers SET status=?, resolved_at=CURRENT_TIMESTAMP WHERE offer_id=? AND status='pending'",(status,offer_id))
    return cur.rowcount

class TradeSwapError(Exception): pass

def swap_card_ownership_for_offer(conn,offer_id:str)->dict:
    offer=conn.execute("SELECT * FROM trade_offers WHERE offer_id=?",(offer_id,)).fetchone()
    if not offer: raise TradeSwapError("Offer not found.")
    def internal(discord_id:str):
        row=conn.execute("SELECT id FROM users WHERE discord_user_id=?",(discord_id,)).fetchone()
        return row["id"] if row else None
    sender=internal(offer["sender_user_id"]); receiver=internal(offer["receiver_user_id"])
    if not sender or not receiver: raise TradeSwapError("Could not resolve internal user IDs.")
    def owner(code):
        row=conn.execute("SELECT user_id FROM claims WHERE item_code=? AND removed_at IS NULL",(code,)).fetchone()
        return row["user_id"] if row else None
    offer_codes=get_offer_item_codes(conn,offer_id)
    requested=get_offer_requested_codes(conn,offer_id)
    if not requested and offer["listing_id"]: requested=get_listing_item_codes(conn,offer["listing_id"])
    for code in offer_codes:
        if owner(code)!=sender: raise TradeSwapError(f"Card `{code}` no longer belongs to sender.")
    for code in requested:
        if owner(code)!=receiver: raise TradeSwapError(f"Card `{code}` no longer belongs to receiver.")
    for code in offer_codes:
        conn.execute("UPDATE claims SET user_id=? WHERE item_code=? AND removed_at IS NULL",(receiver,code))
    for code in requested:
        conn.execute("UPDATE claims SET user_id=? WHERE item_code=? AND removed_at IS NULL",(sender,code))
    if offer["listing_id"]: close_listing(conn, offer["listing_id"])
    return {"moved_to_receiver":offer_codes,"moved_to_sender":requested}

def get_user_incoming_offers(conn, discord_user_id:int)->list[Any]:
    return conn.execute("""SELECT o.offer_id,o.sender_user_id,o.listing_id,o.created_at,GROUP_CONCAT(oc.item_code, ',') AS offer_codes
    FROM trade_offers o LEFT JOIN trade_offer_cards oc ON oc.offer_id=o.offer_id
    WHERE o.receiver_user_id=? AND o.status='pending' GROUP BY o.offer_id ORDER BY o.created_at DESC""",(str(discord_user_id),)).fetchall()

def get_user_sent_offers(conn, discord_user_id:int)->list[Any]:
    return conn.execute("""SELECT o.offer_id,o.receiver_user_id,o.listing_id,o.status,o.created_at,GROUP_CONCAT(oc.item_code, ',') AS offer_codes
    FROM trade_offers o LEFT JOIN trade_offer_cards oc ON oc.offer_id=o.offer_id
    WHERE o.sender_user_id=? AND o.status IN ('pending','accepted','declined') GROUP BY o.offer_id ORDER BY o.created_at DESC LIMIT 20""",(str(discord_user_id),)).fetchall()

def get_all_users_with_cards(conn)->list[Any]:
    return conn.execute("""SELECT DISTINCT u.discord_user_id,u.display_name,COUNT(c.id) AS card_count FROM users u JOIN claims c ON c.user_id=u.id
    WHERE c.removed_at IS NULL AND u.discord_user_id IS NOT NULL AND u.kind='discord' GROUP BY u.id ORDER BY u.display_name ASC""").fetchall()
