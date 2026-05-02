"""
Discord/bin_listener.py

Bin show mode — host types a number in #claim-bot-commands,
card posts to catalog immediately. No queue, no claim, no username matching.
Attribution handled separately via Bin Manager dashboard.
"""

from __future__ import annotations
import os
import re
from pathlib import Path

import discord
from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH, override=True)

CLAIM_BOT_COMMANDS_CHANNEL_ID = int(os.getenv("CLAIM_BOT_COMMANDS_CHANNEL_ID", "0"))


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

        # Verify channel also uses on_message — don't conflict
        if not content.isdigit():
            return

        # Check show mode
        try:
            from Core.show_service import require_active_show
            from Core.show_settings_service import get_setting
            active    = require_active_show()
            show_mode = get_setting(active.db_path, "show_mode") or "standard"
        except Exception:
            await message.reply("⚠️ No active show.", mention_author=False)
            return

        if show_mode != "bin":
            return

        item_number = int(content)
        item_code   = f"N{item_number:03d}"

        # Log to auction order list
        from Core.bin_queue import log_auction
        log_auction(item_number)

        # Ensure inventory slot exists
        try:
            from Core.db import db_session
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            with db_session(active.db_path) as conn:
                existing = conn.execute(
                    "SELECT item_code FROM inventory_items WHERE item_code = ?", (item_code,)
                ).fetchone()
                if not existing:
                    conn.execute(
                        "INSERT INTO inventory_items (item_code, status, post_mode, created_at, updated_at) "
                        "VALUES (?, 'available', 'claim', ?, ?)",
                        (item_code, now, now),
                    )
        except Exception as e:
            await message.reply(f"❌ Could not create slot for `{item_code}`: {e}", mention_author=False)
            return

        # Publish to catalog — no claim button in bin mode
        try:
            from Discord.publish_direct import publish_item_direct
            pub = await publish_item_direct(item_code, show_mode="bin")
        except Exception as e:
            await message.reply(f"❌ Publish failed for `{item_code}`: {e}", mention_author=False)
            return

        if pub.get("ok"):
            await message.reply(f"✅ **{item_code}** posted", mention_author=False)
        else:
            await message.reply(f"⚠️ `{item_code}`: {pub.get('error', 'publish failed')}", mention_author=False)
