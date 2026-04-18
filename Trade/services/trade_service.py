"""
Trade/services/trade_service.py

Business logic and orchestration for the trade system.
Uses Core.db.db_session — same pattern as the rest of V3.

PERSISTENT MESSAGE MODEL (2 per channel):
  MSG_HOME     → combined stats + binder, always refreshed
  MSG_LISTINGS → listings/offers detail, posted on first demand then kept updated

All other content (card search, offer notifications) is ephemeral or
posted as non-persistent messages that don't get edited.
"""

from __future__ import annotations

import logging
import math
import uuid
from pathlib import Path
from typing import Optional

import discord

from Core.db import db_session
from Trade.db.trade_db import (
    get_trade_channel_id,
    save_trade_channel_id,
    get_trade_ui_message_id,
    save_trade_ui_message_id,
    get_user_card_count,
    get_user_cards_page,
    get_user_active_listing_count,
    get_user_incoming_offer_count,
    save_listing,
    save_offer,
    resolve_offer,
    swap_card_ownership_for_offer,
    search_card_by_item_code,
    close_listing,
    get_offer_row,
    get_offer_item_codes,
    get_listing_item_codes,
)
from Trade.ui.trade_embeds import (
    build_home_embed,
    build_listings_embed,
    build_public_listing_embed,
    build_offer_received_embed,
)
from Trade.ui.trade_views import (
    TradeHomeView,
    TradeListingsView,
    TradeOfferResponseView,
)

log = logging.getLogger(__name__)

BINDER_PAGE_SIZE = 3

MSG_HOME     = "home"
MSG_LISTINGS = "listings"


# ---------------------------------------------------------------------------
# Channel management
# ---------------------------------------------------------------------------

async def ensure_trade_channel_for_user(
    db_path: Path,
    guild: discord.Guild,
    member: discord.Member,
    trade_category_id: int,
    announce_channel_id: Optional[int] = None,
) -> discord.TextChannel:
    with db_session(db_path) as conn:
        existing_id = get_trade_channel_id(conn, guild.id, member.id)

    if existing_id:
        ch = guild.get_channel(existing_id)
        if ch:
            return ch

    category = guild.get_channel(trade_category_id)
    if category is None:
        raise RuntimeError(f"Trade category {trade_category_id} not found in guild {guild.id}")

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            manage_messages=True,
            read_message_history=True,
        ),
    }

    safe_name = f"trade-{member.display_name}".lower().replace(" ", "-")[:80]
    channel = await guild.create_text_channel(
        name=safe_name,
        category=category,
        overwrites=overwrites,
        topic=f"Private trade channel for {member.display_name}",
    )

    with db_session(db_path) as conn:
        save_trade_channel_id(conn, guild.id, member.id, channel.id)

    log.info("Created trade channel %s for user %s", channel.id, member.id)
    return channel


# ---------------------------------------------------------------------------
# Persistent message helper
# ---------------------------------------------------------------------------

async def _edit_or_send(
    db_path: Path,
    channel: discord.TextChannel,
    user_id: int,
    message_type: str,
    embed: discord.Embed,
    view: discord.ui.View,
) -> discord.Message:
    with db_session(db_path) as conn:
        existing_id = get_trade_ui_message_id(conn, channel.guild.id, user_id, message_type)

    if existing_id:
        try:
            message = await channel.fetch_message(existing_id)
            await message.edit(embed=embed, view=view)
            with db_session(db_path) as conn:
                save_trade_ui_message_id(
                    conn, channel.guild.id, user_id, channel.id, message_type, message.id
                )
            return message
        except discord.NotFound:
            log.warning("Persistent %s message gone for user %s, posting new one", message_type, user_id)
        except Exception as e:
            log.error("Failed to edit persistent %s message: %s", message_type, e)

    message = await channel.send(embed=embed, view=view)
    with db_session(db_path) as conn:
        save_trade_ui_message_id(
            conn, channel.guild.id, user_id, channel.id, message_type, message.id
        )
    return message


# ---------------------------------------------------------------------------
# Home refresh (combined stats + binder)
# ---------------------------------------------------------------------------

async def refresh_trade_home(
    db_path: Path,
    channel: discord.TextChannel,
    user_id: int,
    page: int = 0,
    announce_channel_id: Optional[int] = None,
) -> discord.Message:
    with db_session(db_path) as conn:
        total_cards     = get_user_card_count(conn, user_id)
        active_listings = get_user_active_listing_count(conn, user_id)
        incoming_offers = get_user_incoming_offer_count(conn, user_id)
        total_pages     = max(1, math.ceil(total_cards / BINDER_PAGE_SIZE))
        page            = max(0, min(page, total_pages - 1))
        rows            = get_user_cards_page(conn, user_id, page, BINDER_PAGE_SIZE)

    embed = build_home_embed(
        total_cards=total_cards,
        active_listings=active_listings,
        incoming_offers=incoming_offers,
        rows=rows,
        page=page,
        total_pages=total_pages,
    )
    view = TradeHomeView(
        db_path=db_path,
        guild_id=channel.guild.id,
        user_id=user_id,
        page=page,
        total_pages=total_pages,
        announce_channel_id=announce_channel_id,
    )
    return await _edit_or_send(db_path, channel, user_id, MSG_HOME, embed, view)


# ---------------------------------------------------------------------------
# Listings refresh (posted on demand, then kept updated)
# ---------------------------------------------------------------------------

async def refresh_trade_listings(
    db_path: Path,
    channel: discord.TextChannel,
    user_id: int,
) -> discord.Message:
    with db_session(db_path) as conn:
        active_listings = get_user_active_listing_count(conn, user_id)
        incoming_offers = get_user_incoming_offer_count(conn, user_id)
        # TODO: get_user_sent_offer_count once offer repo is extended
        sent_offers     = 0

        # Fetch active listing details for display
        listing_rows = _get_user_active_listing_rows(conn, user_id)

    embed = build_listings_embed(
        active_listings=active_listings,
        incoming_offers=incoming_offers,
        sent_offers=sent_offers,
        listing_rows=listing_rows,
    )
    view = TradeListingsView(db_path=db_path, user_id=user_id)
    return await _edit_or_send(db_path, channel, user_id, MSG_LISTINGS, embed, view)


def _get_user_active_listing_rows(conn, user_id: int) -> list[dict]:
    """Fetch active listing summaries for the listings embed."""
    rows = conn.execute(
        """
        SELECT l.listing_id, l.looking_for,
               GROUP_CONCAT(lc.item_code, ',') AS codes
        FROM trade_listings l
        LEFT JOIN trade_listing_cards lc ON lc.listing_id = l.listing_id
        WHERE l.owner_user_id = ? AND l.status = 'active'
        GROUP BY l.listing_id
        ORDER BY l.created_at DESC
        """,
        (str(user_id),),
    ).fetchall()

    result = []
    for row in rows:
        result.append({
            "listing_id": row["listing_id"],
            "looking_for": row["looking_for"],
            "item_codes": row["codes"].split(",") if row["codes"] else [],
        })
    return result


async def refresh_all_trade_messages(
    db_path: Path,
    channel: discord.TextChannel,
    user_id: int,
    announce_channel_id: Optional[int] = None,
) -> None:
    """Refresh home. Only refresh listings if it's already been posted."""
    await refresh_trade_home(db_path, channel, user_id, page=0, announce_channel_id=announce_channel_id)

    with db_session(db_path) as conn:
        listings_exists = get_trade_ui_message_id(conn, channel.guild.id, user_id, MSG_LISTINGS)

    if listings_exists:
        await refresh_trade_listings(db_path, channel, user_id)


# ---------------------------------------------------------------------------
# Listing flow
# ---------------------------------------------------------------------------

async def handle_create_listing(
    db_path: Path,
    interaction: discord.Interaction,
    guild_id: int,
    user_id: int,
    item_codes: list[str],
    looking_for: Optional[str],
    announce_channel_id: Optional[int],
) -> None:
    with db_session(db_path) as conn:
        for code in item_codes:
            row = search_card_by_item_code(conn, code)
            if not row:
                await interaction.followup.send(f"Card `{code}` not found.", ephemeral=True)
                return
            if row["owner_discord_user_id"] != str(user_id):
                await interaction.followup.send(f"Card `{code}` does not belong to you.", ephemeral=True)
                return

        listing_id = str(uuid.uuid4())[:8].upper()
        save_listing(conn, listing_id, guild_id, user_id, item_codes, looking_for)

    if announce_channel_id and interaction.guild:
        announce_ch = interaction.guild.get_channel(announce_channel_id)
        if announce_ch:
            member        = interaction.guild.get_member(user_id)
            owner_display = member.mention if member else f"<@{user_id}>"
            embed = build_public_listing_embed(
                listing_id=listing_id,
                item_codes=item_codes,
                owner_display=owner_display,
                looking_for=looking_for,
            )
            await announce_ch.send(embed=embed)

    # Refresh home (stat counts change) and listings if already posted
    await refresh_all_trade_messages(db_path, interaction.channel, user_id, announce_channel_id)
    await interaction.followup.send(f"Listing `{listing_id}` created!", ephemeral=True)


# ---------------------------------------------------------------------------
# Offer flow
# ---------------------------------------------------------------------------

async def handle_send_offer(
    db_path: Path,
    interaction: discord.Interaction,
    sender_user_id: int,
    receiver_user_id: int,
    item_codes: list[str],
    listing_id: Optional[str] = None,
) -> None:
    with db_session(db_path) as conn:
        for code in item_codes:
            row = search_card_by_item_code(conn, code)
            if not row:
                await interaction.followup.send(f"Card `{code}` not found.", ephemeral=True)
                return
            if row["owner_discord_user_id"] != str(sender_user_id):
                await interaction.followup.send(f"Card `{code}` does not belong to you.", ephemeral=True)
                return

        offer_id = str(uuid.uuid4())[:8].upper()
        save_offer(conn, offer_id, interaction.guild.id, sender_user_id, receiver_user_id, item_codes, listing_id)

    with db_session(db_path) as conn:
        receiver_channel_id = get_trade_channel_id(conn, interaction.guild.id, receiver_user_id)

    if receiver_channel_id and interaction.guild:
        receiver_ch = interaction.guild.get_channel(receiver_channel_id)
        if receiver_ch:
            sender_member  = interaction.guild.get_member(sender_user_id)
            sender_display = sender_member.mention if sender_member else f"<@{sender_user_id}>"
            embed = build_offer_received_embed(
                offer_id=offer_id,
                sender_display=sender_display,
                item_codes=item_codes,
            )
            view = TradeOfferResponseView(db_path, offer_id, receiver_user_id)
            await receiver_ch.send(embed=embed, view=view)

    await interaction.followup.send(f"Offer `{offer_id}` sent!", ephemeral=True)


async def handle_offer_accepted(
    db_path: Path,
    interaction: discord.Interaction,
    offer_id: str,
) -> None:
    with db_session(db_path) as conn:
        resolve_offer(conn, offer_id, "accepted")
        swap_card_ownership_for_offer(conn, offer_id)  # TODO: implement

    await interaction.message.edit(content=f"✅ Offer `{offer_id}` accepted.", view=None)
    await interaction.followup.send("Trade accepted! Ownership updated.", ephemeral=True)


async def handle_offer_declined(
    db_path: Path,
    interaction: discord.Interaction,
    offer_id: str,
) -> None:
    with db_session(db_path) as conn:
        resolve_offer(conn, offer_id, "declined")

    await interaction.message.edit(content=f"❌ Offer `{offer_id}` declined.", view=None)
    await interaction.followup.send("Offer declined.", ephemeral=True)
