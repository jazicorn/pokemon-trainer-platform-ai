## v0.3.0 (2026-09-09)


- docs(roadmap): redesign for multi-tenant public API, add phases 9-12
- The API was originally scoped as a private, single-tenant backend
(one static API_KEY, one global PLATFORM_DB_URL) for a single sister
platform. It's now meant to be a genuinely public API where different
callers each bring their own database, which changes the auth design
itself, not just the deployment story.
- - Phase 3 (was "API Key Authentication"): rewritten from a single
  shared API_KEY to per-tenant accounts — a new data/tenants.db,
  admin-provisioned for now (scripts/provision_tenant.py) with
  self-serve deferred to Phase 10, Fernet-encrypted per-tenant
  platform_db_url, and require_api_key resolving a per-request
  TenantContext instead of reading one global env var. The CLI's own
  PLATFORM_DB_URL/config.platform_db_url is untouched.
- Phase 9 (Deployment): reframed from a private/network-isolated
  backend-to-backend link to a genuinely public service — real
  TLS/reverse-proxy now required, plus a callout that data/tenants.db
  needs a persistent volume across redeploys.
- Phase 10 (new): self-serve POST /accounts/register, validating a
  submitted platform_db_url against the schema contract before
  storing it, plus key rotation/revocation.
- Phase 11 (new): a local admin web UI (not a CLI) for managing
  tenants — list/create/deactivate/rotate keys — bound to 127.0.0.1
  and deliberately kept off the public reverse proxy, gated by its
  own ADMIN_TOKEN separate from tenant keys and
  TENANT_DB_ENCRYPTION_KEY.
- Phase 12 (new): a GitHub Pages docs/landing site via MkDocs +
  Material, rendering the existing README/docs/ROADMAP/HISTORY
  markdown as-is. Independent of the API phases — can be done any
  time.
- feat(api): add FastAPI dependencies and entry point (Roadmap Phase 1)
- Ships a runnable FastAPI server with a health check, per ROADMAP.md
Phase 1 — the foundation the later phases (auth, trade endpoints,
observability, tests) build on.
- - pyproject.toml: add fastapi>=0.115.0, uvicorn[standard]>=0.34.0
- src/api/__init__.py, src/api/app.py: FastAPI `app` with a `lifespan`
  that runs the same startup() sequence the CLI uses (phoenix=False —
  the API runs unattended, no interactive telemetry prompt needed
  until Phase 6 wires real request tracing through). GET /health is
  unauthenticated, per Phase 3's plan to exempt it from API-key auth.
- api_server.py: root entry point mirroring app.py's own sys.path
  setup, launches uvicorn against api.app:app.
- Makefile: add run-api target.
- Verified: pyright/ruff clean, full `make test` suite (271 tests)
unaffected. The /health handler was exercised directly (bypassing
startup()'s live Docker/telemetry side effects, consistent with how
startup() itself hasn't been run directly in this session) and
returned a real {"status": "ok", "chromadb": true}.

## v0.2.2 (2026-09-09)


- fix(ci): stop release.yml self-retrigger, fix tag orphaned by amend
- Two compounding bugs, both surfaced by trying to release 0.2.1:
- 1. release.yml triggers on every push to main, including its own bump
   commit (deliberately, via the App token, so the tag push can trigger
   image-publish.yml downstream). Pushing "chore(release): bump ...
   0.2.0 → 0.2.1" immediately kicked off a second run that tried to
   bump again on top of it (0.2.1 → 0.3.0), which then failed outright.
   Guard the job to skip runs whose own head commit is a release bump.
- 2. The "Sync uv.lock" step recomputed the tag name via
   `git describe --tags --abbrev=0` *after* amending the bump commit.
   Amending creates a new commit SHA, orphaning the tag `cz bump` had
   just created (it still points at the pre-amend commit, no longer an
   ancestor of HEAD) — so `git describe` silently fell back to the
   *previous* release's tag instead. That force-moved the already-
   pushed v0.2.0 tag onto the new 0.2.1 commit locally, and the
   subsequent (correctly non-force) push was rejected because remote
   v0.2.0 already pointed elsewhere. The real v0.2.1 tag was created
   but never pushed.
-    Fix: capture the tag name once, in the same step that creates it,
   before any amend can orphan it, and reuse that fixed string in every
   later step instead of ever recomputing it.
- chore(release): bump version 0.2.0 → 0.2.1

## v0.2.1 (2026-09-08)


- fix(ci): push the release tag explicitly instead of --follow-tags
- `git push --follow-tags` only pushes *annotated* tags — cz.toml doesn't
set `annotated_tag`, so `cz bump` creates lightweight ones. The push
step exited 0 and looked successful, but silently never pushed the
tag. This is exactly what happened with v0.2.0: the bump commit landed
on main, but no v0.2.0 tag ever reached the remote, so image-publish.yml
(which only triggers on a pushed `v*` tag) never ran and no Docker
image was built.
- Push the branch and tag explicitly by name instead of relying on
--follow-tags' annotated-tags-only behavior.
- Also add scripts/release.sh: a manual release script (bump, sync
uv.lock, push) for running a release from the console when the
automated pipeline can't be used, mirroring release.yml's own steps.

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
