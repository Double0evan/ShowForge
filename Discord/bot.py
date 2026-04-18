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


async def post_raw_to_thread(thread, *, item_code, claimer_name, raw_url, filename):
    resp  = requests.get(raw_url, timeout=25)
    resp.raise_for_status()
    fn    = filename or f"{item_code}.jpg"
    file  = discord.File(fp=io.BytesIO(resp.content), filename=fn)
    embed = discord.Embed(title=f"RAW: {item_code}", description=f"Claimed by **{claimer_name}**")
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
                await post_raw_to_thread(
                    thread, item_code=item_code, claimer_name=display_name,
                    raw_url=raw["attachment_url"], filename=raw.get("filename"),
                )
            except Exception:
                pass
        try:
            await interaction.message.delete()
        except Exception:
            pass
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
        return sfw_thread.id, nsfw_thread.id

    future = asyncio.run_coroutine_threadsafe(_create_threads(), _discord_loop)
    try:
        sfw_id, nsfw_id = future.result(timeout=25)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    # Save thread IDs directly to the show DB — avoids an HTTP round-trip back
    # to the backend which can fail silently under load
    try:
        from Core.show_service import require_active_show
        from Core.show_settings_service import set_setting
        active = require_active_show()
        set_setting(active.db_path, "claims_thread_sfw",  str(sfw_id))
        set_setting(active.db_path, "claims_thread_nsfw", str(nsfw_id))
    except Exception as e:
        # Fall back to HTTP if direct DB access fails
        try:
            requests.post(f"{BACKEND_BASE_URL}/shows/settings/set",
                          params={"key": "claims_thread_sfw",  "value": str(sfw_id)}, timeout=10)
            requests.post(f"{BACKEND_BASE_URL}/shows/settings/set",
                          params={"key": "claims_thread_nsfw", "value": str(nsfw_id)}, timeout=10)
        except Exception as e2:
            return JSONResponse({"ok": False, "error": f"Threads created but settings save failed: {e2}"}, status_code=500)

    return {"ok": True, "thread_name": thread_name, "sfw_thread_id": sfw_id, "nsfw_thread_id": nsfw_id}


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

    def run_api():
        uvicorn.run(app, host="127.0.0.1", port=8001, log_level="warning")

    threading.Thread(target=run_api, daemon=True).start()
    print("✅ Bot internal API on port 8001")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN missing — check Discord/.env")
    client.run(TOKEN)
