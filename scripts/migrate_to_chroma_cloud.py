#!/usr/bin/env python3
"""Migrate RAG data to Chroma Cloud (ROADMAP.md Phase 9).

Not a vector-level export/import — this project holds no irreplaceable embedded content.
rag/ingest.py's ingest_pokemon_data() already re-fetches Pokemon data from PokeAPI and Smogon
tier/strategy data from Smogon as the source of truth, then calls PokemonVectorStore.add_pokemon
/add_documents — which, with CHROMA_API_KEY set, is already the Chroma Cloud path
(rag/vector_store.py's "presence of the value is the switch" behavior). "Migrating" is just
running that same ingestion again with Chroma Cloud active, so this script is a thin, explicit
entry point for that — not a separate migration implementation.

Usage:
    uv run python scripts/migrate_to_chroma_cloud.py

Requires CHROMA_API_KEY to be set (and CHROMA_TENANT/CHROMA_DATABASE, if your account needs
them) — see .env.example. Refuses to run otherwise, rather than silently re-ingesting into
local self-hosted ChromaDB and calling that a migration.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/ is importable — mirrors app.py/api_server.py/provision_tenant.py's own setup.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))


def main() -> None:
    from config import config

    if not config.chroma_api_key:
        print(
            "CHROMA_API_KEY is not set — nothing to migrate to. Set it (see .env.example) and re-run.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    from rag.ingest import ingest_pokemon_data

    print(f"Migrating to Chroma Cloud (tenant={config.chroma_tenant or 'default'})...")
    count = ingest_pokemon_data()
    print(f"Done — {count} Pokemon (+ their Smogon strategy documents) ingested into Chroma Cloud.")


if __name__ == "__main__":
    main()
