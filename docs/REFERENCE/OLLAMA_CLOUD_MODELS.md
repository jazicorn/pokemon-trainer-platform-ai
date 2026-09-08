# Ollama Cloud Models

**Last updated:** 2026-09-08, via:

```bash
curl https://ollama.com/api/tags
```

This list changes as Ollama adds/retires cloud models — re-run the command above and
update this table when it does. There's no automation for this; it's a manual snapshot.

This project currently uses **`gpt-oss:120b`** (direct API) / **`gpt-oss:120b-cloud`**
(local-proxy) — see `MODELS["llama-cloud"]` in [`src/config.py`](../../src/config.py) and
[GETTING_STARTED.md](../GETTING_STARTED.md) for the two ways to reach it.

## Known Limitation: Structured Output

Per [pydantic-ai's own Ollama docs](https://pydantic.dev/docs/ai/models/ollama/), Ollama
Cloud doesn't enforce `json_schema` yet — it accepts `response_format` with a schema
without error, but doesn't apply grammar-constrained decoding, so the schema is silently
not enforced. pydantic-ai auto-detects a Cloud path (an `ollama.com` base URL, or a model
name ending in `-cloud`) and disables `supports_json_schema_output` accordingly; using
`NativeOutput` with a Cloud model raises a clear `UserError` instead of silently
misbehaving.

**Not currently a live issue for this project** — none of the agents in `src/agents/` use
`output_type=`/`NativeOutput`/`result_type=`; every agent returns plain string output. This
would only start mattering if a future phase (e.g. `ROADMAP.md`'s FastAPI server, which
introduces typed Pydantic response models) adds structured output to an agent that might
run on `llama-cloud`.

## Available Models

| Model | Size | Last Modified |
| --- | --- | --- |
| `deepseek-v4-flash:0731` | 155.4 GB | 2026-07-31 |
| `deepseek-v4-pro:0813` | 831.4 GB | 2026-08-13 |
| `gemma4:31b` | 58.3 GB | 2026-04-02 |
| `glm-5.1` | 1404.2 GB | 2026-04-07 |
| `glm-5.2` | — | 2026-06-16 |
| `glm-5.3` | 703.6 GB | 2026-08-28 |
| `glm-5.3-flash` | 305.7 GB | 2026-08-26 |
| `gpt-oss:120b` ⭐ | 60.8 GB | 2025-08-05 |
| `gpt-oss:20b` | 12.8 GB | 2025-08-05 |
| `kimi-k2.6` | 554.3 GB | 2026-04-20 |
| `kimi-k2.7-code` | 554.3 GB | 2026-06-12 |
| `kimi-k3` | 1453.7 GB | 2026-07-27 |
| `minimax-m2.7` | 447.8 GB | 2026-03-18 |
| `minimax-m3` | — | 2026-06-01 |
| `mistral-large-3:675b` | 635.2 GB | 2025-12-02 |
| `nemotron-3-nano:30b` | 30.4 GB | 2025-12-15 |
| `nemotron-3-super` | 214.7 GB | 2026-03-11 |
| `nemotron-3-ultra` | — | 2026-06-04 |
| `qwen3.5:397b` | 369.7 GB | 2026-02-16 |

⭐ = model this project's `llama-cloud` config key uses.

A `—` size means Ollama's API returned `0` for that model (seen for `glm-5.2`,
`minimax-m3`, `nemotron-3-ultra` in this snapshot) — not necessarily a tiny model, likely
just unreported by the API for these entries.

## Switching to a Different Cloud Model

Ollama's own docs confirm `gpt-oss:120b` (direct API) vs `gpt-oss:120b-cloud`
(local-proxy) as one pair — that a `-cloud` suffix is the *general* local-proxy naming
convention for every model in this list is inferred from that single example, not
independently confirmed per-model. Verify with `ollama pull <model>-cloud` before
relying on it for a different model. Update `MODELS["llama-cloud"]` in `src/config.py`:

```python
"llama-cloud": ModelConfig(
    ModelProvider.OLLAMA,
    "qwen3.5:397b-cloud",       # local-proxy name — verify this actually resolves
    direct_api_model_name="qwen3.5:397b",  # direct API name (matches the table above)
),
```
