"""
Discord/commands/staff.py

Staff slash commands:
  /award      — give claim credits to a member
  /publish_wm — manually publish a watermarked item to catalog
"""

import io
import asyncio
import requests

import discord
from discord import app_commands


def register(
    tree: app_commands.CommandTree,
    core,
    build_claim_view,
    catalog_channel_id_for,
):
    @tree.command(name="award", description="Give claim credits to a member (staff)")
    @app_commands.describe(user="Member to award", amount="Number of credits")
    async def award(interaction: discord.Interaction, user: discord.Member, amount: int):
        if amount <= 0:
            await interaction.response.send_message("Amount must be > 0", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            internal_user_id, _ = core.upsert_discord_user(user.id, user.display_name)
            for _ in range(amount):
                core.award_voucher(internal_user_id, "STAFF_ADJUST", "Discord /award")
        except Exception as e:
            print(f"AWARD ERROR: {e}")
            await interaction.followup.send("❌ Error awarding credits", ephemeral=True)
            return

        await interaction.followup.send(
            f"✅ Gave {amount} credit(s) to {user.display_name}", ephemeral=True
        )

    async def _download_bytes(url: str) -> bytes:
        def _do():
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            return r.content
        return await asyncio.to_thread(_do)

    @tree.command(name="publish_wm", description="Publish watermarked item to catalog (staff)")
    @app_commands.describe(item_code="e.g. S001 or N001", rating="sfw or nsfw")
    async def publish_wm(interaction: discord.Interaction, item_code: str, rating: str):
        item_code = item_code.strip().upper()
        rating    = rating.strip().lower()

        if rating not in ("sfw", "nsfw"):
            await interaction.response.send_message("Rating must be 'sfw' or 'nsfw'", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            wm = core.get_media(item_code=item_code, variant="watermarked", rating=rating)
        except Exception as e:
            await interaction.followup.send(f"❌ Backend error: {e}", ephemeral=True)
            return

        if not wm or not wm.get("attachment_url"):
            await interaction.followup.send(
                f"❌ No watermarked media found for **{item_code}** ({rating}).", ephemeral=True
            )
            return

        try:
            data = await _download_bytes(wm["attachment_url"])
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to download image: {e}", ephemeral=True)
            return

        try:
            channel_id = catalog_channel_id_for(rating)
            channel    = interaction.client.get_channel(channel_id) or await interaction.client.fetch_channel(channel_id)
            filename   = wm.get("filename") or f"{item_code}.jpg"
            await channel.send(
                content=f"**{item_code}**",
                file=discord.File(fp=io.BytesIO(data), filename=filename),
                view=build_claim_view(item_code),
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to post to catalog: {e}", ephemeral=True)
            return

        await interaction.followup.send(
            f"✅ Published **{item_code}** to catalog ({rating}).", ephemeral=True
        )
