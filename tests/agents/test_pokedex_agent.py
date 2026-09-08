"""Tests for Pokedex Expert agent."""

from unittest.mock import MagicMock

import pytest
from pydantic_ai import AgentRunResult
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from agents.pokedex_expert import (
    TYPE_CHART,
    PokedexDependencies,
    pokedex_expert,
)

# ---------------------------------------------------------------------------
# Helpers (same pattern as test_legitimacy_guard.py)
# ---------------------------------------------------------------------------


def _is_tool_result_in_history(messages: list[ModelMessage]) -> bool:
    """Return True if any message in history contains a ToolReturnPart."""
    for msg in messages:
        if isinstance(msg, ModelRequest) and any(isinstance(part, ToolReturnPart) for part in msg.parts):
            return True
    return False


def _get_tool_returns(result: AgentRunResult[str]) -> list[str]:
    """Extract all tool return values from the full conversation history."""
    returns: list[str] = []
    for msg in result.all_messages():
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, ToolReturnPart):
                    returns.append(str(part.content))
    return returns


class TestTypeChart:
    """Tests for type effectiveness chart."""

    def test_fire_beats_grass(self):
        assert ("fire", "grass") in TYPE_CHART
        assert "super effective" in TYPE_CHART[("fire", "grass")]

    def test_water_beats_fire(self):
        assert ("water", "fire") in TYPE_CHART
        assert "super effective" in TYPE_CHART[("water", "fire")]

    def test_chart_is_not_empty(self):
        assert len(TYPE_CHART) > 0


class TestPokedexDependencies:
    """Tests for PokedexDependencies."""

    def test_allows_none_vector_store(self):
        deps = PokedexDependencies(vector_store=None)
        assert deps.vector_store is None

    def test_allows_arbitrary_types(self):
        # Should not raise
        deps = PokedexDependencies()
        assert deps.vector_store is None


class TestPokedexExpertAgent:
    """Tests for the Pokedex Expert agent configuration."""

    def test_agent_has_system_prompt(self):
        assert pokedex_expert.system_prompt is not None

    def test_agent_model_configured(self):
        # Verify agent has a model configured
        assert pokedex_expert.model is not None


# ---------------------------------------------------------------------------
# Async integration tests — agent actually runs with FunctionModel
# ---------------------------------------------------------------------------


class TestPokedexAgentIntegration:
    pytestmark = pytest.mark.asyncio
    """Async integration tests: agent.run() is called with mocked LLM."""

    async def test_search_pokemon_tool_is_invoked(self):
        """FunctionModel triggers search_pokemon; vector_store.query is called."""
        mock_store = MagicMock()
        mock_store.query.return_value = [{"document": "Pikachu — Electric type. HP: 35, Attack: 55, Speed: 90."}]
        deps = PokedexDependencies.model_construct(vector_store=mock_store)

        def mock_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            if _is_tool_result_in_history(messages):
                return ModelResponse(parts=[TextPart(content="Turn complete.")])
            return ModelResponse(parts=[ToolCallPart(tool_name="search_pokemon", args={"query": "pikachu"})])

        with pokedex_expert.override(model=FunctionModel(mock_model)):
            result = await pokedex_expert.run("Tell me about Pikachu.", deps=deps)

        mock_store.query.assert_called_once()
        tool_outputs = _get_tool_returns(result)
        assert any("Pikachu" in out for out in tool_outputs)

    async def test_search_pokemon_no_vector_store_returns_unavailable(self):
        """When vector_store is None, search_pokemon returns a graceful message."""
        deps = PokedexDependencies(vector_store=None)

        def mock_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            if _is_tool_result_in_history(messages):
                return ModelResponse(parts=[TextPart(content="Turn complete.")])
            return ModelResponse(parts=[ToolCallPart(tool_name="search_pokemon", args={"query": "pikachu"})])

        with pokedex_expert.override(model=FunctionModel(mock_model)):
            result = await pokedex_expert.run("Tell me about Pikachu.", deps=deps)

        tool_outputs = _get_tool_returns(result)
        assert any("not available" in out.lower() for out in tool_outputs)

    async def test_type_effectiveness_returns_correct_matchup(self):
        """get_type_effectiveness tool returns the expected effectiveness string."""
        deps = PokedexDependencies(vector_store=None)

        def mock_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            if _is_tool_result_in_history(messages):
                return ModelResponse(parts=[TextPart(content="Turn complete.")])
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="get_type_effectiveness",
                        args={"attacking_type": "fire", "defending_type": "grass"},
                    )
                ]
            )

        with pokedex_expert.override(model=FunctionModel(mock_model)):
            result = await pokedex_expert.run("How effective is Fire vs Grass?", deps=deps)

        tool_outputs = _get_tool_returns(result)
        assert any("super effective" in out.lower() for out in tool_outputs)

    async def test_type_effectiveness_unknown_matchup_returns_normal(self):
        """An unmapped type pair falls back to normal effectiveness (1x)."""
        deps = PokedexDependencies(vector_store=None)

        def mock_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            if _is_tool_result_in_history(messages):
                return ModelResponse(parts=[TextPart(content="Turn complete.")])
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="get_type_effectiveness",
                        args={"attacking_type": "normal", "defending_type": "normal"},
                    )
                ]
            )

        with pokedex_expert.override(model=FunctionModel(mock_model)):
            result = await pokedex_expert.run("How effective is Normal vs Normal?", deps=deps)

        tool_outputs = _get_tool_returns(result)
        assert any("1x" in out or "normal" in out.lower() for out in tool_outputs)

    async def test_tool_call_is_recorded_in_message_history(self):
        """Verifies the tool call part appears in the new_messages() history."""
        deps = PokedexDependencies(vector_store=None)

        def mock_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            if _is_tool_result_in_history(messages):
                return ModelResponse(parts=[TextPart(content="Turn complete.")])
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="get_type_effectiveness",
                        args={"attacking_type": "water", "defending_type": "fire"},
                    )
                ]
            )

        with pokedex_expert.override(model=FunctionModel(mock_model)):
            result = await pokedex_expert.run("Water vs Fire?", deps=deps)

        tool_invoked = any(
            isinstance(part, ToolCallPart) and part.tool_name == "get_type_effectiveness"
            for msg in result.new_messages()
            if isinstance(msg, ModelResponse)
            for part in msg.parts
        )
        assert tool_invoked
