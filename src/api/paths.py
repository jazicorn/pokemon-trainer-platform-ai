"""Endpoint path constants — the one place a route's path (and the version
prefix) is spelled out. api.app's route decorators and the test suite both
import directly from here, so a version bump or a path change is a one-line
edit in this file, nowhere else.
"""

from __future__ import annotations

API_PREFIX = "/v1"

# Unversioned — mounted directly on `app`, not on protected_router.
HEALTH = "/health"

# Versioned — these already include API_PREFIX, so protected_router is
# included with no separate prefix argument.
CHAT = f"{API_PREFIX}/chat"
TRADE_EVALUATE = f"{API_PREFIX}/trade/evaluate"
TRADE_SUGGESTIONS = f"{API_PREFIX}/trade/suggestions"
OFFERS = f"{API_PREFIX}/offers"
OFFERS_SEND = f"{API_PREFIX}/offers/send"
POKEDEX_QUERY = f"{API_PREFIX}/pokedex/query"
MARKET_QUERY = f"{API_PREFIX}/market/query"

# Self-serve tenant registration (ROADMAP.md Phase 15). ACCOUNTS_REGISTER is
# the one route on protected_router's version prefix that skips
# require_api_key — it's how a caller gets a key in the first place.
ACCOUNTS_REGISTER = f"{API_PREFIX}/accounts/register"
ACCOUNTS_ROTATE_KEY = f"{API_PREFIX}/accounts/rotate-key"
ACCOUNTS = f"{API_PREFIX}/accounts"
