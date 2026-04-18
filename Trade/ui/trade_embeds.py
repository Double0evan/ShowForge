"""
Trade/ui/trade_embeds.py

Pure embed builder functions — no DB calls, no Discord API calls.
All field names match V3's inventory_items / claims / media_assets schema.

ARCHITECTURE — Two persistent messages per trade channel:
  MSG_HOME    : Combined inventory stats + binder page (always visible, always refreshed)
  MSG_LISTINGS: Listings & offers detail (posted on demand via My Offers button,
                then kept persistent like home)

Sub-pages (card search results, other user's inventory) are always ephemeral —
they are never posted as persistent channel messages.
"""

from __future__ import annotations

from typing import Any, Optional

import discord


# ---------------------------------------------------------------------------
# Home + Binder combined (single persistent message)
# ---------------------------------------------------------------------------

def build_home_embed(
    *,
    total_cards: int,
    active_listings: int,
    incoming_offers: int,
    rows: list[Any],
    page: int,
    total_pages: int,
) -> discord.Embed:
    """
    The single always-visible home message.
    Combines inventory stats (top) with the current binder page (bottom).
    rows comes from get_user_cards_page() — up to 3 items per page.
    """
    offers_val = f"**{incoming_offers}** ⚠️" if incoming_offers > 0 else f"**{incoming_offers}**"

    embed = discord.Embed(
        title="📦  Your Inventory",
        color=0x5865F2,
    )

    # Stats — render as 3 inline columns on desktop, stacked on mobile
    embed.add_field(name="Total Cards", value=f"**{total_cards}**", inline=True)
    embed.add_field(name="Listings",    value=f"**{active_listings}**", inline=True)
    embed.add_field(name="Offers",      value=offers_val, inline=True)

    # Binder section
    if not rows:
        embed.add_field(
            name="📒  Binder",
            value="_No cards yet._",
            inline=False,
        )
    else:
        lines = []
        for row in rows:
            lines.append(f"◆  `{row['item_code']}`")

        embed.add_field(
            name=f"📒  Binder  ·  Page {page + 1} / {total_pages}",
            value="\n".join(lines),
            inline=False,
        )

        # Thumbnail from first card with an image
        for row in rows:
            if row.get("image_url"):
                embed.set_thumbnail(url=row["image_url"])
                break

    embed.set_footer(text="3 cards per page  ·  Use the buttons below to navigate")
    return embed


# ---------------------------------------------------------------------------
# Listings & Offers (second persistent message, shown on demand)
# ---------------------------------------------------------------------------

def build_listings_embed(
    *,
    active_listings: int,
    incoming_offers: int,
    sent_offers: int,
    listing_rows: Optional[list[dict]] = None,
) -> discord.Embed:
    """
    Listings & offers message. Posted the first time the user taps My Offers,
    then kept updated like the home message.
    listing_rows: list of dicts with keys listing_id, item_codes, looking_for
    """
    embed = discord.Embed(
        title="📢  Listings & Offers",
        color=0xFAA61A,
    )

    embed.add_field(name="Active Listings", value=f"**{active_listings}**", inline=True)
    embed.add_field(name="Incoming",        value=f"**{incoming_offers}**", inline=True)
    embed.add_field(name="Sent",            value=f"**{sent_offers}**",     inline=True)

    if listing_rows:
        for listing in listing_rows:
            codes       = "  ".join(f"`{c}`" for c in listing.get("item_codes", []))
            looking_for = listing.get("looking_for") or "Open to offers"
            embed.add_field(
                name=f"Listing  `{listing['listing_id']}`",
                value=f"{codes}\n↳ Looking for: {looking_for}",
                inline=False,
            )
    elif active_listings == 0:
        embed.add_field(name="", value="_No active listings._", inline=False)

    embed.set_footer(text="Use buttons below to manage listings and respond to offers")
    return embed


# ---------------------------------------------------------------------------
# Card detail — ephemeral only (Find Card Owner result)
# ---------------------------------------------------------------------------

def build_card_detail_embed(
    *,
    row: Any,
    owner_display: str,
) -> discord.Embed:
    """
    Ephemeral result shown only to the person who searched.
    Never posted as a persistent channel message.
    """
    status_color = {
        "available": 0x3BA55C,
        "claimed":   0x5865F2,
        "removed":   0xED4245,
    }.get(row.get("status", ""), 0x87898C)

    embed = discord.Embed(
        title=f"Card  `{row['item_code']}`",
        color=status_color,
    )
    embed.add_field(name="Status", value=row["status"].capitalize(), inline=True)
    embed.add_field(name="Owner",  value=owner_display,              inline=True)

    if row.get("image_url"):
        embed.set_thumbnail(url=row["image_url"])

    embed.set_footer(text="Use Make Offer below to send a trade offer to the owner")
    return embed


# ---------------------------------------------------------------------------
# Public listing announcement — posted to announce channel only
# ---------------------------------------------------------------------------

def build_public_listing_embed(
    *,
    listing_id: str,
    item_codes: list[str],
    owner_display: str,
    looking_for: Optional[str],
) -> discord.Embed:
    embed = discord.Embed(
        title="🆕  New Trade Listing",
        color=0x248046,
    )
    offering_lines = "\n".join(f"• `{code}`" for code in item_codes)
    embed.add_field(name="Offering",    value=offering_lines,                           inline=False)
    embed.add_field(name="Owner",       value=owner_display,                            inline=True)
    embed.add_field(name="Looking For", value=looking_for or "Alt Art / Open to Offers", inline=False)
    embed.set_footer(text=f"Listing {listing_id}  ·  Open your private trade thread to make an offer")
    return embed


# ---------------------------------------------------------------------------
# Offer received — posted in recipient's channel, not persistent
# ---------------------------------------------------------------------------

def build_offer_received_embed(
    *,
    offer_id: str,
    sender_display: str,
    item_codes: list[str],
) -> discord.Embed:
    embed = discord.Embed(
        title="📨  Incoming Trade Offer",
        color=0xFAA61A,
    )
    embed.add_field(name="From", value=sender_display, inline=False)
    offering_lines = "\n".join(f"• `{code}`" for code in item_codes)
    embed.add_field(name="They're Offering", value=offering_lines, inline=False)
    embed.set_footer(text=f"Offer {offer_id}  ·  Accept or Decline below")
    return embed
