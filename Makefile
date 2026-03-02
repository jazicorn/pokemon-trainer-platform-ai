# Pokemon Trainer's Second Brain — common commands
# Run `make help` to see all targets.
#
# Requires:
#   - uv        (https://docs.astral.sh/uv/)
#   - op CLI    (https://developer.1password.com/docs/cli/) for targets that use 1Password
#   - Docker / Colima for ChromaDB targets

.DEFAULT_GOAL := help

# ── App ───────────────────────────────────────────────────────────────────────

run: ## Run app with Anthropic claude-sonnet (default) via 1Password
	op run --env-file .env.op -- uv run python app.py

run-gemini: ## Run app with Gemini Flash via 1Password
	POKEMON_MODEL=gemini-flash op run --env-file .env.op -- uv run python app.py

run-openai: ## Run app with GPT-4o via 1Password
	POKEMON_MODEL=gpt-4o op run --env-file .env.op -- uv run python app.py

run-ollama: ## Run app with local Ollama llama model (no API key needed)
	POKEMON_MODEL=llama USE_OLLAMA_EMBEDDINGS=true uv run python app.py

# ── Tests ─────────────────────────────────────────────────────────────────────

test: ## Run all unit/integration tests with mocked LLM (no live keys needed)
	uv run pytest tests/ -v --tb=short -m "not requires_chromadb"

test-live: ## Run tests against live LLM APIs via 1Password
	op run --env-file .env.op -- uv run pytest tests/ -v --tb=short -m "not requires_chromadb"

test-rag: ## Run ChromaDB integration tests (ChromaDB must be running)
	uv run pytest tests/ -v -m "requires_chromadb" -s

# ── Data ──────────────────────────────────────────────────────────────────────

ingest: ## Index Pokemon into ChromaDB (fetches from PokeAPI — ChromaDB must be running)
	uv run python -m src.rag.ingest

generate-data: ## Generate mock platform trade data and user collection
	uv run python -m src.data.generator

# ── Phoenix ───────────────────────────────────────────────────────────────────

phoenix-start: ## Start Phoenix observability server (Docker)
	docker start phoenix-pokemon-trainer 2>/dev/null || \
	docker run -d --name phoenix-pokemon-trainer -p 6006:6006 arizephoenix/phoenix:latest
	@echo "Phoenix starting at http://127.0.0.1:6006"

phoenix-stop: ## Stop Phoenix Docker container
	docker stop phoenix-pokemon-trainer 2>/dev/null || true
	@echo "Phoenix stopped."

# ── ChromaDB ──────────────────────────────────────────────────────────────────

chromadb-start: ## Start ChromaDB Docker container (interactive — manages Colima if needed)
	./chromadb_setup/chromadb-docker.sh start

chromadb-stop: ## Stop ChromaDB Docker container
	./chromadb_setup/chromadb-docker.sh stop

chromadb-status: ## Show ChromaDB container and server status
	./chromadb_setup/chromadb-docker.sh status

# ── Database ──────────────────────────────────────────────────────────────────

reset-db: ## Delete the local SQLite database (recreated automatically on next run)
	rm -f data/memory.db
	@echo "✓ Database reset. It will be recreated on next 'make run'."

# ── Evals ─────────────────────────────────────────────────────────────────────

eval: ## Run trade advisor evaluation via pydantic-evals (requires API key)
	op run --env-file .env.op -- uv run python -c \
		"import sys; sys.path.insert(0, 'src'); import asyncio; from evals.eval_trade_advisor import main; asyncio.run(main())"

eval-rag: ## Run RAG vs no-RAG comparison eval (requires API key + ChromaDB)
	op run --env-file .env.op -- uv run python -c \
		"import sys; sys.path.insert(0, 'src'); import asyncio; from evals.eval_rag_comparison import main; asyncio.run(main())"

# ── Help ──────────────────────────────────────────────────────────────────────

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*##"}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

.PHONY: run run-gemini run-openai run-ollama \
        test test-live test-rag \
        eval eval-rag \
        reset-db \
        ingest generate-data \
        phoenix-start phoenix-stop \
        chromadb-start chromadb-stop chromadb-status \
        help
