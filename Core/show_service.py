"""
Core/show_service.py
"""
from pathlib import Path
from Core.show_manager import ShowManager


def _find_repo_root() -> Path:
    """Walk up from this file to find the project root."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "Discord" / ".env").exists():
            return parent
        if (parent / "DB").exists() and (parent / "Discord").exists():
            return parent
        if (parent / "pyproject.toml").exists():
            return parent
    return Path(__file__).resolve().parents[2]


manager = ShowManager(_find_repo_root())


def require_active_show():
    active = manager.get_active()
    if not active:
        raise Exception("No active show set")
    return active
