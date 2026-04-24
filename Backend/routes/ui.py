from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.templating import Jinja2Templates

from Backend.services.publish_service import publish_item

from Core.inventory_service import list_inventory, remove_item
from Core.claim_service import list_claims, remove_claim, ClaimError
from Core.show_service import require_active_show
from Core.show_manager import ShowManager
from Core.media_service import get_media
from Core.voucher_service import get_balance, staff_adjust, award_voucher
from Core.user_service import find_pending_by_name, transfer_credits
from Core.normalize import normalize_name
from Core.db import db_session

import asyncio
import json
import os
import requests
import shutil
import threading
from pathlib import Path
from dotenv import set_key, dotenv_values

router    = APIRouter()
templates = Jinja2Templates(directory="Backend/ui/templates")

def _find_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "Discord" / ".env").exists():
            return parent
        if (parent / "pyproject.toml").exists():
            return parent
        if (parent / "DB").exists() and (parent / "Discord").exists():
            return parent
    return Path(__file__).resolve().parents[2]

REPO_ROOT = _find_repo_root()
ENV_PATH  = REPO_ROOT / "Discord" / ".env"
BOT_API   = "http://127.0.0.1:8001"
shows     = ShowManager(REPO_ROOT)


# ── helpers ───────────────────────────────────────────────────────────────────

def _env() -> dict:
    return dotenv_values(ENV_PATH)


def _inbox_path(rating: str) -> Path:
    # Read directly from .env each time so we always get the current value
    # even if the env var wasn't set when the process started
    env    = dotenv_values(ENV_PATH)
    parent = Path(env.get("WATCHER_PARENT_DIR") or os.getenv("WATCHER_PARENT_DIR", r"D:\V3Shows"))
    folder = "SFW" if rating == "sfw" else "NSFW"
    p      = parent / "INBOX" / folder
    p.mkdir(parents=True, exist_ok=True)
    return p


def _list_past_shows() -> list[dict]:
    shows_root  = REPO_ROOT / "DB" / "shows"
    active_file = REPO_ROOT / "DB" / "active_show.json"
    active_id   = None
    if active_file.exists():
        try:
            active_id = json.loads(active_file.read_text())["show_id"]
        except Exception:
            pass
    result = []
    if shows_root.exists():
        for d in sorted(shows_root.iterdir(), reverse=True):
            db = d / "show.db"
            if not db.exists():
                continue
            result.append({"show_id": d.name, "is_active": d.name == active_id, "db_path": str(db)})
    return result


def _base_ctx(page: str, request: Request) -> dict:
    active = shows.get_active()
    show_type = None
    if active:
        try:
            from Core.show_settings_service import get_setting
            show_type = get_setting(active.db_path, "show_type")
        except Exception:
            pass
    return {
        "request":        request,
        "page":           page,
        "active_show":    active.show_id if active else None,
        "show_type":      show_type,
        "items":          [],
        "claims":         [],
        "users":          [],
        "past_shows":     [],
        "members":        {},
        "env":            {},
        "console_result": None,
        "selected_show":  None,
    }


def _resolve_user_by_name(db_path, display_name: str) -> dict | None:
    normalized = normalize_name(display_name)
    with db_session(db_path) as conn:
        row = conn.execute(
            "SELECT id, display_name, kind FROM users WHERE normalized_name = ? ORDER BY CASE kind WHEN 'discord' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END LIMIT 1",
            (normalized,),
        ).fetchone()
    return dict(row) if row else None


def _resolve_user_by_discord_id(db_path, discord_id: str) -> dict | None:
    with db_session(db_path) as conn:
        row = conn.execute(
            "SELECT id, display_name, kind FROM users WHERE discord_user_id = ?", (discord_id,)
        ).fetchone()
    return dict(row) if row else None


# ── NATIVE PICKERS ────────────────────────────────────────────────────────────

@router.get("/ui/pick/folder")
def pick_folder():
    result = {}
    def _open():
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk(); root.withdraw(); root.wm_attributes("-topmost", True)
            selected = filedialog.askdirectory(title="Select Folder")
            root.destroy()
            result["path"] = selected or None
        except Exception as e:
            result["error"] = str(e)
    t = threading.Thread(target=_open); t.start(); t.join(timeout=60)
    return {"ok": bool(result.get("path")), "path": result.get("path")}


@router.get("/ui/pick/file")
def pick_file(accept: str = ""):
    result = {}
    def _open():
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk(); root.withdraw(); root.wm_attributes("-topmost", True)
            ftypes = [("All files", "*.*")]
            if accept:
                exts    = [e.strip() for e in accept.split(",") if e.strip()]
                pattern = " ".join(f"*{e}" for e in exts)
                ftypes  = [(f"Images ({pattern})", pattern)] + ftypes
            selected = filedialog.askopenfilename(title="Select File", filetypes=ftypes)
            root.destroy()
            result["path"] = selected or None
        except Exception as e:
            result["error"] = str(e)
    t = threading.Thread(target=_open); t.start(); t.join(timeout=60)
    return {"ok": bool(result.get("path")), "path": result.get("path")}


# ── SHOW CONTROL ──────────────────────────────────────────────────────────────

@router.post("/ui/show/new")
async def ui_new_show(date: str = Form(...), name: str = Form(...)):
    ref = shows.create_new_show(date, name)

    # Ask the bot to create the Discord archival claim threads
    discord_result = {}
    try:
        r = requests.post(
            f"{BOT_API}/new_show",
            json={"show_id": ref.show_id, "date": date, "name": name},
            timeout=30,
        )
        discord_result = r.json()
    except Exception as e:
        discord_result = {"ok": False, "error": str(e)}

    return {
        "ok":      True,
        "show_id": ref.show_id,
        "discord": discord_result,
    }


@router.post("/ui/show/end")
async def ui_end_show():
    active = shows.get_active()
    if not active:
        return {"ok": False, "error": "No active show"}
    shows.clear_active()
    return {"ok": True, "ended": active.show_id}


# ── INVENTORY ─────────────────────────────────────────────────────────────────

@router.get("/ui")
def ui_home(request: Request):
    ctx    = _base_ctx("inventory", request)
    active = shows.get_active()
    if active:
        raw_items = list_inventory(active.db_path)
        for item in raw_items:
            code   = item["item_code"]
            rating = "nsfw" if code.startswith("N") else "sfw"
            media  = get_media(active.db_path, code, "watermarked", rating)
            item["preview_url"] = media["attachment_url"] if media else None
        ctx["items"] = raw_items
    return templates.TemplateResponse("index.html", ctx)


@router.post("/ui/publish")
async def ui_publish(item_code: str = Form(...)):
    active = require_active_show()
    return await asyncio.to_thread(publish_item, item_code, active)


@router.post("/ui/publish_all")
async def ui_publish_all():
    active  = require_active_show()
    results = []
    for item in list_inventory(active.db_path):
        if item["status"] != "available" or item.get("published_at"):
            continue
        try:
            results.append(await asyncio.to_thread(publish_item, item["item_code"], active))
        except Exception as e:
            results.append({"ok": False, "error": str(e)})
    return {"ok": True, "results": results}


@router.post("/ui/republish")
async def ui_republish(item_code: str = Form(...)):
    """Clear published_at and re-send to catalog — used when a Discord post was deleted."""
    active    = require_active_show()
    item_code = item_code.strip().upper()

    with db_session(active.db_path) as conn:
        row = conn.execute(
            "SELECT status, post_mode FROM inventory_items WHERE item_code = ?", (item_code,)
        ).fetchone()
        if not row:
            return {"ok": False, "message": f"{item_code} not found"}
        if row["status"] != "available":
            return {"ok": False, "message": f"{item_code} is {row['status']} — can only republish available items"}
        conn.execute(
            "UPDATE inventory_items SET published_at = NULL WHERE item_code = ?", (item_code,)
        )

    return await asyncio.to_thread(publish_item, item_code, active)


@router.post("/ui/republish")
async def ui_republish(item_code: str = Form(...)):
    """Clear published_at and re-send to catalog — used when a Discord post was deleted."""
    active    = require_active_show()
    item_code = item_code.strip().upper()

    with db_session(active.db_path) as conn:
        row = conn.execute(
            "SELECT status, post_mode FROM inventory_items WHERE item_code = ?", (item_code,)
        ).fetchone()
        if not row:
            return {"ok": False, "message": f"{item_code} not found"}
        if row["status"] != "available":
            return {"ok": False, "message": f"{item_code} is {row['status']} — can only republish available items"}
        conn.execute(
            "UPDATE inventory_items SET published_at = NULL WHERE item_code = ?", (item_code,)
        )

    return await asyncio.to_thread(publish_item, item_code, active)


@router.post("/ui/inventory/remove")
async def ui_remove_item(item_code: str = Form(...)):
    active = require_active_show()
    return remove_item(active.db_path, item_code=item_code)


@router.get("/ui/inventory/poll")
def ui_inventory_poll():
    active = shows.get_active()
    if not active:
        return {"ok": False, "items": []}
    return {
        "ok": True,
        "items": [{"item_code": i["item_code"], "status": i["status"], "published_at": i["published_at"], "updated_at": i["updated_at"]}
                  for i in list_inventory(active.db_path)],
    }


# ── DRAG & DROP UPLOAD ────────────────────────────────────────────────────────

@router.post("/ui/inbox/upload")
async def ui_inbox_upload(rating: str = Form(...), files: list[UploadFile] = File(...)):
    inbox         = _inbox_path(rating)
    saved, errors = [], []
    for f in files:
        if not f.filename:
            continue
        if Path(f.filename).suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
            errors.append(f"{f.filename}: unsupported type")
            continue
        try:
            with open(inbox / f.filename, "wb") as out:
                shutil.copyfileobj(f.file, out)
            saved.append(f.filename)
        except Exception as e:
            errors.append(f"{f.filename}: {e}")
    return {"ok": True, "saved": saved, "errors": errors, "inbox": str(inbox)}


# ── CLAIMS ────────────────────────────────────────────────────────────────────

@router.get("/ui/claims")
def ui_claims(request: Request):
    ctx    = _base_ctx("claims", request)
    active = shows.get_active()
    if active:
        claims = list_claims(active.db_path, include_removed=False)
        for c in claims:
            code   = c["item_code"]
            rating = "nsfw" if code.startswith("N") else "sfw"
            media  = get_media(active.db_path, code, "watermarked", rating)
            c["preview_url"] = media["attachment_url"] if media else None
        ctx["claims"] = claims
    return templates.TemplateResponse("index.html", ctx)


@router.post("/ui/claims/summary")
async def ui_claims_summary(rating: str = Form(...)):
    """
    Delete all messages in the claims archival thread for the given rating,
    then post a sorted summary grouped by user with RAW images attached.
    """
    active = require_active_show()
    rating = rating.strip().lower()

    try:
        r = requests.post(f"{BOT_API}/claims/summary", json={"rating": rating}, timeout=120)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/ui/claims/summary")
async def ui_claims_summary(rating: str = Form(...)):
    """
    Delete all messages in the claims archival thread for the given rating,
    then post a sorted summary grouped by user with RAW images attached.
    """
    rating = rating.strip().lower()
    try:
        r = requests.post(f"{BOT_API}/claims/summary", json={"rating": rating}, timeout=120)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/ui/claims/summary")
async def ui_claims_summary(rating: str = Form(...)):
    """Delete all messages in the claims thread, post sorted summary with RAW images."""
    rating = rating.strip().lower()
    try:
        r = requests.post(f"{BOT_API}/claims/summary", json={"rating": rating}, timeout=120)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/ui/claims/remove")
async def ui_remove_claim(item_code: str = Form(...), refund: str = Form("true")):
    active    = require_active_show()
    do_refund = refund.lower() in ("true", "1", "yes")
    try:
        return remove_claim(active.db_path, item_code=item_code, refund=do_refund, reason="Removed via UI")
    except ClaimError as e:
        return {"ok": False, "code": e.code, "message": e.message}


# ── USERS ─────────────────────────────────────────────────────────────────────

@router.get("/ui/users")
def ui_users(request: Request):
    ctx    = _base_ctx("users", request)
    active = shows.get_active()
    if active:
        with db_session(active.db_path) as conn:
            rows = conn.execute(
                "SELECT id, kind, discord_user_id, display_name, created_at FROM users ORDER BY id ASC"
            ).fetchall()
        users = []
        for r in rows:
            u            = dict(r)
            u["balance"] = get_balance(active.db_path, u["id"])
            users.append(u)
        ctx["users"] = users
    return templates.TemplateResponse("index.html", ctx)


@router.post("/ui/users/adjust")
async def ui_adjust_credits(user_id: int = Form(...), delta: int = Form(...), note: str = Form("")):
    active = require_active_show()
    return staff_adjust(active.db_path, user_id=user_id, delta=delta, note=note or None)


@router.post("/ui/users/award_bulk")
async def ui_award_bulk(user_ids: str = Form(...), amount: int = Form(...), note: str = Form("")):
    active  = require_active_show()
    ids     = [int(x.strip()) for x in user_ids.split(",") if x.strip().isdigit()]
    if not ids:
        return {"ok": False, "message": "No valid user IDs"}
    if amount < 1:
        return {"ok": False, "message": "Amount must be at least 1"}
    results = []
    for uid in ids:
        try:
            for _ in range(amount):
                award_voucher(active.db_path, user_id=uid, reason="STAFF_ADJUST", note=note or f"Bulk award x{amount}")
            results.append({"user_id": uid, "ok": True})
        except Exception as e:
            results.append({"user_id": uid, "ok": False, "error": str(e)})
    return {"ok": True, "awarded": sum(1 for r in results if r["ok"]), "results": results}


# ── MEMBERS SEARCH (proxy) ────────────────────────────────────────────────────

@router.get("/ui/members/search")
def ui_members_search(q: str = ""):
    try:
        r = requests.get(f"{BOT_API}/members/search", params={"q": q, "limit": 8}, timeout=3)
        return r.json()
    except Exception as e:
        return {"ok": False, "results": [], "error": str(e)}


# ── WATCHER ───────────────────────────────────────────────────────────────────

@router.get("/ui/watcher")
def ui_watcher(request: Request):
    return templates.TemplateResponse("index.html", _base_ctx("watcher", request))


@router.get("/ui/watcher/log")
def ui_watcher_log(lines: int = 200):
    try:
        from Watcher.watcher_logger import read_lines, is_alive
        # Check processing flag
        flag_file = REPO_ROOT / "logs" / "watcher_process.flag"
        processing = flag_file.exists() and flag_file.read_text().strip() == "1"
        return {"ok": True, "alive": is_alive(), "processing": processing, "lines": read_lines(lines)}
    except Exception as e:
        return {"ok": False, "alive": False, "processing": False, "lines": [], "error": str(e)}


@router.post("/ui/watcher/clear")
def ui_watcher_clear():
    try:
        from Watcher.watcher_logger import clear
        clear()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/ui/watcher/start")
def ui_watcher_start():
    try:
        r = requests.post(f"{BOT_API}/watcher/start", timeout=5)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/ui/watcher/stop")
def ui_watcher_stop():
    try:
        r = requests.post(f"{BOT_API}/watcher/stop", timeout=5)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── HISTORY ───────────────────────────────────────────────────────────────────

@router.get("/ui/history")
def ui_history(request: Request, show_id: str = ""):
    ctx               = _base_ctx("history", request)
    ctx["past_shows"] = _list_past_shows()

    if show_id:
        db_path = REPO_ROOT / "DB" / "shows" / show_id / "show.db"
        if db_path.exists():
            from Core.db import ensure_db
            ensure_db(db_path)
            raw_items = list_inventory(db_path)
            for item in raw_items:
                code   = item["item_code"]
                rating = "nsfw" if code.startswith("N") else "sfw"
                media  = get_media(db_path, code, "watermarked", rating)
                item["preview_url"] = media["attachment_url"] if media else None
            claims = list_claims(db_path, include_removed=True)
            with db_session(db_path) as conn:
                rows  = conn.execute("SELECT id, kind, discord_user_id, display_name FROM users ORDER BY id ASC").fetchall()
                users = [dict(r) | {"balance": get_balance(db_path, r["id"])} for r in rows]
            ctx.update({"items": raw_items, "claims": claims, "users": users})
        ctx["selected_show"] = show_id

    return templates.TemplateResponse("index.html", ctx)


# ── CONSOLE ───────────────────────────────────────────────────────────────────

@router.get("/ui/console")
def ui_console(request: Request):
    ctx    = _base_ctx("console", request)
    active = shows.get_active()
    if active:
        # Pass users + items so the Jinja fallback in autocomplete works
        try:
            with db_session(active.db_path) as conn:
                rows = conn.execute(
                    "SELECT id, display_name FROM users ORDER BY display_name ASC"
                ).fetchall()
            ctx["users"] = [{"id": r["id"], "display_name": r["display_name"]} for r in rows]
        except Exception:
            pass
        try:
            ctx["items"] = list_inventory(active.db_path)
        except Exception:
            pass
    return templates.TemplateResponse("index.html", ctx)


@router.get("/ui/console/context")
def ui_console_context():
    """
    JSON endpoint — returns member display names + available item codes
    for the console autocomplete. Members come from the bot's live cache
    so names are available before anyone has interacted with the bot.
    """
    # Get names from bot member cache (all server members)
    try:
        r = requests.get(f"{BOT_API}/members", timeout=5)
        data = r.json()
        verified   = [m["display_name"] for m in data.get("verified",   []) if m.get("display_name")]
        unverified = [m["display_name"] for m in data.get("unverified", []) if m.get("display_name")]
        names = sorted(set(verified + unverified), key=str.lower)
    except Exception:
        names = []

    # Get item codes from active show DB
    active = shows.get_active()
    codes  = []
    if active:
        try:
            items = list_inventory(active.db_path)
            codes = [i["item_code"] for i in items if i["status"] not in ("removed", "claimed_removed")]
        except Exception:
            pass

    return {"ok": True, "users": names, "codes": codes}


@router.post("/ui/console/run")
async def ui_console_run(command: str = Form(...)):
    cmd   = command.strip()
    parts = cmd.split()
    if not parts:
        return {"ok": False, "message": "Empty command"}

    verb   = parts[0].lower()
    active = shows.get_active()

    try:
        # award <name_or_id> <amount>
        if verb == "award" and len(parts) >= 3:
            name_or_id = parts[1].strip('"')
            amt        = int(parts[2])
            note       = " ".join(parts[3:]).strip('"') if len(parts) > 3 else "Console award"
            if not active:
                return {"ok": False, "message": "No active show"}
            uid = int(name_or_id) if name_or_id.isdigit() else None
            if uid is None:
                # Always look up from member cache first so we get the Discord ID
                # This prevents awarding to a pending/phantom user instead of the real Discord user
                try:
                    r           = requests.get(f"{BOT_API}/members", timeout=5)
                    data        = r.json()
                    all_members = data.get("verified", []) + data.get("unverified", [])
                    matched     = next(
                        (m for m in all_members if m.get("display_name", "").lower() == name_or_id.lower()),
                        None
                    )
                except Exception:
                    matched = None

                if matched:
                    # Upsert by Discord ID — always prefer discord-linked record
                    discord_id   = matched.get("discord_id")
                    display_name = matched.get("display_name", name_or_id)
                    with db_session(active.db_path) as conn:
                        existing = conn.execute(
                            "SELECT id FROM users WHERE discord_user_id = ?", (discord_id,)
                        ).fetchone()
                        if existing:
                            uid = existing["id"]
                        else:
                            cur = conn.execute(
                                "INSERT INTO users (kind, discord_user_id, display_name, normalized_name, created_at) "
                                "VALUES ('discord', ?, ?, ?, datetime('now'))",
                                (discord_id, display_name, normalize_name(display_name)),
                            )
                            uid = cur.lastrowid
                else:
                    # Not in server — fall back to DB name match
                    user = _resolve_user_by_name(active.db_path, name_or_id)
                    if not user:
                        return {"ok": False, "message": f"User '{name_or_id}' not found in server or DB"}
                    uid = user["id"]
            for _ in range(amt):
                award_voucher(active.db_path, user_id=uid, reason="STAFF_ADJUST", note=note)
            bal = get_balance(active.db_path, uid)
            note_suffix = f" [{note}]" if note and note != "Console award" else ""
            return {"ok": True, "message": f"Awarded {amt} credit(s) to {name_or_id}{note_suffix}. Balance: {bal}"}

        # award_discord <discord_id> <amount>
        elif verb == "award_discord" and len(parts) >= 3:
            discord_id = parts[1]
            amt        = int(parts[2])
            if not active:
                return {"ok": False, "message": "No active show"}
            user = _resolve_user_by_discord_id(active.db_path, discord_id)
            if not user:
                return {"ok": False, "message": f"Discord user {discord_id} not found in DB"}
            uid = user["id"]
            for _ in range(amt):
                award_voucher(active.db_path, user_id=uid, reason="STAFF_ADJUST", note="Console award_discord")
            return {"ok": True, "message": f"Awarded {amt} credit(s) to {user['display_name']}. Balance: {get_balance(active.db_path, uid)}"}

        # add_guest <name> [amount]
        elif verb == "add_guest" and len(parts) >= 2:
            if parts[1].startswith('"'):
                joined = " ".join(parts[1:])
                end    = joined.find('"', 1)
                name   = joined[1:end] if end > 0 else joined[1:]
                amt    = int(parts[len(name.split()) + 1]) if len(parts) > len(name.split()) + 1 and parts[len(name.split()) + 1].isdigit() else 0
            else:
                name = parts[1]
                amt  = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 0
            if not active:
                return {"ok": False, "message": "No active show"}
            existing = _resolve_user_by_name(active.db_path, name)
            if existing:
                uid = existing["id"]
                msg = f"User '{name}' already exists (#{uid})"
            else:
                with db_session(active.db_path) as conn:
                    cur = conn.execute(
                        "INSERT INTO users (kind, discord_user_id, display_name, normalized_name, created_at) VALUES ('pending', NULL, ?, ?, datetime('now'))",
                        (name, normalize_name(name)),
                    )
                    uid = cur.lastrowid
                msg = f"Guest '{name}' created (#{uid})"
            if amt > 0:
                for _ in range(amt):
                    award_voucher(active.db_path, user_id=uid, reason="STAFF_ADJUST", note="Guest credit — transfers on Discord join")
                msg += f". Awarded {amt} credit(s)."
            return {"ok": True, "message": msg}

        # balance <name_or_id>
        elif verb == "balance" and len(parts) >= 2:
            name_or_id = parts[1].strip('"')
            if not active:
                return {"ok": False, "message": "No active show"}
            if name_or_id.isdigit():
                uid  = int(name_or_id)
                name = f"user #{uid}"
            else:
                user = _resolve_user_by_name(active.db_path, name_or_id)
                if not user:
                    return {"ok": False, "message": f"User '{name_or_id}' not found"}
                uid, name = user["id"], user["display_name"]
            return {"ok": True, "message": f"{name} (#{uid}) — balance: {get_balance(active.db_path, uid)} credit(s)"}

        # remove_claim <code> [norefund]
        elif verb == "remove_claim" and len(parts) >= 2:
            code   = parts[1].upper()
            refund = not (len(parts) >= 3 and parts[2].lower() == "norefund")
            if not active:
                return {"ok": False, "message": "No active show"}
            remove_claim(active.db_path, item_code=code, refund=refund, reason="Console remove")
            return {"ok": True, "message": f"Claim on {code} removed. Refunded: {refund}"}

        # remove_item <code>
        elif verb == "remove_item" and len(parts) >= 2:
            if not active:
                return {"ok": False, "message": "No active show"}
            return remove_item(active.db_path, item_code=parts[1].upper())

        # publish <code>
        elif verb == "publish" and len(parts) >= 2:
            if not active:
                return {"ok": False, "message": "No active show"}
            return await asyncio.to_thread(publish_item, parts[1].upper(), active)

        # new_show <date> <name...>
        elif verb == "new_show" and len(parts) >= 3:
            ref = shows.create_new_show(parts[1], " ".join(parts[2:]))
            return {"ok": True, "message": f"Show created: {ref.show_id}"}

        # end_show
        elif verb == "end_show":
            if not active:
                return {"ok": False, "message": "No active show"}
            shows.clear_active()
            return {"ok": True, "message": f"Show ended: {active.show_id}"}

        else:
            return {"ok": False, "message": f"Unknown command: '{verb}'. Try: award, award_discord, add_guest, balance, remove_claim, remove_item, publish, new_show, end_show"}

    except ClaimError as e:
        return {"ok": False, "message": f"{e.code}: {e.message}"}
    except Exception as e:
        return {"ok": False, "message": str(e)}


# ── SETTINGS ──────────────────────────────────────────────────────────────────

@router.get("/ui/settings")
def ui_settings(request: Request):
    ctx        = _base_ctx("settings", request)
    ctx["env"] = _env()
    return templates.TemplateResponse("index.html", ctx)


@router.post("/ui/settings/save")
async def ui_settings_save(
    WATCHER_PARENT_DIR:      str = Form(""),
    WM_TEMPLATE_SFW:         str = Form(""),
    WM_TEMPLATE_NSFW:        str = Form(""),
    UPLOAD_THREAD_RAW_SFW:   str = Form(""),
    UPLOAD_THREAD_WM_SFW:    str = Form(""),
    UPLOAD_THREAD_RAW_NSFW:  str = Form(""),
    UPLOAD_THREAD_WM_NSFW:   str = Form(""),
    CATALOG_SFW_CHANNEL_ID:  str = Form(""),
    CATALOG_NSFW_CHANNEL_ID: str = Form(""),
    CLAIMS_SFW_CHANNEL_ID:   str = Form(""),
    CLAIMS_NSFW_CHANNEL_ID:  str = Form(""),
    WATCHER_POST_MODE:       str = Form(""),
):
    fields = {
        "WATCHER_PARENT_DIR": WATCHER_PARENT_DIR, "WM_TEMPLATE_SFW": WM_TEMPLATE_SFW,
        "WM_TEMPLATE_NSFW": WM_TEMPLATE_NSFW, "UPLOAD_THREAD_RAW_SFW": UPLOAD_THREAD_RAW_SFW,
        "UPLOAD_THREAD_WM_SFW": UPLOAD_THREAD_WM_SFW, "UPLOAD_THREAD_RAW_NSFW": UPLOAD_THREAD_RAW_NSFW,
        "UPLOAD_THREAD_WM_NSFW": UPLOAD_THREAD_WM_NSFW, "CATALOG_SFW_CHANNEL_ID": CATALOG_SFW_CHANNEL_ID,
        "CATALOG_NSFW_CHANNEL_ID": CATALOG_NSFW_CHANNEL_ID, "CLAIMS_SFW_CHANNEL_ID": CLAIMS_SFW_CHANNEL_ID,
        "CLAIMS_NSFW_CHANNEL_ID": CLAIMS_NSFW_CHANNEL_ID, "WATCHER_POST_MODE": WATCHER_POST_MODE,
    }
    for key, value in fields.items():
        if value.strip():
            set_key(str(ENV_PATH), key, value.strip())
    return {"ok": True}
