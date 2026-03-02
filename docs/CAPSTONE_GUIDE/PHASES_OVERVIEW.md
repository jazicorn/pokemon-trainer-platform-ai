# Capstone Phases Overview

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

## Phase Map

| Phase | Title | Layer | Key Test Files |
| --- | --- | --- | --- |
| [01](phase-01-project-setup.md) | Project Setup & Infrastructure | Foundation | `test_config.py`, `test_startup_validation.py` |
| [02](phase-02-mock-data.md) | Mock Data & Models | Data | `test_data.py` |
| [03](phase-03-memory-system.md) | Memory System | Persistence | `test_memory.py`, `test_memory_persistence.py` |
| [04](phase-04-pii-guardrails.md) | PII Guardrails | Safety | `test_guardrails.py` |
| [05](phase-05-pokedex-expert.md) | Pokedex Expert | Agent (RAG) | `test_pokedex_agent.py`, `test_rag.py` |
| [06](phase-06-market-analyst.md) | Market Analyst | Agent (Analytics) | `test_trade_analytics.py` |
| [07](phase-07-market-forecasting.md) | Market Forecasting | Agent Enhancement | `test_trade_analytics.py` |
| [08](phase-08-legitimacy-guard.md) | Legitimacy Guard | Agent (Compliance) | `test_legitimacy_guard.py` |
| [09](phase-09-trade-advisor.md) | Trade Advisor | Orchestrator | `test_trade_advisor.py` |
| [10](phase-10-multi-agent-orchestration.md) | Multi-Agent Orchestration | Architecture | `test_multi_agent.py` |
| [11](phase-11-cli-interface.md) | CLI Interface | User Interface | `test_cli.py` |
| [12](phase-12-trade-offers.md) | Trade Offers | Feature Extension | `test_trade_offers.py` |
| [13](phase-13-evaluations.md) | Evaluations | Quality Measurement | `test_evals.py`, `test_evals_execution.py` |
| [14](phase-14-mcp-server.md) | MCP Server *(optional)* | External Integration | `test_mcp_server.py` |

---

## Dependency Diagram

The diagram below shows which phases depend on which. Read it top-to-bottom: a phase can only be
understood after understanding everything above it on its branch.

```text
                    ┌─────────────────────────────────┐
                    │  Phase 1: Project Setup          │
                    │  config, startup, observability  │
                    └───────────────┬─────────────────┘
                                    │
                    ┌───────────────▼─────────────────┐
                    │  Phase 2: Mock Data & Models     │
                    │  Pydantic models, trade history  │
                    └───────┬───────────────┬──────────┘
                            │               │
           ┌────────────────▼──┐     ┌──────▼──────────────┐
           │ Phase 3: Memory   │     │ Phase 4: PII         │
           │ SQLite, prefs,    │     │ Guardrails           │
           │ conversation      │     │ filter + middleware   │
           └────────┬──────────┘     └──────┬───────────────┘
                    │                        │
     ┌──────────────▼────────────────────────▼────────────────────┐
     │              Specialized Agents                             │
     │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────┐ │
     │  │ Phase 5: Pokedex │  │ Phase 6: Market  │  │Phase 8:  │ │
     │  │ Expert (RAG)     │  │ Analyst          │  │Legitimacy│ │
     │  │                  │  │       +          │  │Guard     │ │
     │  │                  │  │ Phase 7: Market  │  │          │ │
     │  │                  │  │ Forecasting      │  │          │ │
     │  └────────┬─────────┘  └──────┬───────────┘  └────┬─────┘ │
     └───────────┼───────────────────┼──────────────────┼─────────┘
                 │                   │                  │
                 └───────────────────▼──────────────────┘
                         ┌───────────────────────┐
                         │ Phase 9: Trade Advisor │
                         │ Orchestrator           │
                         └───────────┬────────────┘
                                     │
                         ┌───────────▼────────────────┐
                         │ Phase 10: Multi-Agent       │
                         │ Orchestration               │
                         └───────────┬────────────────┘
                                     │
                    ┌────────────────▼──────────────────┐
                    │  Phase 11: CLI Interface           │
                    └────────────┬──────────────────────┘
                                 │
                    ┌────────────▼──────────────────────┐
                    │  Phase 12: Trade Offers            │
                    └────────────┬──────────────────────┘
                                 │
          ┌──────────────────────▼────────────────────────────┐
          │  Phase 13: Evaluations  |  Phase 14: MCP Server   │
          │  quality measurement    |  optional, external      │
          └─────────────────────────────────────────────────── ┘
```

---

## Running All Tests

```bash
# Full test suite — skips ChromaDB-dependent vector store tests
uv run pytest tests/ -v --tb=short --ignore=tests/test_rag.py

# Full suite including vector store tests (requires ChromaDB running)
uv run pytest tests/ -v --tb=short

# Single phase
uv run pytest tests/test_memory.py tests/test_memory_persistence.py -v

# Eval framework only (no API key needed — uses mocked LLM)
uv run pytest tests/test_evals.py tests/test_evals_execution.py -v

# MCP server only (no API key needed)
uv run pytest tests/test_mcp_server.py -v
```

See [`docs/REFERENCE/TESTING.md`](../REFERENCE/TESTING.md) for detailed test configuration, async patterns
(`pytest-asyncio`, `anyio_backend` fixture), and troubleshooting tips.

---

## Layer Summary

Understanding where each phase sits in the overall architecture helps with navigation:

**Foundation (Phases 1-2)**: Config, environment validation, startup sequence, SQLite schema init,
observability, and all Pydantic data models. Nothing agent-related — just the infrastructure
everything else builds on.

**Persistence & Safety (Phases 3-4)**: The memory system (conversation history, user preferences,
trade history in SQLite) and the PII guardrail layer (regex filter + middleware that wraps agent
calls). These run as infrastructure, not agents.

**Specialized Agents (Phases 5-8)**: Four focused agents, each with a narrow domain:

- Phase 5: Pokedex Expert — answers Pokemon fact questions via ChromaDB RAG retrieval
- Phase 6: Market Analyst — computes demand ratios and trade success rates from platform data
- Phase 7: Market Forecasting — adds momentum scores and bullish/bearish sentiment on top of the
  market analyst
- Phase 8: Legitimacy Guard — checks for illegal ball/Pokemon combinations and scam indicators

**Orchestration (Phases 9-10)**: The Trade Advisor (Phase 9) wires together the four specialists
into a single agent that handles user queries end-to-end. Phase 10 documents the multi-agent
delegation architecture and usage token propagation.

**User Interface (Phases 11-12)**: The Typer CLI (Phase 11) and the trade offers feature (Phase 12)
that extends the advisor with async offer management and pending offer tracking.

**Quality & Integration (Phases 13-14)**: Evaluations (Phase 13) measure agent accuracy with a
structured scoring framework. The MCP server (Phase 14) exposes all four agent functions as tools
consumable by external AI clients.
