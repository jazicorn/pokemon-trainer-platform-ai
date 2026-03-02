# Phase 4: PII Guardrails

## Overview

Phase 4 is the privacy and safety layer. Before any user message is stored to conversation history
or passed to an agent, it passes through a PII filter that detects and redacts personally
identifiable information — email addresses, phone numbers, SSNs, credit card numbers, IP addresses,
usernames, and names following known prefixes.

The guardrail is implemented as a **middleware** that wraps message processing. It is transparent to
agents: they receive already-filtered input and their outputs are also optionally filtered before
storage.

## Where It Fits

```text
Phase 3: Memory System (messages stored after filtering)
        ↓
Phase 4: PII Guardrails
        ↓
CLI and agents that receive user input before it is stored or forwarded
```

## Key Files

- `src/guardrails/pii_filter.py` — Core detection and filtering. Defines `PIIPatterns` (pattern
  constants and placeholders), `POKEMON_NAMES` (frozenset exclusion list), and the `PIIFilter` class
  with `detect_pii()`, `filter_pii()`, `has_pii()`, and `get_pii_report()`. Module-level convenience
  functions delegate to a shared `_filter` instance.
- `src/guardrails/middleware.py` — `GuardrailMiddleware` class and `create_safe_input()`. The
  middleware wraps input/output processing with enable/disable flags. `create_safe_input()` is the
  public entry point used by the CLI.
- `src/guardrails/__init__.py` — Re-exports all public symbols: `PIIFilter`, `PIIMatch`,
  `PIIPatterns`, `POKEMON_NAMES`, `filter_pii`, `has_pii`, `detect_pii`, `get_pii_report`,
  `GuardrailMiddleware`, `ProcessedInput`, `create_safe_input`.

## Key Concepts

**Combined regex pattern**: `PIIFilter` uses `@cached_property` to compile a single named-group
regex for all pattern types at first use. The pattern uses named groups (`(?P<email>...)`,
`(?P<phone>...)`, etc.) so `match.lastgroup` identifies which type matched. This avoids running six
separate `.finditer()` calls per message.

**Separate name pattern**: Name detection uses a different regex (also `@cached_property`) that
requires a prefix like `my friend`, `my buddy`, `trader`, or `person named` before the capitalized
word. This conservative approach minimizes false positives. Names are detected separately from the
combined pattern and yielded by `_find_name_matches()`.

**Pokemon name exclusion list**: `POKEMON_NAMES` is a `frozenset` of common Pokemon names. When
`_find_name_matches()` finds a capitalized word that matches the name pattern, it checks
`first_name.lower() in POKEMON_NAMES` before yielding — so "my friend Pikachu" does not trigger name
redaction.

**Descending replacement**: `filter_pii()` sorts all `PIIMatch` objects by `start` position in
descending order before applying replacements. This ensures that replacing a match at position 30
does not shift the indices of matches at earlier positions (10, 20, etc.).

**`ProcessedInput` return type**: `create_safe_input()` returns a `ProcessedInput` dataclass with
three fields: `text` (filtered string), `had_pii` (bool), and `warning` (human-readable string). The
CLI displays `warning` to the user when PII is detected, so they know something was redacted.

**All input paths are filtered**: The CLI's main `process_input()` method filters `user_input`
before passing it to `parse_command()`, so all command paths receive pre-filtered text. The
interactive Pokedex prompt (`Prompt.ask` in `handle_pokedex`) also passes its input through
`create_safe_input()` before saving to conversation memory, since that path collects new user input
outside the main loop.

**Input vs. output filtering**: `GuardrailMiddleware` has separate `filter_input` (default: `True`)
and `filter_output` (default: `False`) flags. Output filtering is off by default — agent responses
rarely contain PII, and filtering them can corrupt structured recommendations containing Pokemon
names that coincidentally match patterns.

## Exploring the Code

Read `pii_filter.py` from top to bottom. Note that `PIIPatterns` is a class holding only `ClassVar`
constants — it is never instantiated. `PIIFilter` is the actual worker class; the module-level
functions (`filter_pii`, `has_pii`, etc.) simply delegate to a shared `_filter = PIIFilter()`
instance.

Pay attention to how `_combined_pattern` is built: it joins the `PATTERNS` dict values into named
groups using `"|".join(...)`. The `re.IGNORECASE` flag means email patterns match `User@EXAMPLE.COM`
and phone patterns match mixed-case formatted numbers.

In `middleware.py`, read `process_input()` — it returns `(filtered_text, pii_report_dict)`. The
`pii_report_dict` is the output of `get_pii_report()`, which includes `has_pii`, `pii_count`,
`pii_types`, and a list of `{type, position}` entries. Then read `create_safe_input()` to see how
the same detection is used with a friendlier return type.

The `POKEMON_NAMES` frozenset is defined in `pii_filter.py` and also exported from
`guardrails/__init__.py` — downstream code that needs to check if a word is a Pokemon name can
import it directly.

## Running the Code

```bash
# Basic filtering
uv run python -c "
import sys; sys.path.insert(0, 'src')
from guardrails import create_safe_input

result = create_safe_input('My name is John and my email is john@example.com')
print('Filtered:', result.text)
print('Had PII:', result.had_pii)
print('Warning:', result.warning)
"

# Pokemon names should not be filtered
uv run python -c "
import sys; sys.path.insert(0, 'src')
from guardrails import create_safe_input

result = create_safe_input('I want to trade my Charizard for Dragonite')
print('Kept:', result.text)
print('Had PII:', result.had_pii)
"

# Get a detailed PII report
uv run python -c "
import sys; sys.path.insert(0, 'src')
from guardrails import get_pii_report

report = get_pii_report('Email john@example.com or call 555-123-4567')
print(report)
"

# Use the middleware directly
uv run python -c "
import sys; sys.path.insert(0, 'src')
from guardrails import GuardrailMiddleware

mw = GuardrailMiddleware(filter_input=True, filter_output=False)
filtered, report = mw.process_input('My SSN is 123-45-6789')
print('Filtered:', filtered)
print('Report:', report)
"
```

Expected output for the first example:

```text
Filtered: My name is [NAME] and my email is [EMAIL]
Had PII: True
Warning: Note: Some personal information was detected and filtered for your privacy.
```

## Running the Tests

```bash
uv run pytest tests/guardrails/test_guardrails.py -v
```

Test groups:

- `TestPIIPatterns` — verifies `PIIPatterns.PATTERNS` is non-empty, that every pattern type has a
  corresponding placeholder in `PIIPatterns.PLACEHOLDERS`, that `POKEMON_NAMES` is a `frozenset`,
  and that common Pokemon names are present in it.
- `TestPIIDetection` — uses a `PIIFilter()` fixture to check detection of email, phone, SSN,
  username, and name (with prefix). Also verifies no false positive when text contains a Pokemon
  name after a name prefix ("my friend Pikachu"), and no detection in clean trade-related text.
- `TestPIIFiltering` — uses the module-level convenience functions to verify that `filter_pii()`
  replaces matches with the correct placeholder, that `filter_pii()` returns the input unchanged
  when no PII is found, and that `has_pii()` returns the correct boolean.
- `TestGuardrailMiddleware` — checks `process_input()` with `filter_input=True` and
  `filter_input=False`, and `process_output()` with `filter_output=True` and `filter_output=False`
  (the default).
- `TestCreateSafeInput` — checks that the function returns a `ProcessedInput` instance, that clean
  text returns `had_pii=False` and empty `warning`, and that text with PII returns `had_pii=True`
  and a warning string containing the word "privacy".

## Common Gotchas

**Name detection requires a prefix**: The name pattern only fires on names that follow `my friend`,
`my buddy`, `user`, `trader`, `person named`, or `someone called`. A raw capitalized name like "John
wants to trade" will not be redacted. This is intentional to minimize false positives against
Pokemon names like "Ash" or "Blue" that appear in casual trade conversation.

**Order matters in replacement**: `filter_pii()` sorts matches by start position descending before
replacing. If you add a new pattern type, make sure `PIIPatterns.PLACEHOLDERS` has an entry for it —
otherwise `PIIPatterns.PLACEHOLDERS.get(match.pii_type, "[REDACTED]")` will fall back to
`[REDACTED]`.

**SSN vs. phone overlap**: The SSN pattern (`\d{3}[-\s]?\d{2}[-\s]?\d{4}`) and phone pattern can
both match certain 9-digit strings. Because the patterns run as named groups in a single combined
regex, Python's `re` engine will match the first alternative that succeeds at each position. The
order in `PIIPatterns.PATTERNS` (which uses Python 3.7+ insertion order) determines priority.

**`filter_output=False` by default**: If you observe that an agent response containing an email
address is being stored unfiltered, this is expected behavior. Enable output filtering explicitly
with `GuardrailMiddleware(filter_output=True)` if your use case requires it.
