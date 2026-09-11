"""Shared utility functions."""

from __future__ import annotations

import httpx

from config import config


def is_chromadb_running() -> bool:
    """Check if the self-hosted ChromaDB server is reachable and healthy.

    Self-hosted specifically — startup.py's own local-Docker-ChromaDB auto-start logic (CLI
    only) depends on this checking exactly that, regardless of whether Chroma Cloud is also
    configured. For a reachability check that's correct in either mode, see
    is_vector_store_running() below — that's what api/app.py's /health uses.
    """
    try:
        response = httpx.get(f"{config.chromadb_url}/api/v2/heartbeat", timeout=2.0)
        return response.status_code == 200
    except httpx.RequestError:
        return False


def is_vector_store_running() -> bool:
    """Check whether the RAG layer's actual active backend is reachable — Chroma Cloud if
    config.chroma_api_key is set (rag/vector_store.py's own "presence of the value is the
    switch" idiom), self-hosted ChromaDB otherwise.

    Exists because is_chromadb_running() alone would silently misreport a healthy Chroma Cloud
    deployment as unhealthy — it only ever checks config.chromadb_url, which a Chroma-Cloud-only
    deployment (e.g. Fly, per docs/DEPLOYMENT.md) has no reason to have anything reachable at.
    """
    if not config.chroma_api_key:
        return is_chromadb_running()

    try:
        from rag.vector_store import create_cloud_client

        create_cloud_client().heartbeat()
        return True
    except Exception:
        return False
