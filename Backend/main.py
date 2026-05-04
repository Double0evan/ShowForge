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
    import requests as _req
    s      = _shows()
    active = s.get_active()
    if not active:
        raise HTTPException(status_code=400, detail="No active show.")

    # Lock trades before ending
    try:
        _req.post("http://127.0.0.1:8001/trade/lock", timeout=5)
    except Exception:
        pass

    # Generate and post trade report
    report_result = {}
    try:
        r = _req.post("http://127.0.0.1:8001/trade/report", timeout=60)
        report_result = r.json()
    except Exception as e:
        report_result = {"ok": False, "error": str(e)}

    s.clear_active()
    return {"ok": True, "ended_show": active.show_id, "trade_report": report_result}

@app.post("/shows/settings/set")
def api_show_setting_set(key: str, value: str):
    active = require_active_show()
    set_setting(active.db_path, key, value)
    return {"ok": True, "key": key, "value": value}

@app.get("/shows/settings/get")
def api_show_setting_get(key: str):
    try:
        active = require_active_show()
        return {"ok": True, "key": key, "value": get_setting(active.db_path, key)}
    except Exception:
        return {"ok": True, "key": key, "value": None}


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
    merged_from = None

    with db_session(active.db_path) as conn:
        # Check if Discord user already exists
        existing = conn.execute(
            "SELECT id FROM users WHERE discord_user_id = ?", (discord_user_id,)
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE users SET display_name = ?, normalized_name = ? WHERE discord_user_id = ?",
                (display_name, normalize_name(display_name), discord_user_id),
            )
            discord_user_id_int = int(existing["id"])
        else:
            cur = conn.execute(
                "INSERT INTO users (kind, discord_user_id, display_name, normalized_name, created_at) "
                "VALUES ('discord', ?, ?, ?, datetime('now'))",
                (discord_user_id, display_name, normalize_name(display_name)),
            )
            discord_user_id_int = cur.lastrowid

        # Auto-merge: find any pending/guest users with matching normalized name
        norm = normalize_name(display_name)
        pending = conn.execute(
            "SELECT id, display_name FROM users "
            "WHERE kind IN ('pending', 'guest') AND normalized_name = ? AND id != ?",
            (norm, discord_user_id_int),
        ).fetchall()

        for p in pending:
            pending_id = p["id"]

            # Transfer all voucher ledger entries
            conn.execute(
                "UPDATE voucher_ledger SET user_id = ? WHERE user_id = ?",
                (discord_user_id_int, pending_id),
            )
            # Transfer all claims
            conn.execute(
                "UPDATE claims SET user_id = ? WHERE user_id = ? AND removed_at IS NULL",
                (discord_user_id_int, pending_id),
            )
            # Mark pending user as merged
            conn.execute(
                "UPDATE users SET kind = 'merged', display_name = display_name || ' [merged]' WHERE id = ?",
                (pending_id,),
            )
            merged_from = p["display_name"]
            print(f"[MERGE] Auto-merged pending user '{p['display_name']}' (id={pending_id}) -> discord user id={discord_user_id_int}")

    result = {"ok": True, "user_id": discord_user_id_int, "kind": "discord"}
    if merged_from:
        result["merged_from"] = merged_from
    return result

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

# ── Show Mode ─────────────────────────────────────────────────────────────────

@app.post("/shows/mode")
def set_show_mode(mode: str):
    """Set show mode: 'standard' or 'bin'"""
    if mode not in ("standard", "bin"):
        raise HTTPException(status_code=400, detail="mode must be 'standard' or 'bin'")
    active = require_active_show()
    set_setting(active.db_path, "show_mode", mode)
    return {"ok": True, "show_mode": mode}

@app.get("/shows/mode")
def get_show_mode():
    try:
        active = require_active_show()
        mode = get_setting(active.db_path, "show_mode") or "standard"
        return {"ok": True, "show_mode": mode}
    except Exception:
        return {"ok": True, "show_mode": "standard"}


# ── Watcher Control ───────────────────────────────────────────────────────────

@app.get("/watcher/debug")
def watcher_debug():
    """Returns the resolved paths so you can see where the backend is looking."""
    from pathlib import Path
    this_file = Path(__file__).resolve()
    return {
        "this_file": str(this_file),
        "parents": [str(p) for p in this_file.parents[:5]],
    }

@app.post("/watcher/start")
def start_whatnot_watcher():
    """Launch the Whatnot screen watcher in a new terminal window."""
    import subprocess
    from pathlib import Path

    this_file = Path(__file__).resolve()

    # Search upward from this file for the repo root (contains run.py or .venv)
    repo_root = this_file.parent
    for _ in range(6):
        if (repo_root / "run.py").exists() or (repo_root / ".venv").exists():
            break
        repo_root = repo_root.parent

    venv_python = repo_root / ".venv" / "Scripts" / "python.exe"

    # Check all likely locations for the watcher script
    candidates = [
        repo_root / "whatnot_watcher_test.py",
        repo_root / "Discord" / "whatnot_watcher_test.py",
        this_file.parent.parent / "whatnot_watcher_test.py",
        this_file.parent.parent / "Discord" / "whatnot_watcher_test.py",
    ]
    watcher_script = next((p for p in candidates if p.exists()), None)

    if watcher_script is None:
        checked = [str(p) for p in candidates]
        raise HTTPException(
            status_code=404,
            detail=f"whatnot_watcher_test.py not found. Checked: {checked}"
        )

    python = str(venv_python) if venv_python.exists() else "python"
    subprocess.Popen(
        f'start "V3 Whatnot Watcher" cmd /k "{python} {watcher_script}"',
        shell=True,
        cwd=str(repo_root),
    )
    return {"ok": True, "message": "Whatnot watcher launched"}
# ── Bin Queue ─────────────────────────────────────────────────────────────────

@app.get("/bin/peek")
def api_bin_peek():
    from Core.bin_queue import peek_latest_sale
    return {"ok": True, "sale": peek_latest_sale()}

@app.get("/bin/queue")
def api_bin_queue():
    """All unmatched pending sales."""
    try:
        from Core.bin_queue import _connect
        conn = _connect()
        rows = conn.execute(
            "SELECT * FROM pending_sales WHERE matched = 0 ORDER BY detected_at DESC"
        ).fetchall()
        conn.close()
        return {"ok": True, "pending": [dict(r) for r in rows]}
    except Exception as e:
        return {"ok": False, "pending": [], "error": str(e)}

@app.get("/bin/history")
def api_bin_history(limit: int = 50):
    """Recent matched + unmatched sales for the dashboard."""
    from Core.bin_queue import _connect
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM pending_sales ORDER BY detected_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return {"ok": True, "sales": [dict(r) for r in rows]}

@app.post("/bin/clear")
def api_bin_clear():
    from Core.bin_queue import clear_queue
    return {"ok": True, "cleared": clear_queue()}

@app.delete("/bin/queue/{row_id}")
def api_bin_delete_sale(row_id: int):
    """Remove a single pending sale from the queue by its row ID."""
    try:
        from Core.bin_queue import _connect
        conn = _connect()
        cur = conn.execute("DELETE FROM pending_sales WHERE id = ? AND matched = 0", (row_id,))
        conn.commit()
        conn.close()
        return {"ok": True, "deleted": cur.rowcount > 0}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/bin/inject")
def api_bin_inject(username: str, auction_number: int = 0):
    """Manually inject a fake sale for testing without the screen watcher."""
    from Core.bin_queue import push_sale
    import random
    if auction_number == 0:
        auction_number = random.randint(1, 999)
    row_id = push_sale(auction_number, username)
    return {"ok": True, "auction_number": auction_number, "username": username, "row_id": row_id}

@app.post("/bin/reassign")
def api_bin_reassign(item_code: str, new_discord_display_name: str, refund_old: bool = True):
    """
    Reassign a bin show claim to a different Discord user.
    Use when OCR matched the wrong person or you need to correct a pairing.
    - Removes the old claim (with optional voucher refund)
    - Creates a new claim for the correct user
    - Correct user must already exist in the show DB (have joined + been upserted)
    """
    active = require_active_show()
    item_code = item_code.strip().upper()

    with db_session(active.db_path) as conn:
        from Core.normalize import normalize_name as _norm
        # Prefer discord user, then any kind
        target = conn.execute(
            "SELECT id FROM users WHERE normalized_name = ? ORDER BY CASE kind WHEN 'discord' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END LIMIT 1",
            (_norm(new_discord_display_name),)
        ).fetchone()
        if not target:
            # Try exact display_name match as fallback
            target = conn.execute(
                "SELECT id FROM users WHERE display_name = ? LIMIT 1",
                (new_discord_display_name,)
            ).fetchone()
        if not target:
            cur = conn.execute(
                "INSERT INTO users (kind, discord_user_id, display_name, normalized_name, created_at) "
                "VALUES ('pending', NULL, ?, ?, datetime('now'))",
                (new_discord_display_name, _norm(new_discord_display_name)),
            )
            target_id = cur.lastrowid
        else:
            target_id = target["id"]
        print(f"[REASSIGN] target_id={target_id} for {new_discord_display_name}")

        # Check item exists
        item = conn.execute(
            "SELECT status FROM inventory_items WHERE item_code = ?", (item_code,)
        ).fetchone()
        if not item:
            raise HTTPException(status_code=404, detail=f"Item {item_code} not found")

    # Remove existing claim if any
    try:
        remove_claim(active.db_path, item_code=item_code, refund=refund_old, reason="Staff reassign")
    except ClaimError:
        pass  # No existing claim — fine, just create the new one

    # Force item back to available in case remove_claim didn't fully reset it
    with db_session(active.db_path) as conn:
        conn.execute(
            "UPDATE inventory_items SET status = 'available' WHERE item_code = ?",
            (item_code,)
        )
        # Also hard-remove any lingering active claim rows
        conn.execute(
            "UPDATE claims SET removed_at = datetime('now'), removed_reason = 'Staff reassign override' "
            "WHERE item_code = ? AND removed_at IS NULL",
            (item_code,)
        )

    # Award voucher + create claim for new user
    # We always award first so the voucher balance check in create_claim passes.
    # This is a staff correction so no user actually "spends" a credit — it balances out.
    try:
        award_voucher(active.db_path, user_id=target_id, reason="STAFF_ADJUST", note=f"Reassign credit {item_code}")
        result = create_claim(active.db_path, item_code=item_code, user_id=target_id, source="staff")
        return {"ok": True, "item_code": item_code, "reassigned_to": new_discord_display_name, "claim_id": result["claim_id"]}
    except ClaimError as e:
        raise HTTPException(status_code=400, detail={"code": e.code, "message": e.message})
# ── Bin Match Reviews ─────────────────────────────────────────────────────────

@app.get("/bin/reviews")
def api_bin_reviews():
    """Unresolved low-confidence match reviews for the dashboard."""
    from Core.bin_queue import _connect
    conn = _connect()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS match_reviews (
                id                   INTEGER PRIMARY KEY,
                item_code            TEXT NOT NULL,
                auction_number       INTEGER NOT NULL,
                whatnot_user         TEXT NOT NULL,
                guest_user_id        INTEGER NOT NULL,
                closest_discord_name TEXT,
                match_score          REAL,
                resolved             INTEGER NOT NULL DEFAULT 0,
                resolved_at          TEXT,
                created_at           TEXT NOT NULL
            )
        """)
        conn.commit()
        rows = conn.execute(
            "SELECT * FROM match_reviews WHERE resolved = 0 ORDER BY created_at DESC"
        ).fetchall()
        return {"ok": True, "reviews": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.post("/bin/reviews/{review_id}/reassign")
def api_bin_review_reassign(review_id: int, discord_display_name: str):
    """
    Reassign a flagged guest claim to a verified Discord user by display name.
    Transfers the claim from the guest to the matched user.
    """
    from Core.bin_queue import _connect
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM match_reviews WHERE id = ? AND resolved = 0", (review_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Review not found or already resolved")
        review = dict(row)
    finally:
        conn.close()

    active = require_active_show()

    # Find the target user by display name in the show DB
    with db_session(active.db_path) as conn:
        target_user = conn.execute(
            "SELECT id FROM users WHERE display_name = ? AND kind = 'discord'",
            (discord_display_name,),
        ).fetchone()
        if not target_user:
            raise HTTPException(status_code=404, detail=f"Discord user '{discord_display_name}' not found")
        target_id = target_user["id"]

        # Move the claim
        conn.execute(
            "UPDATE claims SET user_id = ? WHERE item_code = ? AND removed_at IS NULL",
            (target_id, review["item_code"]),
        )
        # Transfer any credits from guest to real user
        conn.execute(
            "UPDATE voucher_ledger SET user_id = ? WHERE user_id = ?",
            (target_id, review["guest_user_id"]),
        )

    # Mark resolved
    bq_conn = _connect()
    try:
        bq_conn.execute(
            "UPDATE match_reviews SET resolved = 1, resolved_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), review_id),
        )
        bq_conn.commit()
    finally:
        bq_conn.close()

    return {"ok": True, "item_code": review["item_code"], "reassigned_to": discord_display_name}


@app.post("/bin/reviews/{review_id}/keep_guest")
def api_bin_review_keep_guest(review_id: int):
    """Mark a review as resolved — keep the guest claim as-is."""
    from Core.bin_queue import _connect
    conn = _connect()
    try:
        conn.execute(
            "UPDATE match_reviews SET resolved = 1, resolved_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), review_id),
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()
# ── Trade Admin ───────────────────────────────────────────────────────────────

@app.post("/trade/lock")
def api_trade_lock_proxy():
    """Lock trades — proxies to bot API which has show DB access."""
    import requests as _req
    try:
        r = _req.post("http://127.0.0.1:8001/trade/lock", timeout=10)
        return r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/trade/unlock")
def api_trade_unlock_proxy():
    import requests as _req
    try:
        r = _req.post("http://127.0.0.1:8001/trade/unlock", timeout=10)
        return r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/trade/close_channels")
def api_trade_close_channels_proxy():
    """Delete all trade channels — proxies to bot API (needs Discord access)."""
    import requests as _req
    try:
        r = _req.post("http://127.0.0.1:8001/trade/close_channels", timeout=90)
        return r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/trade/refresh_all")
def api_trade_refresh_all_proxy():
    """Refresh all trade channel home messages — proxies to bot API."""
    import requests as _req
    try:
        r = _req.post("http://127.0.0.1:8001/trade/refresh_all", timeout=120)
        return r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/trade/report")
def api_trade_report_proxy():
    """Generate trade report, save CSV, post to claims thread."""
    import requests as _req
    try:
        r = _req.post("http://127.0.0.1:8001/trade/report", timeout=90)
        return r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/shows/{show_id}/trade_report")
def get_trade_report_csv(show_id: str):
    """Download the trade report CSV for a past show."""
    from fastapi.responses import FileResponse
    from Core.show_service import _find_repo_root
    repo_root = _find_repo_root()
    csv_path  = repo_root / "DB" / "shows" / show_id / "trade_report.csv"
    if not csv_path.exists():
        raise HTTPException(status_code=404, detail="No trade report found for this show.")
    return FileResponse(
        path=str(csv_path),
        filename=f"trade_report_{show_id}.csv",
        media_type="text/csv",
    )

