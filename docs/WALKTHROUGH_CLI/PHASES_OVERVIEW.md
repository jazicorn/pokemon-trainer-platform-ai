# Pokemon Trainer Platform - AI: Stages Overview

This guide walks through the Pokemon Trade Advisor codebase **phase by phase** — from infrastructure
to the fully assembled multi-agent system. Each phase focuses on **understanding and testing** the
code that's already been built, rather than building from scratch.

## How to Use These Docs

Each phase doc follows the same structure:

- **Overview** — what the component does and why it exists
- **Where It Fits** — dependency context shown as a simple diagram
- **Key Files** — source files and their purpose
- **Key Concepts** — ideas you must understand to work with this component
- **Exploring the Code** — guided reading hints to orient you in the source
- **Running the Code** — exact commands to invoke the component directly
- **Running the Tests** — scoped pytest commands with notes on what each test class verifies
- **Common Gotchas** — known tricky spots (where applicable)

Work through the phases in order — each phase builds on the understanding from the previous ones.
You can also jump directly to any phase if you need to understand one component in isolation.

---

## Stage Map

| Stage | Title | Layer | Key Test Files |
| --- | --- | --- | --- |
| [01](phase-01-project-setup.md) | Project Setup & Infrastructure | Foundation | `core/test_config.py`, `core/test_startup_validation.py` |
| [02](phase-02-mock-data.md) | Mock Data & Models | Data | `data/test_data.py` |
| [03](phase-03-memory-system.md) | Memory System | Persistence | `memory/test_memory.py`, `memory/test_memory_persistence.py` |
| [04](phase-04-pii-guardrails.md) | PII Guardrails | Safety | `guardrails/test_guardrails.py` |
| [05](phase-05-pokedex-expert.md) | Pokedex Expert | Agent (RAG) | `agents/test_pokedex_agent.py`, `rag/test_rag.py` |
| [06](phase-06-market-analyst.md) | Market Analyst | Agent (Analytics) | `agents/test_trade_analytics.py` |
| [07](phase-07-market-forecasting.md) | Market Forecasting | Agent Enhancement | `agents/test_trade_analytics.py` |
| [08](phase-08-legitimacy-guard.md) | Legitimacy Guard | Agent (Compliance) | `agents/test_legitimacy_guard.py` |
| [09](phase-09-trade-advisor.md) | Trade Advisor | Orchestrator | `agents/test_trade_advisor.py` |
| [10](phase-10-multi-agent-orchestration.md) | Multi-Agent Orchestration | Architecture | `agents/test_multi_agent.py` |
| [11](phase-11-cli-interface.md) | CLI Interface | User Interface | `cli/test_cli.py` |
| [12](phase-12-trade-offers.md) | Trade Offers | Feature Extension | `agents/test_trade_offers.py` |
| [13](phase-13-evaluations.md) | Evaluations | Quality Measurement | `evals/test_evals.py`, `evals/test_evals_execution.py` |
| [14](phase-14-mcp-server.md) | MCP Server *(optional)* | External Integration | `mcp/test_mcp_server.py` |

---

## Dependency Diagram

The diagram below shows which phases depend on which. Read it top-to-bottom: a phase can only be
understood after understanding everything above it on its branch.

```text
                    ┌─────────────────────────────────┐
                    │  Stage 1: Project Setup          │
                    │  config, startup, observability  │
                    └───────────────┬─────────────────┘
                                    │
                    ┌───────────────▼─────────────────┐
                    │  Stage 2: Mock Data & Models     │
                    │  Pydantic models, trade history  │
                    └───────┬───────────────┬──────────┘
                            │               │
           ┌────────────────▼──┐     ┌──────▼──────────────┐
           │ Stage 3: Memory   │     │ Stage 4: PII         │
           │ SQLite, prefs,    │     │ Guardrails           │
           │ conversation      │     │ filter + middleware   │
           └────────┬──────────┘     └──────┬───────────────┘
                    │                        │
     ┌──────────────▼────────────────────────▼────────────────────┐
     │              Specialized Agents                             │
     │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────┐ │
     │  │ Stage 5: Pokedex │  │ Stage 6: Market  │  │Stage 8:  │ │
     │  │ Expert (RAG)     │  │ Analyst          │  │Legitimacy│ │
     │  │                  │  │       +          │  │Guard     │ │
     │  │                  │  │ Stage 7: Market  │  │          │ │
     │  │                  │  │ Forecasting      │  │          │ │
     │  └────────┬─────────┘  └──────┬───────────┘  └────┬─────┘ │
     └───────────┼───────────────────┼──────────────────┼─────────┘
                 │                   │                  │
                 └───────────────────▼──────────────────┘
                         ┌───────────────────────┐
                         │ Stage 9: Trade Advisor │
                         │ Orchestrator           │
                         └───────────┬────────────┘
                                     │
                         ┌───────────▼────────────────┐
                         │ Stage 10: Multi-Agent       │
                         │ Orchestration               │
                         └───────────┬────────────────┘
                                     │
                    ┌────────────────▼──────────────────┐
                    │  Stage 11: CLI Interface           │
                    └────────────┬──────────────────────┘
                                 │
                    ┌────────────▼──────────────────────┐
                    │  Stage 12: Trade Offers            │
                    └────────────┬──────────────────────┘
                                 │
          ┌──────────────────────▼────────────────────────────┐
          │  Stage 13: Evaluations  |  Stage 14: MCP Server   │
          │  quality measurement    |  optional, external      │
          └─────────────────────────────────────────────────── ┘
```

---

## Running All Tests

```bash
# Full test suite — skips ChromaDB-dependent vector store tests
uv run pytest tests/ -v --tb=short -m "not requires_chromadb"

# Full suite including vector store tests (requires ChromaDB running)
uv run pytest tests/ -v --tb=short

# Single phase
uv run pytest tests/memory/test_memory.py tests/memory/test_memory_persistence.py -v

# Eval framework only (no API key needed — uses mocked LLM)
uv run pytest tests/evals/test_evals.py tests/evals/test_evals_execution.py -v

# MCP server only (no API key needed)
uv run pytest tests/mcp/test_mcp_server.py -v
```

See [`docs/REFERENCE/TESTING.md`](../REFERENCE/TESTING.md) for detailed test configuration, async patterns
(`pytest-asyncio`, `anyio_backend` fixture), and troubleshooting tips.

---

## Layer Summary

Understanding where each phase sits in the overall architecture helps with navigation:

**Foundation (Stages 1-2)**: Config, environment validation, startup sequence, SQLite schema init,
observability, and all Pydantic data models. Nothing agent-related — just the infrastructure
everything else builds on.

**Persistence & Safety (Stages 3-4)**: The memory system (conversation history, user preferences,
trade history in SQLite) and the PII guardrail layer (regex filter + middleware that wraps agent
calls). These run as infrastructure, not agents.

**Specialized Agents (Stages 5-8)**: Four focused agents, each with a narrow domain:

- Stage 5: Pokedex Expert — answers Pokemon fact questions via ChromaDB RAG retrieval
- Stage 6: Market Analyst — computes demand ratios and trade success rates from platform data
- Stage 7: Market Forecasting — adds momentum scores and bullish/bearish sentiment on top of the
  market analyst
- Stage 8: Legitimacy Guard — checks for illegal ball/Pokemon combinations and scam indicators

**Orchestration (Stages 9-10)**: The Trade Advisor (Stage 9) wires together the four specialists
into a single agent that handles user queries end-to-end. Stage 10 documents the multi-agent
delegation architecture and usage token propagation.

**User Interface (Stages 11-12)**: The Typer CLI (Stage 11) and the trade offers feature (Stage 12)
that extends the advisor with async offer management and pending offer tracking.

**Quality & Integration (Stages 13-14)**: Evaluations (Stage 13) measure agent accuracy with a
structured scoring framework. The MCP server (Stage 14) exposes all four agent functions as tools
consumable by external AI clients.
