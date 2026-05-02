"""
Watcher/watcher_service.py

Watches INBOX/SFW and INBOX/NSFW for new image files.
For each file:
  1. Assigns an item code (S### or N###)
  2. Moves file to the show's RAW folder
  3. Watermarks it → Watermarked folder
  4. Uploads RAW to private Discord RAW thread
  5. Uploads WM  to private Discord WM thread
  6. Registers media URLs in the backend DB
  7. Registers item in inventory DB
  8. If WATCHER_POST_MODE=display, posts WM to catalog with no claim button
     If WATCHER_POST_MODE=auto, posts WM to catalog WITH claim button
     If WATCHER_POST_MODE=hold (default), does not post to catalog automatically
"""

import asyncio
import os
import re
import sqlite3
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

import discord
import requests
from PIL import Image
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from dotenv import load_dotenv, dotenv_values

# Load .env from Discord folder, regardless of working directory
_ENV_PATH = Path(__file__).resolve().parents[1] / "Discord" / ".env"
load_dotenv(dotenv_path=_ENV_PATH, override=True)

from Watcher.watcher_logger import log, heartbeat, clear as clear_log

RATING  = Literal["sfw", "nsfw"]
ITEM_RE = re.compile(r"^(S|N)(\d{3})$", re.I)


def _read_env(key: str, default: str = "") -> str:
    """Re-reads from .env file each call so runtime changes take effect."""
    try:
        val = dotenv_values(_ENV_PATH).get(key)
        if val and val.strip():
            return val.strip()
    except Exception:
        pass
    return os.getenv(key, default)


def get_post_mode() -> str:
    """
    Re-reads WATCHER_POST_MODE from .env each call.
    Returns: 'hold' | 'display' | 'auto'
      hold    — upload to private threads only, publish manually via UI (default)
      display — also post WM to catalog with NO claim button (display only)
      auto    — also post WM to catalog WITH claim button
    """
    v = _read_env("WATCHER_POST_MODE", "hold").strip().lower().strip("'\"")
    if v in ("display", "auto"):
        return v
    return "hold"


def compress_image(path: Path, max_size_mb: float = 7.5):
    import io
    img = Image.open(path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    quality = 90
    while True:
        buffer  = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality)
        size_mb = buffer.tell() / (1024 * 1024)
        if size_mb <= max_size_mb or quality <= 30:
            with open(path, "wb") as f:
                f.write(buffer.getvalue())
            break
        quality -= 10


def ordinal(n: int) -> str:
    suffix = "th" if 10 <= (n % 100) <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def show_folder_name(dt: datetime) -> str:
    return f"{dt.strftime('%B')} {ordinal(dt.day)} {dt.year}"


@dataclass
class WatcherConfig:
    backend_url:             str
    discord_token:           str
    parent_dir:              Path
    inbox_sfw:               Path
    inbox_nsfw:              Path
    upload_thread_raw_sfw:   int
    upload_thread_wm_sfw:    int
    upload_thread_raw_nsfw:  int
    upload_thread_wm_nsfw:   int
    catalog_sfw_channel_id:  int
    catalog_nsfw_channel_id: int
    watermark_template_sfw:  Path
    watermark_template_nsfw: Path
    upload_delay_sec:        float = 1.2
    catalog_delay_sec:       float = 1.8


class StateDB:
    """Per-show-day SQLite DB tracking processed files and allocated codes."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _init(self):
        con = sqlite3.connect(self.db_path, timeout=10)
        con.execute("CREATE TABLE IF NOT EXISTS counters(rating TEXT PRIMARY KEY, next_num INTEGER NOT NULL)")
        con.execute("CREATE TABLE IF NOT EXISTS processed(src_path TEXT PRIMARY KEY, item_code TEXT NOT NULL, rating TEXT NOT NULL, created_at TEXT NOT NULL)")
        con.execute("INSERT OR IGNORE INTO counters(rating,next_num) VALUES('sfw',1)")
        con.execute("INSERT OR IGNORE INTO counters(rating,next_num) VALUES('nsfw',1)")
        con.commit()
        con.close()

    def already_processed(self, src_path: Path) -> bool:
        con = sqlite3.connect(self.db_path, timeout=10)
        cur = con.execute("SELECT 1 FROM processed WHERE src_path=?", (str(src_path),))
        ok  = cur.fetchone() is not None
        con.close()
        return ok

    def mark_processed(self, src_path: Path, item_code: str, rating: str):
        con = sqlite3.connect(self.db_path, timeout=10)
        con.execute(
            "INSERT OR REPLACE INTO processed(src_path,item_code,rating,created_at) VALUES(?,?,?,?)",
            (str(src_path), item_code, rating, datetime.utcnow().isoformat()),
        )
        con.commit()
        con.close()

    def allocate_code(self, rating: RATING) -> str:
        con = sqlite3.connect(self.db_path, timeout=10)
        cur = con.execute("SELECT next_num FROM counters WHERE rating=?", (rating,))
        n   = int(cur.fetchone()[0])
        con.execute("UPDATE counters SET next_num=? WHERE rating=?", (n + 1, rating))
        con.commit()
        con.close()
        return f"{'S' if rating == 'sfw' else 'N'}{n:03d}"


def ensure_show_dirs(root: Path):
    for p in [root/"SFW"/"RAW", root/"SFW"/"Watermarked",
              root/"NSFW"/"RAW", root/"NSFW"/"Watermarked", root/"_state"]:
        p.mkdir(parents=True, exist_ok=True)


def watermark(raw_path: Path, out_path: Path, template_path: Path):
    log(f"Watermarking {raw_path.name}")
    raw = Image.open(raw_path).convert("RGBA")
    wm  = Image.open(template_path).convert("RGBA")

    target_w = int(raw.width * 0.8)
    scale    = target_w / wm.width
    wm2      = wm.resize((int(wm.width * scale), int(wm.height * scale)))
    alpha    = wm2.split()[3].point(lambda p: int(p * 0.42))
    wm2.putalpha(alpha)

    x, y    = (raw.width - wm2.width) // 2, (raw.height - wm2.height) // 2
    overlay = Image.new("RGBA", raw.size, (0, 0, 0, 0))
    overlay.paste(wm2, (x, y), wm2)

    out = Image.alpha_composite(raw, overlay).convert("RGB")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.save(out_path, quality=92)
    log(f"Watermark saved: {out_path.name}")


def upsert_media(backend_url: str, *, item_code, variant, rating,
                 channel_id, message_id, attachment_url, filename, content_type):
    r = requests.post(f"{backend_url}/media/upsert", params={
        "item_code": item_code, "variant": variant, "rating": rating,
        "source_channel_id": str(channel_id), "source_message_id": str(message_id),
        "attachment_url": attachment_url, "filename": filename,
        "content_type": content_type or "",
    }, timeout=20)
    r.raise_for_status()


def register_inventory(backend_url: str, item_code: str, post_mode: str = "claim"):
    """Create the inventory_items row in the active show DB."""
    try:
        r = requests.post(
            f"{backend_url}/inventory/upsert",
            params={"item_code": item_code, "post_mode": post_mode},
            timeout=10,
        )
        if r.ok:
            log(f"Inventory registered: {item_code} [{post_mode}]")
        else:
            log(f"Inventory register failed: {r.text}", "WARN")
    except Exception as e:
        log(f"Inventory register error: {e}", "WARN")


class WatcherClient(discord.Client):
    def __init__(self, cfg: WatcherConfig, state: StateDB, initial_show_id: str = ""):
        super().__init__(intents=discord.Intents.none())
        self.cfg                = cfg
        self.state              = state
        self._active_show_id    = initial_show_id   # tracked so heartbeat can detect show changes
        self.queue: asyncio.Queue[tuple[Path, RATING]] = asyncio.Queue()
        self.processing_enabled = False  # Start paused — UI must trigger processing
        # Anchored to project root via __file__ — correct regardless of working directory
        self._flag_file = Path(__file__).resolve().parents[1] / "logs" / "watcher_process.flag"

    def upload_thread_for(self, rating: RATING, variant: str) -> int:
        variant = variant.lower()
        if rating == "sfw"  and variant == "raw":         return self.cfg.upload_thread_raw_sfw
        if rating == "sfw"  and variant == "watermarked": return self.cfg.upload_thread_wm_sfw
        if rating == "nsfw" and variant == "raw":         return self.cfg.upload_thread_raw_nsfw
        return self.cfg.upload_thread_wm_nsfw

    def catalog_channel_for(self, rating: RATING) -> int:
        return self.cfg.catalog_nsfw_channel_id if rating == "nsfw" else self.cfg.catalog_sfw_channel_id

    def claim_view(self, item_code: str) -> discord.ui.View:
        v = discord.ui.View(timeout=None)
        v.add_item(discord.ui.Button(
            label="Claim", style=discord.ButtonStyle.success, custom_id=f"claim:{item_code}"
        ))
        return v

    async def on_ready(self):
        log(f"Watcher logged in as: {self.user}")
        heartbeat()

    async def setup_hook(self):
        self.loop           = asyncio.get_running_loop()
        self.worker_task    = asyncio.create_task(self.worker_loop())
        self.heartbeat_task = asyncio.create_task(self.heartbeat_loop())

    async def heartbeat_loop(self):
        while True:
            heartbeat()

            # ── Show-ID polling ───────────────────────────────────────────────
            # Re-key StateDB whenever the active show changes so each new show
            # gets a fresh counter starting at N001 / S001.
            # Run the HTTP call in a thread — requests.get is blocking and must
            # not run directly on the Discord event loop.
            try:
                def _fetch_show_id() -> str:
                    r = requests.get(
                        f"{self.cfg.backend_url}/shows/active", timeout=3
                    )
                    return (r.json().get("active_show") or "").strip()

                show_id = await asyncio.to_thread(_fetch_show_id)
                if show_id and show_id != self._active_show_id:
                    self._active_show_id = show_id
                    safe_id    = "".join(
                        c if c.isalnum() or c in ("-", "_") else "_"
                        for c in show_id
                    )
                    state_root = self.cfg.parent_dir / "_watcher_state"
                    state_root.mkdir(parents=True, exist_ok=True)
                    self.state = StateDB(state_root / f"{safe_id}.sqlite")
                    log(f"Active show → {show_id} | StateDB: {safe_id}.sqlite")
            except Exception:
                pass

            # ── Flag file polling ─────────────────────────────────────────────
            # UI writes "1" or "0" to this file to start/stop processing.
            try:
                enabled = self._flag_file.exists() and self._flag_file.read_text().strip() == "1"
                if enabled != self.processing_enabled:
                    self.processing_enabled = enabled
                    if enabled:
                        log("Processing ENABLED via UI — scanning inbox...")
                        await self.scan_and_enqueue_inbox()
                    else:
                        log("Processing PAUSED via UI")
            except Exception:
                pass

            await asyncio.sleep(3)

    async def enqueue_file(self, path: Path, rating: RATING):
        log(f"Queued: {path.name} [{rating.upper()}]")
        await self.queue.put((path, rating))

    async def scan_and_enqueue_inbox(self):
        """Scan both inboxes and enqueue any files waiting there."""
        count = 0
        for rating, inbox in [("sfw", self.cfg.inbox_sfw), ("nsfw", self.cfg.inbox_nsfw)]:
            for p in sorted(inbox.iterdir()):
                if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                    if not self.state.already_processed(p):
                        await self.enqueue_file(p, rating)
                        count += 1
        return count

    async def worker_loop(self):
        log("Worker loop started — watching for files")
        while True:
            src_path, rating = await self.queue.get()
            log(f"Processing: {src_path.name} [{rating.upper()}]")
            try:
                if self.state.already_processed(src_path):
                    log(f"Skipped (already processed): {src_path.name}", "SKIP")
                    continue

                await asyncio.sleep(1.5)  # wait for file to finish writing

                now       = datetime.now()
                show_root = self.cfg.parent_dir / show_folder_name(now)
                ensure_show_dirs(show_root)

                # Derive item code from filename number if possible (e.g. 001.jpg -> N001)
                # Fall back to sequential counter only if filename has no leading number.
                import re as _re
                _stem = src_path.stem  # filename without extension
                _m    = _re.match(r"^(\d+)", _stem)
                if _m:
                    _n    = int(_m.group(1))
                    prefix = "S" if rating == "sfw" else "N"
                    item_code = f"{prefix}{_n:03d}"
                else:
                    item_code = self.state.allocate_code(rating)
                ext       = src_path.suffix.lower() or ".jpg"
                subdir    = "SFW" if rating == "sfw" else "NSFW"
                raw_dst   = show_root / subdir / "RAW" / f"{item_code}{ext}"
                wm_dst    = show_root / subdir / "Watermarked" / f"{item_code}.jpg"

                log(f"Assigned code: {item_code}")
                raw_dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, raw_dst)
                if src_path.exists():
                    os.remove(src_path)
                log(f"Moved to RAW: {raw_dst.name}")

                # Watermark
                template = self.cfg.watermark_template_sfw if rating == "sfw" else self.cfg.watermark_template_nsfw
                watermark(raw_dst, wm_dst, template)

                # Upload RAW to private thread
                log(f"Uploading RAW: {item_code}")
                raw_thread_id = self.upload_thread_for(rating, "raw")
                raw_thread    = self.get_channel(raw_thread_id) or await self.fetch_channel(raw_thread_id)
                if getattr(raw_thread, "archived", False):
                    await raw_thread.edit(archived=False)
                compress_image(raw_dst)
                raw_msg = await raw_thread.send(file=discord.File(raw_dst))
                await asyncio.sleep(self.cfg.upload_delay_sec)
                raw_att = raw_msg.attachments[0]
                upsert_media(self.cfg.backend_url, item_code=item_code, variant="raw", rating=rating,
                             channel_id=raw_thread_id, message_id=raw_msg.id,
                             attachment_url=raw_att.url, filename=raw_att.filename,
                             content_type=raw_att.content_type)
                log(f"RAW uploaded: {item_code}")

                # Upload WM to private thread
                log(f"Uploading watermarked: {item_code}")
                wm_thread_id = self.upload_thread_for(rating, "watermarked")
                wm_thread    = self.get_channel(wm_thread_id) or await self.fetch_channel(wm_thread_id)
                if getattr(wm_thread, "archived", False):
                    await wm_thread.edit(archived=False)
                compress_image(wm_dst)
                wm_msg = await wm_thread.send(file=discord.File(wm_dst))
                await asyncio.sleep(self.cfg.upload_delay_sec)
                wm_att = wm_msg.attachments[0]
                upsert_media(self.cfg.backend_url, item_code=item_code, variant="watermarked", rating=rating,
                             channel_id=wm_thread_id, message_id=wm_msg.id,
                             attachment_url=wm_att.url, filename=wm_att.filename,
                             content_type=wm_att.content_type)
                log(f"Watermarked uploaded: {item_code}")

                # Register in inventory DB — pass post_mode so it's recorded
                post_mode = get_post_mode()
                inv_post_mode = "display" if post_mode == "display" else "claim"
                register_inventory(self.cfg.backend_url, item_code, inv_post_mode)

                # Post to catalog based on WATCHER_POST_MODE — re-read each time
                if post_mode in ("display", "auto"):
                    cat_id = self.catalog_channel_for(rating)
                    cat_ch = self.get_channel(cat_id) or await self.fetch_channel(cat_id)
                    embed = discord.Embed(title=item_code, color=0x2b2d31)
                    embed.set_image(url=f"attachment://{wm_dst.name}")

                    if post_mode == "display":
                        # Display only — no claim button
                        await cat_ch.send(embed=embed, file=discord.File(wm_dst))
                        log(f"Display-posted: {item_code} (no claim button)")
                    else:
                        # Auto — with claim button
                        await cat_ch.send(embed=embed, file=discord.File(wm_dst), view=self.claim_view(item_code))
                        log(f"Auto-published: {item_code} (with claim button)")
                    await asyncio.sleep(self.cfg.catalog_delay_sec)

                self.state.mark_processed(src_path, item_code, rating)
                log(f"✓ Done: {item_code} [{rating.upper()}]")

            except Exception as e:
                log(f"ERROR processing {src_path.name}: {e}", "ERROR")


class InboxHandler(FileSystemEventHandler):
    def __init__(self, client: WatcherClient, rating: RATING):
        self.client = client
        self.rating = rating

    def on_created(self, event):
        if event.is_directory:
            return
        p = Path(event.src_path)
        if p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
            log(f"Ignored (unsupported type): {p.name}", "SKIP")
            return
        # Only enqueue if processing is enabled (not paused)
        if self.client.processing_enabled:
            asyncio.run_coroutine_threadsafe(
                self.client.enqueue_file(p, self.rating), self.client.loop
            )
        else:
            log(f"Staged (waiting for manual trigger): {p.name}", "INFO")


async def main():
    clear_log()
    log("=== Watcher starting ===")

    parent = Path(_read_env("WATCHER_PARENT_DIR", r"D:\V3Shows"))

    cfg = WatcherConfig(
        backend_url             = _read_env("BACKEND_URL", "http://127.0.0.1:8000"),
        discord_token           = _read_env("DISCORD_TOKEN", ""),
        parent_dir              = parent,
        inbox_sfw               = parent / "INBOX" / "SFW",
        inbox_nsfw              = parent / "INBOX" / "NSFW",
        upload_thread_raw_sfw   = int(_read_env("UPLOAD_THREAD_RAW_SFW",  "0")),
        upload_thread_wm_sfw    = int(_read_env("UPLOAD_THREAD_WM_SFW",   "0")),
        upload_thread_raw_nsfw  = int(_read_env("UPLOAD_THREAD_RAW_NSFW", "0")),
        upload_thread_wm_nsfw   = int(_read_env("UPLOAD_THREAD_WM_NSFW",  "0")),
        catalog_sfw_channel_id  = int(_read_env("CATALOG_SFW_CHANNEL_ID",  "0")),
        catalog_nsfw_channel_id = int(_read_env("CATALOG_NSFW_CHANNEL_ID", "0")),
        watermark_template_sfw  = Path(_read_env("WM_TEMPLATE_SFW",  r".\templates\sfw.png")),
        watermark_template_nsfw = Path(_read_env("WM_TEMPLATE_NSFW", r".\templates\nsfw.png")),
    )

    cfg.inbox_sfw.mkdir(parents=True, exist_ok=True)
    cfg.inbox_nsfw.mkdir(parents=True, exist_ok=True)

    log(f"Watching SFW:    {cfg.inbox_sfw}")
    log(f"Watching NSFW:   {cfg.inbox_nsfw}")
    log(f"Backend:         {cfg.backend_url}")
    log(f"Post mode:       {get_post_mode()}")

    # Key the state DB by the active show_id so each show gets its own
    # counters starting at N001 / S001.  Falls back to an empty string so
    # the heartbeat loop can detect the first real show on its first poll.
    state_root = cfg.parent_dir / "_watcher_state"
    state_root.mkdir(parents=True, exist_ok=True)

    try:
        r              = requests.get(f"{cfg.backend_url}/shows/active", timeout=5)
        active_show_id = (r.json().get("active_show") or "").strip()
    except Exception:
        active_show_id = ""

    if active_show_id:
        safe_id = "".join(
            c if c.isalnum() or c in ("-", "_") else "_" for c in active_show_id
        )
        state = StateDB(state_root / f"{safe_id}.sqlite")
        log(f"Active show:     {active_show_id}")
        log(f"State DB:        {state_root / (safe_id + '.sqlite')}")
    else:
        # No active show yet — use a temporary DB; heartbeat will re-key on first show
        state = StateDB(state_root / "_pending.sqlite")
        log("State DB:        _pending.sqlite (no active show — will re-key on first show)")

    client = WatcherClient(cfg, state, initial_show_id=active_show_id)

    obs = Observer()
    obs.schedule(InboxHandler(client, "sfw"),  str(cfg.inbox_sfw),  recursive=False)
    obs.schedule(InboxHandler(client, "nsfw"), str(cfg.inbox_nsfw), recursive=False)
    obs.start()
    log("Observer started — ready for files")

    try:
        await client.start(cfg.discord_token.strip())
    finally:
        obs.stop()
        obs.join()
        log("=== Watcher stopped ===")


if __name__ == "__main__":
    asyncio.run(main())
