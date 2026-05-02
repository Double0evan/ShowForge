"""Trade/ui/trade_embeds.py - stable rebuild."""
from __future__ import annotations
from typing import Any, Optional
import discord

def build_home_embed(*, total_cards:int, active_listings:int, incoming_offers:int, rows:list[Any], page:int, total_pages:int)->discord.Embed:
    offers_val=f"**{incoming_offers}** ⚠️" if incoming_offers>0 else f"**{incoming_offers}**"
    embed=discord.Embed(title="📦  Your Inventory", color=0x5865F2)
    embed.add_field(name="Total Cards", value=f"**{total_cards}**", inline=True)
    embed.add_field(name="Listings", value=f"**{active_listings}**", inline=True)
    embed.add_field(name="Offers", value=offers_val, inline=True)
    if not rows:
        embed.add_field(name="📒  Binder", value="_No cards yet._", inline=False)
        embed.set_footer(text="Use the buttons below to trade")
    else:
        row=dict(rows[0]) if not isinstance(rows[0],dict) else rows[0]
        embed.add_field(name=f"📒  Binder  ·  Card {page+1} of {total_cards}", value=f"**`{row['item_code']}`**", inline=False)
        if row.get("image_url"): embed.set_image(url=row["image_url"])
        embed.set_footer(text="◀ Prev / Next ▶ to browse")
    return embed

def build_listings_embed(*, active_listings:int, incoming_offers:int, sent_offers:int, listing_rows:Optional[list[dict]]=None)->discord.Embed:
    embed=discord.Embed(title="📢  Listings & Offers", color=0xFAA61A)
    embed.add_field(name="Active Listings", value=f"**{active_listings}**", inline=True)
    embed.add_field(name="Incoming", value=f"**{incoming_offers}**", inline=True)
    embed.add_field(name="Sent", value=f"**{sent_offers}**", inline=True)
    if listing_rows:
        for listing in listing_rows:
            codes="  ".join(f"`{c}`" for c in listing.get("item_codes",[]))
            looking_for=listing.get("looking_for") or "Open to offers"
            embed.add_field(name=f"Listing  `{listing['listing_id']}`", value=f"{codes}\n↳ Looking for: {looking_for}", inline=False)
    elif active_listings==0:
        embed.add_field(name="", value="_No active listings._", inline=False)
    embed.set_footer(text="Use buttons below to manage listings and respond to offers")
    return embed

def build_card_detail_embed(*, row:Any, owner_display:str)->discord.Embed:
    row=dict(row) if not isinstance(row,dict) else row
    status_color={"available":0x3BA55C,"claimed":0x5865F2,"removed":0xED4245}.get(row.get("status",""),0x87898C)
    embed=discord.Embed(title=f"Card  `{row['item_code']}`", color=status_color)
    embed.add_field(name="Status", value=(row.get("status") or "unknown").capitalize(), inline=True)
    embed.add_field(name="Owner", value=owner_display, inline=True)
    if row.get("image_url"): embed.set_image(url=row["image_url"])
    embed.set_footer(text="Use Make Offer below to send a trade offer to the owner")
    return embed

def build_public_listing_embed(*, listing_id:str, item_codes:list[str], owner_display:str, owner_mention:Optional[str]=None, looking_for:Optional[str]=None, preview_code:Optional[str]=None, preview_url:Optional[str]=None, index:int=0, total:int=1)->discord.Embed:
    embed=discord.Embed(title=owner_display, color=0x248046)
    embed.add_field(name="Offering", value="\n".join(f"• `{code}`" for code in item_codes) or "_No cards listed._", inline=False)
    embed.add_field(name="Looking For", value=looking_for or "Open to offers", inline=False)
    if preview_code:
        more_count=max(0,total-1)
        txt=f"`{preview_code}` ({index+1}/{total})"
        if total>1: txt+=f"  •  +{more_count} more card{'s' if more_count != 1 else ''}"
        embed.add_field(name="Preview", value=txt, inline=False)
    if preview_url: embed.set_image(url=preview_url)
    embed.set_footer(text=f"Listing {listing_id}  ·  Browse cards or tap Make Offer below")
    return embed

def build_offer_received_embed(*, offer_id:str, sender_display:str, item_codes:list[str], requested_codes:Optional[list[str]]=None, preview_code:Optional[str]=None, preview_url:Optional[str]=None, requested_preview_url:Optional[str]=None, index:int=0, total:int=1)->discord.Embed:
    embed=discord.Embed(title="📨  Incoming Trade Offer", color=0xFAA61A)
    embed.add_field(name="From", value=sender_display, inline=False)
    # Offered cards
    offering_val="\n".join(f"• `{code}`" for code in item_codes) or "_No cards listed._"
    if total > 1:
        offering_val += f"\n\n*Showing {index+1} of {total} — use ◀ ▶ to browse*"
    embed.add_field(name=f"🃏  They're Offering ({total} card{'s' if total != 1 else ''})", value=offering_val, inline=False)
    if requested_codes:
        embed.add_field(name="🎯  They Want", value="\n".join(f"• `{code}`" for code in requested_codes), inline=False)
    # Main image = current offered card preview
    if preview_url:
        embed.set_image(url=preview_url)
    # Thumbnail = the card they're requesting (so receiver sees both)
    if requested_preview_url:
        embed.set_thumbnail(url=requested_preview_url)
    embed.set_footer(text=f"Offer {offer_id}  ·  Use ◀ ▶ to browse offered cards, then Accept or Decline")
    return embed
