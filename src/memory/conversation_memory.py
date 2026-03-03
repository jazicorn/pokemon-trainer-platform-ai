"""Manage conversation history."""

from __future__ import annotations

from typing import Any

from .database import get_connection


class ConversationMemory:
    """Manage conversation history for context."""

    def __init__(self, user_id: str, max_history: int = 20):
        """Initialize for a specific user."""
        self.user_id = user_id
        self.max_history = max_history

    def add_message(self, role: str, content: str) -> None:
        """Add a message to conversation history."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO conversation_history (user_id, role, content)
                VALUES (?, ?, ?)
            """, (self.user_id, role, content))
            conn.commit()

        self._trim_history()

    def get_history(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Get conversation history."""
        limit = limit or self.max_history

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT role, content, created_at
                FROM conversation_history
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (self.user_id, limit))
            rows = cursor.fetchall()

        return [
            {
                "role": row["role"],
                "content": row["content"],
                "timestamp": row["created_at"],
            }
            for row in reversed(rows)
        ]

    def get_context_string(self, limit: int = 5) -> str:
        """Get recent conversation as context string."""
        history = self.get_history(limit=limit)

        if not history:
            return "No previous conversation."

        lines = ["Recent conversation:"]
        for msg in history:
            role = "User" if msg["role"] == "user" else "Assistant"
            content = msg["content"][:200]
            if len(msg["content"]) > 200:
                content += "..."
            lines.append(f"{role}: {content}")

        return "\n".join(lines)

    def _trim_history(self) -> None:
        """Remove old messages beyond max_history."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM conversation_history
                WHERE user_id = ? AND id NOT IN (
                    SELECT id FROM conversation_history
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                )
            """, (self.user_id, self.user_id, self.max_history))
            conn.commit()

    def clear(self) -> None:
        """Clear all conversation history for user."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM conversation_history WHERE user_id = ?",
                (self.user_id,),
            )
            conn.commit()


class RecommendationMemory:
    """Track recommendations and user feedback."""

    def __init__(self, user_id: str):
        """Initialize for a specific user."""
        self.user_id = user_id

    def save_recommendation(
        self,
        offered_pokemon: str,
        requested_pokemon: str,
        recommendation: str,
        reasoning: str,
    ) -> int:
        """Save a trade recommendation."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO recommendations
                (user_id, offered_pokemon, requested_pokemon, recommendation,
                 reasoning)
                VALUES (?, ?, ?, ?, ?)
            """, (
                self.user_id,
                offered_pokemon,
                requested_pokemon,
                recommendation,
                reasoning,
            ))
            conn.commit()
            return cursor.lastrowid or 0

    def record_feedback(
        self,
        recommendation_id: int,
        followed: bool,
        feedback: str | None = None,
    ) -> None:
        """Record user feedback on a recommendation."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE recommendations
                SET user_followed = ?, user_feedback = ?
                WHERE id = ?
            """, (1 if followed else 0, feedback, recommendation_id))
            conn.commit()

    def get_past_recommendations(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get past recommendations for this user."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM recommendations
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (self.user_id, limit))
            rows = cursor.fetchall()

        return [dict(row) for row in rows]
    