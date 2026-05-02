"""
Discord/publish_direct.py

Standalone async publish function used by bin_listener to post items
to the catalog channel without going through the HTTP API (avoids deadlock).
Imported at call time — not at module load — to prevent circular imports.
"""
from __future__ import annotations
import os
import discord


async def publish_item_direct(item_code: str, show_mode: str = "standard") -> dict:
    """
    Posts the watermarked image to the correct catalog channel.
    Called directly as a coroutine from bin_listener — no HTTP round-trip.
    """
    from dotenv import dotenv_values
    from pathlib import Path
    from Discord.bot_instance import client
    from Discord.core_client import CoreClient
    from Discord.ui_components import build_claim_view

    _ENV_PATH = Path(__file__).resolve().parent / ".env"
    env_vals   = dotenv_values(_ENV_PATH)

    BACKEND_BASE_URL = os.getenv("BACKEND_URL") or os.getenv("BACKEND_BASE_URL") or "http://127.0.0.1:8000"
    core = CoreClient(BACKEND_BASE_URL)

    rating  = "nsfw" if item_code.startswith("N") else "sfw"
    env_key = "CATALOG_NSFW_CHANNEL_ID" if rating == "nsfw" else "CATALOG_SFW_CHANNEL_ID"
    raw     = (env_vals.get(env_key) or os.getenv(env_key, "0") or "0").strip().strip("'").strip('"')
    channel_id = int(raw) if raw.isdigit() else 0

    if not channel_id:
        return {"ok": False, "error": f"{env_key} not configured"}

    try:
        wm = core.get_media(item_code=item_code, variant="watermarked", rating=rating)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    if not wm or not wm.get("attachment_url"):
        return {"ok": False, "error": "No watermarked media found for this item"}

    channel = client.get_channel(channel_id) or await client.fetch_channel(channel_id)

    embed = discord.Embed(title=item_code, color=0x2b2d31)
    embed.set_image(url=wm["attachment_url"])

    if show_mode == "bin":
        msg = await channel.send(embed=embed)
    else:
        msg = await channel.send(embed=embed, view=build_claim_view(item_code))

    return {"ok": True, "message_id": msg.id}
