from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .db import ensure_db

UTC = timezone.utc

def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()

@dataclass(frozen=True)
class ShowRef:
    show_id: str              # folder name
    db_path: Path             # path to sqlite db

class ShowManager:
    """
    Controls active show pointer and per-show db creation.

    Layout:
      DB/
        active_show.json
        shows/<show_id>/show.db
    """
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.db_root = repo_root / "DB"
        self.shows_root = self.db_root / "shows"
        self.active_file = self.db_root / "active_show.json"
        self.shows_root.mkdir(parents=True, exist_ok=True)

    def _show_db_path(self, show_id: str) -> Path:
        return self.shows_root / show_id / "show.db"

    def get_active(self) -> Optional[ShowRef]:
        if not self.active_file.exists():
            return None
        data = json.loads(self.active_file.read_text(encoding="utf-8"))
        show_id = data.get("show_id")
        if not show_id:
            return None
        db_path = self._show_db_path(show_id)
        if not db_path.exists():
            return None

        # IMPORTANT:
        # If the DB already existed from an older version, upgrade it now.
        ensure_db(db_path)

        return ShowRef(show_id=show_id, db_path=db_path)


    def set_active(self, show_id: str) -> ShowRef:
        db_path = self._show_db_path(show_id)
        ensure_db(db_path)
        payload = {"show_id": show_id, "set_at": now_iso()}
        self.active_file.parent.mkdir(parents=True, exist_ok=True)
        self.active_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return ShowRef(show_id=show_id, db_path=db_path)

    def clear_active(self) -> None:
        if self.active_file.exists():
            self.active_file.unlink()

    def create_new_show(self, date_yyyy_mm_dd: str, name: str) -> ShowRef:
        safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name.strip())
        show_id = f"{date_yyyy_mm_dd}_{safe_name}"
        return self.set_active(show_id)
