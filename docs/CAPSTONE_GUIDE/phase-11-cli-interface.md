# Phase 11: CLI Interface

## Overview

Phase 11 is the user-facing application layer. It provides an interactive terminal experience built
with **Rich** where users type commands and receive AI-powered trade advice. The CLI handles command
parsing, routes each command to the appropriate agent function, maintains conversation context, and
renders results as formatted markdown inside Rich panels.

The CLI is the primary way to experience the full system end-to-end.

## Where It Fits

```text
All agent phases (Pokedex, Market Analyst, Legitimacy Guard, Trade Advisor)
Phase 3: Memory System (conversation history, preferences)
Phase 4: PII Guardrails (create_safe_input wraps every input)
        ↓
Phase 11: CLI Interface
        ↓
Phase 12: Trade Offers (adds new CLI commands to the existing parser)
```

## Key Files

- `src/cli/commands.py` — `CommandType` enum, `TradeParams` and `OfferParams` named tuples,
  `ParsedCommand` dataclass, `parse_command()` public function, and the private helpers
  `_parse_trade()` and `_parse_offer()`. Pure parsing logic with no I/O side effects.
- `src/cli/app.py` — `TradeCLI` class with one `handle_*` async method per command type. Also
  defines the `HEADER` string (shown on launch and on `help`), `ABOUT_TEXT`, and `main()` (the REPL
  entry point).
- `capstone/app.py` — The root entry point. Adds `src/` to `sys.path`, calls `startup()`, then calls
  `cli.app.main()`.

## Key Concepts

**Separation of parsing and handling**: `parse_command()` in `commands.py` is a pure function — it
takes a string, returns a `ParsedCommand`, and has no side effects. The `TradeCLI` class in `app.py`
does all the I/O. This separation makes parsing trivially unit-testable (no mocking of console or
agents).

**CommandType dispatch**: The main loop calls `parse_command()` then `match cmd.command_type:`
against every `CommandType` variant in `_dispatch_command()`. The full set of variants:

```text
TRADE, SUGGEST, POKEDEX, MARKET, PREFS, HISTORY, INDEX,
ABOUT, CLEAR, HELP, QUIT,
OFFERS, OFFER_SEND, OFFER_ACCEPT, OFFER_DECLINE,
UNKNOWN
```

`UNKNOWN` with non-empty `args` is the AI fallback — the raw input is passed to
`evaluate_trade(raw_query=...)` so natural language questions work without an exact command keyword.

**Three-layer command lookup in `parse_command()`**: The function uses a fast-path cascade before
falling through to regex:

1. `_QUIT_COMMANDS` / `_HELP_COMMANDS` — `frozenset` membership, O(1)
2. `_SIMPLE_COMMANDS` — `dict` lookup, O(1)
3. `_PREFIX_COMMANDS` — `tuple` of `(prefix, CommandType, prefix_len)`, scanned in order
4. `offer ... to ... for ...` — substring checks then `_parse_offer()`
5. `trade ...` / `... for ...` — `_parse_trade()`
6. Natural language offers intent — `_OFFERS_NL_PATTERN` regex + word set intersection
7. Fall through to `UNKNOWN`

**Natural language offers detection**: Unrecognized input that contains a word matching
`r"\boffers?\b"` and at least one word from `{"what", "show", "my", "have", "pending", ...}` is
routed to `CommandType.OFFERS`. This means "what offers do I have?" triggers the inbox without the
user knowing the exact command.

**Rich console**: All output goes through `console.print()`. `_print_result()` wraps agent text in a
`Panel` with a `Markdown` renderer, so agent responses with headers, bold, and bullet points display
correctly. The `HEADER` string contains Rich markup (`[bold cyan]`, `[dim]`, `[italic]`) and is
printed directly with `console.print(HEADER)`.

**PII guardrail on every input**: Before `parse_command()` is called,
`create_safe_input(user_input)` scans the input for PII patterns. If it finds any, it strips them
and sets `had_pii=True` — the CLI prints a warning and continues with the sanitized text. This is
transparent to the agent layer.

**Conversation memory**: After every AI interaction (`handle_trade`, `handle_suggest`,
`handle_pokedex`, `handle_market`, `handle_offers`), the CLI appends both the user message and
assistant response to `self.conversation` (a `ConversationMemory` instance). The `history` command
retrieves the last 5 exchanges.

**Multi-user support via `--user` flag**: `main()` uses `argparse` to accept `--user user_002`. The
`TradeCLI` is constructed with that user ID, which flows into `load_user_collection()` and
`evaluate_trade()` calls.

## Exploring the Code

Start with `commands.py`. Read `CommandType` enum entries, then the lookup structures
(`_QUIT_COMMANDS`, `_SIMPLE_COMMANDS`, `_PREFIX_COMMANDS`), then trace through `parse_command()` for
a few example inputs mentally. Finally read `_parse_trade()` and `_parse_offer()` to see the
split-based grammar for the two structured commands.

In `app.py`, compare `handle_trade()` and `handle_pokedex()` side by side — both use a
`console.status(...)` spinner, call an async agent function, call `_print_result()`, and update
conversation memory. The pattern is consistent across all AI handlers.

Then read `handle_offers()` to see how the same handler method dispatches on `args.strip().lower()
== "sent"` to produce two different views (inbox vs. sent) without needing two separate
`CommandType` variants.

Read `_dispatch_command()` to see the full `match` statement — this is the single place where every
command routes to its handler.

## Running the Code

```bash
# Launch the full CLI (1Password-managed secrets)
op run --env-file .env.op -- uv run python app.py

# Launch as a different user
op run --env-file .env.op -- uv run python app.py --user user_002

# Commands to try inside the CLI:
# > help                               — show all commands
# > trade pikachu for charizard        — evaluate a specific trade
# > trade my gengar for their alakazam — evaluate with natural phrasing
# > suggest                            — get proactive trade recommendations
# > pokedex What type is Gengar?       — Pokedex lookup
# > pokedex                            — prompts for query interactively
# > market                             — trending Pokemon report
# > market Eevee demand                — targeted market query
# > What is the current market sentiment? — natural language (AI fallback)
# > prefs                              — view/update trading preferences
# > history                            — last 5 conversation exchanges
# > about                              — project overview panel
# > clear                              — clear screen and reprint header
# > quit / exit / q                    — exit the application
```

## Running the Tests

```bash
# All CLI tests
uv run pytest tests/test_cli.py -v

# Run a specific test class
uv run pytest tests/test_cli.py::TestParseCommand -v
uv run pytest tests/test_cli.py::TestParseTrade -v
uv run pytest tests/test_cli.py::TestParseOffers -v
```

Test groups in `test_cli.py`:

| Class | What it covers |
| --- | --- |
| `TestParseCommand` | Every command keyword routes to correct `CommandType`; `trade` parses params; `pokedex`/`market` capture args; empty input and unknown text return `UNKNOWN` |
| `TestParseTrade` | `_parse_trade()` with valid input, missing `for`, missing Pokemon, `my`/`their` keywords |
| `TestParseCommandPerformance` | 50k parses (10k iterations x 5 commands) complete under 100ms; `frozenset` lookup structures exist |
| `TestTradeParams` | `TradeParams` NamedTuple field and positional access |
| `TestParseOffers` | `offers`, `offers sent`, `offer X to user for Y`, multi-word Pokemon, `accept N`, `decline N`, missing `to`/`for` edge cases |
| `TestParseOffer` | `_parse_offer()` helper directly — valid, missing `to`, missing `for`, empty parts |
| `TestOfferParams` | `OfferParams` NamedTuple field and positional access |
| `TestParsedCommand` | Dataclass default values (`args=""`, `trade_params=None`, `offer_params=None`) |

All tests are synchronous — `parse_command()` is pure and needs no async infrastructure.

## Common Gotchas

**`_PREFIX_COMMANDS` order matters**: The prefix scan is a linear search through a tuple. `"offers"`
appears in `_PREFIX_COMMANDS` (handling `"offers sent"` → args `"sent"`), but `"offers"` alone also
appears in `_SIMPLE_COMMANDS`. The simple command lookup runs first, so bare `"offers"` hits the
dict path before the prefix scan ever runs. If you reorder these lookups, the behavior changes.

**NL intent detection runs after all structured parsing**: The `_OFFERS_NL_PATTERN` check is the
last branch before the final `UNKNOWN` return. Any input that already matched an earlier path
(prefix, trade, offer-send) will never reach it. This is intentional — exact matches always win over
intent detection.

**Rich markup in `HEADER` is not validated at load time**: The `HEADER` string is a plain Python
string constant. Unclosed or malformed Rich markup tags (e.g., `[bold` without `]`) cause the entire
string to render as plain text or raise at `console.print()` time. There is no lint-time check;
verify changes by running the app.

**`UNKNOWN` with empty args is silently ignored**: In `_dispatch_command()`, the `UNKNOWN` case
checks `if not cmd.args.strip(): return`. Pressing Enter on a blank line does nothing — no error, no
response. This is intentional UX.

**`handle_offer_accept("all")` uses a different code path**: When `offer_id_str` starts with
`"all"`, the method fetches the full inbox and calls `update_status()` on each offer. When it's a
number, it calls `update_status()` on a single ID. An invalid non-numeric, non-"all" string prints a
usage hint and returns without touching the database.
