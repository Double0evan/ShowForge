# Trade System V1 — V3 Integration Package

## Folder Layout

Drop the entire `Trade/` folder into your `V3_Bot/` root alongside `Core/`, `Discord/`, etc.

```
V3_Bot/
├── Core/
├── Discord/
├── Trade/               ← drop here
│   ├── db/
│   │   └── trade_db.py
│   ├── services/
│   │   └── trade_service.py
│   ├── ui/
│   │   ├── trade_embeds.py
│   │   └── trade_views.py
│   └── trade_hook.py
└── ...
```

## Integration Steps

### 1. Add env vars to `Discord/.env`

```
TRADE_CATEGORY_ID=<Discord category channel ID for private trade channels>
TRADE_ANNOUNCE_CHANNEL_ID=<public channel ID for listing announcements>  # optional
```

### 2. Add env reads to `Discord/bot.py`

In the env block near the top of `bot.py`:

```python
TRADE_CATEGORY_ID         = get_int_env("TRADE_CATEGORY_ID", 0)
TRADE_ANNOUNCE_CHANNEL_ID = get_int_env("TRADE_ANNOUNCE_CHANNEL_ID", 0)
```

### 3. Import and init in `Discord/bot.py`

```python
from Trade.trade_hook import init_trade_tables, register_trade_commands, on_item_assigned_trade
```

### 4. Init trade tables when a show opens

Wherever your bot opens/switches the active show DB, add:

```python
init_trade_tables(active_db_path)
```

### 5. Register slash commands in `on_ready()`

Add before `tree.sync()`:

```python
if TRADE_CATEGORY_ID:
    register_trade_commands(
        tree,
        db_path=active_db_path,
        trade_category_id=TRADE_CATEGORY_ID,
        announce_channel_id=TRADE_ANNOUNCE_CHANNEL_ID or None,
    )
```

### 6. Hook into item assignment

After a card is claimed/assigned, call:

```python
await on_item_assigned_trade(
    db_path=active_db_path,
    guild=guild,
    member=member,
    trade_category_id=TRADE_CATEGORY_ID,
    announce_channel_id=TRADE_ANNOUNCE_CHANNEL_ID or None,
)
```

## DB Schema Notes

Trade tables are added to the **same show DB** as your existing schema. They do not conflict with any existing table. The trade system reads from these existing V3 tables (read-only):

| Table | Columns used |
|---|---|
| `inventory_items` | `item_code`, `status`, `post_mode` |
| `claims` | `item_code`, `user_id`, `removed_at` |
| `users` | `discord_user_id`, `display_name` |
| `media_assets` | `item_code`, `variant`, `attachment_url` |

## What's Still Stubbed / TODO

| Feature | File | Notes |
|---|---|---|
| `swap_card_ownership_for_offer` | `Trade/db/trade_db.py` | Ownership model TBD — needs UPDATE on `claims` |
| Sent offer count | `Trade/services/trade_service.py` | Returns 0 |
| View Incoming / View Sent pages | `Trade/ui/trade_views.py` | Buttons present, content stub |
| Edit / Cancel Listing | `Trade/ui/trade_views.py` | Buttons present, content stub |

## Slash Commands Added

| Command | Description |
|---|---|
| `/trade_open [@member]` | Open/refresh all 3 persistent messages in trade channel |
| `/trade_refresh [@member]` | Force-refresh all 3 persistent messages |
