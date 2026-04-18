import discord

def build_claim_view(item_code: str) -> discord.ui.View:
    item_code = item_code.strip().upper()

    view = discord.ui.View(timeout=None)

    button = discord.ui.Button(
        label="⬆ Claim",
        style=discord.ButtonStyle.success,
        custom_id=f"claim:{item_code}",
        disabled=False,
    )

    view.add_item(button)
    return view