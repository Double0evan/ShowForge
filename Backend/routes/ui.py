from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.templating import Jinja2Templates

from Backend.services.publish_service import publish_item

from Core.inventory_service import list_inventory, remove_item
from Core.claim_service import list_claims, remove_claim, ClaimError
from Core.show_service import require_active_show
from Core.show_manager import ShowManager
from Core.media_service import get_media
from Core.voucher_service import get_balance, staff_adjust, award_voucher
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
BOT_API   = os.getenv("BOT_API_URL", "http://127.0.0.1:8001")
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
        except Exception as e:
            print(f"[UI] Could not read active show file: {e}")
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
        except Exception as e:
            print(f"[UI] Could not load show_type setting: {e}")
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

    try:
        from Core.bin_queue import clear_auction_log
        clear_auction_log()
    except Exception:
        pass

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
def ui_end_show():
    active = shows.get_active()
    if not active:
        return {"ok": False, "error": "No active show"}
    shows.clear_active()
    # Clear auction log on show end
    try:
        from Core.bin_queue import clear_auction_log
        clear_auction_log()
    except Exception:
        pass
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


# ── Bin Show Manager ─────────────────────────────────────────────────────────

@router.get("/ui/binshow")
def ui_binshow(request: Request):
    ctx = _base_ctx("binshow", request)
    active = shows.get_active()
    if active:
        items = list_inventory(active.db_path)
        ctx["items"] = {i["item_code"]: i for i in items}
    return templates.TemplateResponse("index.html", ctx)


@router.get("/ui/binshow/fuzzy")
def ui_binshow_fuzzy(whatnot_name: str):
    """Fuzzy match a Whatnot username against verified Discord members via bot API."""
    import requests as _req, re
    # Fetch members from bot API (port 8001) — backend has no direct Discord access
    try:
        r = _req.get(f"{BOT_API}/members", timeout=5)
        data = r.json()
        members = data.get("verified", []) + data.get("unverified", [])
    except Exception as e:
        return {"ok": False, "match": None, "score": 0, "error": str(e)}

    def _normalize(s):
        return re.sub(r"[^a-z0-9]", "", s.lower())

    def _similarity(a, b):
        if not a or not b: return 0.0
        if a == b: return 1.0
        m, n = len(a), len(b)
        dp = [[0]*(n+1) for _ in range(m+1)]
        for i in range(1, m+1):
            for j in range(1, n+1):
                dp[i][j] = dp[i-1][j-1]+1 if a[i-1]==b[j-1] else max(dp[i-1][j], dp[i][j-1])
        return dp[m][n] / max(m, n)

    target = _normalize(whatnot_name.strip())
    if not target:
        return {"ok": False, "match": None, "score": 0}

    try:
        import requests as _req2
        r2 = _req2.get(f"{BOT_API}/members", timeout=5)
        data2 = r2.json()
        members = data2.get("verified", []) + data2.get("unverified", [])
    except Exception as e2:
        return {"ok": False, "match": None, "score": 0, "error": str(e2)}
    best_name, best_id, best_score = None, None, 0.0

    for m in members:
        norm = _normalize(m["display_name"])
        if norm == target:
            return {"ok": True, "match": m["display_name"], "discord_id": m["discord_id"], "score": 1.0}
        score = _similarity(target, norm)
        # Suffix boost
        if len(target) >= 4 and norm.endswith(target):
            score = max(score, 0.88)
        parts = norm.split("_") if "_" in norm else []
        if parts and target in parts:
            score = max(score, 0.92)
        if score > best_score:
            best_score, best_name, best_id = score, m["display_name"], m["discord_id"]

    if best_score >= 0.75:
        return {"ok": True, "match": best_name, "discord_id": best_id, "score": round(best_score, 2)}
    return {"ok": False, "match": best_name, "discord_id": best_id, "score": round(best_score, 2)}


@router.get("/ui/binshow/log")
def ui_binshow_log():
    """Return the auction log in order."""
    from Core.bin_queue import get_auction_log
    return {"ok": True, "rows": get_auction_log()}


@router.delete("/ui/binshow/log/{auction_id}")
def ui_binshow_log_delete(auction_id: int, remove_claim: bool = False, refund: bool = False):
    """
    Remove a row from the auction log.
    remove_claim=true: also removes the claim on the associated item (no refund for bin shows).
    """
    from Core.bin_queue import delete_auction_log_entry, restamp_auction_claim_numbers, get_auction_entry
    active = require_active_show()

    claim_removed = False
    claim_error   = None

    if remove_claim:
        row = get_auction_entry(auction_id)
        if row and row.get("card_number") and row.get("claimed"):
            item_code = f"N{int(row['card_number']):03d}"
            try:
                from Core.claim_service import remove_claim as rc
                rc(active.db_path, item_code, refund=False, reason="Bin log row deleted")
                claim_removed = True
            except Exception as e:
                claim_error = str(e)

    deleted = delete_auction_log_entry(auction_id)
    if deleted:
        restamp_auction_claim_numbers(active.db_path)

    return {"ok": True, "deleted": deleted, "claim_removed": claim_removed, "claim_error": claim_error}


@router.post("/ui/binshow/log/insert")
def ui_binshow_log_insert(after_id: int = Form(None)):
    """Insert a placeholder row (other sale / cancellation) after the given auction id."""
    from Core.bin_queue import insert_placeholder
    active = require_active_show()
    new_id = insert_placeholder(after_id=after_id, show_db_path=active.db_path)
    return {"ok": True, "inserted_id": new_id}


@router.post("/ui/binshow/log/{auction_id}/assign")
def ui_binshow_log_assign(
    auction_id: int,
    whatnot_name: str = Form(...),
    discord_name: str = Form(...),
    discord_id:   str = Form(""),
):
    """Assign a winner to an auction log entry and create the claim."""
    active       = require_active_show()
    whatnot_name = whatnot_name.strip()
    discord_name = discord_name.strip()

    # Get the card number for this auction
    from Core.bin_queue import get_auction_entry, update_auction_winner
    row = get_auction_entry(auction_id)

    if not row:
        return {"ok": False, "error": "Auction entry not found"}

    card_number = row["card_number"]
    auction_number = row["position"]
    item_code   = f"N{card_number:03d}"

    try:
        from Core.db import db_session
        from Core.normalize import normalize_name
        from Core.voucher_service import award_voucher
        from Core.claim_service import create_claim, ClaimError
        from datetime import datetime, timezone

        def _now():
            return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

        with db_session(active.db_path) as conn2:
            norm = normalize_name(discord_name)
            user_row = None
            # Always try discord_id first — most reliable
            if discord_id:
                user_row = conn2.execute(
                    "SELECT id FROM users WHERE discord_user_id = ? LIMIT 1", (str(discord_id),)
                ).fetchone()
            # Fall back to normalized name, prefer discord kind
            if not user_row:
                user_row = conn2.execute(
                    "SELECT id FROM users WHERE normalized_name = ? AND kind = 'discord' LIMIT 1",
                    (norm,)
                ).fetchone()
            # Last resort — any kind
            if not user_row:
                user_row = conn2.execute(
                    "SELECT id FROM users WHERE normalized_name = ? LIMIT 1", (norm,)
                ).fetchone()
            if user_row:
                user_id = user_row["id"]
            else:
                # Create pending user — will merge when they verify
                cur2 = conn2.execute(
                    "INSERT INTO users (kind, discord_user_id, display_name, normalized_name, created_at) "
                    "VALUES ('pending', ?, ?, ?, datetime('now'))",
                    (discord_id or None, discord_name, norm),
                )
                user_id = cur2.lastrowid

            existing = conn2.execute(
                "SELECT status FROM inventory_items WHERE item_code = ?", (item_code,)
            ).fetchone()
            if not existing:
                now = _now()
                conn2.execute(
                    "INSERT INTO inventory_items (item_code, status, post_mode, created_at, updated_at) "
                    "VALUES (?, 'available', 'claim', ?, ?)",
                    (item_code, now, now),
                )
            elif existing["status"] not in ("available",):
                return {"ok": False, "error": f"{item_code} is already {existing['status']}"}

        award_voucher(active.db_path, user_id=user_id, reason="STAFF_ADJUST",
                      note=f"Bin auction #{auction_number} card {item_code}")
        create_claim(active.db_path, item_code=item_code, user_id=user_id,
                     source="bin", auction_number=str(auction_number))
        update_auction_winner(auction_id, whatnot_name, discord_name)

        # Ensure the user record has discord_user_id set
        if discord_id:
            with db_session(active.db_path) as conn4:
                conn4.execute(
                    "UPDATE users SET discord_user_id = ?, kind = 'discord' WHERE id = ? AND (discord_user_id IS NULL OR discord_user_id = '')",
                    (discord_id, user_id),
                )
        # Also stamp auction_number directly on the claim row
        from Core.db import db_session as _dbs3
        with _dbs3(active.db_path) as conn3:
            conn3.execute(
                "UPDATE claims SET auction_number = ? WHERE item_code = ? AND removed_at IS NULL",
                (str(auction_number), item_code),
            )

        # Open trade channel — search by name if no discord_id
        try:
            import requests as _req
            _open_id = discord_id
            if not _open_id:
                sr = _req.get(f"{BOT_API}/members/search",
                              params={"q": discord_name, "limit": 1}, timeout=5)
                results = sr.json().get("results", [])
                if results:
                    _open_id = str(results[0].get("id", ""))
            if _open_id:
                _req.post(f"{BOT_API}/trade/open_for_user",
                          params={"discord_user_id": _open_id}, timeout=10)
                print(f"[BINSHOW] Trade channel opened for discord_id={_open_id}")
            else:
                print(f"[BINSHOW] Could not find discord_id for {discord_name} — trade channel skipped")
        except Exception as e:
            print(f"[BINSHOW] Trade channel error: {e}")

        return {"ok": True, "item_code": item_code, "assigned_to": discord_name}

    except ClaimError as e:
        return {"ok": False, "error": e.message}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/ui/binshow/log/clear")
def ui_binshow_log_clear():
    from Core.bin_queue import clear_auction_log
    n = clear_auction_log()
    return {"ok": True, "cleared": n}


@router.get("/ui/binshow/preview")
def ui_binshow_preview(item_code: str):
    active = shows.get_active()
    if not active:
        return {"url": None}
    rating = "nsfw" if item_code.startswith("N") else "sfw"
    media  = get_media(active.db_path, item_code, "watermarked", rating)
    return {"url": media["attachment_url"] if media else None}


@router.get("/ui/binshow/state")
def ui_binshow_state():
    """Return current claims so page can restore state on reload."""
    active = shows.get_active()
    if not active:
        return {"rows": {}}
    from Core.claim_service import list_claims
    from Core.media_service import get_media as _get_media
    claims = list_claims(active.db_path, include_removed=False)
    rows = {}
    for c in claims:
        code = c["item_code"]
        if not code.startswith("N"):
            continue
        try:
            n = int(code[1:])
        except ValueError:
            continue
        rows[str(n)] = {
            "whatnot_name": c.get("user_display_name", ""),
            "discord_name": c.get("user_display_name", ""),
            "status": "done",
        }
    return {"rows": rows}


@router.post("/ui/binshow/submit")
async def ui_binshow_submit(
    auction_number: int = Form(...),
    whatnot_name:   str = Form(...),
    discord_name:   str = Form(...),
    discord_id:     str = Form(""),
):
    """
    Assign auction_number card to discord_name and publish to catalog.
    Creates user if not found. Works entirely without the bin queue.
    """
    active    = require_active_show()
    item_code = f"N{auction_number:03d}"
    discord_name = discord_name.strip()
    whatnot_name = whatnot_name.strip()

    try:
        from Core.db import db_session
        from Core.normalize import normalize_name
        from Core.voucher_service import award_voucher
        from Core.claim_service import create_claim, ClaimError
        from Core.show_settings_service import get_setting
        from datetime import datetime, timezone

        def _now():
            return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

        # Use discord_name if matched, otherwise fall back to whatnot_name as guest
        effective_name = discord_name if discord_name else whatnot_name

        # Find or create user — never blocks on missing match
        with db_session(active.db_path) as conn:
            norm = normalize_name(effective_name)
            row  = None
            if discord_id:
                row = conn.execute(
                    "SELECT id FROM users WHERE discord_user_id = ? LIMIT 1",
                    (str(discord_id),)
                ).fetchone()
            if not row:
                row = conn.execute(
                    "SELECT id FROM users WHERE normalized_name = ? AND kind IN ('discord','pending','guest') LIMIT 1",
                    (norm,)
                ).fetchone()
            if row:
                user_id = row["id"]
            else:
                # Create pending/guest user with Whatnot name — merges later when they verify
                cur = conn.execute(
                    "INSERT INTO users (kind, discord_user_id, display_name, normalized_name, created_at) "
                    "VALUES ('pending', NULL, ?, ?, datetime('now'))",
                    (effective_name, norm),
                )
                user_id = cur.lastrowid

            # Ensure inventory row
            existing = conn.execute(
                "SELECT item_code, status FROM inventory_items WHERE item_code = ?", (item_code,)
            ).fetchone()
            if not existing:
                now = _now()
                conn.execute(
                    "INSERT INTO inventory_items (item_code, status, post_mode, created_at, updated_at) "
                    "VALUES (?, 'available', 'claim', ?, ?)",
                    (item_code, now, now),
                )
            elif existing["status"] not in ("available",):
                return {"ok": False, "error": f"{item_code} is already {existing['status']}"}

        # Award voucher + claim
        award_voucher(active.db_path, user_id=user_id, reason="STAFF_ADJUST",
                      note=f"Bin show auction #{auction_number}")

        # Set auction_number on claim
        from Core.db import db_session as _dbs
        create_claim(active.db_path, item_code=item_code, user_id=user_id,
                     source="bin", auction_number=str(auction_number))

        # Card is already posted by host typing in Discord — just return success
        return {
            "ok": True,
            "item_code": item_code,
            "assigned_to": discord_name,
            "published": True,
        }

    except ClaimError as e:
        return {"ok": False, "error": e.message}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/ui/inventory/assign")
def ui_inventory_assign(item_code: str = Form(...), display_name: str = Form(...)):
    """Direct-assign an item to any user by display name. Creates user if needed."""
    active    = require_active_show()
    item_code = item_code.strip().upper()
    display_name = display_name.strip()
    if not display_name:
        return {"ok": False, "error": "Display name required"}
    try:
        from Core.db import db_session
        from Core.normalize import normalize_name
        from Core.voucher_service import award_voucher
        from Core.claim_service import create_claim, ClaimError
        from datetime import datetime, timezone

        def _now():
            return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

        with db_session(active.db_path) as conn:
            norm = normalize_name(display_name)
            row  = conn.execute(
                "SELECT id FROM users WHERE normalized_name = ? AND kind IN ('discord','pending','guest') LIMIT 1",
                (norm,)
            ).fetchone()
            if row:
                user_id = row["id"]
            else:
                cur = conn.execute(
                    "INSERT INTO users (kind, discord_user_id, display_name, normalized_name, created_at) "
                    "VALUES ('pending', NULL, ?, ?, datetime('now'))",
                    (display_name, norm),
                )
                user_id = cur.lastrowid

            existing = conn.execute(
                "SELECT item_code FROM inventory_items WHERE item_code = ?", (item_code,)
            ).fetchone()
            if not existing:
                now = _now()
                conn.execute(
                    "INSERT INTO inventory_items (item_code, status, post_mode, created_at, updated_at) "
                    "VALUES (?, 'available', 'claim', ?, ?)",
                    (item_code, now, now),
                )

        award_voucher(active.db_path, user_id=user_id, reason="STAFF_ADJUST", note=f"Direct assign {item_code}")
        create_claim(active.db_path, item_code=item_code, user_id=user_id, source="staff")
        return {"ok": True, "item_code": item_code, "assigned_to": display_name}

    except ClaimError as e:
        return {"ok": False, "error": e.message}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/ui/claims/set_auction")
def ui_claims_set_auction(item_code: str = Form(...), auction_number: str = Form(...)):
    """Update the auction_number on a claim — for correcting OCR misreads."""
    active = require_active_show()
    item_code = item_code.strip().upper()
    num = auction_number.strip() or None
    try:
        from Core.db import db_session
        with db_session(active.db_path) as conn:
            cur = conn.execute(
                "UPDATE claims SET auction_number = ? WHERE item_code = ? AND removed_at IS NULL",
                (num, item_code),
            )
            if cur.rowcount == 0:
                return {"ok": False, "error": f"No active claim found for {item_code}"}
        return {"ok": True, "item_code": item_code, "auction_number": num}
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

@router.post("/ui/history/delete")
def ui_history_delete(show_id: str = Form(...)):
    """Permanently delete a show and all its data."""
    import shutil
    shows_root = REPO_ROOT / "DB" / "shows"
    show_dir   = shows_root / show_id

    # Safety: don't delete active show
    active = shows.get_active()
    if active and active.show_id == show_id:
        return {"ok": False, "error": "Cannot delete the active show. End the show first."}

    if not show_dir.exists():
        return {"ok": False, "error": f"Show '{show_id}' not found."}

    try:
        shutil.rmtree(show_dir)
        return {"ok": True, "deleted": show_id}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/ui/history/download")
def ui_history_download(show_id: str, variant: str = "watermarked"):
    """
    Download a zip of images for a show.
    variant: 'watermarked', 'raw', or 'both'
    """
    import zipfile, io
    from fastapi.responses import StreamingResponse

    shows_root = REPO_ROOT / "DB" / "shows"
    show_dir   = shows_root / show_id

    if not show_dir.exists():
        from fastapi import HTTPException
        raise HTTPException(404, f"Show '{show_id}' not found")

    # Build zip in memory
    zip_buffer = io.BytesIO()
    count = 0

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # Look in show folder for images
        show_folder = REPO_ROOT.parent / "shows" / show_id if (REPO_ROOT.parent / "shows" / show_id).exists() else None

        # Also check WATCHER_PARENT_DIR/shows/show_id
        env = _env()
        parent = Path(env.get("WATCHER_PARENT_DIR", str(REPO_ROOT)))
        alt_folder = Path(parent) / "shows" / show_id

        folder = show_folder or (alt_folder if alt_folder.exists() else None)

        if folder and folder.exists():
            for rating in ("SFW", "NSFW"):
                for var in ("RAW", "Watermarked"):
                    if variant == "watermarked" and var == "RAW":
                        continue
                    if variant == "raw" and var == "Watermarked":
                        continue
                    img_dir = folder / rating / var
                    if not img_dir.exists():
                        continue
                    for img in sorted(img_dir.iterdir()):
                        if img.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                            arc_name = f"{rating}/{var}/{img.name}" if variant == "both" else img.name
                            zf.write(img, arc_name)
                            count += 1

    if count == 0:
        from fastapi import HTTPException
        raise HTTPException(404, "No images found for this show. Images may only exist on Discord CDN.")

    zip_buffer.seek(0)
    filename = f"{show_id}_{variant}.zip"
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
        except Exception as e:
            print(f"[UI] Console users load failed: {e}")
        try:
            ctx["items"] = list_inventory(active.db_path)
        except Exception as e:
            print(f"[UI] Console inventory load failed: {e}")
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
    except Exception as e:
        print(f"[UI] Console member context load failed: {e}")
        names = []

    # Get item codes from active show DB
    active = shows.get_active()
    codes  = []
    if active:
        try:
            items = list_inventory(active.db_path)
            codes = [i["item_code"] for i in items if i["status"] not in ("removed", "claimed_removed")]
        except Exception as e:
            print(f"[UI] Console item context load failed: {e}")

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
                except Exception as e:
                    print(f"[UI] Console member lookup failed: {e}")
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


@router.get("/ui/show/reset_claims")
@router.post("/ui/show/reset_claims")
def ui_show_reset_claims():
    """Wipe all claims, users, vouchers. Keep inventory and media intact."""
    active = require_active_show()
    try:
        with db_session(active.db_path) as conn:
            conn.execute("DELETE FROM claims")
            conn.execute("DELETE FROM voucher_ledger")
            conn.execute("DELETE FROM users")
            conn.execute("UPDATE inventory_items SET status = 'available'")
        # Clear auction log
        from Core.bin_queue import clear_auction_log
        clear_auction_log()
        return {"ok": True, "message": "Claims, users, vouchers wiped. Inventory reset to available."}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Server-side image upload ──────────────────────────────────────────────────

@router.post("/ui/upload")
async def ui_upload(
    rating: str = Form(...),
    files: list[UploadFile] = File(...),
):
    """
    Upload images directly from browser.
    Server watermarks and uploads to Discord — no local watcher needed.
    """
    import asyncio, io, shutil, tempfile
    from pathlib import Path as _Path
    from datetime import datetime as _dt, timezone as _tz

    active = require_active_show()
    rating = rating.lower().strip()
    if rating not in ("sfw", "nsfw"):
        return {"ok": False, "error": "Invalid rating"}

    env = _env()
    parent     = _Path(env.get("WATCHER_PARENT_DIR", "/home/v3bot"))
    template_p = _Path(env.get(f"WM_TEMPLATE_{'NSFW' if rating == 'nsfw' else 'SFW'}", f"/home/v3bot/templates/{rating}.png"))
    bot_api    = env.get("BOT_API_URL", BOT_API)

    # State DB for item code allocation
    from Watcher.watcher_service import StateDB, watermark, compress_image, upsert_media
    state_root = parent / "shows" / active.show_id / "_state"
    state_root.mkdir(parents=True, exist_ok=True)
    state = StateDB(state_root / "watcher.sqlite")

    results = []
    for file in files:
        try:
            ext      = _Path(file.filename).suffix.lower() or ".jpg"
            raw_data = await file.read()

            # Save to temp file
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(raw_data)
                tmp_path = _Path(tmp.name)

            # Allocate code — use filename number if it's a 3-digit number
            import re as _re
            _fname_stem = _Path(file.filename).stem
            _fname_match = _re.fullmatch(r'\d{3}', _fname_stem)
            if _fname_match:
                prefix = "S" if rating == "sfw" else "N"
                item_code = f"{prefix}{_fname_stem}"
                # Register this number in StateDB so sequential allocator skips past it
                state._force_code(rating, int(_fname_stem))
            else:
                item_code = state.allocate_code(rating)
            show_root = parent / "shows" / active.show_id
            raw_dir   = show_root / ("SFW" if rating == "sfw" else "NSFW") / "RAW"
            wm_dir    = show_root / ("SFW" if rating == "sfw" else "NSFW") / "Watermarked"
            raw_dir.mkdir(parents=True, exist_ok=True)
            wm_dir.mkdir(parents=True, exist_ok=True)

            raw_dst = raw_dir / f"{item_code}{ext}"
            wm_dst  = wm_dir  / f"{item_code}.jpg"

            shutil.copy2(tmp_path, raw_dst)
            tmp_path.unlink(missing_ok=True)

            compress_image(raw_dst)
            watermark(raw_dst, wm_dst, template_p)
            compress_image(wm_dst)

            # Upsert inventory
            from Core.inventory_service import next_inventory_code
            # item_code already allocated via StateDB — just insert it
            from Core.db import db_session
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            with db_session(active.db_path) as conn:
                existing = conn.execute("SELECT item_code FROM inventory_items WHERE item_code=?", (item_code,)).fetchone()
                if not existing:
                    conn.execute(
                        "INSERT INTO inventory_items (item_code, status, post_mode, created_at, updated_at) VALUES (?, 'available', 'claim', ?, ?)",
                        (item_code, now, now)
                    )

            # Upload RAW and WM to Discord via bot API
            import requests as _req

            def _upload_file(variant, path):
                thread_key = f"UPLOAD_THREAD_{'RAW' if variant == 'raw' else 'WM'}_{rating.upper()}"
                thread_id  = env.get(thread_key, "0").strip().strip("'").strip('"')
                r = _req.post(
                    f"{bot_api}/upload_media",
                    data={"item_code": item_code, "variant": variant, "rating": rating, "thread_id": thread_id},
                    files={"file": (path.name, open(path, "rb"))},
                    timeout=60,
                )
                result = r.json()
                # Backend registers media after bot returns URL (avoids deadlock)
                if result.get("ok") and result.get("attachment_url"):
                    from Core.media_service import upsert_media as _upsert_media
                    _upsert_media(
                        active.db_path,
                        item_code=item_code,
                        variant=variant,
                        rating=rating,
                        source_channel_id=thread_id,
                        source_message_id=str(result.get("message_id", "")),
                        attachment_url=result["attachment_url"],
                        filename=result.get("filename", path.name),
                        content_type=result.get("content_type", ""),
                    )
                return result

            raw_result = _upload_file("raw", raw_dst)
            wm_result  = _upload_file("watermarked", wm_dst)

            results.append({"ok": True, "item_code": item_code, "raw": raw_result, "wm": wm_result})

        except Exception as e:
            results.append({"ok": False, "error": str(e), "file": file.filename})

    return {"ok": True, "results": results}
