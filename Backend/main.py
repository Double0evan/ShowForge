"""
Backend/main.py

FastAPI application — the backend API server.
Runs on port 8000.
"""

import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from Core.show_service import require_active_show
from Core.show_manager import ShowManager
from Core.inventory_service import generate_inventory, list_inventory, remove_item, next_inventory_code
from Core.claim_service import create_claim, remove_claim, list_claims, ClaimError
from Core.db import db_session
from Core.normalize import normalize_name
from Core.show_settings_service import set_setting, get_setting
from Core.media_service import upsert_media, get_media
from Core.voucher_service import award_voucher, staff_adjust, get_balance, list_ledger
from Core.user_service import find_pending_by_name, transfer_credits

from Backend.routes.ui import router as ui_router
from Backend.routes.members import router as members_router

app = FastAPI(title="V3_Bot Backend", version="0.2.0")
app.include_router(ui_router)
app.include_router(members_router)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    try:
        active = require_active_show()
        return {"ok": True, "active_show": active.show_id}
    except Exception:
        return {"ok": True, "active_show": None}


# ── Shows ─────────────────────────────────────────────────────────────────────

class NewShowReq(BaseModel):
    date: str = Field(..., description="YYYY-MM-DD")
    name: str = Field(..., description="Show name")


def _shows():
    """Get a ShowManager anchored to the correct repo root."""
    from Core.show_service import _find_repo_root
    return ShowManager(_find_repo_root())


@app.get("/shows/active")
def get_active_show():
    active = _shows().get_active()
    return {
        "active_show": active.show_id if active else None,
        "db_path":     str(active.db_path) if active else None,
    }

@app.post("/shows/new")
def new_show(req: NewShowReq):
    ref = _shows().create_new_show(req.date, req.name)
    return {"ok": True, "show_id": ref.show_id}

@app.post("/shows/end")
def end_show():
    s      = _shows()
    active = s.get_active()
    if not active:
        raise HTTPException(status_code=400, detail="No active show.")
    s.clear_active()
    return {"ok": True, "ended_show": active.show_id}

@app.post("/shows/settings/set")
def api_show_setting_set(key: str, value: str):
    active = require_active_show()
    set_setting(active.db_path, key, value)
    return {"ok": True, "key": key, "value": value}

@app.get("/shows/settings/get")
def api_show_setting_get(key: str):
    active = require_active_show()
    return {"ok": True, "key": key, "value": get_setting(active.db_path, key)}


# ── Users ─────────────────────────────────────────────────────────────────────

@app.post("/users/create_pending")
def create_pending_user(display_name: str):
    active = require_active_show()
    with db_session(active.db_path) as conn:
        cur = conn.execute(
            "INSERT INTO users (kind, discord_user_id, display_name, normalized_name, created_at) "
            "VALUES ('pending', NULL, ?, ?, datetime('now'))",
            (display_name, normalize_name(display_name)),
        )
        return {"ok": True, "user_id": cur.lastrowid}

@app.post("/users/upsert_discord")
def upsert_discord_user(discord_user_id: str, display_name: str):
    active = require_active_show()
    with db_session(active.db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE discord_user_id = ?", (discord_user_id,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE users SET display_name = ?, normalized_name = ? WHERE discord_user_id = ?",
                (display_name, normalize_name(display_name), discord_user_id),
            )
            return {"ok": True, "user_id": int(existing["id"]), "kind": "discord"}
        cur = conn.execute(
            "INSERT INTO users (kind, discord_user_id, display_name, normalized_name, created_at) "
            "VALUES ('discord', ?, ?, ?, datetime('now'))",
            (discord_user_id, display_name, normalize_name(display_name)),
        )
        return {"ok": True, "user_id": cur.lastrowid, "kind": "discord"}

@app.get("/users/find_pending")
def api_find_pending(display_name: str):
    try:
        active = require_active_show()
    except Exception:
        return {"found": False}
    result = find_pending_by_name(active.db_path, display_name)
    return result if result else {"found": False}

@app.post("/users/transfer_credits")
def api_transfer_credits(from_user_id: int, to_user_id: int, amount: int):
    active = require_active_show()
    return transfer_credits(active.db_path, from_user_id=from_user_id, to_user_id=to_user_id, amount=amount)


# ── Inventory ─────────────────────────────────────────────────────────────────

@app.post("/inventory/generate")
def api_generate_inventory(count: int):
    active = require_active_show()
    return generate_inventory(active.db_path, count)

@app.get("/inventory")
def api_list_inventory():
    active = require_active_show()
    return {"items": list_inventory(active.db_path)}

@app.post("/inventory/remove")
def api_remove_inventory_item(item_code: str):
    active = require_active_show()
    return remove_item(active.db_path, item_code=item_code)

@app.post("/inventory/next_code")
def api_next_code(rating: str, post_mode: str = "claim"):
    active = require_active_show()
    return next_inventory_code(active.db_path, rating, post_mode)

@app.post("/inventory/upsert")
def api_inventory_upsert(item_code: str, post_mode: str = "claim"):
    """
    Creates an inventory row for a specific code if it doesn't exist.
    Called by the watcher after uploading files.
    post_mode: 'claim' (default) or 'display'
    """
    from datetime import datetime, timezone
    active    = require_active_show()
    item_code = item_code.strip().upper()
    post_mode = post_mode if post_mode in ("claim", "display") else "claim"
    now       = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    with db_session(active.db_path) as conn:
        existing = conn.execute(
            "SELECT item_code FROM inventory_items WHERE item_code = ?", (item_code,)
        ).fetchone()
        if existing:
            return {"ok": True, "item_code": item_code, "created": False}
        conn.execute(
            "INSERT INTO inventory_items (item_code, status, post_mode, created_at, updated_at, published_at) "
            "VALUES (?, 'available', ?, ?, ?, NULL)",
            (item_code, post_mode, now, now),
        )
    return {"ok": True, "item_code": item_code, "created": True, "post_mode": post_mode}


# ── Media ─────────────────────────────────────────────────────────────────────

@app.post("/media/upsert")
def api_media_upsert(
    item_code: str, variant: str, rating: str,
    source_channel_id: str, source_message_id: str, attachment_url: str,
    filename: str | None = None, content_type: str | None = None,
):
    active = require_active_show()
    return upsert_media(
        active.db_path, item_code=item_code, variant=variant, rating=rating,
        source_channel_id=source_channel_id, source_message_id=source_message_id,
        attachment_url=attachment_url, filename=filename, content_type=content_type,
    )

@app.get("/media/get")
def api_media_get(item_code: str, variant: str, rating: str):
    active = require_active_show()
    return {"ok": True, "media": get_media(active.db_path, item_code=item_code, variant=variant, rating=rating)}


# ── Vouchers ──────────────────────────────────────────────────────────────────

@app.post("/vouchers/award")
def api_award_voucher(user_id: int, reason: str = "WINNER", note: str | None = None):
    active = require_active_show()
    return award_voucher(active.db_path, user_id=user_id, reason=reason, note=note)

@app.post("/vouchers/adjust")
def api_staff_adjust(user_id: int, delta: int, note: str | None = None):
    active = require_active_show()
    return staff_adjust(active.db_path, user_id=user_id, delta=delta, note=note)

@app.get("/vouchers/balance")
def api_balance(user_id: int):
    active = require_active_show()
    return {"user_id": user_id, "balance": get_balance(active.db_path, user_id)}

@app.get("/vouchers/ledger")
def api_ledger(user_id: int | None = None):
    active = require_active_show()
    return {"rows": list_ledger(active.db_path, user_id=user_id)}


# ── Claims ────────────────────────────────────────────────────────────────────

@app.post("/claims/create")
def api_create_claim(item_code: str, user_id: int, source: str = "staff"):
    active = require_active_show()
    try:
        return create_claim(active.db_path, item_code=item_code, user_id=user_id, source=source)
    except ClaimError as e:
        raise HTTPException(status_code=400, detail={"code": e.code, "message": e.message})

@app.post("/claims/remove")
def api_remove_claim(item_code: str, refund: bool = True, reason: str = "Removed by staff"):
    active = require_active_show()
    try:
        return remove_claim(active.db_path, item_code=item_code, refund=refund, reason=reason)
    except ClaimError as e:
        raise HTTPException(status_code=400, detail={"code": e.code, "message": e.message})

@app.get("/claims")
def api_list_claims(include_removed: bool = False):
    active = require_active_show()
    return {"claims": list_claims(active.db_path, include_removed=include_removed)}

@app.post("/claims/attempt")
def api_attempt_claim(item_code: str, user_id: int):
    active = require_active_show()
    try:
        return create_claim(active.db_path, item_code=item_code, user_id=user_id, source="button")
    except ClaimError as e:
        return {"ok": False, "code": e.code, "message": e.message}
