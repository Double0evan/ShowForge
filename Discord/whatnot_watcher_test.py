"""
whatnot_watcher_test.py

Screen OCR watcher for Whatnot activity feed.
PRINT ONLY - does not post to backend or Discord.
"""

import re
from pathlib import Path
import sys
import time
from datetime import datetime

try:
    import mss
except ImportError:
    print("Missing: pip install mss"); sys.exit(1)

try:
    from PIL import Image, ImageFilter, ImageEnhance
except ImportError:
    print("Missing: pip install pillow"); sys.exit(1)

try:
    import pytesseract
except ImportError:
    print("Missing: pip install pytesseract"); sys.exit(1)

import requests

# Locate .env regardless of where the script lives:
# - If in project root: Discord/.env
# - If in Discord/: .env (same folder)
_script_dir = Path(__file__).resolve().parent
_env_candidates = [
    _script_dir / "Discord" / ".env",   # running from project root
    _script_dir / ".env",               # running from Discord/ folder
]
from dotenv import load_dotenv
for _ep in _env_candidates:
    if _ep.exists():
        load_dotenv(dotenv_path=_ep, override=True)
        break

pytesseract.pytesseract.tesseract_cmd = r"F:\tesseract\tesseract.exe"

SCAN_INTERVAL = 2.0
DEDUPE_WINDOW = 60

# Bot internal API — watcher posts detected sales here
BOT_API_URL = "http://127.0.0.1:8001"

# Allow ) | , after username — OCR reads the badge border as punctuation
SALE_PATTERN = re.compile(
    r"@?([\w][\w\d_\.]{2,})[)\]|,]?\s+won\s+the\s+(auction|giveaway)",
    re.IGNORECASE,
)

ITEM_PATTERN = re.compile(
    r"(?:single|lot|sale)\s+on\s+screen\s+#\s*(\d+)",
    re.IGNORECASE,
)
BARE_NUM_PATTERN = re.compile(r"#\s*(\d{2,4})")
TIMESTAMP_PATTERN = re.compile(r"^\d+\s+(?:second|minute|hour)s?\s+ago", re.IGNORECASE)
NOW_PATTERN = re.compile(r"^now$", re.IGNORECASE)


def preprocess(img):
    img = img.convert("L")
    w, h = img.size
    img = img.resize((w * 2, h * 2), Image.LANCZOS)
    img = ImageEnhance.Contrast(img).enhance(1.8)
    img = img.filter(ImageFilter.SHARPEN)
    return img



def post_sale_to_bot(auction_number: int, username: str) -> bool:
    """Push a detected sale into the bot bin queue. Returns True on success."""
    try:
        r = requests.post(
            f"{BOT_API_URL}/bin/sale",
            json={"auction_number": auction_number, "username": username},
            timeout=5,
        )
        return r.json().get("ok", False)
    except Exception as e:
        print(f"  [WARN] Could not post sale to bot: {e}")
        return False


def parse_sales(text):
    lines = [l.strip() for l in text.splitlines()]
    classified = []
    for line in lines:
        if not line:
            classified.append(("BLANK", line, None)); continue
        m = SALE_PATTERN.search(line)
        if m:
            classified.append(("SALE", line, {"username": m.group(1), "type": m.group(2).lower()})); continue
        m = ITEM_PATTERN.search(line)
        if m:
            classified.append(("ITEM", line, {"item": f"#{m.group(1)}"})); continue
        m = BARE_NUM_PATTERN.search(line)
        if m and not TIMESTAMP_PATTERN.search(line):
            classified.append(("ITEM", line, {"item": f"#{m.group(1)}"})); continue
        if TIMESTAMP_PATTERN.search(line) or NOW_PATTERN.match(line):
            classified.append(("TIMESTAMP", line, None)); continue
        classified.append(("OTHER", line, None))

    results = []
    for i, (kind, line, data) in enumerate(classified):
        if kind != "SALE":
            continue
        item_text = "unknown"
        for j in range(i + 1, min(i + 5, len(classified))):
            jkind, _, jdata = classified[j]
            if jkind == "SALE":
                break
            if jkind == "ITEM":
                item_text = jdata["item"]
                break
        results.append({"username": data["username"], "type": data["type"], "item": item_text})
    return results


def make_key(sale, now):
    num = re.search(r"#(\d+)", sale["item"])
    if num:
        return f"item{num.group(1)}"
    if sale["item"] == "unknown":
        return f"{sale['username'].lower()}|{sale['type']}|{int(now // DEDUPE_WINDOW)}"
    return f"{sale['username'].lower()}|{sale['item'].lower()}"


def _get_virtual_desktop():
    """Return (left, top, width, height) of the full virtual desktop spanning all monitors."""
    with mss.mss() as sct:
        # monitors[0] is the combined virtual screen in mss
        m = sct.monitors[0]
        return m["left"], m["top"], m["width"], m["height"]


def select_region():
    """
    Full-desktop overlay for region selection — works across all monitors.
    The tkinter window is positioned at the virtual desktop origin so it
    covers every monitor, not just the primary.
    """
    import tkinter as tk
    print("\nOverlay opening in 2 seconds...")
    time.sleep(2)

    vx, vy, vw, vh = _get_virtual_desktop()

    result = {}
    root = tk.Tk()
    root.overrideredirect(True)
    # Span the full virtual desktop (all monitors)
    root.geometry(f"{vw}x{vh}+{vx}+{vy}")
    root.attributes("-alpha", 0.35)
    root.attributes("-topmost", True)
    root.configure(bg="black")
    root.lift()
    root.focus_force()
    root.after(50, root.focus_force)

    canvas = tk.Canvas(root, cursor="cross", bg="black", highlightthickness=0)
    canvas.pack(fill=tk.BOTH, expand=True)

    label = tk.Label(
        root,
        text="  Drag over activity feed — release to confirm  |  ESC to cancel  ",
        fg="white", bg="#1a1a1a", font=("Arial", 13, "bold"), pady=8, padx=12,
    )
    label.place(relx=0.5, rely=0.02, anchor="n")

    # Monitor dividers — visual guide showing monitor boundaries
    with mss.mss() as sct:
        for mon in sct.monitors[1:]:  # skip [0] which is the combined screen
            rx = mon["left"] - vx
            ry = mon["top"]  - vy
            rw = mon["width"]
            rh = mon["height"]
            canvas.create_rectangle(rx, ry, rx + rw, ry + rh,
                                    outline="#444444", width=1, dash=(6, 4))
            canvas.create_text(rx + rw // 2, ry + 20,
                               text=f"Monitor {mon.get('name', '')}  {rw}×{rh}",
                               fill="#666666", font=("Arial", 10))

    state = {"start": None, "rect": None}

    def on_press(e):
        state["start"] = (e.x + vx, e.y + vy)  # store absolute coords
        if state["rect"]: canvas.delete(state["rect"])

    def on_drag(e):
        if not state["start"]: return
        x0, y0 = state["start"][0] - vx, state["start"][1] - vy
        if state["rect"]: canvas.delete(state["rect"])
        state["rect"] = canvas.create_rectangle(x0, y0, e.x, e.y,
                                                 outline="#ff3333", width=3)
        label.config(text=(
            f"  W:{abs(e.x - x0)}  H:{abs(e.y - y0)}"
            f"  pos:({min(x0, e.x) + vx}, {min(y0, e.y) + vy})"
            f"  —  release to confirm  |  ESC to cancel  "
        ))

    def on_release(e):
        if not state["start"]: return
        x0, y0 = state["start"]          # absolute
        x1, y1 = e.x + vx, e.y + vy     # absolute
        w, h = abs(x1 - x0), abs(y1 - y0)
        if w > 10 and h > 10:
            result["region"] = {
                "left":  min(x0, x1),
                "top":   min(y0, y1),
                "width":  w,
                "height": h,
            }
        root.destroy()

    def on_escape(e): root.destroy()

    canvas.bind("<ButtonPress-1>",  on_press)
    canvas.bind("<B1-Motion>",      on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    root.bind("<Escape>", on_escape)
    root.mainloop()

    if not result:
        print("No region selected.")
        sys.exit(0)

    r = result["region"]
    print(f"Region: left={r['left']} top={r['top']} width={r['width']} height={r['height']}")
    return r


def show_region_indicator(region: dict):
    """
    Draws a persistent always-on-top colored border exactly over the
    capture region so you can see what the watcher is reading at all times.
    Runs in a background thread — close by pressing ESC in the indicator window.
    """
    import tkinter as tk
    import threading

    def _run():
        try:
            x, y, w, h = region["left"], region["top"], region["width"], region["height"]
            border = 3

            win = tk.Tk()
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            win.attributes("-transparentcolor", "black")
            win.configure(bg="black")
            # Position window exactly over the capture region
            win.geometry(f"{w + border*2}x{h + border*2}+{x - border}+{y - border}")

            canvas = tk.Canvas(win, bg="black", highlightthickness=0,
                               width=w + border*2, height=h + border*2)
            canvas.pack()

            # Outer border rectangle (visible)
            canvas.create_rectangle(
                0, 0, w + border*2 - 1, h + border*2 - 1,
                outline="#ff3333", width=border,
            )
            # Interior is transparent (black = transparent due to transparentcolor)

            # Small label showing region size
            canvas.create_text(
                4, 4,
                text=f" {w}×{h} ",
                anchor="nw",
                fill="#ff3333",
                font=("Arial", 9, "bold"),
            )

            def on_escape(e): win.destroy()
            win.bind("<Escape>", on_escape)
            win.mainloop()
        except Exception as e:
            print(f"[INDICATOR] {e}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


def main():
    print("=" * 55)
    print("  WHATNOT ACTIVITY WATCHER  (print-only test mode)")
    print("=" * 55)
    region = select_region()
    show_region_indicator(region)
    print(f"\nScanning every {SCAN_INTERVAL}s  |  Ctrl+C to stop\n")
    print("-" * 55)

    seen = {}
    scan_count = 0
    OCR_CONFIG = "--psm 6 --oem 3"

    with mss.mss() as sct:
        while True:
            try:
                scan_count += 1
                now = time.time()
                ts = datetime.now().strftime("%H:%M:%S")

                raw = sct.grab(region)
                img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
                processed = preprocess(img)
                img.save("E:\\debug_raw.png")
                processed.save("E:\\debug_processed.png")

                text = pytesseract.image_to_string(processed, config=OCR_CONFIG)
                sales = parse_sales(text)

                print(f"[{ts}] scan #{scan_count} — {len(sales)} sale(s) parsed")

                for sale in sales:
                    key = make_key(sale, now)
                    elapsed = now - seen.get(key, 0)
                    is_new = key not in seen
                    status = "NEW" if is_new else f"dup {int(elapsed)}s ago"
                    print(f"         [{status:>12s}]  @{sale['username']}  |  {sale['item']}")
                    if is_new or elapsed > DEDUPE_WINDOW:
                        seen[key] = now
                        print(f"  >>> [{ts}]  @{sale['username']}  —  {sale['item']}  ({sale['type']})")
                        # Push to bot queue so bin listener can match it
                        num = re.search(r"#(\d+)", sale["item"])
                        if num:
                            ok = post_sale_to_bot(int(num.group(1)), sale["username"])
                            print(f"         [BOT QUEUE {'OK' if ok else 'FAIL'}]")
                        print()

                time.sleep(SCAN_INTERVAL)

            except KeyboardInterrupt:
                print("\nStopped.")
                print(f"Total scans: {scan_count} | Unique seen: {len(seen)}")
                break
            except Exception as e:
                print(f"[ERROR] {e}")
                time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    main()
