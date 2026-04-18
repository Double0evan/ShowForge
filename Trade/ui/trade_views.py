"""
Trade/ui/trade_views.py

Discord UI Views and Modals for the trade system.
V3 pattern: no cog reference — Views receive db_path and config directly.

PERSISTENT MESSAGE LAYOUT (2 messages per channel):
  TradeHomeView    → MSG_HOME    (stats + binder, always present)
  TradeListingsView → MSG_LISTINGS (listings/offers, posted on first My Offers tap)

Everything else is ephemeral.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import discord

from Trade.ui.trade_embeds import build_card_detail_embed
from Trade.db.trade_db import search_card_by_item_code


# ---------------------------------------------------------------------------
# Owner-only guard mixin
# ---------------------------------------------------------------------------

class OwnerOnlyMixin:
    user_id: int

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This is not your trade channel.", ephemeral=True
            )
            return False
        return True


# ---------------------------------------------------------------------------
# Home view (combined stats + binder)
# Row 0: prev page / next page navigation
# Row 1: actions — Create Listing, Find Card, My Offers
# ---------------------------------------------------------------------------

class TradeHomeView(OwnerOnlyMixin, discord.ui.View):
    def __init__(
        self,
        db_path: Path,
        guild_id: int,
        user_id: int,
        page: int,
        total_pages: int,
        announce_channel_id: Optional[int] = None,
    ):
        super().__init__(timeout=None)
        self.db_path             = db_path
        self.guild_id            = guild_id
        self.user_id             = user_id
        self.page                = page
        self.total_pages         = total_pages
        self.announce_channel_id = announce_channel_id

        # Disable nav buttons at boundaries
        self.prev_page.disabled = page == 0
        self.next_page.disabled = page >= total_pages - 1

    # ── Row 0: binder navigation ────────────────────────────────────────────

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary, row=0)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        from Trade.services.trade_service import refresh_trade_home
        await interaction.response.defer()
        await refresh_trade_home(
            self.db_path, interaction.channel, self.user_id,
            page=self.page - 1, announce_channel_id=self.announce_channel_id,
        )

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, row=0)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        from Trade.services.trade_service import refresh_trade_home
        await interaction.response.defer()
        await refresh_trade_home(
            self.db_path, interaction.channel, self.user_id,
            page=self.page + 1, announce_channel_id=self.announce_channel_id,
        )

    # ── Row 1: actions ───────────────────────────────────────────────────────

    @discord.ui.button(label="Create Listing", style=discord.ButtonStyle.success, row=1)
    async def create_listing(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(
            CreateListingModal(self.db_path, self.guild_id, self.user_id, self.announce_channel_id)
        )

    @discord.ui.button(label="Find Card", style=discord.ButtonStyle.secondary, row=1)
    async def find_card(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(
            FindCardOwnerModal(self.db_path, self.user_id)
        )

    @discord.ui.button(label="My Offers", style=discord.ButtonStyle.primary, row=1)
    async def my_offers(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        from Trade.services.trade_service import refresh_trade_listings
        await interaction.response.defer(ephemeral=True)
        await refresh_trade_listings(self.db_path, interaction.channel, self.user_id)
        await interaction.followup.send("Listings updated below.", ephemeral=True)


# ---------------------------------------------------------------------------
# Listings view (second persistent message, shown on demand)
# ---------------------------------------------------------------------------

class TradeListingsView(OwnerOnlyMixin, discord.ui.View):
    def __init__(self, db_path: Path, user_id: int):
        super().__init__(timeout=None)
        self.db_path = db_path
        self.user_id = user_id

    @discord.ui.button(label="View Incoming", style=discord.ButtonStyle.primary, row=0)
    async def view_incoming(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        # TODO: paginated ephemeral incoming offers list
        await interaction.response.send_message("Incoming offers — coming soon.", ephemeral=True)

    @discord.ui.button(label="View Sent", style=discord.ButtonStyle.secondary, row=0)
    async def view_sent(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        # TODO: paginated ephemeral sent offers list
        await interaction.response.send_message("Sent offers — coming soon.", ephemeral=True)

    @discord.ui.button(label="Edit Listing", style=discord.ButtonStyle.secondary, row=1)
    async def edit_listing(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        # TODO: select listing → edit flow
        await interaction.response.send_message("Edit listing — coming soon.", ephemeral=True)

    @discord.ui.button(label="Cancel Listing", style=discord.ButtonStyle.danger, row=1)
    async def cancel_listing(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        # TODO: select listing → cancel flow
        await interaction.response.send_message("Cancel listing — coming soon.", ephemeral=True)


# ---------------------------------------------------------------------------
# Offer response view (posted in recipient's channel, not persistent)
# ---------------------------------------------------------------------------

class TradeOfferResponseView(discord.ui.View):
    def __init__(self, db_path: Path, offer_id: str, receiver_user_id: int):
        super().__init__(timeout=None)
        self.db_path          = db_path
        self.offer_id         = offer_id
        self.receiver_user_id = receiver_user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.receiver_user_id:
            await interaction.response.send_message(
                "This offer is not addressed to you.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.success, row=0)
    async def accept_offer(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        from Trade.services.trade_service import handle_offer_accepted
        await interaction.response.defer()
        await handle_offer_accepted(self.db_path, interaction, self.offer_id)

    @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.danger, row=0)
    async def decline_offer(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        from Trade.services.trade_service import handle_offer_declined
        await interaction.response.defer()
        await handle_offer_declined(self.db_path, interaction, self.offer_id)


# ---------------------------------------------------------------------------
# Make Offer inline view (ephemeral card search result)
# ---------------------------------------------------------------------------

class MakeOfferView(discord.ui.View):
    def __init__(
        self,
        db_path: Path,
        sender_user_id: int,
        target_item_code: str,
        receiver_user_id: int,
        listing_id: Optional[str] = None,
    ):
        super().__init__(timeout=120)
        self.db_path          = db_path
        self.sender_user_id   = sender_user_id
        self.target_item_code = target_item_code
        self.receiver_user_id = receiver_user_id
        self.listing_id       = listing_id

    @discord.ui.button(label="Make Offer", style=discord.ButtonStyle.success)
    async def make_offer(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(
            MakeOfferModal(
                self.db_path,
                self.sender_user_id,
                self.target_item_code,
                self.receiver_user_id,
                self.listing_id,
            )
        )


# ---------------------------------------------------------------------------
# Modals
# ---------------------------------------------------------------------------

class FindCardOwnerModal(discord.ui.Modal, title="Find Card Owner"):
    item_code_input = discord.ui.TextInput(
        label="Item Code",
        placeholder="e.g. N001 or S042",
        required=True,
        max_length=10,
    )

    def __init__(self, db_path: Path, user_id: int):
        super().__init__()
        self.db_path = db_path
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        from Core.db import db_session
        item_code = str(self.item_code_input).strip().upper()

        with db_session(self.db_path) as conn:
            row = search_card_by_item_code(conn, item_code)

        if not row:
            await interaction.response.send_message(
                f"Card `{item_code}` not found.", ephemeral=True
            )
            return

        owner_discord_id = row["owner_discord_user_id"]
        if owner_discord_id:
            owner_member  = interaction.guild.get_member(int(owner_discord_id)) if interaction.guild else None
            owner_display = owner_member.mention if owner_member else f"<@{owner_discord_id}>"
        else:
            owner_display = row.get("owner_display_name") or "Unknown / Unclaimed"

        embed = build_card_detail_embed(row=row, owner_display=owner_display)

        if owner_discord_id and int(owner_discord_id) != self.user_id:
            view = MakeOfferView(self.db_path, self.user_id, item_code, int(owner_discord_id))
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)


class CreateListingModal(discord.ui.Modal, title="Create Listing"):
    item_codes_input = discord.ui.TextInput(
        label="Item Code(s)",
        placeholder="1–3 codes, comma separated — e.g. N001, N044",
        required=True,
        max_length=50,
    )
    looking_for = discord.ui.TextInput(
        label="Looking For",
        placeholder="Alt art, specific codes, or open to offers",
        required=False,
        max_length=200,
        style=discord.TextStyle.short,
    )

    def __init__(
        self,
        db_path: Path,
        guild_id: int,
        user_id: int,
        announce_channel_id: Optional[int],
    ):
        super().__init__()
        self.db_path             = db_path
        self.guild_id            = guild_id
        self.user_id             = user_id
        self.announce_channel_id = announce_channel_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        from Trade.services.trade_service import handle_create_listing

        raw        = str(self.item_codes_input).strip().upper()
        item_codes = [c.strip() for c in raw.split(",") if c.strip()]

        if not 1 <= len(item_codes) <= 3:
            await interaction.response.send_message(
                "Please enter between 1 and 3 item codes.", ephemeral=True
            )
            return

        looking_for = str(self.looking_for).strip() or None
        await interaction.response.defer(ephemeral=True)
        await handle_create_listing(
            self.db_path, interaction, self.guild_id, self.user_id,
            item_codes, looking_for, self.announce_channel_id,
        )


class MakeOfferModal(discord.ui.Modal, title="Make Offer"):
    item_codes_input = discord.ui.TextInput(
        label="Your Item Code(s) to Offer",
        placeholder="1–3 codes, comma separated — e.g. N055, N078",
        required=True,
        max_length=50,
    )

    def __init__(
        self,
        db_path: Path,
        sender_user_id: int,
        target_item_code: str,
        receiver_user_id: int,
        listing_id: Optional[str] = None,
    ):
        super().__init__()
        self.db_path          = db_path
        self.sender_user_id   = sender_user_id
        self.target_item_code = target_item_code
        self.receiver_user_id = receiver_user_id
        self.listing_id       = listing_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        from Trade.services.trade_service import handle_send_offer

        raw        = str(self.item_codes_input).strip().upper()
        item_codes = [c.strip() for c in raw.split(",") if c.strip()]

        if not 1 <= len(item_codes) <= 3:
            await interaction.response.send_message(
                "Please enter between 1 and 3 item codes.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        await handle_send_offer(
            self.db_path, interaction,
            self.sender_user_id, self.receiver_user_id,
            item_codes, self.listing_id,
        )
