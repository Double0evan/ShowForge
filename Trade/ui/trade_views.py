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
    get_user_cards_all,
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
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your trade channel.", ephemeral=True)
            return False
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
    Shows a paginated select of `owner_user_id`'s cards.
    On confirm, calls `on_confirm(interaction, selected_codes)`.
    Used for both listing and offer flows.
    """
    def __init__(
        self,
        all_rows: list,
        owner_user_id: int,
        actor_user_id: int,
        page: int,
        max_values: int,
        title: str,
        on_confirm,           # async callable(interaction, codes)
        selected: list[str] | None = None,
    ):
        super().__init__(timeout=120)
        self.all_rows      = all_rows
        self.owner_user_id = owner_user_id
        self.actor_user_id = actor_user_id
        self.page          = page
        self.max_values    = max_values
        self.title         = title
        self.on_confirm    = on_confirm
        self._selected     = list(selected or [])

        total_pages = max(1, math.ceil(len(all_rows) / PAGE_SIZE))
        page_rows   = all_rows[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]

        self._select = CardPickerSelect(page_rows, self._selected, f"Select card(s) — page {page+1}/{total_pages}", max_values)
        self.add_item(self._select)

        self.prev_btn.disabled = page == 0
        self.next_btn.disabled = (page + 1) * PAGE_SIZE >= len(all_rows)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.actor_user_id:
            await interaction.response.send_message("This picker is not for you.", ephemeral=True)
            return False
        return True

    def _rebuild(self, new_page: int) -> "CardPickerView":
        # Merge any newly selected values into running selection
        merged = list(set(self._selected + list(self._select.values)))
        return CardPickerView(
            self.all_rows, self.owner_user_id, self.actor_user_id,
            new_page, self.max_values, self.title, self.on_confirm, merged,
        )

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, row=1)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(view=self._rebuild(self.page - 1))

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary, row=1)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(view=self._rebuild(self.page + 1))

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.success, row=1)
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        merged = list(set(self._selected + list(self._select.values)))
        if not merged:
            await interaction.response.send_message("Select at least one card first.", ephemeral=True)
            return
        if len(merged) > self.max_values:
            await interaction.response.send_message(f"Select at most {self.max_values} card(s).", ephemeral=True)
            return
        await self.on_confirm(interaction, merged)

    @discord.ui.button(label="✕ Cancel", style=discord.ButtonStyle.danger, row=1)
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

    embed = discord.Embed(title=title, color=0x5865F2)
    embed.description = f"{'Up to ' + str(max_values) + ' cards' if max_values > 1 else '1 card'} — use ◀ ▶ to page if needed, then ✅ Confirm."
    view = CardPickerView(rows, owner_user_id, actor_user_id, 0, max_values, title, on_confirm)

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
        await interaction.response.send_message("Incoming offers — coming soon.", ephemeral=True)

    @discord.ui.button(label="View Sent", style=discord.ButtonStyle.secondary, row=0, custom_id="trade_listings_view_sent")
    async def view_sent(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message("Sent offers — coming soon.", ephemeral=True)

    @discord.ui.button(label="Edit Listing", style=discord.ButtonStyle.secondary, row=1, custom_id="trade_listings_edit_listing")
    async def edit_listing(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message("Edit listing — coming soon.", ephemeral=True)

    @discord.ui.button(label="Cancel Listing", style=discord.ButtonStyle.danger, row=1, custom_id="trade_listings_cancel_listing")
    async def cancel_listing(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message("Cancel listing — coming soon.", ephemeral=True)


# ── Offer Response ────────────────────────────────────────────────────────────

class TradeOfferResponseView(discord.ui.View):
    def __init__(self, db_path: Path, offer_id: str, receiver_user_id: int, item_codes: Optional[list[str]] = None, preview_urls: Optional[list[Optional[str]]] = None, page: int = 0, sender_display: str = "Unknown"):
        super().__init__(timeout=None)
        self.offer_id         = offer_id
        self.receiver_user_id = receiver_user_id
        self.item_codes       = item_codes or []
        self.preview_urls     = preview_urls or []
        self.page             = page
        self.sender_display   = sender_display
        has_pages             = len(self.item_codes) > 1
        self.prev.disabled    = not has_pages or page == 0
        self.next.disabled    = not has_pages or page >= len(self.item_codes) - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.receiver_user_id:
            await interaction.response.send_message("This offer is not addressed to you.", ephemeral=True)
            return False
        return True

    async def _update_page(self, interaction: discord.Interaction, new_page: int):
        from Trade.ui.trade_embeds import build_offer_received_embed
        code  = self.item_codes[new_page] if self.item_codes else None
        image = self.preview_urls[new_page] if self.preview_urls and new_page < len(self.preview_urls) else None
        embed = build_offer_received_embed(offer_id=self.offer_id, sender_display=self.sender_display, item_codes=self.item_codes, preview_code=code, preview_url=image, index=new_page, total=len(self.item_codes) or 1)
        await interaction.response.edit_message(embed=embed, view=TradeOfferResponseView(None, self.offer_id, self.receiver_user_id, self.item_codes, self.preview_urls, page=new_page, sender_display=self.sender_display))

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary, row=0, custom_id="trade_offer_prev")
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button): await self._update_page(interaction, self.page - 1)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, row=0, custom_id="trade_offer_next")
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button): await self._update_page(interaction, self.page + 1)

    @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.success, row=1, custom_id="trade_offer_accept")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        from Trade.services.trade_service import handle_offer_accepted
        await interaction.response.defer(ephemeral=True)
        await handle_offer_accepted(_get_db_path(), interaction, self.offer_id)

    @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.danger, row=1, custom_id="trade_offer_decline")
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        from Trade.services.trade_service import handle_offer_declined
        await interaction.response.defer(ephemeral=True)
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

        if owner_id and str(owner_id) != str(self.user_id):
            # Attach a Make Offer button to the card detail embed
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
