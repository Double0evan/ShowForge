V3_Bot — Project Brief for Claude Code
What This Is
A modular system for managing live collectible card shows:

Staff upload images → watcher watermarks them → uploads to private Discord threads
Staff publish items to a public Discord catalog channel
Discord users claim items by clicking a button (Surprise Set mode)
OR items are posted display-only with no claim button (Bin Show mode)
Per-show SQLite databases, full audit trail, voucher/credit system

Architecture
V3_Bot/
├── run.py / run.bat           # Launcher — starts all 3 processes
├── requirements.txt
├── Core/                      # Pure business logic, no Discord/HTTP
│   ├── schema.sql             # SQLite schema
│   ├── db.py                  # Connection, migrations, WAL mode
│   ├── show_manager.py        # Show creation, active show pointer
│   ├── show_service.py        # require_active_show() helper
│   ├── show_settings_service.py
│   ├── inventory_service.py
│   ├── media_service.py
│   ├── claim_service.py       # FIFO voucher spend, race condition handling
│   ├── voucher_service.py
│   ├── user_service.py
│   └── normalize.py
├── Discord/
│   ├── bot.py                 # Discord client + FastAPI internal API (port 8001)
│   ├── bot_instance.py        # Shared discord.Client instance
│   ├── core_client.py         # HTTP client → backend API (port 8000)
│   ├── member_cache.py        # In-memory guild member cache
│   ├── ui_components.py       # Claim button view
│   └── commands/
│       ├── __init__.py        # register_all() — add new groups here
│       └── staff.py           # /award, /publish_wm slash commands
├── Backend/
│   ├── main.py                # FastAPI port 8000
│   ├── routes/
│   │   ├── ui.py              # All /ui/* routes
│   │   └── members.py         # /ui/members routes
│   ├── services/
│   │   └── publish_service.py # Publish item → bot API → Discord
│   └── ui/templates/
│       └── index.html         # Jinja2 — 8-page dark theme UI
├── Watcher/
│   ├── watcher_service.py     # File watcher, watermark, Discord upload
│   └── watcher_logger.py      # Log file + heartbeat
└── DB/                        # Runtime
    ├── active_show.json
    └── shows/<show_id>/show.db
Three Separate Processes
ProcessPortDescriptionBackend (uvicorn)8000FastAPI — UI routes, business logic APIBot (discord.py)8001Discord client + internal bot APIWatcher—File watcher, watermark, upload pipeline
Critical: Backend and Bot are separate processes. The backend has NO Discord connection. All Discord operations must go through the bot's API on port 8001.
The Core Bug — Async/Event Loop Deadlock
This is the #1 priority fix.
The bot runs discord.Client on the main thread's asyncio event loop. It also starts a FastAPI/uvicorn server in a daemon thread (threading.Thread(target=run_api)). Uvicorn creates its own event loop in that thread.
The bot API endpoints need to submit coroutines to the Discord event loop. Current approach:
python_discord_loop = None  # set in on_ready

future = asyncio.run_coroutine_threadsafe(coro, _discord_loop)
result = future.result(timeout=20)  # DEADLOCKS
This deadlocks because:

If the endpoint is async def → runs on uvicorn's loop → future.result() blocks uvicorn's loop → deadlock
If the endpoint is def (sync) → runs in threadpool → BUT _discord_loop may not be set correctly

Affected endpoints in Discord/bot.py:

POST /publish — publish item to Discord catalog channel
POST /new_show — create archival claim threads
POST /watcher/start — write flag file (should not need Discord at all)

The correct fix: Store client.loop (not asyncio.get_event_loop()) in on_ready, make affected endpoints def (sync, runs in threadpool), use run_coroutine_threadsafe(coro, client.loop).result().
Known Issues (Priority Order)
1. Discord loop deadlock [BLOCKING]
See above. /publish and /new_show hang. Fix by:

Replace _discord_loop = asyncio.get_event_loop() with _discord_loop = client.loop
Ensure affected endpoints are def not async def
/watcher/start and /watcher/stop just write a file — remove Discord dependency entirely

2. Publish fails [blocked by #1]
POST /publish in bot.py reaches the channel_id print but never completes the send. Deadlock.
3. New Show threads not created [blocked by #1]
POST /new_show in bot.py creates the show DB fine but Discord thread creation deadlocks.
4. Watcher Start/Stop [minor, partially blocked by #1]
Flag file approach is correct. /watcher/start and /watcher/stop just write "1" or "0" to logs/watcher_process.flag. These should be pure sync file operations with no Discord involvement — remove any Discord loop usage from them.
5. End Show not confirmed working
POST /ui/show/end — need to verify. Likely a separate issue from the loop deadlock.
6. Watcher auto-processes without Start button
The watcher starts with processing_enabled = False and polls a flag file every 3s. Needs end-to-end test once #1 is fixed.
7. Item numbering doesn't reset on new show
StateDB in watcher_service.py should be keyed by active show_id from the backend. Code is in but untested.
8. Discord CDN image previews expire
media_assets.attachment_url stores Discord CDN URLs which expire. Inventory page shows broken images after ~24hrs. Options: re-fetch on demand, or store local file paths as fallback.
9. Stat cards show spinners instead of numbers
In index.html, "In Catalog" and "Claimed" stat cards. Jinja2 filter on published_at or status field returning null/unexpected type.
10. UI polish

Removed items show Publish button (should be hidden)
Publish button label inconsistent across items
Console new_show command doesn't set show_type

Key Data Flows
Watcher Pipeline
INBOX/SFW or INBOX/NSFW (file dropped)
  → watcher picks up (only if flag file = "1")
  → assign code (N### or S###) from StateDB
  → move to show folder RAW
  → watermark → Watermarked folder
  → upload RAW to private Discord thread → upsert media_assets
  → upload WM to private Discord thread → upsert media_assets
  → POST /inventory/upsert (creates inventory_items row)
  → if WATCHER_POST_MODE=auto: post to catalog with claim button
  → if WATCHER_POST_MODE=display: post to catalog, no claim button
  → if WATCHER_POST_MODE=hold: do nothing (manual publish)
Publish Flow (manual)
UI "Publish to Catalog" button
  → POST /ui/publish (backend)
  → publish_service.py checks item status + media exists
  → POST http://127.0.0.1:8001/publish (bot API)
  → bot fetches channel, sends message (with or without claim button based on post_mode)
  → backend stamps published_at
Claim Flow
User clicks claim button in Discord
  → on_interaction in bot.py
  → verify role check
  → upsert user
  → POST /claims/attempt (backend)
  → claim_service.create_claim (FIFO voucher spend, race condition guarded)
  → fetch RAW media → post to archival thread
  → delete catalog message
Show Types
Set at show creation, stored in show_settings DB and written to .env:

Surprise Set → WATCHER_POST_MODE=auto (claim button shown)
Bin Show → WATCHER_POST_MODE=display (display only, no claim button)

post_mode column on inventory_items tracks per-item whether it was posted as claim or display.
Environment Variables (Discord/.env)
DISCORD_TOKEN=
GUILD_ID=
VERIFIED_ROLE_ID=
VERIFY_CHANNEL_ID=
CATALOG_SFW_CHANNEL_ID=
CATALOG_NSFW_CHANNEL_ID=
CLAIMS_SFW_CHANNEL_ID=
CLAIMS_NSFW_CHANNEL_ID=
UPLOAD_THREAD_RAW_SFW=
UPLOAD_THREAD_WM_SFW=
UPLOAD_THREAD_RAW_NSFW=
UPLOAD_THREAD_WM_NSFW=
WATCHER_PARENT_DIR=
WM_TEMPLATE_SFW=
WM_TEMPLATE_NSFW=
WATCHER_POST_MODE=hold  # hold | display | auto
Schema (Core/schema.sql)
Key tables:

users — discord/pending/guest/merged kinds
inventory_items — item codes, status, post_mode, published_at
media_assets — Discord attachment URLs (RAW + watermarked)
voucher_ledger — FIFO credit system (+1/-1 rows, never edited)
claims — active and removed claims with audit trail
show_settings — per-show key/value (thread IDs, show_type, post_mode)

What's Working

Watcher file detection and watermarking
Private Discord thread uploads (RAW + WM)
Inventory registration and display in UI
Show creation (DB side)
Member cache and guild member loading
Claims flow (when publish works)
Voucher FIFO accounting
UI layout (8 pages, dark theme)
Settings page with env editing
History page (read-only past shows)
Console with autocomplete

What's NOT Working

/publish endpoint (deadlock)
/new_show Discord thread creation (deadlock)
Watcher start/stop button (needs clean test)
End show (unconfirmed)

After every bug fix, you must run the relevant test or manually reproduce the issue before telling me it's fixed. Do not return control to me until you have confirmed the fix works.



Dependencies
fastapi==0.115.0
uvicorn==0.30.6
starlette==0.38.6   # MUST be pinned — 1.0.0 breaks TemplateResponse
pydantic>=2.10.0
jinja2==3.1.4       # MUST be pinned — 3.1.6 breaks LRU cache
python-multipart>=0.0.9
discord.py>=2.3.0
requests>=2.31.0
python-dotenv>=1.0.0
Pillow>=10.0.0
watchdog>=4.0.0