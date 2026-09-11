"""Tests for the admin UI's in-memory session/CSRF store (ROADMAP.md Phase 16)."""

from __future__ import annotations

from admin.sessions import create_session, destroy_session, get_csrf_token


class TestCreateSession:
    def test_returns_distinct_session_id_and_csrf_token(self) -> None:
        session_id, csrf_token = create_session()
        assert session_id
        assert csrf_token
        assert session_id != csrf_token

    def test_two_sessions_never_collide(self) -> None:
        first_id, _ = create_session()
        second_id, _ = create_session()
        assert first_id != second_id


class TestGetCsrfToken:
    def test_returns_the_token_for_a_real_session(self) -> None:
        session_id, csrf_token = create_session()
        assert get_csrf_token(session_id) == csrf_token

    def test_returns_none_for_an_unknown_session(self) -> None:
        assert get_csrf_token("not-a-real-session") is None

    def test_returns_none_for_none(self) -> None:
        assert get_csrf_token(None) is None


class TestDestroySession:
    def test_session_no_longer_resolves_afterward(self) -> None:
        session_id, _ = create_session()
        destroy_session(session_id)
        assert get_csrf_token(session_id) is None

    def test_destroying_an_unknown_session_does_not_raise(self) -> None:
        destroy_session("not-a-real-session")

    def test_destroying_none_does_not_raise(self) -> None:
        destroy_session(None)
