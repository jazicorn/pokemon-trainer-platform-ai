"""Loads generated JSON (or live platform DB data) into typed Pydantic models.

No agent reads raw JSON directly — everything goes through this module.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from data.models import PlatformTrades, UserCollection


def get_data_dir() -> Path:
    """Return the ``data/`` directory at the project root.

    Resolves relative to this file's location (``src/data/loader.py`` →
    project root), matching ``memory.database.get_db_path()``'s convention.
    A standalone function (not a class method) so it's easy to monkeypatch in
    tests without touching the module-level ``@lru_cache``.
    """
    return Path(__file__).parent.parent.parent / "data"


@lru_cache(maxsize=1)
def load_platform_trades() -> PlatformTrades:
    """Load platform-wide trade history.

    Reads from the live platform database when ``PLATFORM_DB_URL`` is
    configured, otherwise from ``data/platform_trades.json``. Cached for the
    life of the process — call ``load_platform_trades.cache_clear()`` first
    if you need a fresh read (e.g. after redirecting ``get_data_dir`` in a
    test).
    """
    from data.platform_db import get_platform_db

    db = get_platform_db()
    if db is not None:
        return db.fetch_trades(days=90)

    path = get_data_dir() / "platform_trades.json"
    with open(path) as f:
        raw = json.load(f)
    return PlatformTrades.model_validate(raw)


def load_user_collection(user_id: str) -> UserCollection:
    """Load a single user's collection and preferences.

    Reads from the live platform database when ``PLATFORM_DB_URL`` is
    configured, otherwise from ``data/user_collection.json``. Raises
    ``ValueError`` if the mock file was generated for a different user —
    loading it under the wrong ID would be a programming error.
    """
    from data.platform_db import get_platform_db

    db = get_platform_db()
    if db is not None:
        return db.fetch_user_collection(user_id)

    path = get_data_dir() / "user_collection.json"
    with open(path) as f:
        raw = json.load(f)
    collection = UserCollection.model_validate(raw)

    if collection.user_id != user_id:
        raise ValueError(f"User '{user_id}' not found in {path} (file is for '{collection.user_id}')")

    return collection
