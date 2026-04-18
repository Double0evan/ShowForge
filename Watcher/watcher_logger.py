"""
Watcher/watcher_logger.py
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

MAX_LINES = 500

_HERE         = Path(__file__).resolve().parent
REPO_ROOT     = _HERE.parent
LOG_DIR       = REPO_ROOT / "logs"
LOG_FILE      = LOG_DIR / "watcher.log"
HEARTBEAT_FILE = LOG_DIR / "watcher.heartbeat"


def _ensure_dir():
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def log(msg: str, level: str = "INFO"):
    _ensure_dir()
    now  = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{now}] [{level}] {msg}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)
    try:
        lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
        if len(lines) > MAX_LINES:
            LOG_FILE.write_text("\n".join(lines[-MAX_LINES:]) + "\n", encoding="utf-8")
    except Exception:
        pass
    print(line, end="")


def heartbeat():
    _ensure_dir()
    try:
        HEARTBEAT_FILE.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
    except Exception:
        pass


def read_lines(n: int = 100) -> list[str]:
    if not LOG_FILE.exists():
        return []
    try:
        return LOG_FILE.read_text(encoding="utf-8").splitlines()[-n:]
    except Exception:
        return []


def is_alive(timeout_seconds: int = 15) -> bool:
    if not HEARTBEAT_FILE.exists():
        return False
    try:
        ts    = datetime.fromisoformat(HEARTBEAT_FILE.read_text(encoding="utf-8").strip())
        return (datetime.now(timezone.utc) - ts).total_seconds() < timeout_seconds
    except Exception:
        return False


def clear():
    _ensure_dir()
    LOG_FILE.write_text("", encoding="utf-8")
