"""Trade/services/trade_service.py - stable rebuild."""
from __future__ import annotations
import logging, math, uuid
from pathlib import Path
from typing import Optional
import discord
from Core.db import db_session
from Trade.db.trade_db import (
    get_trade_channel_id, save_trade_channel_id, get_trade_ui_message_id, save_trade_ui_message_id, delete_trade_ui_message_id,
    get_user_card_count, get_user_cards_page, get_user_active_listing_count, get_user_incoming_offer_count,
    save_listing, save_offer, resolve_offer, swap_card_ownership_for_offer, decline_conflicting_pending_offers, search_card_by_item_code,
    get_offer_row, save_listing_public_message, get_listing_public_message, delete_listing_public_message
)
from Trade.ui.trade_embeds import build_home_embed, build_listings_embed, build_public_listing_embed, build_offer_received_embed, build_offer_notification_embed
from Trade.ui.trade_views import TradeHomeView, TradeListingsView, TradeOfferResponseView, TradeOfferNotificationView
log=logging.getLogger(__name__)
BINDER_PAGE_SIZE=1
MSG_HOME="home"; MSG_LISTINGS="listings"

async def ensure_trade_channel_for_user(db_path:Path,guild:discord.Guild,member:discord.Member,trade_category_id:int,announce_channel_id:Optional[int]=None)->discord.TextChannel:
    with db_session(db_path) as conn: existing_id=get_trade_channel_id(conn,guild.id,member.id)
    if existing_id:
        ch=guild.get_channel(existing_id)
        if ch: return ch
    category=guild.get_channel(trade_category_id)
    if category is None: raise RuntimeError(f"Trade category {trade_category_id} not found in guild {guild.id}")
    overwrites={
        guild.default_role:discord.PermissionOverwrite(view_channel=False),
        member:discord.PermissionOverwrite(view_channel=True,send_messages=True,read_message_history=True),
        guild.me:discord.PermissionOverwrite(view_channel=True,send_messages=True,manage_messages=True,read_message_history=True),
    }
    safe_name=f"trade-{member.display_name}".lower().replace(" ","-")[:80]
    channel=await guild.create_text_channel(name=safe_name,category=category,overwrites=overwrites,topic=f"Private trade channel for {member.display_name}")
    with db_session(db_path) as conn: save_trade_channel_id(conn,guild.id,member.id,channel.id)
    log.info("Created trade channel %s for user %s", channel.id, member.id)
    return channel

async def _edit_or_send(db_path:Path,channel:discord.TextChannel,user_id:int,message_type:str,embed:discord.Embed,view:discord.ui.View)->discord.Message:
    with db_session(db_path) as conn: existing_id=get_trade_ui_message_id(conn,channel.guild.id,user_id,message_type)
    if existing_id:
        try:
            message=await channel.fetch_message(existing_id)
            await message.edit(embed=embed,view=view)
            with db_session(db_path) as conn: save_trade_ui_message_id(conn,channel.guild.id,user_id,channel.id,message_type,message.id)
            return message
        except discord.NotFound: log.warning("Persistent %s message gone for user %s, posting new one", message_type, user_id)
        except Exception as e: log.error("Failed to edit persistent %s message: %s", message_type, e)
    message=await channel.send(embed=embed,view=view)
    with db_session(db_path) as conn: save_trade_ui_message_id(conn,channel.guild.id,user_id,channel.id,message_type,message.id)
    return message

async def refresh_trade_home(db_path:Path,channel:discord.TextChannel,user_id:int,page:int=0,announce_channel_id:Optional[int]=None)->discord.Message:
    with db_session(db_path) as conn:
        total_cards=get_user_card_count(conn,user_id); active_listings=get_user_active_listing_count(conn,user_id); incoming_offers=get_user_incoming_offer_count(conn,user_id)
        total_pages=max(1,math.ceil(total_cards/BINDER_PAGE_SIZE)); page=max(0,min(page,total_pages-1)); rows=[dict(r) for r in get_user_cards_page(conn,user_id,page,BINDER_PAGE_SIZE)]
    embed=build_home_embed(total_cards=total_cards,active_listings=active_listings,incoming_offers=incoming_offers,rows=rows,page=page,total_pages=total_pages)
    view=TradeHomeView(db_path=db_path,guild_id=channel.guild.id,user_id=user_id,page=page,total_pages=total_pages,announce_channel_id=announce_channel_id)
    return await _edit_or_send(db_path,channel,user_id,MSG_HOME,embed,view)

async def refresh_trade_listings(db_path:Path,channel:discord.TextChannel,user_id:int)->discord.Message:
    with db_session(db_path) as conn:
        active_listings=get_user_active_listing_count(conn,user_id); incoming_offers=get_user_incoming_offer_count(conn,user_id); sent_offers=0; listing_rows=_get_user_active_listing_rows(conn,user_id)
    embed=build_listings_embed(active_listings=active_listings,incoming_offers=incoming_offers,sent_offers=sent_offers,listing_rows=listing_rows)
    return await _edit_or_send(db_path,channel,user_id,MSG_LISTINGS,embed,TradeListingsView(db_path=db_path,user_id=user_id))

def _get_user_active_listing_rows(conn,user_id:int)->list[dict]:
    rows=conn.execute("""SELECT l.listing_id,l.looking_for,GROUP_CONCAT(lc.item_code, ',') AS codes
    FROM trade_listings l LEFT JOIN trade_listing_cards lc ON lc.listing_id=l.listing_id
    WHERE l.owner_user_id=? AND l.status='active' GROUP BY l.listing_id ORDER BY l.created_at DESC""",(str(user_id),)).fetchall()
    return [{"listing_id":r["listing_id"],"looking_for":r["looking_for"],"item_codes":r["codes"].split(",") if r["codes"] else []} for r in rows]

async def refresh_all_trade_messages(db_path:Path,channel:discord.TextChannel,user_id:int,announce_channel_id:Optional[int]=None)->None:
    await refresh_trade_home(db_path,channel,user_id,page=0,announce_channel_id=announce_channel_id)
    with db_session(db_path) as conn: exists=get_trade_ui_message_id(conn,channel.guild.id,user_id,MSG_LISTINGS)
    if exists: await refresh_trade_listings(db_path,channel,user_id)

async def reset_trade_messages(db_path:Path,channel:discord.TextChannel,user_id:int,announce_channel_id:Optional[int]=None)->None:
    with db_session(db_path) as conn:
        ids=[get_trade_ui_message_id(conn,channel.guild.id,user_id,MSG_HOME), get_trade_ui_message_id(conn,channel.guild.id,user_id,MSG_LISTINGS)]
    for msg_id in ids:
        if not msg_id: continue
        try:
            msg=await channel.fetch_message(msg_id); await msg.delete()
        except discord.NotFound: pass
        except Exception as e: log.warning("Could not delete old trade message %s: %s", msg_id, e)
    with db_session(db_path) as conn:
        delete_trade_ui_message_id(conn,channel.guild.id,user_id,MSG_HOME)
        delete_trade_ui_message_id(conn,channel.guild.id,user_id,MSG_LISTINGS)
    try:
        await refresh_trade_home(db_path,channel,user_id,page=0,announce_channel_id=announce_channel_id)
    except Exception as e:
        log.error("reset_trade_messages: refresh_trade_home failed: %s", e); raise
    try:
        await refresh_trade_listings(db_path,channel,user_id)
    except Exception as e:
        log.error("reset_trade_messages: refresh_trade_listings failed: %s", e)

async def handle_create_listing(db_path:Path,interaction:discord.Interaction,guild_id:int,user_id:int,item_codes:list[str],looking_for:Optional[str],announce_channel_id:Optional[int])->None:
    with db_session(db_path) as conn:
        for code in item_codes:
            row=search_card_by_item_code(conn,code)
            if not row: await interaction.followup.send(f"Card `{code}` not found.",ephemeral=True); return
            if row["owner_discord_user_id"] != str(user_id): await interaction.followup.send(f"Card `{code}` does not belong to you.",ephemeral=True); return
        listing_id=str(uuid.uuid4())[:8].upper(); save_listing(conn,listing_id,guild_id,user_id,item_codes,looking_for)
    if announce_channel_id and interaction.guild:
        announce_ch=interaction.guild.get_channel(announce_channel_id)
        if announce_ch:
            from Trade.ui.trade_views import PublicListingView
            member=interaction.guild.get_member(user_id); owner_display=member.display_name if member else f"User {user_id}"
            preview_urls=[]
            with db_session(db_path) as conn:
                for code in item_codes:
                    row=search_card_by_item_code(conn,code); preview_urls.append(row["image_url"] if row else None)
            embed=build_public_listing_embed(listing_id=listing_id,item_codes=item_codes,owner_display=owner_display,owner_mention=None,looking_for=looking_for,preview_code=item_codes[0] if item_codes else None,preview_url=preview_urls[0] if preview_urls else None,index=0,total=len(item_codes) if item_codes else 1)
            view=PublicListingView(db_path,listing_id,user_id,owner_display,item_codes,preview_urls,looking_for,page=0)
            msg=await announce_ch.send(embed=embed,view=view)
            with db_session(db_path) as conn: save_listing_public_message(conn,listing_id,msg.channel.id,msg.id)
    await refresh_all_trade_messages(db_path,interaction.channel,user_id,announce_channel_id)
    await interaction.followup.send(f"Listing `{listing_id}` created!",ephemeral=True)

async def handle_send_offer(db_path:Path,interaction:discord.Interaction,sender_user_id:int,receiver_user_id:int,item_codes:list[str],listing_id:Optional[str]=None,target_item_code:Optional[str]=None)->None:
    with db_session(db_path) as conn:
        for code in item_codes:
            row=search_card_by_item_code(conn,code)
            if not row: await interaction.followup.send(f"Card `{code}` not found.",ephemeral=True); return
            if row["owner_discord_user_id"] != str(sender_user_id): await interaction.followup.send(f"Card `{code}` does not belong to you.",ephemeral=True); return
        offer_id=str(uuid.uuid4())[:8].upper(); save_offer(conn,offer_id,interaction.guild.id,sender_user_id,receiver_user_id,item_codes,listing_id,requested_codes=[target_item_code] if target_item_code else None)
    with db_session(db_path) as conn: receiver_channel_id=get_trade_channel_id(conn,interaction.guild.id,receiver_user_id)
    if receiver_channel_id and interaction.guild:
        receiver_ch=interaction.guild.get_channel(receiver_channel_id)
        if receiver_ch:
            sender_member=interaction.guild.get_member(sender_user_id); sender_display=sender_member.mention if sender_member else f"<@{sender_user_id}>"
            preview_urls=[]
            requested_preview_url=None
            with db_session(db_path) as conn:
                for code in item_codes:
                    row=search_card_by_item_code(conn,code); preview_urls.append(row["image_url"] if row else None)
                if target_item_code:
                    req_row=search_card_by_item_code(conn,target_item_code)
                    requested_preview_url=req_row["image_url"] if req_row else None
            notif_embed = build_offer_notification_embed(
                offer_id=offer_id,
                sender_display=sender_display,
                item_codes=item_codes,
                requested_codes=[target_item_code] if target_item_code else None,
            )
            await receiver_ch.send(
                embed=notif_embed,
                view=TradeOfferNotificationView(
                    db_path, offer_id, receiver_user_id,
                    item_codes=item_codes, preview_urls=preview_urls,
                    sender_display=sender_display,
                ),
            )
    await interaction.followup.send(f"Offer `{offer_id}` sent!",ephemeral=True)

async def _log_trade(db_path, guild, offer_id, sender_user_id, receiver_user_id, offer_codes, requested_codes):
    """Post a compact trade record to the show trade log thread."""
    try:
        from Core.show_settings_service import get_setting
        thread_id_str = get_setting(db_path, "trade_log_thread_id")
        if not thread_id_str:
            return
        thread = guild.get_channel(int(thread_id_str)) or await guild.fetch_channel(int(thread_id_str))
        if not thread:
            return
        if getattr(thread, "archived", False):
            await thread.edit(archived=False)

        # Fetch auction numbers for all cards involved
        def _card_str(code, conn):
            row = conn.execute("""
                SELECT c.auction_number
                FROM claims c
                WHERE c.item_code = ? AND c.removed_at IS NULL
            """, (code,)).fetchone()
            num = row["auction_number"] if row else None
            return f"{code} #{num}" if num else code

        with db_session(db_path) as conn:
            s_cards = ", ".join(_card_str(c, conn) for c in offer_codes)    or "none"
            r_cards = ", ".join(_card_str(c, conn) for c in requested_codes) or "none"

        sender_m      = guild.get_member(sender_user_id)
        receiver_m    = guild.get_member(receiver_user_id)
        sender_name   = sender_m.display_name   if sender_m   else f"<@{sender_user_id}>"
        receiver_name = receiver_m.display_name if receiver_m else f"<@{receiver_user_id}>"

        line = f"{sender_name} {s_cards}  <->  {receiver_name} {r_cards}"
        await thread.send(line)
    except Exception as e:
        log.warning("Could not post to trade log thread: %s", e)


async def handle_offer_accepted(db_path:Path,interaction:discord.Interaction,offer_id:str)->None:
    with db_session(db_path) as conn:
        offer=get_offer_row(conn,offer_id)
        if not offer:
            await interaction.followup.send(f"Offer `{offer_id}` was not found.",ephemeral=True)
            return
        moved=swap_card_ownership_for_offer(conn,offer_id)
        resolve_offer(conn,offer_id,"accepted")
        declined_ids=decline_conflicting_pending_offers(conn,offer_id,moved["moved_to_receiver"]+moved["moved_to_sender"])
        # Get sender info for each declined offer so we can notify them
        declined_senders=[]
        for did in declined_ids:
            drow=get_offer_row(conn,did)
            if drow: declined_senders.append((did,int(drow["sender_user_id"])))
        public_ref=None
        if offer and offer["listing_id"]:
            public_ref=get_listing_public_message(conn,offer["listing_id"]); delete_listing_public_message(conn,offer["listing_id"])
    if public_ref and interaction.guild:
        try:
            ch=interaction.guild.get_channel(int(public_ref["channel_id"])) or await interaction.guild.fetch_channel(int(public_ref["channel_id"]))
            msg=await ch.fetch_message(int(public_ref["message_id"])); await msg.delete()
        except discord.NotFound: pass
        except Exception as e: log.warning("Could not delete public listing post for offer %s: %s",offer_id,e)
    await interaction.channel.send(f"✅ Trade accepted — {offer_id} complete.")
    await interaction.followup.send("Trade accepted! Ownership updated.", ephemeral=True)
    if not interaction.guild or not offer: return

    # Refresh both users' trade channels
    for uid in (int(offer["sender_user_id"]), int(offer["receiver_user_id"])):
        try:
            with db_session(db_path) as conn: channel_id=get_trade_channel_id(conn,interaction.guild.id,uid)
            if channel_id and (ch:=interaction.guild.get_channel(channel_id)): await refresh_all_trade_messages(db_path,ch,uid)
        except Exception as e: log.warning("Could not refresh trade channel for user %s after trade: %s",uid,e)

    # Notify senders of conflicting offers that were auto-declined
    if interaction.guild:
        for declined_offer_id, sender_uid in declined_senders:
            try:
                with db_session(db_path) as conn:
                    sender_ch_id = get_trade_channel_id(conn, interaction.guild.id, sender_uid)
                if sender_ch_id:
                    sender_ch = interaction.guild.get_channel(sender_ch_id)
                    if sender_ch:
                        await sender_ch.send(
                            f"❌ Your offer  was automatically declined — the requested card was traded to someone else.",
                        )
            except Exception as e:
                log.warning("Could not notify sender %s of auto-decline: %s", sender_uid, e)

    # Log the trade to the show trade log thread
    from Trade.db.trade_db import get_offer_item_codes, get_offer_requested_codes
    with db_session(db_path) as conn:
        offer_codes     = get_offer_item_codes(conn, offer_id)
        requested_codes = get_offer_requested_codes(conn, offer_id)
    await _log_trade(
        db_path, interaction.guild, offer_id,
        int(offer["sender_user_id"]), int(offer["receiver_user_id"]),
        offer_codes, requested_codes,
    )

async def handle_offer_declined(db_path:Path,interaction:discord.Interaction,offer_id:str)->None:
    with db_session(db_path) as conn:
        offer = get_offer_row(conn, offer_id)
        resolve_offer(conn,offer_id,"declined")
    await interaction.followup.send("Offer declined.", ephemeral=True)
    # Refresh receiver channel so counts update + notify sender
    if offer and interaction.guild:
        receiver_id = int(offer["receiver_user_id"])
        sender_id   = int(offer["sender_user_id"])
        try:
            with db_session(db_path) as conn:
                channel_id = get_trade_channel_id(conn, interaction.guild.id, receiver_id)
            if channel_id and (ch := interaction.guild.get_channel(channel_id)):
                await refresh_all_trade_messages(db_path, ch, receiver_id)
        except Exception as e:
            log.warning("Could not refresh trade channel after decline: %s", e)
        # Notify sender in their trade channel
        try:
            with db_session(db_path) as conn:
                sender_ch_id = get_trade_channel_id(conn, interaction.guild.id, sender_id)
            if sender_ch_id:
                sender_ch = interaction.guild.get_channel(sender_ch_id)
                if sender_ch:
                    receiver_member = interaction.guild.get_member(receiver_id)
                    receiver_name   = receiver_member.display_name if receiver_member else f"<@{receiver_id}>"
                    await sender_ch.send(f"❌ Your offer `{offer_id}` to **{receiver_name}** was declined.")
        except Exception as e:
            log.warning("Could not notify sender of decline: %s", e)
