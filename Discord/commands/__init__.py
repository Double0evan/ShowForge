"""
Discord/commands/__init__.py

Central registration point for all slash command groups.
To add a new command group:
  1. Create Discord/commands/yourfeature.py with a register(tree, core, ...) function
  2. Import and call it here
"""

from discord import app_commands
from Discord.commands import staff


def register_all(
    tree: app_commands.CommandTree,
    core,
    build_claim_view,
    catalog_channel_id_for,
    **kwargs,
):
    staff.register(
        tree=tree,
        core=core,
        build_claim_view=build_claim_view,
        catalog_channel_id_for=catalog_channel_id_for,
    )
    # Future:
    # from Discord.commands import trade
    # trade.register(tree=tree, core=core, **kwargs)
