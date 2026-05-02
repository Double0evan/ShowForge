"""Trade/trade_hook.py - stable rebuild."""
from __future__ import annotations
from pathlib import Path
from typing import Optional
import discord
from discord import app_commands
from Core.db import db_session
from Trade.db.trade_db import ensure_trade_tables
from Trade.services.trade_service import ensure_trade_channel_for_user, refresh_trade_home, refresh_all_trade_messages, reset_trade_messages

def _get_db_path()->Path:
    from Core.show_service import require_active_show
    return require_active_show().db_path

def init_trade_tables(db_path:Path)->None:
    with db_session(db_path) as conn: ensure_trade_tables(conn)

async def on_item_assigned_trade(db_path:Path,guild:discord.Guild,member:discord.Member,trade_category_id:int,announce_channel_id:Optional[int]=None)->None:
    init_trade_tables(db_path)
    channel=await ensure_trade_channel_for_user(db_path,guild,member,trade_category_id,announce_channel_id)
    await refresh_trade_home(db_path,channel,member.id,page=0,announce_channel_id=announce_channel_id)

def register_trade_commands(tree:app_commands.CommandTree, db_path:Optional[Path], trade_category_id:int, announce_channel_id:Optional[int]=None)->None:
    @tree.command(name="trade_open", description="Open your private trade channel")
    @app_commands.describe(member="Member to open for (staff only — defaults to yourself)")
    async def trade_open(interaction:discord.Interaction, member:Optional[discord.Member]=None):
        target=member or interaction.user
        if not isinstance(target,discord.Member): await interaction.response.send_message("Must be used in a server.",ephemeral=True); return
        await interaction.response.defer(ephemeral=True)
        try: db=_get_db_path(); init_trade_tables(db)
        except Exception as e: await interaction.followup.send(f"❌ No active show: {e}",ephemeral=True); return
        channel=await ensure_trade_channel_for_user(db,interaction.guild,target,trade_category_id,announce_channel_id)
        await refresh_all_trade_messages(db,channel,target.id,announce_channel_id)
        await interaction.followup.send(f"Trade channel ready: {channel.mention}",ephemeral=True)

    @tree.command(name="trade_refresh", description="Force-refresh trade messages")
    @app_commands.describe(member="Member whose trade channel to refresh")
    async def trade_refresh(interaction:discord.Interaction, member:Optional[discord.Member]=None):
        target=member or interaction.user
        if not isinstance(target,discord.Member): await interaction.response.send_message("Must be used in a server.",ephemeral=True); return
        await interaction.response.defer(ephemeral=True)
        try: db=_get_db_path(); init_trade_tables(db)
        except Exception as e: await interaction.followup.send(f"❌ No active show: {e}",ephemeral=True); return
        channel=await ensure_trade_channel_for_user(db,interaction.guild,target,trade_category_id,announce_channel_id)
        await reset_trade_messages(db,channel,target.id,announce_channel_id)
        await interaction.followup.send(f"Refreshed trade messages for {target.mention}",ephemeral=True)
