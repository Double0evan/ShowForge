# V3_Bot — Project Brief
**Version 3.0.0**

---

## What This Is

A modular system for managing live collectible card shows (Whatnot + Discord) with a React web dashboard:

- Staff upload images → watcher watermarks them → uploads to private Discord threads
- Staff publish items to a public Discord catalog channel
- Discord users claim items by clicking a button (standard show mode)
- OR host types item numbers in Discord → assigned via Bin Manager dashboard (bin show mode)
- Per-show SQLite databases, full audit trail, voucher/credit system
- Private per-user trade channels with binder, listings, and offer flow
- React web dashboard replacing original Jinja HTML dashboard

---

## Project Tree

```
V3_Bot/
├── run.py / run.bat                  # Launcher — starts Backend, Bot, Watcher
├── requirements.txt
├── CLAUDE.md                         # This file
│
├── Core/                             # Pure business logic — no Discord, no HTTP
│   ├── schema.sql                    # SQLite schema
│   ├── db.py                         # Connection, WAL mode, idempotent migrations
│   ├── show_manager.py               # Show creation, active_show.json pointer
│   ├── show_service.py               # require_active_show() helper
│   ├── show_settings_service.py      # Per-show key/value store
│   ├── inventory_service.py          # Item code generation and status
│   ├── media_service.py              # Discord attachment URL storage
│   ├── claim_service.py              # FIFO voucher spend, race condition guard
│   ├── voucher_service.py            # Credit ledger (+1/-1 rows, never edited)
│   ├── user_service.py               # Guest merge, fuzzy name matching
│   ├── bin_queue.py                  # Auction log + placeholder insert + restamp
│   └── normalize.py                  # Username normalization for matching
│
├── Discord/
│   ├── bot.py                        # Discord client + FastAPI internal API (port 8001)
│   ├── bot_instance.py               # Shared discord.Client instance
│   ├── core_client.py                # HTTP client → backend (port 8000)
│   ├── member_cache.py               # In-memory guild member cache
│   ├── ui_components.py              # Claim button view builder
│   ├── bin_listener.py               # Watches #claim-bot-commands for bin item numbers
│   ├── publish_direct.py             # Async publish used by bin_listener (no HTTP round-trip)
│   └── commands/
│       ├── __init__.py
│       └── staff.py                  # /award, /publish_wm slash commands
│
├── Backend/
│   ├── main.py                       # FastAPI port 8000
│   ├── routes/
│   │   ├── ui.py                     # All routes — JSON API + legacy UI actions
│   │   └── members.py                # /ui/members — proxies bot member cache
│   └── services/
│       └── publish_service.py        # Publish item → bot API → Discord
│
├── Watcher/
│   ├── watcher_service.py            # File watcher, watermark, Discord upload
│   └── watcher_logger.py             # Log file + heartbeat flag
│
├── Trade/
│   ├── trade_hook.py                 # Entry point — register_trade_commands()
│   ├── db/
│   │   └── trade_db.py               # Trade schema + all DB repo functions
│   ├── services/
│   │   └── trade_service.py          # Business logic — channels, listings, offers
│   └── ui/
│       ├── trade_views.py            # Discord UI Views and Modals
│       └── trade_embeds.py           # Embed builders
│
├── frontend/                         # React dashboard (Vite + React)
│   ├── src/
│   │   ├── App.jsx
│   │   ├── api/
│   │   │   ├── apiClient.js          # fetch wrapper
│   │   │   ├── config.js             # base URL, mock/live mode
│   │   │   ├── endpoints.js          # all backend route paths
│   │   │   ├── mappers.js            # DB row → frontend shape
│   │   │   ├── showforgeApi.js       # main API facade
│   │   │   └── liveShowforgeApi.js   # live implementations
│   │   ├── components/
│   │   │   ├── layout/               # AppShell, Sidebar, TopBar, WorkspaceTabs, RightDock
│   │   │   ├── dashboard/            # DashboardWorkspace
│   │   │   ├── inventory/            # InventoryWorkspace, InventoryRow, InventoryDrawer
│   │   │   ├── claims/               # ClaimsWorkspace, ClaimsRow, ClaimsDrawer
│   │   │   ├── users/                # UsersWorkspace, UserRow, UserDrawer
│   │   │   ├── trades/               # TradesWorkspace
│   │   │   ├── bin/                  # BinManagerWorkspace, BinManagerRow, BinAssignmentDrawer
│   │   │   ├── console/              # ConsoleWorkspace
│   │   │   ├── settings/             # SettingsWorkspace
│   │   │   ├── history/              # HistoryWorkspace
│   │   │   ├── uploads/              # UploadWorkflow
│   │   │   ├── command/              # CommandPalette (Ctrl+K)
│   │   │   └── shared/               # Panel, Button, Badge, DataTable, FilterBar, etc.
│   │   └── hooks/
│   │       ├── useInventory.js
│   │       ├── useClaims.js
│   │       ├── useUsers.js
│   │       ├── useBinManager.js
│   │       └── useUploadQueue.js
│   ├── vite.config.js
│   └── package.json
│
├── DB/                               # Runtime — not committed
│   ├── active_show.json
│   ├── bin_queue.sqlite
│   └── shows/<show_id>/show.db
│
└── logs/
    ├── watcher.log
    ├── watcher.heartbeat
    └── watcher_process.flag
```

---

## Three Processes

| Process | Port | Description |
|---------|------|-------------|
| Backend (uvicorn) | 8000 | FastAPI — all business logic + React API |
| Bot (discord.py) | 8001 | Discord client + internal bot API |
| Watcher | — | File watcher, watermark, upload pipeline |

**Critical:** Backend and Bot are separate processes. The backend has **no Discord connection**. All Discord operations must go through the bot's API on port 8001 using `run_coroutine_threadsafe`.

**Event loop pattern (do not change):**
```python
# In on_ready():
_discord_loop = asyncio.get_running_loop()  # NOT asyncio.get_event_loop()

# In sync bot API endpoints:
future = asyncio.run_coroutine_threadsafe(coro(), _discord_loop)
result = future.result(timeout=20)
```

---

## Show Modes

### Standard Show
- Items uploaded → watermarked → published to catalog with **Claim** button
- Users click button to spend a credit and claim the item
- `show_mode` setting = `"standard"`

### Bin Show
- Host types item number (e.g. `175`) in `#claim-bot-commands`
- `bin_listener.py` logs the auction, publishes `N175` to catalog **without** claim button
- Host pastes buyer's Whatnot name into Bin Manager dashboard
- Fuzzy match runs against Discord members → assign claim
- No voucher/credit spent — bin shows don't use the credit system
- `show_mode` setting = `"bin"`

**Important:** `bin_listener.py` passes `show_mode` variable to `publish_direct.py` — do NOT hardcode `show_mode="bin"`.

---

## Bin Manager — Auction Number System

- Each item typed by the host gets a sequential **auction position** (1st, 2nd, 3rd sold, etc.)
- `position` = auction order; `card_number` = item number typed
- If host auctions a non-card item or a cancellation occurs, insert a **placeholder** row to keep positions aligned
- `insert_placeholder(after_id, show_db_path)` in `bin_queue.py` inserts a blank row and restamps all claim `auction_number` values
- Deleting an assigned row also removes the claim (`remove_claim=true` query param on DELETE endpoint) — no refund since bin shows don't use credits

---

## Key Data Flows

### Watcher Pipeline
```
INBOX/SFW or INBOX/NSFW (file dropped)
  → assign code (N### or S###)
  → move to show folder RAW
  → watermark → Watermarked folder
  → upload RAW to private Discord thread → upsert media_assets
  → upload WM to private Discord thread → upsert media_assets
  → POST /inventory/upsert
  → if WATCHER_AUTO_PUBLISH=1: post to catalog with claim button
  → if 0: hold for manual publish
```

### Publish Flow (manual)
```
UI "Publish" button
  → POST /ui/publish (backend)
  → POST http://127.0.0.1:8001/publish (bot API)
  → bot posts WM to catalog channel with claim button
  → backend stamps published_at
```

### Claim Flow (standard)
```
User clicks claim button
  → on_interaction in bot.py
  → bin mode check (reject if bin show)
  → verified role check
  → upsert Discord user
  → POST /claims/attempt
  → claim_service.create_claim (FIFO voucher, race condition guarded)
  → fetch RAW media → post to archival thread
  → delete catalog message
  → on_item_assigned_trade() → ensure trade channel, refresh binder
```

### Bin Show Flow
```
Host types "175" in #claim-bot-commands
  → bin_listener.on_message
  → check show_mode == 'bin'
  → log_auction(175) → auction_log entry
  → ensure N175 inventory slot exists
  → publish_item_direct(item_code, show_mode=show_mode)  ← no claim button
  → host pastes buyer name into Bin Manager dashboard
  → fuzzy match → assign claim via POST /ui/binshow/log/:id/assign
  → restamp_auction_claim_numbers()
```

### Trade Flow
```
Card assigned → on_item_assigned_trade()
  → ensure_trade_channel_for_user()
  → refresh_trade_home()

User creates listing → CreateListingModal
  → save_listing() → post to announce channel

User makes offer → FindCardOwnerModal → MakeOfferModal
  → save_offer() → post in receiver's channel

Offer accepted → handle_offer_accepted()
  → resolve_offer() + swap_card_ownership_for_offer()
  → refresh both users' trade channels
```

---

## React Dashboard — Pages & Tabs

| Page | Tabs | Description |
|------|------|-------------|
| Dashboard | Show Control, Stats | New/end show, mode toggle, live pulse, recent claims |
| Inventory | Inventory List, Upload Queue | Item table, publish, upload pipeline |
| Claims | Active, Removed, Summary | Claim management, post summaries |
| Users | All Users, Merge Review | Credit management, guest users |
| Trades | Channels, Trade Log | Trade channel management, offer/listing history |
| Bin Manager | Assignment Queue, Auction Log | Bin show workflow |
| Console | Commands, Live Log | Admin commands with autocomplete |
| Settings | Watcher, Discord, Templates | Env config, watermark template upload |
| History | Past Shows | Past show browser + ZIP download |

**Tab state and active page persist in `localStorage`.**
**Panel collapsed state persists in `localStorage` keyed by panel title.**

---

## Backend JSON API Endpoints (React-facing)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/inventory` | Inventory list with preview URLs |
| GET | `/api/claims` | Claims list with preview URLs |
| GET | `/api/users` | Users with balances |
| GET | `/api/binshow/state` | Auction log + pending sales + watcher state |
| GET | `/api/trades` | Channels, listings, offers, completed trades |
| GET | `/api/history/list` | Past show list |
| GET | `/api/history/show` | Past show inventory/claims/users |
| GET | `/shows/active` | Active show ID + mode |
| GET | `/shows/mode` | Current show mode |
| POST | `/shows/mode` | Set show mode (standard/bin) |
| POST | `/ui/binshow/log/insert` | Insert placeholder auction row |
| DELETE | `/ui/binshow/log/:id` | Delete row (optionally remove claim, refund=false for bin) |
| POST | `/ui/settings/template/upload` | Upload watermark template |
| GET | `/ui/settings/template/preview` | Serve current template image |
| GET | `/ui/settings/env` | Read current .env values |

---

## Database Schema

| Table | Purpose |
|-------|---------|
| `users` | Discord/pending/guest/merged user records |
| `inventory_items` | Item codes, status, post_mode, published_at |
| `media_assets` | Discord CDN URLs for RAW + watermarked variants |
| `voucher_ledger` | FIFO credit ledger (+1/-1 rows, never edited) |
| `claims` | Active and removed claims, auction_number, source |
| `show_settings` | Per-show key/value (thread IDs, show_mode, folder path) |
| `trade_user_channels` | Per-user private trade channel IDs |
| `trade_ui_messages` | Persistent message IDs |
| `trade_listings` | Active trade listings |
| `trade_listing_cards` | Items attached to listings |
| `trade_offers` | Trade offers between users |
| `trade_offer_cards` | Items attached to offers |
| `trade_offer_requested_cards` | Items sender wants in return |

**`bin_queue.sqlite`** (separate, cross-show):
- `auction_log` — ordered list of items sold, winner assignment, placeholder rows
- `pending_sales` — unmatched OCR-detected sales (legacy, OCR watcher removed)

---

## Environment Variables (Discord/.env)

```
DISCORD_TOKEN=
GUILD_ID=

# Role gating
VERIFIED_ROLE_ID=
UNVERIFIED_ROLE_ID=
NEWCOMER_ROLE_ID=
VERIFY_CHANNEL_ID=

# Public catalog channels
CATALOG_SFW_CHANNEL_ID=
CATALOG_NSFW_CHANNEL_ID=

# Staff claims archive channels
CLAIMS_SFW_CHANNEL_ID=
CLAIMS_NSFW_CHANNEL_ID=

# Private upload storage threads
UPLOAD_THREAD_RAW_SFW=
UPLOAD_THREAD_WM_SFW=
UPLOAD_THREAD_RAW_NSFW=
UPLOAD_THREAD_WM_NSFW=

# Bin show
CLAIM_BOT_COMMANDS_CHANNEL_ID=

# Trade system
TRADE_CATEGORY_ID=
TRADE_ANNOUNCE_CHANNEL_ID=
TRADE_LOG_CHANNEL_ID=

# Security
HONEYPOT_CHANNEL_ID=

# File watcher
WATCHER_PARENT_DIR=
WM_TEMPLATE_SFW=
WM_TEMPLATE_NSFW=
WATCHER_AUTO_PUBLISH=0   # 1 = auto-post on upload, 0 = manual
```

---

## What's Working

- Full watcher pipeline (file detect → watermark → upload → inventory)
- Publish to catalog (standard and bin modes, mode-aware claim button)
- Claim button flow with FIFO voucher spend and race condition guard
- Bin show: host types number → published without claim button → Bin Manager assignment
- Bin auction number tracking with placeholder insert and restamp
- Bin row delete with claim removal (no refund — bin shows don't use credits)
- Auto-merge of guest/pending users on Discord join
- Trade channel creation, listings, offers, ownership swap
- React dashboard — all pages wired, tab state persists, panel collapse persists
- Dashboard auto-refresh every 20 seconds
- Command palette (Ctrl+K)
- Collapsible sidebar
- Watermark template upload via Settings
- Settings env editor (channels, threads, verification, honeypot, trade)
- History past show browser
- Upload queue with cancel mid-upload

---

## Known Open Issues

1. **Discord CDN URLs expire** (~24hrs) — inventory previews and binder images go stale. Fix: store local file paths as fallback or re-fetch on demand.
2. **Trade stubbed buttons** — View Incoming, View Sent, Edit Listing, Cancel Listing reply "coming soon."
3. **React frontend not yet deployed** — still on Vite dev server. Needs nginx config update and build deploy.
4. **Bot trade endpoints** — `/trade/refresh_user`, `/trade/close_channel`, `/trade/open_for_user` on bot port 8001 may not be implemented yet.
5. **`Trade/Trade/` duplicate folder** — should be deleted.

---

## Upcoming Features (Planned)

### Priority (next sessions)
1. **Auth / Roles / Permissions** — Discord OAuth login, JWT sessions, per-user permission flags in DB, Settings UI for managing staff. Permissions: view, publish, award credits, remove claims, show control, download files, console access, trade management, manage staff.
2. **History ZIP download** — `GET /ui/history/download?show_id=&variant=raw|watermarked` zips and serves the show folder.
3. **Dashboard "no active show" state** — suppress "Failed to fetch" errors gracefully when no show is running.
4. **Right Dock** — make useful (live claim feed, pending bin assignments, active offer count).
5. **Delete bin row + claim** — ✅ Done. No refund for bin shows.

### Medium Term
6. **Web trade UI** — browser-based version of Discord trade flow. Users log in, see binder, create listings, make/accept offers. Same DB, same logic, just web-facing. Foundation for online pack opening.
7. **Discord trade flow polish** — improve embed design and interaction flow.
8. **Online pack opening** — virtual packs containing custom cards users can open via browser.
9. **Giveaway bot** — Discord command for random draws from verified users.

### Longer Term
10. **Tournament system** — Discord sign-up with deck list submission, bracket management, results posting.
11. **Card creator tool** — browser-based card design (upload art + choose border template → export PNG). Standalone service, not tied to inventory. Replaces paid external service.

---

## Dependencies

```
fastapi==0.115.0
uvicorn==0.30.6
starlette==0.38.6       # MUST be pinned
pydantic>=2.10.0
jinja2==3.1.4           # MUST be pinned
python-multipart>=0.0.9
discord.py>=2.3.0
requests>=2.31.0
python-dotenv>=1.0.0
Pillow>=10.0.0
watchdog>=4.0.0
```

---

## Deployment (Droplet)

- Live at `http://167.172.137.169`
- nginx proxies `/` to FastAPI on port 8000
- React build (`npm run build`) output goes to nginx static root
- nginx needs catch-all: `try_files $uri $uri/ /index.html;`
- API routes proxied before catch-all: `/api`, `/ui`, `/shows`, `/bin`, `/trade`, etc.
- Git branch: `react-frontend` → merge to `main` on droplet for deploy

## Vite Dev Proxy (local testing against live droplet)
```js
// vite.config.js
server: {
  proxy: {
    '/api': 'http://167.172.137.169',
    '/ui':  'http://167.172.137.169',
    // ... etc
  }
}
```

---

## Claude Code Usage Notes

- **Narrow prompts only.** Single file, single task.
- **Always read this file first** before making changes.
- **Do not change the event loop pattern.**
- **Do not change starlette/jinja2 pins.**
- **Migrations go in `Core/db.py` `run_migrations()`** — never edit `schema.sql` for existing tables.
- **Trade DB functions** in `Trade/db/trade_db.py` — use `db_session` from `Core.db`.
- **Bin show delete** — always `refund=False`, bin shows don't use credits.
- **`show_mode` in bin_listener** — always pass the variable, never hardcode `"bin"`.
