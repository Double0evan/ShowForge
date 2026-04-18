# V3 Control Panel – Continuation Plan and Project Notes

## Purpose of this file
This file is for resuming the project cleanly in a new chat. It captures:
- the current architecture
- what is already working
- what is partially working but still messy
- the exact next development order
- mistakes to avoid repeating
- what the next chat should ask for first

---

# Project Goal
Build a dark, minimal admin control panel that can run the show workflow without needing to operate from Discord directly.

The panel should eventually handle:
- show creation
- inventory visibility
- publishing items
- claim monitoring and control
- user management
- settings and configuration
- admin command / console actions

Discord should remain the public-facing and claim-facing layer, but the UI should be the main operator dashboard.

---

# High-Level Architecture

## Intended structure
- `Core/` = business logic and source of truth
- `Backend/` = FastAPI routes, UI, web control layer
- `Discord/` = Discord bot and Discord-facing logic
- `Watcher/` = filesystem watcher and image ingestion pipeline

## Mental model
- Core = brain
- Backend = dashboard
- Discord = public interaction layer
- Watcher = ingestion layer

## Rule
Never import from `Backend.main` inside feature modules unless absolutely necessary. Shared logic should live in Core or a small shared service module.

---

# Current Working State

## Confirmed working
### Backend/UI
- FastAPI server starts
- `/ui` loads successfully
- Jinja templates are working
- Inventory page is rendering
- Sidebar layout exists
- Status colors exist for:
  - available
  - claimed
  - removed
  - claimed_removed
- Publish button UI exists
- Publish All button UI exists
- Reset button exists for UI-only button state resets
- Publish is async from frontend, so it no longer hard refreshes the page

### Bot
- Discord bot exists and logs in
- Persistent claim button system already exists in `Discord/bot.py`
- Claim flow is already implemented in bot + backend
- Current claim flow already does:
  - upsert Discord user
  - call backend `/claims/attempt`
  - delete catalog message on success
  - fetch RAW media mapping
  - re-upload RAW into the proper show archival thread
- `/new_show` slash command already exists in bot and currently creates show archival claim threads

### Claims / backend logic
- `Core/claim_service.py` is already implemented and usable
- backend `/claims/attempt` exists and is button-friendly
- vouchers and inventory status updates are already part of claim flow

### Watcher / ingestion pipeline
Watcher is functionally far along and has worked enough to prove the pipeline concept.
Confirmed pieces:
- loads env from `Discord/.env`
- watches configured inbox folders
- detects file create events
- assigns inventory code locally right now
- creates show folder structure
- creates RAW and Watermarked output files
- uploads RAW and WM to Discord upload threads
- calls backend `/media/upsert`
- stores media mapping in DB

### Media architecture
This is important:
- watcher uploads RAW and Watermarked images to private Discord upload threads
- media URLs are stored in DB via `Core/media_service.py`
- these upload-thread CDN links are intended to act like static asset links for later publish / claim use

This means publish should not need to process files again.

---

# Important Current Behavior / Design Decisions

## Publish behavior (locked in)
Publish should use media already stored in DB.

### Expected publish behavior
For an item:
- pull Watermarked media URL from media DB record
- post Watermarked image to public catalog channel
- attach claim button using existing `build_claim_view()`

Claim flow already handles the raw archival side after a user clicks claim.

## Claims channel structure (locked in)
- there is a private claims channel
- each show gets a thread in that private claims channel
- each claim becomes an individual message in that thread

## Public catalog structure
- public catalog gets Watermarked media
- users claim from there using buttons

## Upload-thread structure
The watcher uses upload threads as asset storage:
- RAW SFW thread
- WM SFW thread
- RAW NSFW thread
- WM NSFW thread

These are private storage threads and are not the public catalog.

## File ingestion location
Watcher watches:
- `WATCHER_PARENT_DIR/INBOX/SFW`
- `WATCHER_PARENT_DIR/INBOX/NSFW`

It does **not** watch subfolders recursively.
Do not drop files into `RAW/` or `Watermarked/` under inbox.
They must be dropped directly into the inbox rating folder.

---

# Known Messy / Incomplete Areas

## 1. Publish flow is not cleanly finalized yet
This is the biggest next core task.

Important lessons learned:
- Backend should **not** directly use a live Discord client for publish if that causes process coupling issues
- Importing `Discord.bot` from backend caused crashes due to env loading and process coupling
- UI components like `build_claim_view()` were moved / should remain separate from bot bootstrap concerns

Need to resume by deciding the clean final publish architecture and implementing it without breaking the backend UI.

## 2. Watcher still needs cleanup
Watcher was heavily debugged in this chat. It currently contains a lot of temporary prints and experimentation.

Things learned:
- watchdog fires in a separate thread
- needed `asyncio.run_coroutine_threadsafe(..., self.client.loop)` instead of trying to create tasks from watchdog thread directly
- waiting on `wait_until_ready()` inside worker loop caused confusion / delays
- Windows file handling caused stubborn behavior
- copy-then-delete was safer than straight `replace()`
- large raw files can exceed Discord upload limits
- compression helped with large files
- watermark tuning is still messy and not finalized aesthetically

The watcher should be cleaned once the core pipeline is stable.

## 3. Item-code assignment is still not ideal
Watcher is currently allocating its own code locally.
That is not the preferred final design.

Final design should be:
- backend owns code generation
- watcher asks backend for next code using backend endpoint

There is already a backend endpoint:
- `POST /inventory/next_code`

This should eventually replace local counter allocation in watcher.

## 4. UI previews were started but not fully finalized
The template expects `item.preview_url`, so the `/ui` route should enrich each inventory item with preview URL from media records before rendering.

This should be one of the first things cleaned up in the next chat.

---

# Critical Mistakes to Avoid Repeating

## Do not import `Discord.bot` from backend routes or services
This caused env crashes and process-coupling issues.

## Do not keep duplicate `/ui` routes
At one point `ui.py` had two `/ui` routes, which caused confusing behavior.
There should only be one.

## Do not assume watcher watches nested folders
It is `recursive=False`.
Only direct files in inbox rating folders are seen.

## Do not treat publish as file-processing
Publish should not rename, watermark, or upload source files.
That is watcher’s job.
Publish should use already-stored media mappings.

## Do not assume raw and wm previews exist automatically
UI needs to attach preview URLs explicitly.

## Do not lose sight of process separation
Likely operational setup:
- terminal 1: backend
- terminal 2: bot
- terminal 3: watcher

A future launcher can start all three.

---

# What Was Learned About Watermarking

The user wants a strong centered watermark style more like a large faded overlay, not a small corner logo.
A reference image was shown with a large centered translucent overlay.

However, watermark tuning became a rabbit hole and does **not** need to block the next phase.

Important note for future self:
- watermark is functionally working enough to proceed
- visual perfection can be tuned later
- do not let watermark styling derail UI/publish/control features again

---

# Recommended Next Development Order
This order was explicitly chosen by the user and should be followed.

## 1. UI thumbnails / file awareness
Why first:
- user needs to know which item is which
- publishing without visible previews is frustrating
- makes the system feel usable immediately

Goal:
- each inventory row shows thumbnail preview from media DB
- optionally show filename or other identifying info later

## 2. Proper publish flow
Goal:
- clicking Publish posts Watermarked media to public catalog channel
- uses existing claim button builder
- only available items should publish
- later add publish tracking so remove/republish works properly

## 3. Bulk publish
Goal:
- publish all available items only
- skip claimed / removed / already handled items

## 4. Claim system polish
The claim core is already built.
This phase should focus on polish / visibility, not basic claim logic.
Possible improvements later:
- UI claims panel
- more immediate feedback
- claim reason display if desired

## 5. Settings panel
This should eventually expose:
- watermark template paths
- watcher directory path
- channel IDs / thread IDs
- toggles like auto-publish
- current show info

---

# Exact Next-Chat Resume Point
The best next chat should begin with:

> We are resuming the V3 control panel project.
> Current priority order is:
> 1. UI thumbnails / file awareness
> 2. Proper publish flow
> 3. Bulk publish
> 4. Claim system polish
> 5. Settings panel
> Start with step 1 and help me cleanly wire previews into the inventory UI.

That is the best place to resume.

---

# What the Next Chat Should Ask For / Inspect First
In the next chat, ask to inspect these first if needed:
- `Backend/routes/ui.py`
- `Backend/ui/templates/index.html`
- `Core/media_service.py`
- `Core/inventory_service.py`
- optionally `Discord/bot.py` if publish flow is being wired that turn

Reason:
These are the files directly relevant to step 1 (thumbnails / file awareness).

---

# Specific Technical Notes for Next Chat

## For UI previews
Likely intended route pattern:
- get inventory rows via `list_inventory(active.db_path)`
- for each row, fetch matching media record
- attach `preview_url` to item dict
- render image in template if present

Need to decide whether to preview:
- Watermarked NSFW / SFW depending on item code or rating
- or raw for internal UI

Most likely internal UI can show raw preview, but since publish uses Watermarked media, either can work. Decide based on what is already saved reliably.

## For publish architecture
Likely safest clean design:
- UI/backend triggers a publish action without tightly coupling backend startup to bot startup
- reuse existing `build_claim_view()` from a safe shared module, not from bot bootstrap file if that causes side effects
- reuse existing bot claim system rather than rebuilding button handling

## For publish tracking later
Need a future place to store:
- item_code
- catalog_message_id
- maybe channel_id
- maybe publish timestamp

This will later support:
- remove listing
- republish listing
- prevent duplicate publish

## For watcher cleanup later
Watcher currently contains a lot of debug prints and should eventually be cleaned back down.
Do not clean it before the UI preview and publish flow are stable unless a blocking bug appears.

---

# Service Startup Notes
Current operational model uses separate processes.
A future convenience launcher is a good idea.

Simple `.bat` launcher idea was discussed:
- start backend
- start bot
- start watcher

This is worth building later once core behavior is stable.

---

# Final Reminder to Future Self
Do not restart architecture debates unless necessary.
The user wants practical progress now.

Stick to this order:
1. thumbnails / previews
2. publish
3. bulk publish
4. claim polish
5. settings

And keep responses simple, step-by-step, copy-paste friendly.
