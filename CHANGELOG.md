## v0.2.0 (2026-09-08)


- fix(startup): capture chromadb-docker.sh stderr, add __main__ entrypoint
- `python -m src.startup` did nothing — the module had no `if __name__ ==
"__main__"` block, so `make ingest`/`make generate-data`-style direct
invocations of startup() silently no-opped. Add the entrypoint so it
runs the full startup sequence (env validation, DB init, telemetry
prompt, ChromaDB) standalone, per GETTING_STARTED.md's "Start Services"
step.
- Also stop discarding chromadb-docker.sh's stderr. It was piped to
DEVNULL to suppress noisy Colima/Lima boot logs, but that hid the
actual diagnostic error on failure too (e.g. Docker's own error text
when `docker run` can't start a container it just created), leaving
only the generic "ChromaDB is required to run this program" message.
Extract _run_chromadb_script() to capture stderr and print it (dimmed)
only when the script fails, keeping the happy path silent.
- docs(getting-started): document MacPorts as a Docker/Colima install
path alongside Homebrew, for machines where Homebrew doesn't work well
(e.g. older macOS).
- fix(rag): correct Smogon tier data endpoint path
- TIER_FORMATS used a `formats-data/<id>` path that doesn't exist on the
pkmn.github.io/smogon API, causing every tier fetch in get_tier_map()
to 404 during ingestion. The real API only exposes analyses/formats/
imgs/sets/stats/teams — no formats-data endpoint.
- Point each tier at sets/gen9<tier> instead, the same /sets endpoint
get_sets()/get_analyses() already use successfully. A per-tier
sets/<format-id>.json file is keyed directly by Pokemon name, giving
exactly the species-per-tier list get_tier_map() needs.
- Verified against the live API (all six tiers return data) and via a
full `python -m src.rag.ingest` run — 368 Pokemon now get real tier
assignments instead of an empty map.
- fix: make src/ importable for python -m src.* invocations
- Nothing put src/ on sys.path except two manual sys.path.insert() calls
(app.py, for `python app.py`; tests/conftest.py, for pytest) — any
`python -m src.*` invocation bypassed both. This silently broke
make ingest, make generate-data, and the GETTING_STARTED.md-documented
`python -m src.startup` / `src.evals.*` commands.
- Adds dev-mode-dirs = ["src"] so uv sync's editable install puts src/ on
sys.path universally, plus an include/sources mapping so a real
(non-editable) wheel build lays out the same way.
- test: extend make lint to check tests/, fix all 353 pyright errors
- feat: add Ollama Cloud support and .env/.env.local auto-loading
- Ollama Cloud:
- llama-cloud auto-detects transport from OLLAMA_URL (local-proxy vs direct
  API) instead of needing two separate model keys
- Fixed OLLAMA_BASE_URL never being set at all (pydantic-ai's OllamaProvider
  reads that, not this project's OLLAMA_URL) and missing its required /v1
  suffix — every "ollama:*" model was silently broken before this
- validate_environment() now checks OLLAMA_API_KEY for the direct-API
  transport, matching every other provider
- New make run-ollama-cloud-direct target (no local ollama install needed)
- New docs/REFERENCE/OLLAMA_CLOUD_MODELS.md model snapshot
- .env loading:
- Added python-dotenv; .env and .env.local (new, gitignored) now load
  automatically via config.py — previously .env.example's "copy to .env"
  instructions didn't actually do anything without manual sourcing
- Real environment variables always win over both files; .env.local wins
  over .env
- Also fixes the long-dead OLLAMA_HOST env var name in GETTING_STARTED.md.

## v0.1.0 (2026-09-08)


- ci: add release.yml and image-publish.yml, split CHANGELOG into HISTORY.md
- fix: remove basedpyright-only settings from pyright config
- chore: ignore .claude/ directories
- fix: sort imports now that data.* resolves as first-party
- Adding src/data/ earlier made data.* a resolvable first-party package,
but the files that import from it (agents, cli, rag, tests) were never
re-sorted afterward — a stale .ruff_cache masked this locally the whole
time, so it only ever surfaced in CI.
- ci(hooks): add pre-commit quality gate running make lint
- ci(docker): add image-build workflow, extend failure-comment to cover it
- build(docker): add Dockerfile and docker-compose for local dev stack
- ci: add ci-test, ci-quality, and ci-failure-comment workflows
- build: add Commitizen for Conventional Commits, with release-scope guard
- fix: package the project so ============================================================ ChromaDB Quick Start (Docker / HTTP Mode) ============================================================
- ============================================================
Connecting to ChromaDB Docker Server...
============================================================
❌ Cannot connect to ChromaDB at localhost:8000
   ('chromadb-docker.sh' not found in the current directory)
- ❌ ChromaDB is still not reachable at localhost:8000.
   Run manually: /Users/jasmineanderson/Code/pokemon-trainer-platform-ai/chromadb-docker.sh start actually works
- fix: reconstruct the missing src/data package
- fix: stop .gitignore from swallowing the src/data package
- chore: add ruff lint config, make lint targets, and fix resulting findings
- fix: align GOOGLE_API_KEY naming in 1Password refs, clean up GETTING_STARTED prereqs
- - .env.op / docs/1PASSWORD.md: point op:// reference at GOOGLE_API_KEY
  instead of the stale GEMINI_API_KEY item name, matching the env var
  the app actually reads (src/startup.py)
- docs/GETTING_STARTED.md: consolidate duplicate prerequisite verify
  steps into one block, add Colima install command, use pyenv local
  instead of global, number Next Steps 1-4 instead of repeating 1.
- fix: resolve all Pylance/pyright type errors across chromadb_setup and src
- docs: add web API conversion roadmap
- refactor: renamed walkthrough folder to walkthrough_cli
- chore: removed unused import
- chore: fix markdownlint errors
- feat: add optional PostgreSQL integration via PLATFORM_DB_URL
- chore: fix agent table alignment
- refactor(readme): broaden project description beyond financial framing
- fix: fix pyproject.toml description, remove stale observability/ dir from docs
- fix: fix broken LINTING.md link, stale title, missing agent in docs
- fix: rename phoenix container, fix broken link, update testing doc name
- fix: remove remaining stale capstone/ references (second pass)
- fix: remove remaining stale capstone/ references across project
- fix: observability path, generate-data cmd, pytest dep group + docs
- docs: update monorepo refs to standalone project layout
- docs: rename CAPSTONE_GUIDE → WALKTHROUGH
- docs: update all phase guides for test refactor and pyright switch
- refactor: reorganize tests/ to mirror src/ module structure
- docs: add CHANGELOG and .env.example, fix stale eval_results paths
- chore: switch basedpyright to pyright, fix requires_chromadb mark typing, and add requires_chromadb pytest marker
- fix: replace fragile confirmation flags with typed PendingConfirmation dataclass and tighten accept regex
- refactor: split trade_advisor.py into core, tools, and api modules
- test: fix stale is_chromadb_running imports and add query_pokedex user_id schema test
- feat: reformat prefs command to match status table layout
- fix: correct project metadata, dedup chromadb health check, pass user_id through MCP, and harden phoenix/chromadb startup
- fix: correct project name, python version, dedup chromadb health check, and pass user_id through MCP
- docs: fix markdownlint violations and align table columns in ARIZE_PHOENIX_SETUP
- docs: update README with prerequisites, fix install command, and expand make reference
- feat: initialize Pokemon trainer AI platform with source, tests, and tooling
- Initial commit
