# V3_Bot — Feature Roadmap
**Last updated: May 2026**

---

## In Progress / Next Up

### 1. Auth / Roles / Permissions
**Approach:** Discord OAuth for identity verification + custom DB for authorization

**Flow:**
1. User clicks "Login with Discord" on dashboard landing page
2. Discord confirms identity, returns Discord user ID
3. App checks `staff_permissions` table — if not found, access denied
4. Permissions loaded, features shown/hidden by role

**Permission flags (per staff member):**
- View inventory, claims, users, bin manager, trades, history
- Publish items to catalog
- Award credits to users
- Remove/void claims
- Show control (new show, end show, mode toggle)
- Download ZIP files from history
- Console access (run commands)
- Trade management (refresh/close channels)
- View live DB
- Edit live DB
- Manage staff permissions (owner only)

**Roles:** Owner / Admin / Mod — plus per-user overrides on top of role defaults

**Settings UI:** Permissions tab in Settings page — list of staff, checkboxes per permission

**DB:** Separate `auth.db` (not per-show) with `staff_permissions` table

---

### 2. History ZIP Download
**Endpoint:** `GET /ui/history/download?show_id=&variant=raw|watermarked|both`

Zips the relevant show folder and streams it as a download. Requires "Download Files" permission.

---

### 3. Dashboard "No Active Show" State
Currently shows "Failed to fetch" errors on several pages when no show is running. Should show a clean empty state with a "Create New Show" prompt instead.

---

### 4. Right Dock — Make Useful
Currently shows nothing useful. Planned panels:
- **Activity** — live claim feed (new claims as they happen, auto-refresh)
- **Bin** — unassigned auction rows count, quick link to Bin Manager
- **Trades** — pending offer count, quick link

---

## Medium Term

### 5. Web Trade UI
Browser-based version of the Discord trade system.

**Why:** Some users find Discord channels confusing or tedious to navigate.

**Features:**
- User logs in via Discord OAuth
- Sees their binder (cards they own with images)
- Can create listings (select cards + what they want)
- Can browse other users' listings
- Can make offers on listings
- Can accept/decline incoming offers
- Real-time or polling updates

**Tech:** Same backend DB and logic as Discord trades. New React frontend routes. Requires auth system first.

**Future extension:** Online pack opening — virtual packs of custom cards users can open in the browser, using the same card/inventory system.

---

### 6. Discord Trade Flow Polish
The current Discord trade embeds and modal flow work but feel clunky. Goals:
- Cleaner embed design (better formatting, card image thumbnails)
- Smoother offer flow
- Notifications when offer is accepted/declined (sender currently not notified)
- Complete the stubbed buttons: View Incoming, View Sent, Edit Listing, Cancel Listing

---

### 7. Giveaway Bot
Low priority. For running giveaways during Discord shows.

**Features:**
- `/giveaway start <prize> <duration>` — posts a giveaway embed with a react-to-enter button
- `/giveaway end <id>` — picks a random winner from entrants
- Optional: credit-based entries (spend 1 credit for extra entries)
- Optional: restrict to verified users only

---

## Longer Term

### 8. Tournament System
For running card game tournaments within the Discord server.

**Features:**
- Discord sign-up with form (deck name, card list submission)
- Participant tracking
- Bracket generation (single elimination or round robin — TBD)
- Match result posting
- Staff can report results via dashboard
- Bracket displayed in Discord and/or dashboard

**Open questions:**
- Format (single elim / round robin / swiss?)
- Prize structure?
- Integration with credit/voucher system?

---

### 9. Card Creator Tool
Standalone browser-based card design tool. **Not tied to inventory.** Replaces a paid external service.

**Features:**
- Upload card art image
- Choose border/frame template
- Add text fields (name, stats, flavor text, etc.)
- Live preview canvas (composited in browser)
- Export finished card as PNG
- Optionally: save to account, share link

**Tech:** HTML5 Canvas or Fabric.js for compositing. Similar concept to the watermark pipeline but interactive with live preview.

**Note:** This is a standalone service — cards created here do not automatically enter the inventory/show system unless explicitly added.

---

## Completed ✅

- Full watcher pipeline (file detect → watermark → upload → inventory)
- Publish to catalog (standard and bin modes)
- Claim button flow with FIFO voucher spend
- Bin show: number-based auction → dashboard assignment
- Bin auction position tracking with placeholder insert/restamp
- Bin row delete with claim removal (no refund)
- Trade system (channels, listings, offers, ownership swap)
- React dashboard — all pages wired
- Dashboard auto-refresh, tab persistence, panel collapse persistence
- Command palette (Ctrl+K)
- Collapsible sidebar
- Watermark template upload
- Settings env editor
- History past show browser
- Upload queue with cancel
