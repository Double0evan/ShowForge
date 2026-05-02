"""
Discord/core_client.py

HTTP client for calling the FastAPI backend.
Used by the Discord bot for user management, claims, shows, media, and vouchers.
"""

from __future__ import annotations

from dataclasses import dataclass
import requests


@dataclass(frozen=True)
class CoreClient:
    base_url: str

    # ── Users ─────────────────────────────────────────────────────────────────

    def upsert_discord_user(self, discord_user_id: int, display_name: str) -> tuple[int, bool]:
        """Returns (internal_user_id, was_merged)."""
        r = requests.post(
            f"{self.base_url}/users/upsert_discord",
            params={"discord_user_id": str(discord_user_id), "display_name": display_name},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        return int(data["user_id"]), bool(data.get("merged_from"))

    def upsert_guest_user(self, display_name: str, kind: str = "guest", note: str = "") -> int:
        """Creates a pending/guest user in the active show DB."""
        r = requests.post(
            f"{self.base_url}/users/create_pending",
            params={"display_name": display_name},
            timeout=10,
        )
        r.raise_for_status()
        return int(r.json()["user_id"])

    # ── Claims ────────────────────────────────────────────────────────────────

    def attempt_claim(self, item_code: str, user_id: int) -> dict:
        r = requests.post(
            f"{self.base_url}/claims/attempt",
            params={"item_code": item_code, "user_id": user_id},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()

    # ── Shows ─────────────────────────────────────────────────────────────────

    def create_show(self, date: str, name: str) -> dict:
        r = requests.post(
            f"{self.base_url}/shows/new",
            json={"date": date, "name": name},
            timeout=20,
        )
        r.raise_for_status()
        return r.json()

    def get_active_show(self) -> dict:
        """Returns active show info including db_path."""
        r = requests.get(f"{self.base_url}/shows/active", timeout=10)
        r.raise_for_status()
        return r.json()

    def set_show_setting(self, key: str, value: str) -> dict:
        r = requests.post(
            f"{self.base_url}/shows/settings/set",
            params={"key": key, "value": value},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()

    def get_show_setting(self, key: str) -> str | None:
        r = requests.get(
            f"{self.base_url}/shows/settings/get",
            params={"key": key},
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("value")

    # ── Media ─────────────────────────────────────────────────────────────────

    def get_media(self, *, item_code: str, variant: str, rating: str) -> dict | None:
        r = requests.get(
            f"{self.base_url}/media/get",
            params={"item_code": item_code, "variant": variant, "rating": rating},
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("media")

    # ── Vouchers ──────────────────────────────────────────────────────────────

    def award_voucher(self, user_id: int, reason: str = "STAFF_ADJUST", note: str = "") -> dict:
        """Award a single voucher credit to a user."""
        r = requests.post(
            f"{self.base_url}/vouchers/award",
            params={"user_id": user_id, "reason": reason, "note": note},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
