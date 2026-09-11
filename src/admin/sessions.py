"""In-memory session store for the local admin web UI (ROADMAP.md Phase 16).

Deliberately not persisted anywhere — this is a local, single-operator tool
bound to 127.0.0.1 by default; losing all sessions on a restart just means
logging back in, which is an acceptable tradeoff for the simplicity of not
running a session table/cache alongside `data/tenants.db`.

Each session pairs a session id (the cookie value) with a CSRF token, per
the OWASP synchronizer-token pattern: every state-changing form embeds its
session's CSRF token as a hidden field, checked server-side on submit
against the session that same cookie names — see `require_csrf_token`.
"""

from __future__ import annotations

import secrets

SESSION_COOKIE_NAME = "admin_session"

# session_id -> csrf_token. Both are cryptographically random and unrelated
# to each other, so leaking one doesn't help forge the other.
_sessions: dict[str, str] = {}


def create_session() -> tuple[str, str]:
    """Start a new session. Returns (session_id, csrf_token)."""
    session_id = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    _sessions[session_id] = csrf_token
    return session_id, csrf_token


def get_csrf_token(session_id: str | None) -> str | None:
    """The CSRF token for a session id, or None if it doesn't exist."""
    if session_id is None:
        return None
    return _sessions.get(session_id)


def destroy_session(session_id: str | None) -> None:
    """End a session (logout). A no-op if it doesn't exist."""
    if session_id is not None:
        _sessions.pop(session_id, None)
