"""
Backend/routes/members.py
Proxies member data from the bot's internal API (port 8001).
"""

from __future__ import annotations

from pathlib import Path
from fastapi import APIRouter, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
import requests

BOT_API   = "http://127.0.0.1:8001"
router    = APIRouter()
templates = Jinja2Templates(directory="Backend/ui/templates")


def _find_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "Discord" / ".env").exists():
            return parent
        if (parent / "DB").exists() and (parent / "Discord").exists():
            return parent
        if (parent / "pyproject.toml").exists():
            return parent
    return Path(__file__).resolve().parents[3]


def _fetch_members() -> list[dict]:
    """
    Calls bot /members and returns a normalized flat list.
    member_cache serializes MemberEntry dataclass which has field 'discord_id' (not 'id').
    """
    try:
        r = requests.get(f"{BOT_API}/members", timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print("MEMBERS FETCH ERROR:", e)
        return []

    members: list[dict] = []

    for m in data.get("verified", []):
        members.append({
            "id":           m.get("discord_id", ""),   # field is 'discord_id' in MemberEntry
            "display_name": m.get("display_name") or m.get("username") or "?",
            "username":     m.get("username", ""),
            "roles":        m.get("roles", []),
            "joined_at":    m.get("joined_at", ""),
            "verified":     True,
        })

    for m in data.get("unverified", []):
        members.append({
            "id":           m.get("discord_id", ""),
            "display_name": m.get("display_name") or m.get("username") or "?",
            "username":     m.get("username", ""),
            "roles":        m.get("roles", []),
            "joined_at":    m.get("joined_at", ""),
            "verified":     False,
        })

    members.sort(key=lambda m: (not m["verified"], m["display_name"].lower()))
    return members


@router.get("/ui/members")
def ui_members(request: Request):
    from Core.show_manager import ShowManager
    REPO_ROOT = _find_repo_root()
    shows     = ShowManager(REPO_ROOT)
    active    = shows.get_active()
    members   = _fetch_members()

    return templates.TemplateResponse("index.html", {
        "request":        request,
        "page":           "members",
        "active_show":    active.show_id if active else None,
        "items":          [],
        "claims":         [],
        "users":          [],
        "past_shows":     [],
        "members":        members,
        "env":            {},
        "console_result": None,
        "selected_show":  None,
    })


@router.post("/ui/members/add_guest")
def ui_add_guest(
    display_name: str = Form(...),
    discord_id:   str = Form(""),
    kind:         str = Form("guest"),
    note:         str = Form(""),
):
    """Forwards guest creation to the bot API."""
    try:
        r = requests.post(
            f"{BOT_API}/members/add_guest",
            json={
                "display_name": display_name,
                "discord_id":   discord_id or None,
                "kind":         kind,
                "note":         note,
            },
            timeout=10,
        )
        return r.json()
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
