"""
Discord/bin_listener.py

Watches #claim-bot-commands for bare numbers during bin shows.
Low-confidence matches are flagged for review in the dashboard UI,
not in Discord — so the show host is never slowed down.
"""

from __future__ import annotations

import os
import re
import requests
from datetime import datetime, timezone
from pathlib import Path

import discord
from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH, override=True)

CLAIM_BOT_COMMANDS_CHANNEL_ID = int(os.getenv("CLAIM_BOT_COMMANDS_CHANNEL_ID", "0"))
VERIFIED_ROLE_ID               = int(os.getenv("VERIFIED_ROLE_ID", "0"))

MAX_SALE_AGE_SECONDS  = 3600  # 1 hour — covers any realistic delay between detection and host typing
FUZZY_MATCH_THRESHOLD = 0.75
FUZZY_FLAG_THRESHOLD  = 0.40


def _clean_ocr_name(name: str) -> str:
    return re.sub(r"^[\W_]+|[\W_]+$", "", name).strip()


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i-1] == b[j-1]:
                dp[i][j] = dp[i-1][j-1] + 1
            else:
                dp[i][j] = max(dp[i-1][j], dp[i][j-1])
    return dp[m][n] / max(m, n)


def _find_best_member(guild: discord.Guild, whatnot_username: str) -> tuple[discord.Member | None, float]:
    cleaned = _clean_ocr_name(whatnot_username)
    target  = _normalize(cleaned)
    best_member, best_score = None, 0.0

    for member in guild.members:
        if VERIFIED_ROLE_ID and not any(r.id == VERIFIED_ROLE_ID for r in member.roles):
            continue
        norm = _normalize(member.display_name)
        if norm == target:
            return member, 1.0
        score = _similarity(target, norm)
        if score > best_score:
            best_score, best_member = score, member

    if best_score >= FUZZY_MATCH_THRESHOLD:
        return best_member, best_score
    return None, best_score


def _flag_for_review(
    item_code: str,
    auction_number: int,
    whatnot_user: str,
    guest_user_id: int,
    closest_discord_name: str | None,
    match_score: float,
) -> None:
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
        conn.execute(
            """INSERT INTO match_reviews
               (item_code, auction_number, whatnot_user, guest_user_id,
                closest_discord_name, match_score, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (item_code, auction_number, whatnot_user, guest_user_id,
             closest_discord_name, match_score,
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def _ensure_inventory(db_path, item_code: str) -> None:
    """Create inventory row for item_code if it doesn't exist (bin show — no file drop)."""
    from Core.db import db_session
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with db_session(db_path) as conn:
        existing = conn.execute(
            "SELECT item_code FROM inventory_items WHERE item_code = ?", (item_code,)
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO inventory_items (item_code, status, post_mode, created_at, updated_at) "
                "VALUES (?, 'available', 'claim', ?, ?)",
                (item_code, now, now),
            )


def register_bin_listener(client: discord.Client, core, bot_api_url: str = "http://127.0.0.1:8001"):

    @client.event
    async def on_message(message: discord.Message):
        if message.author.bot:
            return
        if not message.guild:
            return
        if CLAIM_BOT_COMMANDS_CHANNEL_ID == 0 or message.channel.id != CLAIM_BOT_COMMANDS_CHANNEL_ID:
            return

        content = message.content.strip()
        if not content.isdigit():
            return

        # ── Check show mode ───────────────────────────────────────────────
        try:
            from Core.show_service import require_active_show
            from Core.show_settings_service import get_setting
            active    = require_active_show()
            show_mode = get_setting(active.db_path, "show_mode") or "standard"
        except Exception:
            await message.reply("⚠️ No active show. Start a show before using bin mode.", mention_author=False)
            return

        if show_mode != "bin":
            await message.reply("⚠️ Not in bin show mode. Switch to Bin Show in the dashboard first.", mention_author=False)
            return

        item_number = int(content)
        item_code   = f"N{item_number:03d}"

        # ── Peek latest sale (don't consume yet — only confirm on success) ─
        from Core.bin_queue import peek_latest_sale, confirm_sale
        sale = peek_latest_sale()

        if not sale:
            await message.reply(
                "⚠️ No pending Whatnot sale in queue. "
                "Make sure the screen watcher detected the sale before typing the number.",
                mention_author=False,
            )
            return

        detected_at = datetime.fromisoformat(sale["detected_at"])
        if detected_at.tzinfo is None:
            detected_at = detected_at.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - detected_at).total_seconds()

        if age > MAX_SALE_AGE_SECONDS:
            await message.reply(
                f"⚠️ Queued sale (@{sale['username']}, auction #{sale['auction_number']}) "
                f"is {int(age)}s old — too stale.",
                mention_author=False,
            )
            return

        auction_number = sale["auction_number"]
        whatnot_user   = _clean_ocr_name(sale["username"])

        # If OCR couldn't read the auction number, warn but still proceed
        # (host typed the number manually so we trust that)
        if not auction_number or auction_number == 0:
            print(f"[BIN] Auction number was 0/unknown for @{whatnot_user}, using host-typed number {item_number}")
            auction_number = item_number

        # ── Ensure inventory row exists ───────────────────────────────────
        # In bin mode no file is dropped first, so we create the slot now.
        try:
            _ensure_inventory(active.db_path, item_code)
        except Exception as e:
            await message.reply(f"❌ Failed to create inventory slot for `{item_code}`: {e}", mention_author=False)
            return

        # ── Fuzzy match ───────────────────────────────────────────────────
        discord_member, match_score = _find_best_member(message.guild, whatnot_user)

        from Core.db import db_session
        from Core.claim_service import create_claim, ClaimError
        from Core.normalize import normalize_name

        if discord_member:
            # Confident match (≥ threshold)
            match_note = "" if match_score == 1.0 else f" _(fuzzy {match_score:.0%})_"
            try:
                internal_user_id = core.upsert_discord_user(discord_member.id, discord_member.display_name)
                core.award_voucher(internal_user_id, "STAFF_ADJUST", f"Bin show auction #{auction_number}")
                create_claim(active.db_path, item_code=item_code, user_id=internal_user_id,
                             source="bin", auction_number=str(auction_number))
                claimer_label = f"<@{discord_member.id}>{match_note}"
            except ClaimError as e:
                if e.code == "ALREADY_CLAIMED":
                    await message.reply(
                        f"⚠️ {item_code} is already claimed. Queue sale for @{whatnot_user} has been kept — type a different item number.",
                        mention_author=False,
                    )
                else:
                    await message.reply(f"⚠️ Matched @{whatnot_user} but claim failed: {e.message}", mention_author=False)
                return
            except Exception as e:
                await message.reply(f"❌ Error creating claim: {e}", mention_author=False)
                return
        else:
            # No confident match — create guest claim immediately
            try:
                with db_session(active.db_path) as conn:
                    existing = conn.execute(
                        "SELECT id FROM users WHERE kind = 'pending' AND normalized_name = ?",
                        (normalize_name(whatnot_user),),
                    ).fetchone()
                    if existing:
                        guest_id = existing["id"]
                    else:
                        cur = conn.execute(
                            "INSERT INTO users (kind, discord_user_id, display_name, normalized_name, created_at) "
                            "VALUES ('pending', NULL, ?, ?, datetime('now'))",
                            (whatnot_user, normalize_name(whatnot_user)),
                        )
                        guest_id = cur.lastrowid

                from Core.voucher_service import award_voucher
                award_voucher(active.db_path, user_id=guest_id, reason="STAFF_ADJUST",
                              note=f"Bin show auction #{auction_number}")
                create_claim(active.db_path, item_code=item_code, user_id=guest_id,
                             source="bin", auction_number=str(auction_number))

                # Flag for UI review if there was a close-but-not-confident match
                closest_name = None
                if match_score >= FUZZY_FLAG_THRESHOLD:
                    target = _normalize(whatnot_user)
                    for member in message.guild.members:
                        if VERIFIED_ROLE_ID and not any(r.id == VERIFIED_ROLE_ID for r in member.roles):
                            continue
                        if _similarity(target, _normalize(member.display_name)) == match_score:
                            closest_name = member.display_name
                            break

                    _flag_for_review(
                        item_code=item_code,
                        auction_number=auction_number,
                        whatnot_user=whatnot_user,
                        guest_user_id=guest_id,
                        closest_discord_name=closest_name,
                        match_score=match_score,
                    )
                    claimer_label = f"**@{whatnot_user}** _(guest — ⚠️ flagged for review in dashboard)_"
                else:
                    claimer_label = f"**@{whatnot_user}** _(guest — will merge when they join)_"

            except ClaimError as e:
                await message.reply(f"⚠️ Guest claim failed: {e.message}", mention_author=False)
                return
            except Exception as e:
                await message.reply(f"❌ Error creating guest claim: {e}", mention_author=False)
                return

        # ── Confirm sale consumed (claim succeeded) ──────────────────────
        confirm_sale(sale["id"])

        # ── Trade channel ─────────────────────────────────────────────────
        import os as _os
        _trade_cat = int((_os.getenv("TRADE_CATEGORY_ID") or "0").strip().strip("'").strip('"'))
        _trade_ann = int((_os.getenv("TRADE_ANNOUNCE_CHANNEL_ID") or "0").strip().strip("'").strip('"'))
        if _trade_cat and discord_member:
            try:
                from Trade.trade_hook import on_item_assigned_trade
                await on_item_assigned_trade(
                    active.db_path, message.guild, discord_member,
                    _trade_cat, _trade_ann or None,
                )
            except Exception as e:
                print(f"[TRADE] bin trade channel error: {e}")

        # ── Publish ───────────────────────────────────────────────────────
        # Call directly as a coroutine — avoids HTTP self-call deadlock
        try:
            from Discord.publish_direct import publish_item_direct
            pub = await publish_item_direct(item_code, show_mode=show_mode)
        except Exception as e:
            await message.reply(f"✅ Claim recorded but publish failed for `{item_code}`: {e}", mention_author=False)
            return

        if pub.get("ok"):
            await message.reply(
                f"✅ **{item_code}** posted to catalog\n"
                f"🏆 Auction **#{auction_number}** → {claimer_label}",
                mention_author=False,
            )
        else:
            await message.reply(
                f"✅ Claim recorded for `{item_code}` but publish failed: {pub.get('error', 'unknown')}",
                mention_author=False,
            )
