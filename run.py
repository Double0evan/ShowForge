"""
run.py — V3 Bot Launcher

Run from the repo root:
    python run.py

Opens 3 terminal windows:
    [V3 Backend]  — FastAPI on port 8000
    [V3 Bot]      — Discord bot + internal API on port 8001
    [V3 Watcher]  — File watcher

Then opens http://127.0.0.1:8000/ui in your browser.
"""

import subprocess
import sys
import time
import webbrowser
from pathlib import Path

REPO_ROOT     = Path(__file__).resolve().parent
VENV_ACTIVATE = REPO_ROOT / ".venv" / "Scripts" / "activate"
UI_URL        = "http://127.0.0.1:8000/ui"

PROCESSES = [
    {
        "name":    "V3 Backend",
        "command": "uvicorn Backend.main:app --reload --port 8000",
        "delay":   0,
    },
    {
        "name":    "V3 Bot",
        "command": "python -m Discord.bot",
        "delay":   3,
    },
    {
        "name":    "V3 Watcher",
        "command": "python -m Watcher.watcher_service",
        "delay":   5,
    },
]

BROWSER_DELAY = 6


def launch_window(name: str, command: str) -> subprocess.Popen:
    full_cmd  = f'"{VENV_ACTIVATE}" && {command}'
    shell_cmd = f'start "{name}" cmd /k "{full_cmd}"'
    return subprocess.Popen(shell_cmd, shell=True, cwd=str(REPO_ROOT))


def main():
    print("=" * 50)
    print("  V3 Bot Launcher")
    print("=" * 50)

    if not VENV_ACTIVATE.exists():
        print(f"\n❌ venv not found at: {VENV_ACTIVATE}")
        print("   Run: python -m venv .venv")
        print("        .venv\\Scripts\\activate")
        print("        pip install -r requirements.txt")
        sys.exit(1)

    for p in PROCESSES:
        if p["delay"] > 0:
            print(f"   Waiting {p['delay']}s before {p['name']}...")
            time.sleep(p["delay"])
        print(f"▶  Starting {p['name']}...")
        launch_window(p["name"], p["command"])

    print(f"\n⏳ Opening browser in {BROWSER_DELAY}s...")
    time.sleep(BROWSER_DELAY)
    print(f"🌐 {UI_URL}")
    webbrowser.open(UI_URL)

    print("\n✅ All processes launched.")
    print("   Close the terminal windows to stop each service.")
    print("   Press Ctrl+C here to exit the launcher.\n")

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\nLauncher closed. Services still running in their windows.")


if __name__ == "__main__":
    main()
