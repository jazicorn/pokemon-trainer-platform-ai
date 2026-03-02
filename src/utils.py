"""Shared utility functions."""

from __future__ import annotations

import httpx

from config import config


def is_chromadb_running() -> bool:
    """Check if the ChromaDB server is reachable and healthy."""
    try:
        response = httpx.get(f"{config.chromadb_url}/api/v2/heartbeat", timeout=2.0)
        return response.status_code == 200
    except httpx.RequestError:
        return False
