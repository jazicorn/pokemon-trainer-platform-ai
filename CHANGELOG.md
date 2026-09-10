## v0.8.0 (2026-09-10)

### ✨ Features

- **api**: add observability - tracing, logging, error tracking (Roadmap Phase 6)

## v0.7.1 (2026-09-10)

### 🐛 Fixes

- **docker**: run container as non-root

### 👷 CI

- make cancel-in-progress opt-in via a repo variable, off by default

### 📝 Documentation

- **roadmap**: split ROADMAP.md, move security items to their natural phases

## v0.7.0 (2026-09-09)

### ✨ Features

- **api**: add offers and query endpoints (Roadmap Phase 5)

## v0.6.0 (2026-09-09)

### ✨ Features

- **api**: add core trade endpoints (Roadmap Phase 4)

### 📝 Documentation

- **roadmap**: fix Phase 3's misleading verification, add real auth checks to Phase 4

## v0.5.0 (2026-09-09)

### ✨ Features

- **api**: add tenant accounts and API key auth (Roadmap Phase 3)

## v0.4.0 (2026-09-09)

### ✨ Features

- **api**: add Pydantic request/response models (Roadmap Phase 2)

## v0.3.3 (2026-09-09)

### 🐛 Fixes

- unblock make run-api (1Password key, non-interactive telemetry)

### 📝 Documentation

- **roadmap**: add phases 13-27, decouple hosting from analytics consent

## v0.3.2 (2026-09-09)

### 🐛 Fixes

- **ci**: wait for CI before releasing, ship real release notes

## v0.3.1 (2026-09-09)

### 🐛 Fixes

- **ci**: create GitHub Releases on tag push, fix mangled CHANGELOG.md

## v0.3.0 (2026-09-09)

### ✨ Features

- **api**: add FastAPI dependencies and entry point (Roadmap Phase 1)

### 📝 Documentation

- **roadmap**: redesign for multi-tenant public API, add phases 9-12

### 🔧 Chores

- **release**: bump version 0.2.2 → 0.3.0

## v0.2.2 (2026-09-09)

### 🐛 Fixes

- **ci**: stop release.yml self-retrigger, fix tag orphaned by amend

### 🔧 Chores

- **release**: bump version 0.2.1 → 0.2.2
- **release**: bump version 0.2.0 → 0.2.1

## v0.2.1 (2026-09-08)

### 🐛 Fixes

- **ci**: push the release tag explicitly instead of --follow-tags

## v0.2.0 (2026-09-08)

### ✅ Tests

- extend make lint to check tests/, fix all 353 pyright errors

### ✨ Features

- add Ollama Cloud support and .env/.env.local auto-loading

### 🐛 Fixes

- **ci**: sync uv.lock with pyproject.toml version, fix release drift
- **startup**: capture chromadb-docker.sh stderr, add __main__ entrypoint
- **rag**: correct Smogon tier data endpoint path
- make src/ importable for python -m src.* invocations

### 📝 Documentation

- **getting-started**: document MacPorts as a Docker/Colima install
path alongside Homebrew, for machines where Homebrew doesn't work well
(e.g. older macOS).

### 🔧 Chores

- **release**: bump version 0.1.0 → 0.2.0

## v0.1.0 (2026-09-08)

### ♻️ Refactoring

- renamed walkthrough folder to walkthrough_cli
- **readme**: broaden project description beyond financial framing
- reorganize tests/ to mirror src/ module structure
- split trade_advisor.py into core, tools, and api modules

### ✅ Tests

- fix stale is_chromadb_running imports and add query_pokedex user_id schema test

### ✨ Features

- add optional PostgreSQL integration via PLATFORM_DB_URL
- reformat prefs command to match status table layout
- initialize Pokemon trainer AI platform with source, tests, and tooling

### 🐛 Fixes

- remove basedpyright-only settings from pyright config
- sort imports now that data.* resolves as first-party
- package the project so ============================================================ ChromaDB Quick Start (Docker / HTTP Mode) ============================================================
- reconstruct the missing src/data package
- stop .gitignore from swallowing the src/data package
- align GOOGLE_API_KEY naming in 1Password refs, clean up GETTING_STARTED prereqs
- resolve all Pylance/pyright type errors across chromadb_setup and src
- fix pyproject.toml description, remove stale observability/ dir from docs
- fix broken LINTING.md link, stale title, missing agent in docs
- rename phoenix container, fix broken link, update testing doc name
- remove remaining stale capstone/ references (second pass)
- remove remaining stale capstone/ references across project
- observability path, generate-data cmd, pytest dep group + docs
- replace fragile confirmation flags with typed PendingConfirmation dataclass and tighten accept regex
- correct project metadata, dedup chromadb health check, pass user_id through MCP, and harden phoenix/chromadb startup
- correct project name, python version, dedup chromadb health check, and pass user_id through MCP

### 👷 CI

- add release.yml and image-publish.yml, split CHANGELOG into HISTORY.md
- **hooks**: add pre-commit quality gate running make lint
- **docker**: add image-build workflow, extend failure-comment to cover it
- add ci-test, ci-quality, and ci-failure-comment workflows

### 📝 Documentation

- add web API conversion roadmap
- update monorepo refs to standalone project layout
- rename CAPSTONE_GUIDE → WALKTHROUGH
- update all phase guides for test refactor and pyright switch
- add CHANGELOG and .env.example, fix stale eval_results paths
- fix markdownlint violations and align table columns in ARIZE_PHOENIX_SETUP
- update README with prerequisites, fix install command, and expand make reference

### 📦 Build

- **docker**: add Dockerfile and docker-compose for local dev stack
- add Commitizen for Conventional Commits, with release-scope guard

### 🔧 Chores

- ignore .claude/ directories
- add ruff lint config, make lint targets, and fix resulting findings
- removed unused import
- fix markdownlint errors
- fix agent table alignment
- switch basedpyright to pyright, fix requires_chromadb mark typing, and add requires_chromadb pytest marker
