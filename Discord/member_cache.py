"""
Discord/member_cache.py

In-memory cache of Discord guild members.
Updated by bot events. Read by bot internal API for the UI member page and console autocomplete.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional

@dataclass
class MemberEntry:
    discord_id:       str
    display_name:     str
    username:         str
    status:           str   # 'verified' | 'unverified'
    internal_user_id: Optional[int] = None


_members:         dict[str, MemberEntry] = {}
_verified_role_id: int = 0


def init(verified_role_id: int) -> None:
    global _verified_role_id
    _verified_role_id = verified_role_id


def _is_verified(member) -> bool:
    if _verified_role_id == 0:
        return True
    return any(r.id == _verified_role_id for r in member.roles)


def upsert_member(member) -> MemberEntry:
    entry = MemberEntry(
        discord_id   = str(member.id),
        display_name = member.display_name,
        username     = str(member),
        status       = "verified" if _is_verified(member) else "unverified",
    )
    _members[str(member.id)] = entry
    return entry


def remove_member(member_id: int) -> None:
    _members.pop(str(member_id), None)


def get_all() -> list[dict]:
    return [asdict(m) for m in sorted(_members.values(), key=lambda m: m.display_name.lower())]


def get_verified() -> list[dict]:
    return [asdict(m) for m in sorted(_members.values(), key=lambda m: m.display_name.lower()) if m.status == "verified"]


def get_unverified() -> list[dict]:
    return [asdict(m) for m in sorted(_members.values(), key=lambda m: m.display_name.lower()) if m.status == "unverified"]


def search(query: str, limit: int = 10) -> list[dict]:
    q = query.lower().strip()
    if not q:
        return []
    starts, contains = [], []
    for m in _members.values():
        name = m.display_name.lower()
        user = m.username.lower()
        if name.startswith(q) or user.startswith(q):
            starts.append(asdict(m))
        elif q in name or q in user:
            contains.append(asdict(m))
    return (starts + contains)[:limit]


def get_member_by_name(name: str) -> Optional[MemberEntry]:
    name_lower = name.lower().strip()
    for m in _members.values():
        if m.display_name.lower() == name_lower:
            return m
    return None


def count() -> dict:
    verified   = sum(1 for m in _members.values() if m.status == "verified")
    unverified = sum(1 for m in _members.values() if m.status == "unverified")
    return {"total": len(_members), "verified": verified, "unverified": unverified}
