"""
Discord/bot.py
"""

from __future__ import annotations

import io
import os
import threading
from pathlib import Path

import discord
import requests
import uvicorn
from discord import app_commands
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from Discord.bot_instance import client
from Discord.core_client import CoreClient
from Discord.ui_components import build_claim_view
import Discord.member_cache as member_cache

# Load .env from the Discord folder, regardless of working directory
_ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH, override=True)


# ── Env ───────────────────────────────────────────────────────────────────────

def get_int_env(name: str, default: int | None = None) -> int:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        if default is None:
            raise RuntimeError(f"Missing required env var: {name}")
        return default
    return int(v.strip())

TOKEN                   = os.getenv("DISCORD_TOKEN", "")
GUILD_ID                = get_int_env("GUILD_ID", 0)
BACKEND_BASE_URL        = os.getenv("BACKEND_URL") or os.getenv("BACKEND_BASE_URL") or "http://127.0.0.1:8000"
CATALOG_SFW_CHANNEL_ID  = get_int_env("CATALOG_SFW_CHANNEL_ID")
CATALOG_NSFW_CHANNEL_ID = get_int_env("CATALOG_NSFW_CHANNEL_ID")
CLAIMS_SFW_CHANNEL_ID   = get_int_env("CLAIMS_SFW_CHANNEL_ID", 0)
CLAIMS_NSFW_CHANNEL_ID  = get_int_env("CLAIMS_NSFW_CHANNEL_ID", 0)
VERIFY_CHANNEL_ID       = get_int_env("VERIFY_CHANNEL_ID", 0)
VERIFIED_ROLE_ID        = get_int_env("VERIFIED_ROLE_ID", 0)
UPLOAD_THREAD_RAW_SFW   = get_int_env("UPLOAD_THREAD_RAW_SFW")
UPLOAD_THREAD_WM_SFW    = get_int_env("UPLOAD_THREAD_WM_SFW")
UPLOAD_THREAD_RAW_NSFW  = get_int_env("UPLOAD_THREAD_RAW_NSFW")
UPLOAD_THREAD_WM_NSFW   = get_int_env("UPLOAD_THREAD_WM_NSFW")
CLAIM_BOT_COMMANDS_CHANNEL_ID = get_int_env("CLAIM_BOT_COMMANDS_CHANNEL_ID", 0)
TRADE_CATEGORY_ID             = get_int_env("TRADE_CATEGORY_ID", 0)
TRADE_ANNOUNCE_CHANNEL_ID     = get_int_env("TRADE_ANNOUNCE_CHANNEL_ID", 0)
TRADE_LOG_CHANNEL_ID          = get_int_env("TRADE_LOG_CHANNEL_ID", 0)


# ── Helpers ───────────────────────────────────────────────────────────────────

def catalog_channel_id_for(rating: str) -> int:
    return CATALOG_NSFW_CHANNEL_ID if rating.strip().lower() == "nsfw" else CATALOG_SFW_CHANNEL_ID

def upload_thread_id_for(rating: str, variant: str) -> int:
    rating, variant = rating.lower(), variant.lower()
    if rating == "sfw"  and variant == "raw":         return UPLOAD_THREAD_RAW_SFW
    if rating == "sfw"  and variant == "watermarked": return UPLOAD_THREAD_WM_SFW
    if rating == "nsfw" and variant == "raw":         return UPLOAD_THREAD_RAW_NSFW
    return UPLOAD_THREAD_WM_NSFW

def has_verified_role(member: discord.Member) -> bool:
    if VERIFIED_ROLE_ID == 0:
        return True
    return any(r.id == VERIFIED_ROLE_ID for r in member.roles)

def verify_instructions() -> str:
    if VERIFY_CHANNEL_ID:
        return f"Please verify in <#{VERIFY_CHANNEL_ID}> and try again."
    return "Please verify in the server and try again."

def infer_rating_from_catalog_channel(channel_id: int) -> str:
    return "nsfw" if channel_id == CATALOG_NSFW_CHANNEL_ID else "sfw"

def extract_item_code(custom_id: str) -> str | None:
    if not custom_id or not custom_id.startswith("claim:"):
        return None
    return custom_id.split("claim:", 1)[1].strip().upper() or None


# ── Core / intents ────────────────────────────────────────────────────────────

core = CoreClient(BACKEND_BASE_URL)
member_cache.init(VERIFIED_ROLE_ID)

intents         = discord.Intents.default()
intents.members = True
tree            = app_commands.CommandTree(client)


# ── Guest merge ───────────────────────────────────────────────────────────────

def _try_merge_guest(member: discord.Member) -> None:
    try:
        r = requests.get(
            f"{BACKEND_BASE_URL}/users/find_pending",
            params={"display_name": member.display_name},
            timeout=8,
        )
        if r.status_code != 200:
            return
        data = r.json()
        if not data.get("found"):
            return

        pending_id          = data["user_id"]
        balance             = data.get("balance", 0)
        discord_internal_id = core.upsert_discord_user(member.id, member.display_name)

        if balance > 0:
            requests.post(
                f"{BACKEND_BASE_URL}/users/transfer_credits",
                params={"from_user_id": pending_id, "to_user_id": discord_internal_id, "amount": balance},
                timeout=8,
            )
            print(f"[MERGE] {balance} credits: pending#{pending_id} → discord#{discord_internal_id} ({member.display_name})")
        else:
            print(f"[MERGE] Linked pending#{pending_id} → discord#{discord_internal_id} ({member.display_name})")

    except Exception as e:
        print(f"[MERGE] Error for {member.display_name}: {e}")


# ── Member events ─────────────────────────────────────────────────────────────

@client.event
async def on_member_join(member: discord.Member):
    member_cache.upsert_member(member)
    print(f"[MEMBER] Joined: {member.display_name}")
    _try_merge_guest(member)


@client.event
async def on_member_remove(member: discord.Member):
    member_cache.remove_member(member.id)
    print(f"[MEMBER] Left: {member.display_name}")


@client.event
async def on_member_update(before: discord.Member, after: discord.Member):
    member_cache.upsert_member(after)
    before_verified = has_verified_role(before)
    after_verified  = has_verified_role(after)
    if not before_verified and after_verified:
        print(f"[MEMBER] Verified: {after.display_name}")
        _try_merge_guest(after)
    if before.display_name != after.display_name:
        try:
            core.upsert_discord_user(after.id, after.display_name)
        except Exception:
            pass


# ── Claim helpers ─────────────────────────────────────────────────────────────

async def get_claims_thread(interaction: discord.Interaction, rating: str) -> discord.Thread | None:
    if not interaction.guild:
        return None
    key = "claims_thread_nsfw" if rating == "nsfw" else "claims_thread_sfw"
    try:
        thread_id = core.get_show_setting(key)
    except Exception:
        return None
    if not thread_id:
        return None
    try:
        ch = await interaction.guild.fetch_channel(int(thread_id))
        return ch if isinstance(ch, discord.Thread) else None
    except Exception:
        return None


async def post_raw_to_thread(thread, *, item_code, claimer_name, raw_url, filename, voucher_note=None):
    resp  = requests.get(raw_url, timeout=25)
    resp.raise_for_status()
    fn    = filename or f"{item_code}.jpg"
    file  = discord.File(fp=io.BytesIO(resp.content), filename=fn)
    lines = [claimer_name]
    if voucher_note:
        lines.append(voucher_note)
    embed = discord.Embed(title=item_code, description="\n".join(lines))
    embed.set_image(url=f"attachment://{fn}")
    await thread.send(embed=embed, file=file)


# ── Interaction handler (claim buttons) ───────────────────────────────────────

@client.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return

    data      = interaction.data or {}
    custom_id = data.get("custom_id")
    item_code = extract_item_code(custom_id)
    if not item_code:
        return

    await interaction.response.defer(ephemeral=True)

    # Block button claims during bin shows
    try:
        from Core.show_service import require_active_show
        from Core.show_settings_service import get_setting
        _active = require_active_show()
        if get_setting(_active.db_path, "show_mode") == "bin":
            await interaction.followup.send(
                "🎯 This is a bin show — items are claimed via Whatnot auction. "
                "Win the auction on Whatnot to claim this item.",
                ephemeral=True,
            )
            return
    except Exception:
        pass  # no active show or setting missing — allow normal flow

    if not interaction.guild:
        await interaction.followup.send("This can only be used in the server.", ephemeral=True)
        return

    member = interaction.guild.get_member(interaction.user.id)
    if not member:
        await interaction.followup.send("Could not load your member profile.", ephemeral=True)
        return

    if not has_verified_role(member):
        msg = verify_instructions()
        await interaction.followup.send(msg, ephemeral=True)
        try:
            await interaction.user.send(msg)
        except Exception:
            pass
        return

    display_name = member.display_name

    try:
        internal_user_id = core.upsert_discord_user(interaction.user.id, display_name)
    except Exception:
        await interaction.followup.send("Backend error registering your user.", ephemeral=True)
        return

    try:
        result = core.attempt_claim(item_code, internal_user_id)
    except Exception:
        await interaction.followup.send("Backend error attempting claim.", ephemeral=True)
        return

    if result.get("ok") is True:
        rating = infer_rating_from_catalog_channel(interaction.channel_id)
        thread = await get_claims_thread(interaction, rating)
        raw    = None
        try:
            raw = core.get_media(item_code=item_code, variant="raw", rating=rating)
        except Exception:
            pass
        if thread and raw and raw.get("attachment_url"):
            try:
                # Fetch the voucher note so we can show which credit was spent
                voucher_note = None
                try:
                    vr = requests.get(
                        f"{BACKEND_BASE_URL}/vouchers/ledger",
                        params={"user_id": internal_user_id},
                        timeout=5,
                    )
                    rows = vr.json().get("rows", [])
                    # Find the most recent spend row (-1 delta) with a note
                    spend = next((r for r in reversed(rows) if r.get("delta") == -1 and r.get("note")), None)
                    if spend:
                        voucher_note = spend["note"]
                except Exception:
                    pass
                await post_raw_to_thread(
                    thread, item_code=item_code, claimer_name=display_name,
                    raw_url=raw["attachment_url"], filename=raw.get("filename"),
                    voucher_note=voucher_note,
                )
            except Exception:
                pass
        try:
            await interaction.message.delete()
        except Exception:
            pass

        # Open/refresh trade channel for this user
        if TRADE_CATEGORY_ID and interaction.guild:
            try:
                from Trade.trade_hook import on_item_assigned_trade
                from Core.show_service import require_active_show
                active = require_active_show()
                await on_item_assigned_trade(
                    active.db_path, interaction.guild, member,
                    TRADE_CATEGORY_ID, TRADE_ANNOUNCE_CHANNEL_ID or None,
                )
            except Exception as e:
                print(f"[TRADE] on_item_assigned_trade error: {e}")

        await interaction.followup.send(f"✅ Claimed {item_code}", ephemeral=True)
        return

    code     = result.get("code", "ERROR")
    messages = {
        "NO_VOUCHER":      "❌ You don't have any claim credits right now.",
        "ALREADY_CLAIMED": "❌ That item was already claimed.",
        "ITEM_REMOVED":    "❌ That item is no longer available.",
        "ITEM_NOT_FOUND":  "❌ That item code doesn't exist.",
    }
    await interaction.followup.send(messages.get(code, result.get("message", "Claim failed.")), ephemeral=True)


# ── Staff commands ────────────────────────────────────────────────────────────

from Discord.commands import register_all
register_all(
    tree=tree, core=core,
    upload_thread_id_for=upload_thread_id_for,
    build_claim_view=build_claim_view,
    catalog_channel_id_for=catalog_channel_id_for,
)


# ── Bot internal API (port 8001) ──────────────────────────────────────────────

app = FastAPI(title="V3 Bot Internal API")
_discord_loop = None  # Set in on_ready once Discord connects


@app.get("/members")
def api_members():
    return {
        "ok":         True,
        "verified":   member_cache.get_verified(),
        "unverified": member_cache.get_unverified(),
        "counts":     member_cache.count(),
    }


@app.get("/members/search")
def api_members_search(q: str = "", limit: int = 10):
    return {"ok": True, "query": q, "results": member_cache.search(q, limit=limit)}


@app.get("/members/count")
def api_members_count():
    return {"ok": True, **member_cache.count()}


@app.post("/members/add_guest")
def api_add_guest(payload: dict):
    display_name = (payload.get("display_name") or "").strip()
    discord_id   = payload.get("discord_id")
    kind         = payload.get("kind", "guest")
    note         = payload.get("note", "")

    if not display_name:
        return JSONResponse({"ok": False, "error": "display_name required"}, status_code=400)

    try:
        if discord_id:
            internal_id = core.upsert_discord_user(int(discord_id), display_name)
        else:
            internal_id = core.upsert_guest_user(display_name, kind=kind, note=note)
        return {"ok": True, "user_id": internal_id, "display_name": display_name}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.post("/new_show")
def api_new_show(payload: dict):
    """
    Called by the UI when a new show is created.
    Sync function — runs in threadpool so run_coroutine_threadsafe works correctly.
    """
    import asyncio
    from datetime import datetime

    show_id = payload.get("show_id", "")
    date    = payload.get("date", datetime.now().strftime("%Y-%m-%d"))
    name    = payload.get("name", "Show")

    if not GUILD_ID:
        return JSONResponse({"ok": False, "error": "GUILD_ID not set"}, status_code=400)
    if not _discord_loop:
        return JSONResponse({"ok": False, "error": "Discord not ready yet"}, status_code=503)

    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
        thread_name = f"{dt.month}-{dt.day}-{dt.year}"
    except Exception:
        thread_name = date

    async def _create_threads():
        guild = client.get_guild(GUILD_ID) or await client.fetch_guild(GUILD_ID)
        sfw_parent  = guild.get_channel(CLAIMS_SFW_CHANNEL_ID)
        nsfw_parent = guild.get_channel(CLAIMS_NSFW_CHANNEL_ID)
        if not sfw_parent or not nsfw_parent:
            raise ValueError("Claims channels not found — check CLAIMS_SFW/NSFW_CHANNEL_ID in .env")
        sfw_thread = await sfw_parent.create_thread(
            name=thread_name, type=discord.ChannelType.public_thread, auto_archive_duration=10080,
        )
        nsfw_thread = await nsfw_parent.create_thread(
            name=thread_name, type=discord.ChannelType.public_thread, auto_archive_duration=10080,
        )
        await sfw_thread.send(f"🗂️ **Show Archive:** `{show_id}` (SFW claims)")
        await nsfw_thread.send(f"🗂️ **Show Archive:** `{show_id}` (NSFW claims)")

        # Create trade log thread if channel is configured
        trade_log_thread_id = None
        if TRADE_LOG_CHANNEL_ID:
            try:
                log_channel = guild.get_channel(TRADE_LOG_CHANNEL_ID) or await guild.fetch_channel(TRADE_LOG_CHANNEL_ID)
                trade_log_thread = await log_channel.create_thread(
                    name=thread_name,
                    type=discord.ChannelType.public_thread,
                    auto_archive_duration=10080,
                )
                await trade_log_thread.send(
                    f"📝 **Trade Log — {thread_name}**\n`{show_id}`\n\nAll accepted trades will be logged here."
                )
                trade_log_thread_id = trade_log_thread.id
            except Exception as e:
                print(f"[NEW_SHOW] Could not create trade log thread: {e}")

        return sfw_thread.id, nsfw_thread.id, trade_log_thread_id

    future = asyncio.run_coroutine_threadsafe(_create_threads(), _discord_loop)
    try:
        sfw_id, nsfw_id, trade_log_id = future.result(timeout=25)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    # Save thread IDs directly to the show DB
    try:
        from Core.show_service import require_active_show
        from Core.show_settings_service import set_setting
        active = require_active_show()
        set_setting(active.db_path, "claims_thread_sfw",  str(sfw_id))
        set_setting(active.db_path, "claims_thread_nsfw", str(nsfw_id))
        if trade_log_id:
            set_setting(active.db_path, "trade_log_thread_id", str(trade_log_id))
    except Exception as e:
        try:
            requests.post(f"{BACKEND_BASE_URL}/shows/settings/set",
                          params={"key": "claims_thread_sfw",  "value": str(sfw_id)}, timeout=10)
            requests.post(f"{BACKEND_BASE_URL}/shows/settings/set",
                          params={"key": "claims_thread_nsfw", "value": str(nsfw_id)}, timeout=10)
            if trade_log_id:
                requests.post(f"{BACKEND_BASE_URL}/shows/settings/set",
                              params={"key": "trade_log_thread_id", "value": str(trade_log_id)}, timeout=10)
        except Exception as e2:
            return JSONResponse({"ok": False, "error": f"Threads created but settings save failed: {e2}"}, status_code=500)

    return {"ok": True, "thread_name": thread_name, "sfw_thread_id": sfw_id, "nsfw_thread_id": nsfw_id, "trade_log_thread_id": trade_log_id}


# ── Watcher control endpoints ────────────────────────────────────────────────
# Controls the watcher via a flag file that the watcher polls every 3 seconds.
# Flag file location: logs/watcher_process.flag (contains "1" or "0")

_WATCHER_FLAG = Path(__file__).resolve().parent.parent / "logs" / "watcher_process.flag"

def _flag_enabled() -> bool:
    try:
        return _WATCHER_FLAG.exists() and _WATCHER_FLAG.read_text().strip() == "1"
    except Exception:
        return False

def _set_flag(enabled: bool):
    _WATCHER_FLAG.parent.mkdir(parents=True, exist_ok=True)
    _WATCHER_FLAG.write_text("1" if enabled else "0")

@app.get("/watcher/status")
def api_watcher_status():
    from Watcher.watcher_logger import is_alive
    return {
        "ok":         True,
        "running":    is_alive(),
        "processing": _flag_enabled(),
    }

@app.post("/watcher/start")
def api_watcher_start():
    """Enable watcher processing — watcher will pick up files from inbox."""
    _set_flag(True)
    return {"ok": True, "message": "Processing enabled — watcher will pick up inbox files"}

@app.post("/watcher/stop")
def api_watcher_stop():
    """Pause watcher processing — files stay in inbox until started again."""
    _set_flag(False)
    return {"ok": True, "message": "Processing paused"}


@app.post("/publish")
def api_publish(item_code: str, post_mode: str = "claim"):
    import asyncio
    from dotenv import dotenv_values
    rating     = "nsfw" if item_code.startswith("N") else "sfw"
    post_mode  = post_mode if post_mode in ("claim", "display") else "claim"

    # Re-read channel ID from .env each time so it works even if env wasn't
    # set when the process started
    env_vals   = dotenv_values(_ENV_PATH)
    env_key    = "CATALOG_NSFW_CHANNEL_ID" if rating == "nsfw" else "CATALOG_SFW_CHANNEL_ID"
    raw        = (env_vals.get(env_key) or os.getenv(env_key, "0") or "0").strip().strip("'" ).strip('"')
    channel_id = int(raw) if raw.isdigit() else 0
    print(f"[PUBLISH] {item_code} rating={rating} channel_id={channel_id}")

    if not channel_id:
        return {"ok": False, "error": f"{env_key} not configured"}

    try:
        wm = core.get_media(item_code=item_code, variant="watermarked", rating=rating)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    if not wm or not wm.get("attachment_url"):
        return {"ok": False, "error": "No watermarked media found for this item"}

    channel = client.get_channel(channel_id)

    async def send_message():
        nonlocal channel
        if channel is None:
            channel = await client.fetch_channel(channel_id)

        embed = discord.Embed(title=item_code, color=0x2b2d31)
        embed.set_image(url=wm["attachment_url"])

        if post_mode == "display":
            return await channel.send(embed=embed)
        else:
            return await channel.send(embed=embed, view=build_claim_view(item_code))

    future = asyncio.run_coroutine_threadsafe(send_message(), _discord_loop)
    try:
        msg = future.result(timeout=15)
    except Exception as e:
        print(f"[PUBLISH] ERROR: {e}")
        return {"ok": False, "error": str(e)}
    print(f"[PUBLISH] OK message_id={msg.id}")
    return {"ok": True, "message_id": msg.id}


# ── on_ready ──────────────────────────────────────────────────────────────────

@app.post("/claims/summary")
def api_claims_summary(payload: dict):
    """
    Delete all messages in the claims archival thread for the given rating,
    then post a sorted summary grouped by user with one message per claim.
    Sync endpoint — runs in threadpool so run_coroutine_threadsafe works.
    """
    import asyncio
    from Core.show_service import require_active_show
    from Core.claim_service import list_claims
    from Core.media_service import get_media

    rating = (payload.get("rating") or "nsfw").lower()

    if not _discord_loop:
        return JSONResponse({"ok": False, "error": "Discord not ready"}, status_code=503)

    # Get thread ID from show settings
    try:
        from Core.show_settings_service import get_setting
        active     = require_active_show()
        thread_key = "claims_thread_nsfw" if rating == "nsfw" else "claims_thread_sfw"
        thread_id  = get_setting(active.db_path, thread_key)
        if not thread_id:
            return {"ok": False, "error": f"No {rating.upper()} claims thread set — create a new show first"}
        thread_id = int(thread_id)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    # Fetch and group claims by user
    try:
        claims = list_claims(active.db_path, include_removed=False)
        # Filter by rating prefix
        prefix  = "N" if rating == "nsfw" else "S"
        claims  = [c for c in claims if c["item_code"].startswith(prefix)]
        if not claims:
            return {"ok": False, "error": f"No active {rating.upper()} claims found"}

        # Sort: by user name then item code
        claims.sort(key=lambda c: (c["user_display_name"].lower(), c["item_code"]))

        # Attach media URLs
        for c in claims:
            media = get_media(active.db_path, c["item_code"], "raw", rating)
            c["raw_url"]  = media["attachment_url"] if media else None
            c["raw_name"] = media["filename"] if media else f"{c['item_code']}.jpg"
    except Exception as e:
        return {"ok": False, "error": str(e)}

    async def _post_summary():
        thread = client.get_channel(thread_id) or await client.fetch_channel(thread_id)

        # Unarchive if needed
        if getattr(thread, "archived", False):
            await thread.edit(archived=False)

        # Delete all existing messages
        async for msg in thread.history(limit=None):
            try:
                await msg.delete()
            except Exception:
                pass

        # Post header
        await thread.send(f"📋 **SHOW SUMMARY — {rating.upper()}**")

        # Group by user
        from itertools import groupby
        posted = 0
        for user_name, user_claims in groupby(claims, key=lambda c: c["user_display_name"]):
            user_claims = list(user_claims)
            # Post user header
            await thread.send(f"───── **{user_name}** ({len(user_claims)} claim{'s' if len(user_claims) != 1 else ''})")

            for c in user_claims:
                note    = c.get("voucher_note") or ""
                label   = f"{c['item_code']}" + (f" — {note}" if note else "")

                if c["raw_url"]:
                    # Download and re-upload RAW so it shows inline
                    try:
                        resp = requests.get(c["raw_url"], timeout=20)
                        resp.raise_for_status()
                        file  = discord.File(fp=io.BytesIO(resp.content), filename=c["raw_name"])
                        embed = discord.Embed(title=label, color=0x2b2d31)
                        embed.set_image(url=f"attachment://{c['raw_name']}")
                        await thread.send(embed=embed, file=file)
                    except Exception:
                        await thread.send(label)
                else:
                    await thread.send(label)

                posted += 1
                await asyncio.sleep(0.5)  # avoid rate limits

        return posted

    future = asyncio.run_coroutine_threadsafe(_post_summary(), _discord_loop)
    try:
        posted = future.result(timeout=300)  # 5 min timeout for large shows
    except Exception as e:
        return {"ok": False, "error": str(e)}

    # Post trade summary to trade log thread and archive it
    if TRADE_LOG_CHANNEL_ID:
        async def _post_trade_summary():
            try:
                from Core.show_settings_service import get_setting
                from Core.show_service import require_active_show
                from Trade.db.trade_db import ensure_trade_tables
                from Core.db import db_session as _db_session

                active = require_active_show()
                thread_id_str = get_setting(active.db_path, "trade_log_thread_id")
                if not thread_id_str:
                    return

                thread = client.get_channel(int(thread_id_str)) or await client.fetch_channel(int(thread_id_str))
                if not thread:
                    return
                if getattr(thread, "archived", False):
                    await thread.edit(archived=False)

                # Query all accepted trades for this show
                with _db_session(active.db_path) as conn:
                    ensure_trade_tables(conn)
                    rows = conn.execute("""
                        SELECT o.offer_id, o.sender_user_id, o.receiver_user_id, o.resolved_at,
                               GROUP_CONCAT(DISTINCT oc.item_code) AS offer_codes,
                               GROUP_CONCAT(DISTINCT rc.item_code) AS requested_codes
                        FROM trade_offers o
                        LEFT JOIN trade_offer_cards oc ON oc.offer_id = o.offer_id
                        LEFT JOIN trade_offer_requested_cards rc ON rc.offer_id = o.offer_id
                        WHERE o.status = 'accepted'
                        GROUP BY o.offer_id
                        ORDER BY o.resolved_at ASC
                    """).fetchall()

                guild = client.get_guild(GUILD_ID)
                if not rows:
                    await thread.send("📊 **Show ended — no trades were completed this show.**")
                else:
                    # Build auction number lookup
                    from Core.db import db_session as _dbs2
                    with _dbs2(active.db_path) as conn2:
                        auction_map = {}
                        for ar in conn2.execute("SELECT item_code, auction_number FROM claims WHERE removed_at IS NULL").fetchall():
                            if ar["auction_number"]:
                                auction_map[ar["item_code"]] = ar["auction_number"]

                    def _card_str(code):
                        num = auction_map.get(code)
                        return f"{code} #{num}" if num else code

                    lines = [f"📊 **Trade Summary — {len(rows)} trade{'s' if len(rows) != 1 else ''}**"]
                    for row in rows:
                        s_m = guild.get_member(int(row["sender_user_id"]))   if guild else None
                        r_m = guild.get_member(int(row["receiver_user_id"])) if guild else None
                        s_name = s_m.display_name if s_m else f"<@{row['sender_user_id']}>"
                        r_name = r_m.display_name if r_m else f"<@{row['receiver_user_id']}>"
                        offer_codes = row["offer_codes"].split(",")     if row["offer_codes"]     else []
                        req_codes   = row["requested_codes"].split(",") if row["requested_codes"] else []
                        s_cards = ", ".join(_card_str(c) for c in offer_codes)
                        r_cards = ", ".join(_card_str(c) for c in req_codes)
                        lines.append(f"{s_name} {s_cards}  <->  {r_name} {r_cards}")
                    await thread.send("\n".join(lines))

                # Archive the thread
                await thread.edit(archived=True)
                print(f"[TRADE LOG] Summary posted and thread archived")
            except Exception as e:
                print(f"[TRADE LOG] Summary error: {e}")

        asyncio.run_coroutine_threadsafe(_post_trade_summary(), _discord_loop)

    return {"ok": True, "posted": posted, "rating": rating}



@app.post("/bin/sale")
def api_bin_sale(payload: dict):
    """
    Called by the Whatnot screen watcher when a sale is detected.
    Pushes auction_number + username into the bin queue so the bot's
    on_message handler can match it when the host types a bin number.
    """
    auction_number = payload.get("auction_number")
    username       = payload.get("username", "").strip()
    if not auction_number or not username:
        return {"ok": False, "error": "auction_number and username required"}
    try:
        from Core.bin_queue import push_sale
        row_id = push_sale(int(auction_number), username)
        print(f"[BIN] Queued sale: auction #{auction_number} @{username} (id={row_id})")
        return {"ok": True, "id": row_id}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/bin/peek")
def api_bin_peek():
    """Returns the latest pending sale without consuming it."""
    from Core.bin_queue import peek_latest_sale
    sale = peek_latest_sale()
    return {"ok": True, "sale": sale}


@app.post("/bin/clear")
def api_bin_clear():
    """Clear all pending unmatched sales from the queue."""
    from Core.bin_queue import clear_queue
    n = clear_queue()
    return {"ok": True, "cleared": n}


@client.event
async def on_ready():
    try:
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            tree.copy_global_to(guild=guild)
            await tree.sync(guild=guild)
            print(f"✅ Commands synced to guild {GUILD_ID}")
        else:
            await tree.sync()
            print("✅ Commands synced globally")
    except Exception as e:
        print(f"❌ Command sync failed: {e}")

    if GUILD_ID:
        guild = client.get_guild(GUILD_ID)
        if guild:
            count = 0
            async for member in guild.fetch_members(limit=None):
                member_cache.upsert_member(member)
                count += 1
            print(f"✅ Member cache loaded: {count} members")

    print(f"Logged in as {client.user} | Backend: {BACKEND_BASE_URL}")

    # Store the Discord event loop so bot API endpoints can submit coroutines to it
    import asyncio
    global _discord_loop
    _discord_loop = asyncio.get_running_loop()

    # Register bin show listener
    from Discord.bin_listener import register_bin_listener
    register_bin_listener(client, core, bot_api_url="http://127.0.0.1:8001")
    print("✅ Bin listener registered")

    # Init trade system
    if TRADE_CATEGORY_ID:
        try:
            from Trade.trade_hook import register_trade_commands, init_trade_tables
            from Core.show_service import require_active_show
            try:
                active = require_active_show()
                init_trade_tables(active.db_path)
                register_trade_commands(
                    tree,
                    db_path=active.db_path,
                    trade_category_id=TRADE_CATEGORY_ID,
                    announce_channel_id=TRADE_ANNOUNCE_CHANNEL_ID or None,
                )
                print("✅ Trade system registered")
                
            except Exception:
                print("⚠️  Trade: no active show at startup — trade commands registered without DB (will init on first use)")
                register_trade_commands(
                    tree,
                    db_path=None,
                    trade_category_id=TRADE_CATEGORY_ID,
                    announce_channel_id=TRADE_ANNOUNCE_CHANNEL_ID or None,
                )
        except Exception as e:
            print(f"❌ Trade system failed to load: {e}")
    else:
        print("ℹ️  TRADE_CATEGORY_ID not set — trade system disabled")

    def run_api():
        uvicorn.run(app, host="127.0.0.1", port=8001, log_level="warning")

    threading.Thread(target=run_api, daemon=True).start()
    print("✅ Bot internal API on port 8001")


# ── Entry point ───────────────────────────────────────────────────────────────



@app.post("/trade/lock")
def api_trade_lock():
    """Lock trades for the active show (called on show end or manually)."""
    try:
        from Core.show_service import require_active_show
        from Core.show_settings_service import set_setting
        active = require_active_show()
        set_setting(active.db_path, "trade_locked", "1")
        return {"ok": True, "message": "Trades locked"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/trade/unlock")
def api_trade_unlock():
    """Unlock trades for the active show."""
    try:
        from Core.show_service import require_active_show
        from Core.show_settings_service import set_setting
        active = require_active_show()
        set_setting(active.db_path, "trade_locked", "0")
        return {"ok": True, "message": "Trades unlocked"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/trade/close_channels")
def api_trade_close_channels():
    """
    Delete all private trade channels for the active show.
    Runs async channel deletion via the Discord event loop.
    """
    import asyncio

    async def _close_all():
        try:
            from Core.show_service import require_active_show
            from Core.db import db_session
            active = require_active_show()

            if not TRADE_CATEGORY_ID:
                return {"ok": False, "error": "TRADE_CATEGORY_ID not set"}

            guild = client.guilds[0] if client.guilds else None
            if not guild:
                return {"ok": False, "error": "Bot not in any guild"}

            with db_session(active.db_path) as conn:
                rows = conn.execute(
                    "SELECT channel_id FROM trade_user_channels WHERE guild_id = ?",
                    (str(guild.id),),
                ).fetchall()

            closed = 0
            failed = 0
            for row in rows:
                ch_id = int(row["channel_id"])
                try:
                    ch = guild.get_channel(ch_id) or await guild.fetch_channel(ch_id)
                    if ch:
                        await ch.delete(reason="Show ended — trade channels closed")
                        closed += 1
                except Exception:
                    failed += 1

            # Clear channel records so new show starts fresh
            with db_session(active.db_path) as conn:
                conn.execute(
                    "DELETE FROM trade_user_channels WHERE guild_id = ?",
                    (str(guild.id),),
                )
                conn.execute(
                    "DELETE FROM trade_ui_messages WHERE guild_id = ?",
                    (str(guild.id),),
                )

            return {"ok": True, "closed": closed, "failed": failed}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    future = asyncio.run_coroutine_threadsafe(_close_all(), _discord_loop)
    return future.result(timeout=60)

@app.post("/trade/refresh_all")
def api_trade_refresh_all():
    """Kick off a background refresh of all trade channels. Returns immediately."""
    import asyncio

    async def _refresh_all():
        try:
            from Core.show_service import require_active_show
            from Core.db import db_session
            from Trade.services.trade_service import reset_trade_messages
            from Trade.db.trade_db import ensure_trade_tables

            active = require_active_show()
            guild  = client.guilds[0] if client.guilds else None
            if not guild:
                print("[REFRESH_ALL] No guild found")
                return

            with db_session(active.db_path) as conn:
                ensure_trade_tables(conn)
                rows = conn.execute(
                    "SELECT user_id, channel_id FROM trade_user_channels WHERE guild_id = ?",
                    (str(guild.id),),
                ).fetchall()

            print(f"[REFRESH_ALL] Refreshing {len(rows)} trade channel(s)...")
            refreshed = 0
            failed    = 0
            for row in rows:
                user_id    = int(row["user_id"])
                channel_id = int(row["channel_id"])
                try:
                    ch = guild.get_channel(channel_id) or await guild.fetch_channel(channel_id)
                    await reset_trade_messages(active.db_path, ch, user_id, TRADE_ANNOUNCE_CHANNEL_ID or None)
                    refreshed += 1
                except Exception as e:
                    failed += 1
                    print(f"[REFRESH_ALL] Failed user {user_id}: {e}")

            print(f"[REFRESH_ALL] Done — {refreshed} refreshed, {failed} failed")
        except Exception as e:
            print(f"[REFRESH_ALL] Error: {e}")

    asyncio.run_coroutine_threadsafe(_refresh_all(), _discord_loop)
    return {"ok": True, "message": "Refresh started in background — check bot terminal for progress"}


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN missing — check Discord/.env")
    client.run(TOKEN)
