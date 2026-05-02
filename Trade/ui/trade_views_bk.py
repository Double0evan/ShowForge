"""Trade/ui/trade_views.py - stable modal-based rebuild."""
from __future__ import annotations
import math, re
from pathlib import Path
from typing import Optional
import discord
from Core.db import db_session
from Trade.ui.trade_embeds import build_card_detail_embed, build_public_listing_embed
from Trade.db.trade_db import search_card_by_item_code, get_user_card_count, get_user_cards_page

class OwnerOnlyMixin:
    user_id:int
    async def interaction_check(self, interaction:discord.Interaction)->bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your trade channel.", ephemeral=True)
            return False
        return True

class TradeHomeView(OwnerOnlyMixin, discord.ui.View):
    def __init__(self, db_path:Path, guild_id:int, user_id:int, page:int, total_pages:int, announce_channel_id:Optional[int]=None):
        super().__init__(timeout=None)
        self.db_path=db_path; self.guild_id=guild_id; self.user_id=user_id; self.page=page; self.total_pages=total_pages; self.announce_channel_id=announce_channel_id
        self.prev_page.disabled=page==0
        self.next_page.disabled=page>=total_pages-1

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary, row=0)
    async def prev_page(self, interaction:discord.Interaction, button:discord.ui.Button)->None:
        from Trade.services.trade_service import refresh_trade_home
        await interaction.response.defer()
        await refresh_trade_home(self.db_path, interaction.channel, self.user_id, page=self.page-1, announce_channel_id=self.announce_channel_id)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, row=0)
    async def next_page(self, interaction:discord.Interaction, button:discord.ui.Button)->None:
        from Trade.services.trade_service import refresh_trade_home
        await interaction.response.defer()
        await refresh_trade_home(self.db_path, interaction.channel, self.user_id, page=self.page+1, announce_channel_id=self.announce_channel_id)

    @discord.ui.button(label="Create Listing", style=discord.ButtonStyle.success, row=1)
    async def create_listing(self, interaction:discord.Interaction, button:discord.ui.Button)->None:
        await interaction.response.send_modal(CreateListingModal(self.db_path, self.guild_id, self.user_id, self.announce_channel_id))

    @discord.ui.button(label="Search Card", style=discord.ButtonStyle.secondary, row=1)
    async def find_card(self, interaction:discord.Interaction, button:discord.ui.Button)->None:
        await interaction.response.send_modal(FindCardOwnerModal(self.db_path, self.user_id))

    @discord.ui.button(label="Search Users", style=discord.ButtonStyle.secondary, row=1)
    async def search_users(self, interaction:discord.Interaction, button:discord.ui.Button)->None:
        await interaction.response.send_modal(SearchUsersModal(self.db_path, self.user_id))

    @discord.ui.button(label="My Offers", style=discord.ButtonStyle.primary, row=2)
    async def my_offers(self, interaction:discord.Interaction, button:discord.ui.Button)->None:
        from Trade.services.trade_service import refresh_trade_listings
        await interaction.response.defer(ephemeral=True)
        await refresh_trade_listings(self.db_path, interaction.channel, self.user_id)
        await interaction.followup.send("Listings updated below.", ephemeral=True)

class TradeListingsView(OwnerOnlyMixin, discord.ui.View):
    def __init__(self, db_path:Path, user_id:int):
        super().__init__(timeout=None); self.db_path=db_path; self.user_id=user_id
    @discord.ui.button(label="View Incoming", style=discord.ButtonStyle.primary, row=0)
    async def view_incoming(self, interaction:discord.Interaction, button:discord.ui.Button)->None:
        await interaction.response.send_message("Incoming offers — coming soon.", ephemeral=True)
    @discord.ui.button(label="View Sent", style=discord.ButtonStyle.secondary, row=0)
    async def view_sent(self, interaction:discord.Interaction, button:discord.ui.Button)->None:
        await interaction.response.send_message("Sent offers — coming soon.", ephemeral=True)
    @discord.ui.button(label="Edit Listing", style=discord.ButtonStyle.secondary, row=1)
    async def edit_listing(self, interaction:discord.Interaction, button:discord.ui.Button)->None:
        await interaction.response.send_message("Edit listing — coming soon.", ephemeral=True)
    @discord.ui.button(label="Cancel Listing", style=discord.ButtonStyle.danger, row=1)
    async def cancel_listing(self, interaction:discord.Interaction, button:discord.ui.Button)->None:
        await interaction.response.send_message("Cancel listing — coming soon.", ephemeral=True)

class TradeOfferResponseView(discord.ui.View):
    def __init__(self, db_path:Path, offer_id:str, receiver_user_id:int, item_codes:Optional[list[str]]=None, preview_urls:Optional[list[Optional[str]]]=None, page:int=0):
        super().__init__(timeout=None)
        self.db_path=db_path; self.offer_id=offer_id; self.receiver_user_id=receiver_user_id; self.item_codes=item_codes or []; self.preview_urls=preview_urls or []; self.page=page
        has_pages=len(self.item_codes)>1
        self.prev.disabled=not has_pages or page==0
        self.next.disabled=not has_pages or page>=len(self.item_codes)-1
    async def interaction_check(self, interaction:discord.Interaction)->bool:
        if interaction.user.id != self.receiver_user_id:
            await interaction.response.send_message("This offer is not addressed to you.", ephemeral=True); return False
        return True
    async def update_offer_page(self, interaction:discord.Interaction, new_page:int):
        from Trade.ui.trade_embeds import build_offer_received_embed
        sender_display="Unknown"
        if interaction.message and interaction.message.embeds and interaction.message.embeds[0].fields:
            sender_display=interaction.message.embeds[0].fields[0].value
        code=self.item_codes[new_page] if self.item_codes else None
        image=self.preview_urls[new_page] if self.preview_urls and new_page < len(self.preview_urls) else None
        embed=build_offer_received_embed(offer_id=self.offer_id,sender_display=sender_display,item_codes=self.item_codes,preview_code=code,preview_url=image,index=new_page,total=len(self.item_codes) if self.item_codes else 1)
        await interaction.response.edit_message(embed=embed, view=TradeOfferResponseView(self.db_path,self.offer_id,self.receiver_user_id,self.item_codes,self.preview_urls,page=new_page))
    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary, row=0)
    async def prev(self, interaction:discord.Interaction, button:discord.ui.Button)->None:
        await self.update_offer_page(interaction, self.page-1)
    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, row=0)
    async def next(self, interaction:discord.Interaction, button:discord.ui.Button)->None:
        await self.update_offer_page(interaction, self.page+1)
    @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.success, row=1)
    async def accept_offer(self, interaction:discord.Interaction, button:discord.ui.Button)->None:
        from Trade.services.trade_service import handle_offer_accepted
        await interaction.response.defer(); await handle_offer_accepted(self.db_path, interaction, self.offer_id)
    @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.danger, row=1)
    async def decline_offer(self, interaction:discord.Interaction, button:discord.ui.Button)->None:
        from Trade.services.trade_service import handle_offer_declined
        await interaction.response.defer(); await handle_offer_declined(self.db_path, interaction, self.offer_id)

class MakeOfferView(discord.ui.View):
    def __init__(self, db_path:Path, sender_user_id:int, target_item_code:str, receiver_user_id:int, listing_id:Optional[str]=None):
        super().__init__(timeout=120); self.db_path=db_path; self.sender_user_id=sender_user_id; self.target_item_code=target_item_code; self.receiver_user_id=receiver_user_id; self.listing_id=listing_id
    @discord.ui.button(label="Make Offer", style=discord.ButtonStyle.success)
    async def make_offer(self, interaction:discord.Interaction, button:discord.ui.Button)->None:
        await interaction.response.send_modal(MakeOfferModal(self.db_path,self.sender_user_id,self.target_item_code,self.receiver_user_id,self.listing_id))

def _normalize_member_search(raw:str)->str:
    raw=raw.strip(); m=re.search(r"<@!?(\d+)>",raw)
    return m.group(1) if m else raw.lower()

def _search_guild_members(guild:discord.Guild, query:str, exclude_user_id:int)->list[discord.Member]:
    q=_normalize_member_search(query)
    if q.isdigit():
        member=guild.get_member(int(q))
        return [member] if member and member.id!=exclude_user_id and not member.bot else []
    results=[]
    for member in guild.members:
        if member.bot or member.id==exclude_user_id: continue
        if any(q in h for h in [member.display_name.lower(), member.name.lower(), str(member).lower()]): results.append(member)
    results.sort(key=lambda m:(m.display_name.lower(),m.name.lower()))
    return results[:25]

def _get_user_cards_page_for_offer(conn, owner_user_id:int, page:int, page_size:int=1)->tuple[int,int,list[dict]]:
    total=get_user_card_count(conn,owner_user_id); total_pages=max(1,math.ceil(total/page_size)); page=max(0,min(page,total_pages-1))
    return total,total_pages,[dict(r) for r in get_user_cards_page(conn,owner_user_id,page,page_size)]

def _build_user_inventory_embed(*, owner_display:str, rows:list[dict], page:int, total_cards:int)->discord.Embed:
    embed=discord.Embed(title=f"👤  {owner_display}'s Inventory", color=0x57F287)
    if not rows:
        embed.description="_No cards found for this user._"; embed.set_footer(text="Try another user"); return embed
    row=rows[0]
    embed.add_field(name=f"Card {page+1} of {total_cards}", value=f"**`{row['item_code']}`**", inline=False)
    embed.add_field(name="Status", value=row.get("status","available").capitalize(), inline=True)
    if row.get("image_url"): embed.set_image(url=row["image_url"])
    embed.set_footer(text="Browse their cards, then tap Make Offer on the one you want")
    return embed

async def _send_user_inventory_browser(interaction:discord.Interaction, db_path:Path, sender_user_id:int, receiver_user_id:int, owner_display:str, page:int=0, edit_existing:bool=False)->None:
    with db_session(db_path) as conn:
        total,total_pages,rows=_get_user_cards_page_for_offer(conn,receiver_user_id,page,1)
    page=max(0,min(page,total_pages-1)); current=rows[0]["item_code"] if rows else None
    embed=_build_user_inventory_embed(owner_display=owner_display,rows=rows,page=page,total_cards=total)
    view=UserInventoryOfferView(db_path,sender_user_id,receiver_user_id,owner_display,page,total_pages,current)
    if edit_existing: await interaction.response.edit_message(embed=embed, view=view)
    else: await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class UserInventoryOfferView(discord.ui.View):
    def __init__(self, db_path:Path, sender_user_id:int, receiver_user_id:int, owner_display:str, page:int, total_pages:int, current_item_code:Optional[str]):
        super().__init__(timeout=120); self.db_path=db_path; self.sender_user_id=sender_user_id; self.receiver_user_id=receiver_user_id; self.owner_display=owner_display; self.page=page; self.total_pages=total_pages; self.current_item_code=current_item_code
        self.prev_card.disabled=page==0; self.next_card.disabled=page>=total_pages-1; self.make_offer.disabled=current_item_code is None
    async def interaction_check(self, interaction:discord.Interaction)->bool:
        if interaction.user.id!=self.sender_user_id:
            await interaction.response.send_message("This inventory browser is not yours.", ephemeral=True); return False
        return True
    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary, row=0)
    async def prev_card(self, interaction:discord.Interaction, button:discord.ui.Button)->None:
        await _send_user_inventory_browser(interaction,self.db_path,self.sender_user_id,self.receiver_user_id,self.owner_display,page=self.page-1,edit_existing=True)
    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, row=0)
    async def next_card(self, interaction:discord.Interaction, button:discord.ui.Button)->None:
        await _send_user_inventory_browser(interaction,self.db_path,self.sender_user_id,self.receiver_user_id,self.owner_display,page=self.page+1,edit_existing=True)
    @discord.ui.button(label="Make Offer", style=discord.ButtonStyle.success, row=1)
    async def make_offer(self, interaction:discord.Interaction, button:discord.ui.Button)->None:
        if not self.current_item_code:
            await interaction.response.send_message("No card selected.", ephemeral=True); return
        await interaction.response.send_modal(MakeOfferModal(self.db_path,self.sender_user_id,self.current_item_code,self.receiver_user_id,None))

class SearchUsersSelect(discord.ui.Select):
    def __init__(self, db_path:Path, sender_user_id:int, members:list[discord.Member]):
        self.db_path=db_path; self.sender_user_id=sender_user_id; self.member_map={str(m.id):m for m in members}
        options=[discord.SelectOption(label=(m.display_name[:100] if m.display_name else m.name[:100]), value=str(m.id), description=((f"@{m.name}")[:100] if m.name else None)) for m in members[:25]]
        super().__init__(placeholder="Select a user to browse their inventory", min_values=1, max_values=1, options=options)
    async def callback(self, interaction:discord.Interaction)->None:
        member=self.member_map[self.values[0]]
        await _send_user_inventory_browser(interaction,self.db_path,self.sender_user_id,member.id,member.display_name,page=0,edit_existing=True)

class SearchUsersSelectView(discord.ui.View):
    def __init__(self, db_path:Path, sender_user_id:int, members:list[discord.Member]):
        super().__init__(timeout=120); self.sender_user_id=sender_user_id; self.add_item(SearchUsersSelect(db_path,sender_user_id,members))
    async def interaction_check(self, interaction:discord.Interaction)->bool:
        if interaction.user.id!=self.sender_user_id:
            await interaction.response.send_message("This user search is not yours.", ephemeral=True); return False
        return True

class PublicListingView(discord.ui.View):
    def __init__(self, db_path:Path, listing_id:str, owner_user_id:int, owner_display:str, item_codes:list[str], preview_urls:list[Optional[str]], looking_for:Optional[str], page:int=0):
        super().__init__(timeout=None); self.db_path=db_path; self.listing_id=listing_id; self.owner_user_id=owner_user_id; self.owner_display=owner_display; self.item_codes=item_codes; self.preview_urls=preview_urls; self.looking_for=looking_for; self.page=page
        self.prev.disabled=page==0; self.next.disabled=page>=len(item_codes)-1
    async def update(self, interaction:discord.Interaction, new_page:int):
        embed=build_public_listing_embed(listing_id=self.listing_id,item_codes=self.item_codes,owner_display=self.owner_display,owner_mention=None,looking_for=self.looking_for,preview_code=self.item_codes[new_page] if self.item_codes else None,preview_url=self.preview_urls[new_page] if self.preview_urls and new_page<len(self.preview_urls) else None,index=new_page,total=len(self.item_codes) if self.item_codes else 1)
        await interaction.response.edit_message(embed=embed, view=PublicListingView(self.db_path,self.listing_id,self.owner_user_id,self.owner_display,self.item_codes,self.preview_urls,self.looking_for,page=new_page))
    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary, row=0)
    async def prev(self, interaction:discord.Interaction, button:discord.ui.Button): await self.update(interaction,self.page-1)
    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, row=0)
    async def next(self, interaction:discord.Interaction, button:discord.ui.Button): await self.update(interaction,self.page+1)
    @discord.ui.button(label="Make Offer", style=discord.ButtonStyle.success, row=1)
    async def make_offer(self, interaction:discord.Interaction, button:discord.ui.Button):
        if interaction.user.id==self.owner_user_id:
            await interaction.response.send_message("You cannot make an offer on your own listing.", ephemeral=True); return
        if not self.item_codes:
            await interaction.response.send_message("This listing has no cards.", ephemeral=True); return
        await interaction.response.send_modal(MakeOfferModal(self.db_path,interaction.user.id,self.item_codes[self.page],self.owner_user_id,self.listing_id))

class FindCardOwnerModal(discord.ui.Modal, title="Search Card"):
    item_code_input=discord.ui.TextInput(label="Item Code", placeholder="e.g. N001 or S042", required=True, max_length=10)
    def __init__(self, db_path:Path, user_id:int): super().__init__(); self.db_path=db_path; self.user_id=user_id
    async def on_submit(self, interaction:discord.Interaction)->None:
        item_code=str(self.item_code_input).strip().upper()
        with db_session(self.db_path) as conn: row=dict(raw) if (raw:=search_card_by_item_code(conn,item_code)) else None
        if not row:
            await interaction.response.send_message(f"Card `{item_code}` not found.", ephemeral=True); return
        owner_id=row.get("owner_discord_user_id")
        if owner_id:
            member=interaction.guild.get_member(int(owner_id)) if interaction.guild else None; owner_display=member.mention if member else f"<@{owner_id}>"
        else: owner_display=row.get("owner_display_name") or "Unknown / Unclaimed"
        embed=build_card_detail_embed(row=row, owner_display=owner_display)
        if owner_id and str(owner_id)!=str(self.user_id):
            await interaction.response.send_message(embed=embed, view=MakeOfferView(self.db_path,self.user_id,item_code,int(owner_id)), ephemeral=True)
        else: await interaction.response.send_message(embed=embed, ephemeral=True)

class SearchUsersModal(discord.ui.Modal, title="Search Users"):
    user_query_input=discord.ui.TextInput(label="User", placeholder="Type a name, username, or @mention", required=True, max_length=60)
    def __init__(self, db_path:Path, user_id:int): super().__init__(); self.db_path=db_path; self.user_id=user_id
    async def on_submit(self, interaction:discord.Interaction)->None:
        if not interaction.guild:
            await interaction.response.send_message("This can only be used inside a server.", ephemeral=True); return
        matches=_search_guild_members(interaction.guild,str(self.user_query_input).strip(),exclude_user_id=self.user_id)
        if not matches:
            await interaction.response.send_message("No matching users found.", ephemeral=True); return
        if len(matches)==1:
            member=matches[0]; await _send_user_inventory_browser(interaction,self.db_path,self.user_id,member.id,member.display_name,page=0,edit_existing=False); return
        await interaction.response.send_message("Select a user to browse their inventory:", view=SearchUsersSelectView(self.db_path,self.user_id,matches), ephemeral=True)

class CreateListingModal(discord.ui.Modal, title="Create Listing"):
    item_codes_input=discord.ui.TextInput(label="Item Code(s)", placeholder="1–3 codes, comma separated — e.g. N001, N044", required=True, max_length=50)
    looking_for=discord.ui.TextInput(label="Looking For", placeholder="Alt art, specific codes, or open to offers", required=False, max_length=200, style=discord.TextStyle.short)
    def __init__(self, db_path:Path, guild_id:int, user_id:int, announce_channel_id:Optional[int]): super().__init__(); self.db_path=db_path; self.guild_id=guild_id; self.user_id=user_id; self.announce_channel_id=announce_channel_id
    async def on_submit(self, interaction:discord.Interaction)->None:
        from Trade.services.trade_service import handle_create_listing
        item_codes=[c.strip() for c in str(self.item_codes_input).strip().upper().split(",") if c.strip()]
        if not 1<=len(item_codes)<=3:
            await interaction.response.send_message("Please enter between 1 and 3 item codes.", ephemeral=True); return
        await interaction.response.defer(ephemeral=True)
        await handle_create_listing(self.db_path,interaction,self.guild_id,self.user_id,item_codes,str(self.looking_for).strip() or None,self.announce_channel_id)

class MakeOfferModal(discord.ui.Modal, title="Make Offer"):
    item_codes_input=discord.ui.TextInput(label="Your Item Code(s) to Offer", placeholder="1–3 codes, comma separated — e.g. N055, N078", required=True, max_length=50)
    def __init__(self, db_path:Path, sender_user_id:int, target_item_code:str, receiver_user_id:int, listing_id:Optional[str]=None): super().__init__(); self.db_path=db_path; self.sender_user_id=sender_user_id; self.target_item_code=target_item_code; self.receiver_user_id=receiver_user_id; self.listing_id=listing_id
    async def on_submit(self, interaction:discord.Interaction)->None:
        from Trade.services.trade_service import handle_send_offer
        item_codes=[c.strip() for c in str(self.item_codes_input).strip().upper().split(",") if c.strip()]
        if not 1<=len(item_codes)<=3:
            await interaction.response.send_message("Please enter between 1 and 3 item codes.", ephemeral=True); return
        await interaction.response.defer(ephemeral=True)
        await handle_send_offer(self.db_path,interaction,self.sender_user_id,self.receiver_user_id,item_codes,self.listing_id,self.target_item_code)
