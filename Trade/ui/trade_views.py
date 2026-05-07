"""Trade/ui/trade_views.py - inventory-picker rebuild."""
from __future__ import annotations
import math
from pathlib import Path
from typing import Optional
import discord
from Core.db import db_session
from Trade.ui.trade_embeds import build_card_detail_embed, build_public_listing_embed
from Trade.db.trade_db import (
    search_card_by_item_code, get_user_card_count, get_user_cards_page,
    get_user_cards_all, get_offer_row, get_offer_item_codes, get_offer_requested_codes,
)

PAGE_SIZE = 25  # Discord select menu max options


def _get_db_path() -> Path:
    from Core.show_service import require_active_show
    return require_active_show().db_path


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_card_options(rows: list, selected: list[str]) -> list[discord.SelectOption]:
    options = []
    for r in rows:
        code = r["item_code"] if isinstance(r, dict) else r["item_code"]
        options.append(discord.SelectOption(
            label=code,
            value=code,
            default=code in selected,
        ))
    return options


def _search_guild_members(guild: discord.Guild, query: str, exclude_user_id: int) -> list[discord.Member]:
    q = query.lstrip("@").lower()
    return [m for m in guild.members
            if not m.bot and m.id != exclude_user_id
            and (q in m.display_name.lower() or q in m.name.lower())][:25]


# ── Owner-only mixin ──────────────────────────────────────────────────────────

class OwnerOnlyMixin:
    user_id: int
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # If user_id is set, use it directly
        expected = getattr(self, "user_id", 0)
        if expected and interaction.user.id != expected:
            await interaction.response.send_message("This is not your trade channel.", ephemeral=True)
            return False
        # If user_id is 0/None (after restart), look up from DB by channel
        if not expected and interaction.channel:
            try:
                from Trade.db.trade_db import get_channel_owner
                db_path = _get_db_path()
                owner_id = get_channel_owner(db_path, interaction.channel.id)
                if owner_id and interaction.user.id != owner_id:
                    await interaction.response.send_message("This is not your trade channel.", ephemeral=True)
                    return False
                # Restore user_id for future checks
                self.user_id = owner_id or interaction.user.id
            except Exception:
                pass
        return True


# ── Card Picker (shared) ──────────────────────────────────────────────────────

class CardPickerSelect(discord.ui.Select):
    """Paginated select of a user's inventory cards."""
    def __init__(self, rows: list, selected: list[str], placeholder: str, max_values: int):
        self._selected = list(selected)
        options = _build_card_options(rows, selected)
        super().__init__(
            placeholder=placeholder,
            min_values=0,
            max_values=min(max_values, len(options)),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view._selected = self.values  # type: ignore
        await interaction.response.defer()


class CardPickerView(discord.ui.View):
    """
    Image-gallery style card picker.
    Shows one card per page with its image. User clicks Select to add/remove
    from their selection, then Confirm when done.
    """
    def __init__(
        self,
        all_rows: list,
        owner_user_id: int,
        actor_user_id: int,
        page: int,
        max_values: int,
        title: str,
        on_confirm,
        selected: list[str] | None = None,
    ):
        super().__init__(timeout=180)
        self.all_rows      = all_rows
        self.owner_user_id = owner_user_id
        self.actor_user_id = actor_user_id
        self.page          = page
        self.max_values    = max_values
        self.title         = title
        self.on_confirm    = on_confirm
        self._selected     = list(selected or [])

        total = len(all_rows)
        self.prev_btn.disabled    = page == 0
        self.next_btn.disabled    = page >= total - 1
        self.confirm_btn.disabled = len(self._selected) == 0

        # Update Select/Deselect button label
        if total > 0:
            current_code = all_rows[page]["item_code"] if isinstance(all_rows[page], dict) else all_rows[page][0]
            if current_code in self._selected:
                self.select_btn.label = "✓ Deselect"
                self.select_btn.style = discord.ButtonStyle.secondary
            else:
                self.select_btn.label = "＋ Select"
                self.select_btn.style = discord.ButtonStyle.primary
        else:
            self.select_btn.disabled = True

    def _current_code(self) -> str | None:
        if not self.all_rows or self.page >= len(self.all_rows):
            return None
        r = self.all_rows[self.page]
        return r["item_code"] if isinstance(r, dict) else r[0]

    def _build_embed(self) -> discord.Embed:
        total = len(self.all_rows)
        code  = self._current_code()
        embed = discord.Embed(title=self.title, color=0x5865F2)
        embed.set_footer(text=f"Card {self.page + 1} of {total}")

        if self._selected:
            embed.description = f"**Selected ({len(self._selected)}/{self.max_values}):** {', '.join(self._selected)}"
        else:
            embed.description = "No cards selected yet. Click **＋ Select** to add a card."

        if code:
            embed.add_field(name="Card", value=f"", inline=True)
            r = self.all_rows[self.page]
            image_url = r.get("image_url") if isinstance(r, dict) else (r[2] if len(r) > 2 else None)
            if image_url:
                embed.set_image(url=image_url)

        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.actor_user_id:
            await interaction.response.send_message("This picker is not for you.", ephemeral=True)
            return False
        return True

    def _rebuild(self, new_page: int, selected: list[str]) -> "CardPickerView":
        return CardPickerView(
            self.all_rows, self.owner_user_id, self.actor_user_id,
            new_page, self.max_values, self.title, self.on_confirm, selected,
        )

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, row=1)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        new_view = self._rebuild(self.page - 1, self._selected)
        await interaction.response.edit_message(embed=new_view._build_embed(), view=new_view)

    @discord.ui.button(label="＋ Select", style=discord.ButtonStyle.primary, row=1)
    async def select_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        code = self._current_code()
        if not code:
            await interaction.response.send_message("No card here.", ephemeral=True)
            return
        new_selected = list(self._selected)
        if code in new_selected:
            new_selected.remove(code)
        elif len(new_selected) < self.max_values:
            new_selected.append(code)
        else:
            await interaction.response.send_message(
                f"You can only select up to {self.max_values} card(s).", ephemeral=True
            )
            return
        new_view = self._rebuild(self.page, new_selected)
        await interaction.response.edit_message(embed=new_view._build_embed(), view=new_view)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary, row=1)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        new_view = self._rebuild(self.page + 1, self._selected)
        await interaction.response.edit_message(embed=new_view._build_embed(), view=new_view)

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.success, row=2)
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self._selected:
            await interaction.response.send_message("Select at least one card first.", ephemeral=True)
            return
        await self.on_confirm(interaction, self._selected)

    @discord.ui.button(label="✕ Cancel", style=discord.ButtonStyle.danger, row=2)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Cancelled.", embed=None, view=None)


async def _show_card_picker(
    interaction: discord.Interaction,
    db_path: Path,
    owner_user_id: int,
    actor_user_id: int,
    max_values: int,
    title: str,
    on_confirm,
    edit_existing: bool = False,
):
    with db_session(db_path) as conn:
        rows = [dict(r) for r in get_user_cards_all(conn, owner_user_id)]

    if not rows:
        msg = "No cards available to select."
        if edit_existing:
            await interaction.response.edit_message(content=msg, embed=None, view=None)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
        return

    view = CardPickerView(rows, owner_user_id, actor_user_id, 0, max_values, title, on_confirm)
    embed = view._build_embed()

    if edit_existing:
        await interaction.response.edit_message(embed=embed, view=view, content=None)
    else:
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# ── Trade Home ────────────────────────────────────────────────────────────────

class TradeHomeView(OwnerOnlyMixin, discord.ui.View):
    def __init__(self, db_path: Path, guild_id: int, user_id: int, page: int, total_pages: int, announce_channel_id: Optional[int] = None):
        super().__init__(timeout=None)
        self.guild_id           = guild_id
        self.user_id            = user_id
        self.page               = page
        self.total_pages        = total_pages
        self.announce_channel_id = announce_channel_id
        self.prev_page.disabled = page == 0
        self.next_page.disabled = page >= total_pages - 1

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary, row=0, custom_id="trade_home_prev")
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        from Trade.services.trade_service import refresh_trade_home
        await interaction.response.defer()
        await refresh_trade_home(_get_db_path(), interaction.channel, self.user_id, page=self.page - 1, announce_channel_id=self.announce_channel_id)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, row=0, custom_id="trade_home_next")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        from Trade.services.trade_service import refresh_trade_home
        await interaction.response.defer()
        await refresh_trade_home(_get_db_path(), interaction.channel, self.user_id, page=self.page + 1, announce_channel_id=self.announce_channel_id)

    @discord.ui.button(label="Create Listing", style=discord.ButtonStyle.success, row=1, custom_id="trade_home_create_listing")
    async def create_listing(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        db = _get_db_path()
        guild_id = self.guild_id
        user_id  = self.user_id
        ann      = self.announce_channel_id

        async def on_cards_selected(inter: discord.Interaction, codes: list[str]):
            # Show looking_for modal after cards are picked
            await inter.response.send_modal(LookingForModal(db, guild_id, user_id, codes, ann))

        await _show_card_picker(
            interaction, db, user_id, user_id,
            max_values=3, title="Select Cards to List",
            on_confirm=on_cards_selected,
        )

    @discord.ui.button(label="Search Card", style=discord.ButtonStyle.secondary, row=1, custom_id="trade_home_search_card")
    async def find_card(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(FindCardOwnerModal(_get_db_path(), self.user_id))

    @discord.ui.button(label="Search Users", style=discord.ButtonStyle.secondary, row=1, custom_id="trade_home_search_users")
    async def search_users(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(SearchUsersModal(_get_db_path(), self.user_id))

    @discord.ui.button(label="My Offers", style=discord.ButtonStyle.primary, row=2, custom_id="trade_home_my_offers")
    async def my_offers(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        from Trade.services.trade_service import refresh_trade_listings
        await interaction.response.defer(ephemeral=True)
        await refresh_trade_listings(_get_db_path(), interaction.channel, self.user_id)
        await interaction.followup.send("Listings updated below.", ephemeral=True)


# ── Trade Listings ────────────────────────────────────────────────────────────

class TradeListingsView(OwnerOnlyMixin, discord.ui.View):
    def __init__(self, db_path: Path, user_id: int):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="View Incoming", style=discord.ButtonStyle.primary, row=0, custom_id="trade_listings_view_incoming")
    async def view_incoming(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        db = _get_db_path()
        with db_session(db) as conn:
            from Trade.db.trade_db import get_user_incoming_offers
            rows = [dict(r) for r in get_user_incoming_offers(conn, self.user_id)]
        if not rows:
            await interaction.response.send_message("No incoming offers right now.", ephemeral=True)
            return
        await _show_incoming_offers(interaction, db, self.user_id, rows, page=0)

    @discord.ui.button(label="View Sent", style=discord.ButtonStyle.secondary, row=0, custom_id="trade_listings_view_sent")
    async def view_sent(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        db = _get_db_path()
        with db_session(db) as conn:
            from Trade.db.trade_db import get_user_sent_offers
            rows = [dict(r) for r in get_user_sent_offers(conn, self.user_id)]
        if not rows:
            await interaction.response.send_message("No sent offers.", ephemeral=True)
            return
        await _show_sent_offers(interaction, db, self.user_id, rows, page=0)

    @discord.ui.button(label="Edit Listing", style=discord.ButtonStyle.secondary, row=1, custom_id="trade_listings_edit_listing")
    async def edit_listing(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        db = _get_db_path()
        with db_session(db) as conn:
            from Trade.services.trade_service import _get_user_active_listing_rows
            listings = _get_user_active_listing_rows(conn, self.user_id)
        if not listings:
            await interaction.response.send_message("You have no active listings to edit.", ephemeral=True)
            return
        if len(listings) == 1:
            await _show_edit_listing(interaction, db, self.user_id, dict(listings[0]))
        else:
            await interaction.response.send_message(
                "Select a listing to edit:",
                view=ListingSelectView(db, self.user_id, listings, mode="edit"),
                ephemeral=True,
            )

    @discord.ui.button(label="Cancel Listing", style=discord.ButtonStyle.danger, row=1, custom_id="trade_listings_cancel_listing")
    async def cancel_listing(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        db = _get_db_path()
        with db_session(db) as conn:
            from Trade.services.trade_service import _get_user_active_listing_rows
            listings = _get_user_active_listing_rows(conn, self.user_id)
        if not listings:
            await interaction.response.send_message("You have no active listings to cancel.", ephemeral=True)
            return
        if len(listings) == 1:
            await _confirm_cancel_listing(interaction, db, self.user_id, dict(listings[0]))
        else:
            await interaction.response.send_message(
                "Select a listing to cancel:",
                view=ListingSelectView(db, self.user_id, listings, mode="cancel"),
                ephemeral=True,
            )


# ── Offer Response ────────────────────────────────────────────────────────────

class TradeOfferNotificationView(discord.ui.View):
    """
    Small notification posted in receiver channel when an offer arrives.
    Shows minimal info. View button expands the full offer details.
    """
    def __init__(self, db_path, offer_id: str, receiver_user_id: int,
                 item_codes: list, preview_urls: list, sender_display: str):
        super().__init__(timeout=None)
        self.db_path          = db_path
        self.offer_id         = offer_id
        self.receiver_user_id = receiver_user_id
        self.item_codes       = item_codes
        self.preview_urls     = preview_urls
        self.sender_display   = sender_display
        self.notification_message = None  # set after send

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.receiver_user_id:
            await interaction.response.send_message("This offer is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="👁 View Offer", style=discord.ButtonStyle.primary, custom_id="offer_view")
    async def view_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        from Trade.ui.trade_embeds import build_offer_received_embed
        db_path = _get_db_path()
        with db_session(db_path) as conn:
            from Trade.db.trade_db import get_offer_row, get_offer_item_codes, get_offer_requested_codes, search_card_by_item_code
            offer = get_offer_row(conn, self.offer_id)
            if not offer or offer["status"] != "pending":
                await interaction.response.send_message("This offer is no longer active.", ephemeral=True)
                return
            item_codes      = get_offer_item_codes(conn, self.offer_id)
            requested_codes = get_offer_requested_codes(conn, self.offer_id)
            preview_urls = []
            for code in item_codes:
                row = search_card_by_item_code(conn, code)
                preview_urls.append(row["image_url"] if row else None)
            requested_preview_url = None
            if requested_codes:
                req = search_card_by_item_code(conn, requested_codes[0])
                requested_preview_url = req["image_url"] if req else None

        embed = build_offer_received_embed(
            offer_id=self.offer_id,
            sender_display=self.sender_display,
            item_codes=item_codes,
            requested_codes=requested_codes or None,
            preview_code=item_codes[0] if item_codes else None,
            preview_url=preview_urls[0] if preview_urls else None,
            requested_preview_url=requested_preview_url,
            index=0,
            total=len(item_codes),
        )
        view = TradeOfferResponseView(
            db_path, self.offer_id, self.receiver_user_id,
            item_codes=item_codes, preview_urls=preview_urls,
            page=0, sender_display=self.sender_display,
            notification_message=interaction.message,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class TradeOfferResponseView(discord.ui.View):
    def __init__(self, db_path: Path, offer_id: str, receiver_user_id: int, item_codes: Optional[list[str]] = None, preview_urls: Optional[list[Optional[str]]] = None, page: int = 0, sender_display: str = "Unknown", notification_message=None):
        super().__init__(timeout=None)
        self.offer_id             = offer_id
        self.receiver_user_id     = receiver_user_id
        self.item_codes           = item_codes or []
        self.preview_urls         = preview_urls or []
        self.page                 = page
        self.sender_display       = sender_display
        self.notification_message = notification_message
        self.prev.custom_id    = f"trade_offer_prev:{offer_id}"
        self.next.custom_id    = f"trade_offer_next:{offer_id}"
        self.accept.custom_id  = f"trade_offer_accept:{offer_id}"
        self.decline.custom_id = f"trade_offer_decline:{offer_id}"
        has_pages             = len(self.item_codes) > 1
        self.prev.disabled    = not has_pages or page == 0
        self.next.disabled    = not has_pages or page >= len(self.item_codes) - 1

    async def _hydrate(self, interaction: discord.Interaction) -> bool:
        if self.item_codes:
            return True
        db = _get_db_path()
        with db_session(db) as conn:
            offer = get_offer_row(conn, self.offer_id)
            if not offer:
                return False
            self.receiver_user_id = int(offer["receiver_user_id"])
            self.item_codes = get_offer_item_codes(conn, self.offer_id)
            self.requested_codes = get_offer_requested_codes(conn, self.offer_id)
            self.preview_urls = []
            for code in self.item_codes:
                row = search_card_by_item_code(conn, code)
                self.preview_urls.append(dict(row).get("image_url") if row else None)
        if interaction.guild:
            member = interaction.guild.get_member(int(offer["sender_user_id"]))
            self.sender_display = member.mention if member else f"<@{offer['sender_user_id']}>"
        else:
            self.sender_display = f"<@{offer['sender_user_id']}>"
        has_pages = len(self.item_codes) > 1
        self.prev.disabled = not has_pages or self.page == 0
        self.next.disabled = not has_pages or self.page >= len(self.item_codes) - 1
        return True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await self._hydrate(interaction):
            await interaction.response.send_message("This offer no longer exists.", ephemeral=True)
            return False
        if interaction.user.id != self.receiver_user_id:
            await interaction.response.send_message("This offer is not addressed to you.", ephemeral=True)
            return False
        return True

    async def _update_page(self, interaction: discord.Interaction, new_page: int):
        from Trade.ui.trade_embeds import build_offer_received_embed
        if not await self._hydrate(interaction):
            await interaction.response.send_message("This offer no longer exists.", ephemeral=True)
            return
        code  = self.item_codes[new_page] if self.item_codes else None
        image = self.preview_urls[new_page] if self.preview_urls and new_page < len(self.preview_urls) else None
        embed = build_offer_received_embed(offer_id=self.offer_id, sender_display=self.sender_display, item_codes=self.item_codes, requested_codes=getattr(self,"requested_codes",None) or None, preview_code=code, preview_url=image, index=new_page, total=len(self.item_codes) or 1)
        await interaction.response.edit_message(embed=embed, view=TradeOfferResponseView(None, self.offer_id, self.receiver_user_id, self.item_codes, self.preview_urls, page=new_page, sender_display=self.sender_display))

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary, row=0, custom_id="trade_offer_prev")
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button): await self._update_page(interaction, self.page - 1)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, row=0, custom_id="trade_offer_next")
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button): await self._update_page(interaction, self.page + 1)

    @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.success, row=1, custom_id="trade_offer_accept")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        from Trade.services.trade_service import handle_offer_accepted
        await interaction.response.defer(ephemeral=True)
        # Delete the notification message from channel
        if self.notification_message:
            try: await self.notification_message.delete()
            except Exception: pass
        await handle_offer_accepted(_get_db_path(), interaction, self.offer_id)

    @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.danger, row=1, custom_id="trade_offer_decline")
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        from Trade.services.trade_service import handle_offer_declined
        await interaction.response.defer(ephemeral=True)
        # Delete the notification message from channel
        if self.notification_message:
            try: await self.notification_message.delete()
            except Exception: pass
        await handle_offer_declined(_get_db_path(), interaction, self.offer_id)


# ── Public Listing ────────────────────────────────────────────────────────────

class PublicListingView(discord.ui.View):
    def __init__(self, db_path: Path, listing_id: str, owner_user_id: int, owner_display: str, item_codes: list[str], preview_urls: list[Optional[str]], looking_for: Optional[str], page: int = 0):
        super().__init__(timeout=None)
        self.listing_id    = listing_id
        self.owner_user_id = owner_user_id
        self.owner_display = owner_display
        self.item_codes    = item_codes
        self.preview_urls  = preview_urls
        self.looking_for   = looking_for
        self.page          = page
        self.prev.disabled = page == 0
        self.next.disabled = page >= len(item_codes) - 1

    async def _update(self, interaction: discord.Interaction, new_page: int):
        embed = build_public_listing_embed(listing_id=self.listing_id, item_codes=self.item_codes, owner_display=self.owner_display, owner_mention=None, looking_for=self.looking_for, preview_code=self.item_codes[new_page] if self.item_codes else None, preview_url=self.preview_urls[new_page] if self.preview_urls and new_page < len(self.preview_urls) else None, index=new_page, total=len(self.item_codes) or 1)
        await interaction.response.edit_message(embed=embed, view=PublicListingView(None, self.listing_id, self.owner_user_id, self.owner_display, self.item_codes, self.preview_urls, self.looking_for, page=new_page))

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary, row=0, custom_id="trade_public_listing_prev")
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button): await self._update(interaction, self.page - 1)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, row=0, custom_id="trade_public_listing_next")
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button): await self._update(interaction, self.page + 1)

    @discord.ui.button(label="Make Offer", style=discord.ButtonStyle.success, row=1, custom_id="trade_public_listing_make_offer")
    async def make_offer(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.owner_user_id:
            await interaction.response.send_message("You cannot make an offer on your own listing.", ephemeral=True)
            return
        if not self.item_codes:
            await interaction.response.send_message("This listing has no cards.", ephemeral=True)
            return
        db             = _get_db_path()
        sender_id      = interaction.user.id
        receiver_id    = self.owner_user_id
        target_code    = self.item_codes[self.page]
        listing_id     = self.listing_id

        async def on_offer_cards(inter: discord.Interaction, codes: list[str]):
            from Trade.services.trade_service import handle_send_offer
            await inter.response.defer(ephemeral=True)
            await handle_send_offer(db, inter, sender_id, receiver_id, codes, listing_id, target_code)

        await _show_card_picker(interaction, db, sender_id, sender_id, max_values=3,
                                title="Select Your Cards to Offer", on_confirm=on_offer_cards)


# ── Card Detail Make Offer View ───────────────────────────────────────────────

class CardDetailMakeOfferView(discord.ui.View):
    """Attached to the card detail embed — single Make Offer button that opens the picker."""
    def __init__(self, sender_user_id: int, receiver_user_id: int, target_item_code: str):
        super().__init__(timeout=120)
        self.sender_user_id   = sender_user_id
        self.receiver_user_id = receiver_user_id
        self.target_item_code = target_item_code

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.sender_user_id:
            await interaction.response.send_message("This is not your lookup.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Make Offer", style=discord.ButtonStyle.success)
    async def make_offer_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        db          = _get_db_path()
        sender_id   = self.sender_user_id
        receiver_id = self.receiver_user_id
        target_code = self.target_item_code

        async def on_offer_cards(inter: discord.Interaction, codes: list[str]):
            from Trade.services.trade_service import handle_send_offer
            await inter.response.defer(ephemeral=True)
            await handle_send_offer(db, inter, sender_id, receiver_id, codes, None, target_code)

        await _show_card_picker(
            interaction, db, sender_id, sender_id, max_values=3,
            title=f"Select Your Cards to Offer for {target_code}",
            on_confirm=on_offer_cards, edit_existing=True,
        )


# ── Find Card Modal ───────────────────────────────────────────────────────────

class FindCardOwnerModal(discord.ui.Modal, title="Search Card"):
    item_code_input = discord.ui.TextInput(label="Item Code", placeholder="e.g. N001 or S042", required=True, max_length=10)

    def __init__(self, db_path: Path, user_id: int):
        super().__init__()
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        item_code = str(self.item_code_input).strip().upper()
        db = _get_db_path()
        with db_session(db) as conn:
            raw = search_card_by_item_code(conn, item_code)
            row = dict(raw) if raw else None
        if not row:
            await interaction.response.send_message(f"Card `{item_code}` not found.", ephemeral=True)
            return
        owner_id = row.get("owner_discord_user_id")
        if owner_id:
            member = interaction.guild.get_member(int(owner_id)) if interaction.guild else None
            owner_display = member.mention if member else f"<@{owner_id}>"
        else:
            owner_display = row.get("owner_display_name") or "Unknown / Unclaimed"
        embed = build_card_detail_embed(row=row, owner_display=owner_display)

        # Show Make Offer if card belongs to someone else
        # owner_id may be None if owner is a pending user — still show button using display name
        can_offer = owner_id and str(owner_id) != str(self.user_id)
        if not can_offer and not owner_id and row.get("owner_display_name"):
            # Pending user owns it — we cannot make an offer without a discord_id
            pass
        if can_offer:
            view = CardDetailMakeOfferView(self.user_id, int(owner_id), item_code)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)


# ── Search Users ──────────────────────────────────────────────────────────────

class SearchUsersModal(discord.ui.Modal, title="Search Users"):
    user_query_input = discord.ui.TextInput(label="User", placeholder="Type a name, username, or @mention", required=True, max_length=60)

    def __init__(self, db_path: Path, user_id: int):
        super().__init__()
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("This can only be used inside a server.", ephemeral=True)
            return
        matches = _search_guild_members(interaction.guild, str(self.user_query_input).strip(), exclude_user_id=self.user_id)
        if not matches:
            await interaction.response.send_message("No matching users found.", ephemeral=True)
            return
        if len(matches) == 1:
            await _show_user_inventory(interaction, _get_db_path(), self.user_id, matches[0], edit_existing=False)
            return
        await interaction.response.send_message(
            "Select a user:", view=SearchUsersSelectView(_get_db_path(), self.user_id, matches), ephemeral=True
        )


class SearchUsersSelect(discord.ui.Select):
    def __init__(self, db_path: Path, sender_user_id: int, members: list[discord.Member]):
        self.sender_user_id = sender_user_id
        self.member_map = {str(m.id): m for m in members}
        options = [discord.SelectOption(label=m.display_name[:100], value=str(m.id)) for m in members[:25]]
        super().__init__(placeholder="Select a user to browse their inventory", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        member = self.member_map[self.values[0]]
        await _show_user_inventory(interaction, _get_db_path(), self.sender_user_id, member, edit_existing=True)


class SearchUsersSelectView(discord.ui.View):
    def __init__(self, db_path: Path, sender_user_id: int, members: list[discord.Member]):
        super().__init__(timeout=120)
        self.sender_user_id = sender_user_id
        self.add_item(SearchUsersSelect(db_path, sender_user_id, members))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.sender_user_id:
            await interaction.response.send_message("This is not your search.", ephemeral=True)
            return False
        return True


async def _show_user_inventory(
    interaction: discord.Interaction,
    db_path: Path,
    sender_user_id: int,
    target_member: discord.Member,
    edit_existing: bool,
):
    """Show the target user's inventory as a card picker so sender can select cards to offer."""
    receiver_id = target_member.id

    async def on_offer_cards(inter: discord.Interaction, target_codes: list[str]):
        """After selecting which of THEIR cards we want, pick OUR cards to offer."""
        async def on_my_cards(inter2: discord.Interaction, my_codes: list[str]):
            from Trade.services.trade_service import handle_send_offer
            await inter2.response.defer(ephemeral=True)
            await handle_send_offer(
                _get_db_path(), inter2, sender_user_id, receiver_id,
                my_codes, None, target_codes[0] if target_codes else None,
            )

        await _show_card_picker(
            inter, _get_db_path(), sender_user_id, sender_user_id,
            max_values=3, title="Now Select YOUR Cards to Offer",
            on_confirm=on_my_cards, edit_existing=True,
        )

    await _show_card_picker(
        interaction, db_path, receiver_id, sender_user_id,
        max_values=3, title=f"{target_member.display_name}'s Cards — Select What You Want",
        on_confirm=on_offer_cards, edit_existing=edit_existing,
    )


# ── Incoming Offers ──────────────────────────────────────────────────────────

async def _show_incoming_offers(interaction: discord.Interaction, db_path, user_id: int, rows: list, page: int, edit_existing: bool = False):
    row    = rows[page]
    total  = len(rows)
    offer_id    = row["offer_id"]
    sender_id   = int(row["sender_user_id"])
    offer_codes = [c.strip() for c in row["offer_codes"].split(",")] if row.get("offer_codes") else []

    sender_m = interaction.guild.get_member(sender_id) if interaction.guild else None
    sender_display = sender_m.display_name if sender_m else f"<@{sender_id}>"

    with db_session(db_path) as conn:
        from Trade.db.trade_db import get_offer_requested_codes, search_card_by_item_code
        requested = get_offer_requested_codes(conn, offer_id)
        preview_url = None
        if offer_codes:
            r = search_card_by_item_code(conn, offer_codes[0])
            if r: preview_url = dict(r).get("image_url")

    from Trade.ui.trade_embeds import build_offer_received_embed
    embed = build_offer_received_embed(
        offer_id=offer_id, sender_display=sender_display,
        item_codes=offer_codes, requested_codes=requested or None,
        preview_code=offer_codes[0] if offer_codes else None,
        preview_url=preview_url, index=0, total=len(offer_codes) or 1,
    )
    embed.set_footer(text=f"Offer {offer_id}  ·  {page+1} of {total} incoming offers")

    view = IncomingOfferPageView(db_path, user_id, rows, page)
    if edit_existing:
        await interaction.response.edit_message(embed=embed, view=view, content=None)
    else:
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class IncomingOfferPageView(discord.ui.View):
    def __init__(self, db_path, user_id: int, rows: list, page: int):
        super().__init__(timeout=120)
        self.db_path  = db_path
        self.user_id  = user_id
        self.rows     = rows
        self.page     = page
        self.prev_btn.disabled = page == 0
        self.next_btn.disabled = page >= len(rows) - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("These are not your offers.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _show_incoming_offers(interaction, _get_db_path(), self.user_id, self.rows, self.page - 1, edit_existing=True)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _show_incoming_offers(interaction, _get_db_path(), self.user_id, self.rows, self.page + 1, edit_existing=True)

    @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.success)
    async def accept_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        from Trade.services.trade_service import handle_offer_accepted
        await interaction.response.defer(ephemeral=True)
        await handle_offer_accepted(_get_db_path(), interaction, self.rows[self.page]["offer_id"])

    @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.danger)
    async def decline_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        from Trade.services.trade_service import handle_offer_declined
        await interaction.response.defer(ephemeral=True)
        await handle_offer_declined(_get_db_path(), interaction, self.rows[self.page]["offer_id"])


# ── Sent Offers ───────────────────────────────────────────────────────────────

async def _show_sent_offers(interaction: discord.Interaction, db_path, user_id: int, rows: list, page: int, edit_existing: bool = False):
    row   = rows[page]
    total = len(rows)
    offer_id     = row["offer_id"]
    receiver_id  = int(row["receiver_user_id"])
    offer_codes  = [c.strip() for c in row["offer_codes"].split(",")] if row.get("offer_codes") else []
    status       = row["status"]

    receiver_m = interaction.guild.get_member(receiver_id) if interaction.guild else None
    receiver_display = receiver_m.display_name if receiver_m else f"<@{receiver_id}>"

    status_colors = {"pending": 0xFAA61A, "accepted": 0x3BA55C, "declined": 0xED4245}
    status_emoji  = {"pending": "⏳", "accepted": "✅", "declined": "❌"}

    embed = discord.Embed(
        title=f"{status_emoji.get(status, '')} Sent Offer — {status.capitalize()}",
        color=status_colors.get(status, 0x87898C),
    )
    embed.add_field(name="To", value=receiver_display, inline=True)
    embed.add_field(name="Status", value=status.capitalize(), inline=True)
    embed.add_field(
        name="You Offered",
        value="\n".join(f"• `{c}`" for c in offer_codes) or "_none_",
        inline=False,
    )
    embed.set_footer(text=f"Offer {offer_id}  ·  {page+1} of {total} sent offers")

    view = SentOfferPageView(db_path, user_id, rows, page)
    if edit_existing:
        await interaction.response.edit_message(embed=embed, view=view, content=None)
    else:
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class SentOfferPageView(discord.ui.View):
    def __init__(self, db_path, user_id: int, rows: list, page: int):
        super().__init__(timeout=120)
        self.db_path = db_path
        self.user_id = user_id
        self.rows    = rows
        self.page    = page
        self.prev_btn.disabled   = page == 0
        self.next_btn.disabled   = page >= len(rows) - 1
        # Only allow cancel if the current offer is still pending
        self.cancel_btn.disabled = rows[page]["status"] != "pending"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("These are not your offers.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _show_sent_offers(interaction, _get_db_path(), self.user_id, self.rows, self.page - 1, edit_existing=True)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _show_sent_offers(interaction, _get_db_path(), self.user_id, self.rows, self.page + 1, edit_existing=True)

    @discord.ui.button(label="🗑 Cancel Offer", style=discord.ButtonStyle.danger)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        offer_id = self.rows[self.page]["offer_id"]
        db = _get_db_path()
        with db_session(db) as conn:
            from Trade.db.trade_db import resolve_offer
            rows_affected = resolve_offer(conn, offer_id, "declined")
        if rows_affected:
            await interaction.response.edit_message(
                content=f"Offer `{offer_id}` cancelled.", embed=None, view=None
            )
        else:
            await interaction.response.send_message("Could not cancel — offer may have already been resolved.", ephemeral=True)


# ── Listing Select (for edit / cancel when user has multiple listings) ────────

class ListingSelectView(discord.ui.View):
    def __init__(self, db_path, user_id: int, listings: list, mode: str):
        super().__init__(timeout=120)
        self.user_id = user_id
        options = []
        for row in listings[:25]:
            row = dict(row)
            codes = row.get("item_codes", "") or ""
            label = f"{codes[:50]}" if codes else row["listing_id"]
            lf    = row.get("looking_for") or "Open to offers"
            options.append(discord.SelectOption(
                label=label[:100], value=row["listing_id"],
                description=f"↳ {lf}"[:100],
            ))
        sel = discord.ui.Select(placeholder="Select a listing", options=options)

        async def callback(inter: discord.Interaction):
            listing_id = sel.values[0]
            listing    = next((dict(r) for r in listings if r["listing_id"] == listing_id), None)
            if mode == "cancel":
                await _confirm_cancel_listing(inter, _get_db_path(), user_id, listing)
            else:
                await _show_edit_listing(inter, _get_db_path(), user_id, listing)

        sel.callback = callback
        self.add_item(sel)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your listing.", ephemeral=True)
            return False
        return True


async def _confirm_cancel_listing(interaction: discord.Interaction, db_path, user_id: int, listing: dict):
    listing_id = listing["listing_id"]
    codes      = listing.get("item_codes", "") or ""
    embed = discord.Embed(
        title="Cancel Listing?",
        description=f"Listing `{listing_id}`\nCards: {codes}\n\nThis will remove the listing and any public announcement.",
        color=0xED4245,
    )
    view = ConfirmCancelListingView(db_path, user_id, listing_id)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class ConfirmCancelListingView(discord.ui.View):
    def __init__(self, db_path, user_id: int, listing_id: str):
        super().__init__(timeout=60)
        self.user_id    = user_id
        self.listing_id = listing_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Not your listing.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Yes, Cancel Listing", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = _get_db_path()
        with db_session(db) as conn:
            from Trade.db.trade_db import close_listing, get_listing_public_message, delete_listing_public_message
            pub = get_listing_public_message(conn, self.listing_id)
            close_listing(conn, self.listing_id)
            if pub:
                delete_listing_public_message(conn, self.listing_id)

        # Delete public announcement if it exists
        if pub and interaction.guild:
            try:
                ch  = interaction.guild.get_channel(int(pub["channel_id"])) or await interaction.guild.fetch_channel(int(pub["channel_id"]))
                msg = await ch.fetch_message(int(pub["message_id"]))
                await msg.delete()
            except Exception:
                pass

        # Refresh listings message
        try:
            from Trade.services.trade_service import refresh_trade_listings
            from Trade.db.trade_db import get_trade_channel_id
            with db_session(db) as conn:
                ch_id = get_trade_channel_id(conn, interaction.guild.id, self.user_id)
            if ch_id:
                ch = interaction.guild.get_channel(ch_id)
                if ch:
                    await refresh_trade_listings(db, ch, self.user_id)
        except Exception:
            pass

        await interaction.response.edit_message(
            content=f"Listing `{self.listing_id}` cancelled.", embed=None, view=None
        )

    @discord.ui.button(label="Never mind", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Cancelled.", embed=None, view=None)


# ── Edit Listing ──────────────────────────────────────────────────────────────

async def _show_edit_listing(interaction: discord.Interaction, db_path, user_id: int, listing: dict):
    """Open card picker pre-selected with current listing cards."""
    listing_id  = listing["listing_id"]
    current_lf  = listing.get("looking_for") or ""

    with db_session(db_path) as conn:
        from Trade.db.trade_db import get_listing_item_codes
        current_codes = get_listing_item_codes(conn, listing_id)

    async def on_cards_selected(inter: discord.Interaction, new_codes: list[str]):
        await inter.response.send_modal(
            EditListingLookingForModal(db_path, user_id, listing_id, new_codes, current_lf)
        )

    await _show_card_picker(
        interaction, db_path, user_id, user_id,
        max_values=3, title=f"Edit Listing — Select Cards",
        on_confirm=on_cards_selected, edit_existing=True,
    )


class EditListingLookingForModal(discord.ui.Modal, title="Edit Listing"):
    looking_for = discord.ui.TextInput(
        label="Looking For",
        placeholder="Alt art, specific codes, or open to offers",
        required=False, max_length=200, style=discord.TextStyle.short,
    )

    def __init__(self, db_path, user_id: int, listing_id: str, new_codes: list, current_lf: str):
        super().__init__()
        self.user_id    = user_id
        self.listing_id = listing_id
        self.new_codes  = new_codes
        self.looking_for.default = current_lf

    async def on_submit(self, interaction: discord.Interaction) -> None:
        db = _get_db_path()
        new_lf = str(self.looking_for).strip() or None
        with db_session(db) as conn:
            from Trade.db.trade_db import close_listing, get_listing_public_message, delete_listing_public_message
            pub = get_listing_public_message(conn, self.listing_id)
            close_listing(conn, self.listing_id)
            if pub:
                delete_listing_public_message(conn, self.listing_id)

        # Delete old public announcement
        if pub and interaction.guild:
            try:
                ch  = interaction.guild.get_channel(int(pub["channel_id"])) or await interaction.guild.fetch_channel(int(pub["channel_id"]))
                msg = await ch.fetch_message(int(pub["message_id"]))
                await msg.delete()
            except Exception:
                pass

        # Re-create listing with new cards + looking_for
        from Trade.services.trade_service import handle_create_listing
        await interaction.response.defer(ephemeral=True)
        await handle_create_listing(
            db, interaction, interaction.guild.id, self.user_id,
            self.new_codes, new_lf,
            announce_channel_id=None,  # announce_channel_id not available here — refresh will handle it
        )


# ── Looking For Modal (after card selection for listing) ─────────────────────

class LookingForModal(discord.ui.Modal, title="Create Listing"):
    looking_for = discord.ui.TextInput(
        label="Looking For",
        placeholder="Alt art, specific codes, or open to offers",
        required=False, max_length=200, style=discord.TextStyle.short,
    )

    def __init__(self, db_path: Path, guild_id: int, user_id: int, item_codes: list[str], announce_channel_id: Optional[int]):
        super().__init__()
        self.guild_id          = guild_id
        self.user_id           = user_id
        self.item_codes        = item_codes
        self.announce_channel_id = announce_channel_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        from Trade.services.trade_service import handle_create_listing
        await interaction.response.defer(ephemeral=True)
        await handle_create_listing(
            _get_db_path(), interaction, self.guild_id, self.user_id,
            self.item_codes, str(self.looking_for).strip() or None,
            self.announce_channel_id,
        )
