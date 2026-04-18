V3_Bot – SPEC v1.1
Project Overview

V3_Bot is a modular Discord + FastAPI system for managing live show item claims with:

Per-show isolation (separate SQLite DB per show)

FIFO voucher accounting

Public catalog claim buttons

Private RAW delivery

Staff-only archival threads per show

Support for SFW and NSFW item pipelines

The system is designed for:

Manual operation now

Fully automated ingest pipeline (watcher + watermarking) next

1. System Architecture
1.1 Backend (FastAPI + SQLite)

Runs via:

uvicorn Backend.main:app --host 127.0.0.1 --port 8000
Core Characteristics

One SQLite DB per show

Active show tracked centrally

All state (users, vouchers, inventory, media mappings) is show-scoped

Discord is treated as a display/delivery layer only

2. Database Model (Per Show)
2.1 users
CREATE TABLE users (
  id              INTEGER PRIMARY KEY,
  kind            TEXT NOT NULL CHECK(kind IN ('discord','pending')),
  discord_user_id TEXT UNIQUE,
  display_name    TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  created_at      TEXT NOT NULL
);

Supports:

pending → Whatnot/guest users not in Discord

discord → Verified Discord users

2.2 voucher_ledger

FIFO credit model

delta +1 for WINNER

delta -1 for claim spend

consumed_ledger_id tracks FIFO consumption

Claim attempt consumes oldest positive ledger entry first.

2.3 inventory

item_code (S### or N###)

claimed state

removed state

Inventory is show-specific.

2.4 media_assets
CREATE TABLE media_assets (
  id                INTEGER PRIMARY KEY,
  item_code          TEXT NOT NULL,
  variant            TEXT NOT NULL CHECK(variant IN ('raw','watermarked')),
  rating             TEXT NOT NULL CHECK(rating IN ('sfw','nsfw')),
  source_channel_id  TEXT NOT NULL,
  source_message_id  TEXT NOT NULL,
  attachment_url     TEXT NOT NULL,
  filename           TEXT,
  content_type       TEXT,
  created_at         TEXT NOT NULL
);

Purpose:

Maps item_code → RAW + WM Discord attachment locations

Enables RAW repost into claims thread on successful claim

Unique index:

(item_code, variant, rating)
2.5 show_settings
CREATE TABLE show_settings (
  key        TEXT PRIMARY KEY,
  value      TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

Currently used for:

claims_thread_sfw

claims_thread_nsfw

Allows Discord thread IDs to be stored per show.

3. Backend Endpoints
Users

POST /users/create_pending

POST /users/upsert_discord

Claims

POST /claims/attempt

Returns structured codes:

OK

NO_VOUCHER

ALREADY_CLAIMED

ITEM_REMOVED

ITEM_NOT_FOUND

Shows

POST /shows/new

POST /shows/settings/set

GET /shows/settings/get

Media

POST /media/upsert

GET /media/get

4. Discord Bot Architecture

Runs via:

python -m Discord.bot

Uses:

Persistent buttons (custom_id = "claim:<ITEMCODE>")

Guild sync for instant slash command registration

5. Discord Channel Structure
Public Catalog Channels

#Catalog_SFW

#Catalog_NSFW

Contain:

Watermarked embed

Claim button

Private Upload Channels

#Upload_SFW

#Upload_NSFW

Used for:

RAW upload

WM upload

Mapping storage

Public never sees RAW.

Private Claims Channels

#Claims_SFW

#Claims_NSFW

Each show creates:

M-D-YYYY (thread)

Example:

#Claims_NSFW
   2-19-2026

RAW delivery occurs inside these show threads.

6. Claim Flow (Final Behavior)

When a user clicks a claim button:

Bot upserts Discord user → internal user_id

Bot calls /claims/attempt

If success:

Determine rating from catalog channel

Lookup current show thread via /shows/settings/get

Fetch RAW mapping via /media/get

Download RAW attachment

Re-upload RAW into show archival thread

Delete original catalog listing message

Send ephemeral success message

If failure:

Return structured error message

7. Show Creation Flow

Slash command:

/new_show

Behavior:

Uses current system date automatically

Creates show in backend

Creates 2 threads:

#Claims_SFW → M-D-YYYY

#Claims_NSFW → M-D-YYYY

Saves thread IDs into show_settings

8. Item Codes

Format:

S### → SFW

N### → NSFW

Rating must match catalog channel and media mapping.

9. Current Manual Media Workflow

Staff performs:

/ingest_raw

/publish_wm

Claim button posted to catalog

System fully operational manually.

10. Next Phase (Planned)
Folder Watcher Service

Will:

Create show folder:

Shows/<show_id>/
   SFW/RAW
   SFW/WM
   NSFW/RAW
   NSFW/WM

Watch RAW folders

Apply watermark template

Batch items in sets of 10

Upload RAW + WM to private upload channels

Call /media/upsert

Post WM to catalog with claim button

Manual commands will become fallback only.

11. Security Model

RAW never posted publicly

Claims threads live in private staff-only channels

Discord attachment URLs assumed safe within Discord ecosystem

FIFO ledger prevents double-spend

12. Current Status

System state:

Backend stable

Claim logic stable

Voucher FIFO stable

Persistent buttons stable

Archival threads per show working

Manual media ingestion working

Automation layer pending

SPEC Version

SPEC v1.1
Date: Current development milestone after archival threads + media mapping integration.