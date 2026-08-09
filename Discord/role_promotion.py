"""
Discord/role_promotion.py

Automatically promotes members from a "Newcomer" role to a "Member" role
once they've been in the server for 7+ days.

Matches the project's existing pattern (see commands_staff.py, bin_listener.py):
plain discord.Client + app_commands.CommandTree, no Cog system.
"""

from __future__ import annotations

import datetime as dt

import discord
from discord import app_commands
from discord.ext import tasks

MIN_DAYS_BEFORE_PROMOTION = 7

# Loop ticks daily at this UTC time (05:00 UTC ~= midnight EST), but the
# sweep itself only actually runs on Wednesdays (see WEEKDAY check below) —
# shows run Thu/Fri/Sat, so this catches newcomers up right before the run.
CHECK_TIME_UTC = dt.time(hour=5, minute=0, tzinfo=dt.timezone.utc)
RUN_ON_WEEKDAY = 2  # Monday=0 ... Wednesday=2 ... Sunday=6


def register_role_promotion(
    client: discord.Client,
    tree: app_commands.CommandTree,
    newcomer_role_id: int,
    member_role_id: int,
):
    """
    Wires up the daily promotion sweep and the /check_tenure command.
    Call once at import time in bot.py (module level is fine — this does
    NOT start the loop yet).

    Returns the tasks.Loop object. You must start it yourself from inside
    an async context that already has a running event loop — e.g. inside
    your existing on_ready handler:

        _role_promotion_loop = register_role_promotion(client, tree, NEWCOMER_ROLE_ID, MEMBER_ROLE_ID)
        ...
        async def on_ready():
            ...
            if not _role_promotion_loop.is_running():
                _role_promotion_loop.start()

    newcomer_role_id / member_role_id are passed in from bot.py directly
    (NOT imported from Discord.bot) — importing bot.py from a module that
    bot.py itself imports causes Python to re-run bot.py as a second module
    when run via `python -m Discord.bot`, which re-creates the CommandTree
    on the same client and crashes with "already has an associated command
    tree." Always pass values in as args instead.
    """

    @tasks.loop(time=CHECK_TIME_UTC)
    async def promote_eligible_members():
        if dt.datetime.now(dt.timezone.utc).weekday() != RUN_ON_WEEKDAY:
            return

        for guild in client.guilds:
            newcomer_role = guild.get_role(newcomer_role_id)
            member_role = guild.get_role(member_role_id)
            if not newcomer_role or not member_role:
                continue

            cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(
                days=MIN_DAYS_BEFORE_PROMOTION
            )

            for member in newcomer_role.members:
                if member.joined_at and member.joined_at <= cutoff:
                    try:
                        await member.remove_roles(newcomer_role, reason="7+ days in server")
                        await member.add_roles(member_role, reason="7+ days in server")
                    except (discord.Forbidden, discord.HTTPException):
                        # bot's role too low in hierarchy, or a transient API error
                        continue

    @promote_eligible_members.before_loop
    async def before_promote():
        await client.wait_until_ready()

    # Loop is created but NOT started here — no running event loop exists
    # yet at module-import time. Caller must start it from on_ready.

    # -----------------------------------------------------------------
    # Manual check / override
    # -----------------------------------------------------------------
    @tree.command(
        name="check_tenure",
        description="Check and promote a member if they've been here 7+ days",
    )
    @app_commands.describe(member="Member to check")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def check_tenure(interaction: discord.Interaction, member: discord.Member):
        if not interaction.guild:
            await interaction.response.send_message("Run this in a server channel.", ephemeral=True)
            return

        newcomer_role = interaction.guild.get_role(newcomer_role_id)
        member_role = interaction.guild.get_role(member_role_id)

        if newcomer_role is None or member_role is None:
            await interaction.response.send_message(
                "Role IDs aren't configured correctly — check NEWCOMER_ROLE_ID / MEMBER_ROLE_ID in .env.",
                ephemeral=True,
            )
            return

        if newcomer_role not in member.roles:
            await interaction.response.send_message(
                f"{member.mention} doesn't have the newcomer role.",
                ephemeral=True,
            )
            return

        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=MIN_DAYS_BEFORE_PROMOTION)

        if member.joined_at and member.joined_at <= cutoff:
            await member.remove_roles(newcomer_role, reason="7+ days (manual check)")
            await member.add_roles(member_role, reason="7+ days (manual check)")
            await interaction.response.send_message(
                f"Promoted {member.mention} to Member.", ephemeral=True
            )
        else:
            days_in = (dt.datetime.now(dt.timezone.utc) - member.joined_at).days
            days_left = MIN_DAYS_BEFORE_PROMOTION - days_in
            await interaction.response.send_message(
                f"{member.mention} has been here {days_in} day(s) — {days_left} more to go.",
                ephemeral=True,
            )

    return promote_eligible_members
