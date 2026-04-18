# V3 Bot — Whatnot Show Manager

Staff control panel + Discord bot for managing live shows:
watermarking, inventory, voucher credits, and item claiming.

## Structure

```
V3_Bot/
├── run.py                        # Launcher — starts all 3 processes
├── requirements.txt
├── Core/                         # Business logic (no Discord, no HTTP)
│   ├── schema.sql                # SQLite schema (per-show DB)
│   ├── db.py                     # DB connection + migrations
│   ├── show_manager.py           # Show creation + active show pointer
│   ├── show_service.py           # require_active_show() helper
│   ├── show_settings_service.py  # Per-show key/value settings
│   ├── inventory_service.py      # Item codes + status
│   ├── media_service.py          # Discord attachment URL storage
│   ├── claim_service.py          # Claim creation + removal (FIFO)
│   ├── voucher_service.py        # Credit ledger (+1/-1)
│   ├── user_service.py           # Guest merge utilities
│   └── normalize.py              # Name normalization for matching
├── Discord/
│   ├── bot.py                    # Main bot — events, claim buttons, API
│   ├── bot_instance.py           # Shared discord.Client instance
│   ├── core_client.py            # HTTP client for the backend API
│   ├── member_cache.py           # In-memory guild member cache
│   ├── ui_components.py          # Reusable Discord UI (claim button)
│   └── commands/                 # Slash command groups
│       ├── __init__.py           # register_all() — add new groups here
│       └── staff.py              # /award, /publish_wm
├── Backend/
│   ├── main.py                   # FastAPI app (port 8000)
│   ├── routes/
│   │   ├── ui.py                 # All /ui/* routes + console
│   │   └── members.py            # /ui/members routes
│   ├── services/
│   │   └── publish_service.py    # Publish item to catalog channel
│   └── ui/
│       └── templates/
│           └── index.html        # Jinja2 template — all 8 pages
├── Watcher/
│   ├── watcher_service.py        # File watcher + watermark + upload
│   └── watcher_logger.py         # Log file + heartbeat
├── Config/
│   └── settings.example.json     # Example config (no secrets)
└── DB/                           # Created at runtime
    ├── active_show.json
    └── shows/<show_id>/show.db
```

## Quick Start

1. **Install dependencies**
   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure** — copy `Discord/.env.example` to `Discord/.env` and fill in your values

3. **Launch everything**
   ```
   python run.py
   ```
   This opens three terminal windows (Backend, Bot, Watcher) and your browser.

## Adding a New Feature

**New slash command group:**
1. Create `Discord/commands/yourfeature.py` with a `register(tree, core, ...)` function
2. Add it to `Discord/commands/__init__.py` → `register_all()`

**New backend route:**
1. Create `Backend/routes/yourfeature.py` with an `APIRouter`
2. Include it in `Backend/main.py`

**New UI page:**
1. Add `{% if page == 'yourpage' %}` block to `index.html`
2. Add nav link in the sidebar
3. Add a route in `Backend/routes/ui.py`

**New Core service:**
1. Create `Core/yourfeature_service.py`
2. Add any new tables to `Core/schema.sql`
3. Wire up API endpoints in `Backend/main.py`
