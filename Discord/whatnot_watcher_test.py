"""
whatnot_watcher_test.py
Screen OCR watcher for Whatnot activity feed.
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

_script_dir = Path(__file__).resolve().parent
_env_candidates = [
    _script_dir / "Discord" / ".env",
    _script_dir / ".env",
]
from dotenv import load_dotenv
for _ep in _env_candidates:
    if _ep.exists():
        load_dotenv(dotenv_path=_ep, override=True)
        break

pytesseract.pytesseract.tesseract_cmd = r"F:\tesseract\tesseract.exe"

SCAN_INTERVAL = 2.0
DEDUPE_WINDOW = 60
BOT_API_URL = "http://127.0.0.1:8001"

SALE_PATTERN = re.compile(
    r"@?([\w][\w\d_\.]{2,})[)\]|,]?\s+won\s+the\s+(auction|giveaway)",
    re.IGNORECASE,
)
ITEM_PATTERN = re.compile(
    r"(?:single|lot|sale)\s+on\s+screen\s+#\s*(\d+)",
    re.IGNORECASE,
)
BARE_NUM_PATTERN  = re.compile(r"#\s*(\d{2,4})")
TIMESTAMP_PATTERN = re.compile(r"^\d+\s+(?:second|minute|hour)s?\s+ago", re.IGNORECASE)
NOW_PATTERN       = re.compile(r"^now$", re.IGNORECASE)
USERNAME_ONLY_PATTERN = re.compile(r"^@?([\w][\w\d_\.]{2,})[)\]|,]?$", re.IGNORECASE)
WON_PATTERN       = re.compile(r"won\s+the\s+(auction|giveaway)", re.IGNORECASE)


def preprocess(img):
    img = img.convert("L")
    w, h = img.size
    img = img.resize((w * 2, h * 2), Image.LANCZOS)
    img = ImageEnhance.Contrast(img).enhance(1.8)
    img = img.filter(ImageFilter.SHARPEN)
    return img


def post_sale_to_bot(auction_number: int, username: str) -> bool:
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
    raw_lines = [l.strip() for l in text.splitlines()]

    lines = []
    i = 0
    while i < len(raw_lines):
        line = raw_lines[i]
        u = USERNAME_ONLY_PATTERN.match(line)
        if u and i + 1 < len(raw_lines) and WON_PATTERN.search(raw_lines[i + 1]):
            merged = u.group(1) + " " + raw_lines[i + 1]
            if i + 2 < len(raw_lines) and raw_lines[i + 2].lower().startswith("the "):
                merged += " " + raw_lines[i + 2]
                i += 3
            else:
                i += 2
            lines.append(merged)
            continue
        if re.search(r"@?[\w][\w\d_\.]{2,}\s+won$", line, re.IGNORECASE) and i + 1 < len(raw_lines):
            next_line = raw_lines[i + 1]
            if re.match(r"the\s+(auction|giveaway)", next_line, re.IGNORECASE):
                lines.append(line + " " + next_line)
                i += 2
                continue
        lines.append(line)
        i += 1

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
        inline = BARE_NUM_PATTERN.search(line)
        if inline:
            item_text = f"#{inline.group(1)}"
        else:
            for j in range(i + 1, min(i + 8, len(classified))):
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


def pick_monitor():
    """Let user pick which monitor to draw the region on."""
    with mss.mss() as sct:
        monitors = sct.monitors[1:]  # skip [0] (combined)
    if len(monitors) == 1:
        return monitors[0]
    print("\nAvailable monitors:")
    for idx, m in enumerate(monitors):
        print(f"  [{idx + 1}] Monitor {idx + 1}:  {m['width']}x{m['height']}  at ({m['left']}, {m['top']})")
    while True:
        try:
            choice = int(input(f"Select monitor [1-{len(monitors)}]: ").strip())
            if 1 <= choice <= len(monitors):
                return monitors[choice - 1]
        except (ValueError, KeyboardInterrupt):
            pass
        print("Invalid choice.")


def select_region(monitor: dict):
    """
    Draw a region selector overlay on the chosen monitor.
    Uses the monitor's own coordinate space so geometry always works,
    then converts to absolute coords for mss.
    """
    import tkinter as tk
    print("\nOverlay opening in 2 seconds...")
    time.sleep(2)

    # Monitor absolute position and size
    mx, my = monitor["left"], monitor["top"]
    mw, mh = monitor["width"], monitor["height"]

    result = {}
    root = tk.Tk()
    root.overrideredirect(True)
    root.geometry(f"{mw}x{mh}+{mx}+{my}")
    root.attributes("-alpha", 0.35)
    root.attributes("-topmost", True)
    root.configure(bg="black")
    root.lift()
    root.focus_force()
    root.after(50, root.focus_force)

    canvas = tk.Canvas(root, cursor="cross", bg="black", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    label = tk.Label(
        root,
        text="  Drag over activity feed — release to confirm  |  ESC to cancel  ",
        fg="white", bg="#1a1a1a", font=("Arial", 13, "bold"), pady=8, padx=12,
    )
    label.place(relx=0.5, rely=0.02, anchor="n")

    state = {"start": None, "rect": None}

    def on_press(e):
        state["start"] = (e.x, e.y)
        if state["rect"]:
            canvas.delete(state["rect"])

    def on_drag(e):
        if not state["start"]: return
        x0, y0 = state["start"]
        if state["rect"]:
            canvas.delete(state["rect"])
        state["rect"] = canvas.create_rectangle(x0, y0, e.x, e.y, outline="#ff3333", width=3)
        label.config(text=(
            f"  W:{abs(e.x-x0)}  H:{abs(e.y-y0)}"
            f"  —  release to confirm  |  ESC to cancel  "
        ))

    def on_release(e):
        if not state["start"]: return
        x0, y0 = state["start"]
        x1, y1 = e.x, e.y
        w, h = abs(x1 - x0), abs(y1 - y0)
        if w > 10 and h > 10:
            # Canvas coords are relative to monitor top-left
            # Add monitor absolute position to get mss absolute coords
            result["region"] = {
                "left":   min(x0, x1) + mx,
                "top":    min(y0, y1) + my,
                "width":  w,
                "height": h,
            }
        root.destroy()

    def on_escape(e): root.destroy()

    canvas.bind("<ButtonPress-1>",   on_press)
    canvas.bind("<B1-Motion>",       on_drag)
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
            win.geometry(f"{w+border*2}x{h+border*2}+{x-border}+{y-border}")
            canvas = tk.Canvas(win, bg="black", highlightthickness=0,
                               width=w+border*2, height=h+border*2)
            canvas.pack()
            canvas.create_rectangle(0, 0, w+border*2-1, h+border*2-1,
                                    outline="#ff3333", width=border)
            canvas.create_text(4, 4, text=f" {w}×{h} ", anchor="nw",
                               fill="#ff3333", font=("Arial", 9, "bold"))
            win.bind("<Escape>", lambda e: win.destroy())
            win.mainloop()
        except Exception as e:
            print(f"[INDICATOR] {e}")

    threading.Thread(target=_run, daemon=True).start()


def main():
    print("=" * 55)
    print("  WHATNOT ACTIVITY WATCHER")
    print("=" * 55)

    monitor = pick_monitor()
    region  = select_region(monitor)
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
                ts  = datetime.now().strftime("%H:%M:%S")

                raw       = sct.grab(region)
                img       = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
                processed = preprocess(img)
                img.save(r"E:\debug_raw.png")
                processed.save(r"E:\debug_processed.png")

                text  = pytesseract.image_to_string(processed, config=OCR_CONFIG)
                sales = parse_sales(text)

                print(f"[{ts}] scan #{scan_count} — {len(sales)} sale(s) parsed")

                for sale in sales:
                    key     = make_key(sale, now)
                    elapsed = now - seen.get(key, 0)
                    is_new  = key not in seen
                    status  = "NEW" if is_new else f"dup {int(elapsed)}s ago"
                    print(f"         [{status:>12s}]  @{sale['username']}  |  {sale['item']}")
                    if is_new or elapsed > DEDUPE_WINDOW:
                        seen[key] = now
                        print(f"  >>> [{ts}]  @{sale['username']}  —  {sale['item']}  ({sale['type']})")
                        num = re.search(r"#(\d+)", sale["item"])
                        if num:
                            ok = post_sale_to_bot(int(num.group(1)), sale["username"])
                            print(f"         [BOT QUEUE {'OK' if ok else 'FAIL'}]")
                        else:
                            print(f"         [SKIP — auction number unknown]")
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
