"""
Trade/trade_hook.py

Wire the trade system into the V3 bot.

INTEGRATION STEPS
-----------------
1. Add to your Discord/.env:

   TRADE_CATEGORY_ID=<Discord category channel ID>
   TRADE_ANNOUNCE_CHANNEL_ID=<public listing channel ID>  # optional

2. In Discord/bot.py, add after the other imports:

   from Trade.trade_hook import register_trade_commands, on_item_assigned_trade

3. In bot.py's on_ready(), add:

   register_trade_commands(tree, db_path=core.db_path)   # if db_path is accessible
   # OR pass db_path however your bot resolves it per-show

4. Call on_item_assigned_trade() from wherever your bot assigns items to users.

5. Add to your bot.py env block:

   TRADE_CATEGORY_ID    = get_int_env("TRADE_CATEGORY_ID", 0)
   TRADE_ANNOUNCE_CHANNEL_ID = get_int_env("TRADE_ANNOUNCE_CHANNEL_ID", 0)

DB PATH NOTE
------------
V3 uses per-show databases under DB/shows/<date>/show.db.
Pass the active show's db_path when calling trade functions.
The trade tables are appended to that same show DB via ensure_trade_tables().

You can get db_path from CoreClient or however your show manager exposes it:
   from Core.show_manager import get_active_db_path  (or similar)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands

from Core.db import db_session
from Trade.db.trade_db import ensure_trade_tables
from Trade.services.trade_service import (
    ensure_trade_channel_for_user,
    refresh_trade_home,
    refresh_all_trade_messages,
)


def init_trade_tables(db_path: Path) -> None:
    """Call once per show open to ensure trade tables exist in that show's DB."""
    with db_session(db_path) as conn:
        ensure_trade_tables(conn)


async def on_item_assigned_trade(
    db_path: Path,
    guild: discord.Guild,
    member: discord.Member,
    trade_category_id: int,
    announce_channel_id: Optional[int] = None,
) -> None:
    """
    Call this after a card is assigned to a user (claim, staff award, etc.).
    Ensures their private trade channel exists and refreshes their home message.
    """
    channel = await ensure_trade_channel_for_user(
        db_path, guild, member, trade_category_id, announce_channel_id
    )
    await refresh_trade_home(db_path, channel, member.id, announce_channel_id)


def register_trade_commands(
    tree: app_commands.CommandTree,
    db_path: Path,
    trade_category_id: int,
    announce_channel_id: Optional[int] = None,
) -> None:
    """
    Register trade-related slash commands onto the existing command tree.
    Call this in on_ready() after the rest of your commands are registered.
    """

    @tree.command(name="trade_open", description="Open your private trade channel (staff or self)")
    @app_commands.describe(member="Member to open trade channel for (staff only; defaults to yourself)")
    async def trade_open(interaction: discord.Interaction, member: Optional[discord.Member] = None):
        target = member or interaction.user
        if not isinstance(target, discord.Member):
            await interaction.response.send_message("Must be used in a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        channel = await ensure_trade_channel_for_user(
            db_path, interaction.guild, target, trade_category_id, announce_channel_id
        )
        await refresh_all_trade_messages(db_path, channel, target.id, announce_channel_id)
        await interaction.followup.send(f"Trade channel ready: {channel.mention}", ephemeral=True)

    @tree.command(name="trade_refresh", description="Force-refresh all trade messages (staff)")
    @app_commands.describe(member="Member whose trade channel to refresh")
    async def trade_refresh(interaction: discord.Interaction, member: Optional[discord.Member] = None):
        target = member or interaction.user
        if not isinstance(target, discord.Member):
            await interaction.response.send_message("Must be used in a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        channel = await ensure_trade_channel_for_user(
            db_path, interaction.guild, target, trade_category_id, announce_channel_id
        )
        await refresh_all_trade_messages(db_path, channel, target.id, announce_channel_id)
        await interaction.followup.send(f"Refreshed trade messages for {target.mention}", ephemeral=True)
