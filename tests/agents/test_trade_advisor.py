"""Tests for Trade Advisor agent."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from data.models import (
    OwnedPokemon,
    UserCollection,
    UserPreferences,
)
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from agents.trade_advisor import (
    SYSTEM_PROMPT,
    AdvisorDependencies,
    trade_advisor,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_tool_result_in_history(messages) -> bool:
    for msg in messages:
        if isinstance(msg, ModelRequest) and any(isinstance(part, ToolReturnPart) for part in msg.parts):
            return True
    return False


def _get_tool_returns(result) -> list[str]:
    returns = []
    for msg in result.all_messages():
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, ToolReturnPart):
                    returns.append(str(part.content))
    return returns


class TestAdvisorDependencies:
    """Tests for AdvisorDependencies."""

    def test_allows_none_values(self):
        deps = AdvisorDependencies(
            vector_store=None,
            analytics=None,
            user_collection=None,
        )
        assert deps.vector_store is None
        assert deps.analytics is None
        assert deps.user_collection is None

    def test_accepts_user_collection(self):
        collection = UserCollection(
            user_id="test_user",
            pokemon=[
                OwnedPokemon(
                    pokemon_id="pikachu",
                    acquired_date="2024-01-01",
                    acquired_via="catch",
                    tradeable=True,
                )
            ],
            preferences=UserPreferences(
                favorite_types=["electric"],
                goal="complete_gen1",
                trading_style="balanced",
                never_trade=[],
                seeking=["charizard"],
            ),
        )
        deps = AdvisorDependencies(user_collection=collection)
        assert deps.user_collection is not None
        assert deps.user_collection.user_id == "test_user"


class TestTradeAdvisorAgent:
    """Tests for Trade Advisor agent configuration."""

    def test_agent_has_system_prompt(self):
        assert trade_advisor.system_prompt is not None
        assert "trade advisor" in SYSTEM_PROMPT.lower()

    def test_agent_model_configured(self):
        assert trade_advisor.model is not None

    def test_system_prompt_mentions_key_concepts(self):
        prompt_lower = SYSTEM_PROMPT.lower()
        assert "pokemon" in prompt_lower
        assert "market" in prompt_lower
        assert "user" in prompt_lower


class TestUserContextHelpers:
    """Tests for user context tool helpers."""

    @pytest.fixture
    def sample_collection(self):
        return UserCollection(
            user_id="test_user",
            pokemon=[
                OwnedPokemon(
                    pokemon_id="pikachu",
                    acquired_date="2024-01-01",
                    acquired_via="catch",
                    tradeable=True,
                ),
                OwnedPokemon(
                    pokemon_id="mewtwo",
                    acquired_date="2024-01-01",
                    acquired_via="catch",
                    tradeable=False,
                ),
            ],
            preferences=UserPreferences(
                favorite_types=["electric", "psychic"],
                goal="complete_gen1",
                trading_style="value_focused",
                never_trade=["mewtwo"],
                seeking=["charizard", "blastoise"],
            ),
        )

    def test_collection_has_pokemon(self, sample_collection):
        assert len(sample_collection.pokemon) == 2

    def test_collection_has_tradeable_pokemon(self, sample_collection):
        tradeable = [p for p in sample_collection.pokemon if p.tradeable]
        assert len(tradeable) == 1
        assert tradeable[0].pokemon_id == "pikachu"

    def test_collection_has_seeking_list(self, sample_collection):
        assert "charizard" in sample_collection.preferences.seeking
        assert "blastoise" in sample_collection.preferences.seeking

    def test_collection_has_never_trade(self, sample_collection):
        assert "mewtwo" in sample_collection.preferences.never_trade


# ---------------------------------------------------------------------------
# Async integration tests — trade_advisor.run() with FunctionModel
# ---------------------------------------------------------------------------


class TestTradeAdvisorIntegration:
    """Async integration tests verifying tool dispatch and sub-agent delegation."""

    pytestmark = pytest.mark.asyncio

    @pytest.fixture
    def sample_collection(self):
        return UserCollection(
            user_id="test_user",
            pokemon=[
                OwnedPokemon(
                    pokemon_id="pikachu",
                    acquired_date="2024-01-01",
                    acquired_via="catch",
                    tradeable=True,
                ),
            ],
            preferences=UserPreferences(
                favorite_types=["electric"],
                goal="Complete Gen 1",
                trading_style="balanced",
                never_trade=[],
                seeking=["charizard"],
            ),
        )

    async def test_get_pokemon_info_delegates_to_pokedex(self, monkeypatch, sample_collection):
        """get_pokemon_info tool correctly delegates to pokedex_expert.run()."""
        import sys

        # Import directly from the submodule to avoid __init__.py name shadowing
        from agents.pokedex_expert import pokedex_expert as pokedex_expert_agent

        mock_result = MagicMock()
        mock_result.output = "Pikachu: Electric type, 320 BST, fast attacker."
        mock_run = AsyncMock(return_value=mock_result)
        monkeypatch.setattr(pokedex_expert_agent, "run", mock_run)

        # Also patch PokedexDependencies in trade_advisor's namespace so the MagicMock
        # vector_store passes validation when get_pokemon_info creates it.
        ta_mod = sys.modules["agents.trade_advisor_tools"]
        monkeypatch.setattr(ta_mod, "PokedexDependencies", lambda **kwargs: MagicMock())

        deps = AdvisorDependencies.model_construct(
            vector_store=MagicMock(),
            analytics=None,
            user_collection=sample_collection,
        )

        def mock_model(messages, info):
            if _is_tool_result_in_history(messages):
                return ModelResponse(parts=[TextPart(content="Turn complete.")])
            return ModelResponse(parts=[ToolCallPart(tool_name="get_pokemon_info", args={"pokemon": "pikachu"})])

        with trade_advisor.override(model=FunctionModel(mock_model)):
            result = await trade_advisor.run("Tell me about Pikachu.", deps=deps)

        mock_run.assert_called_once()
        tool_outputs = _get_tool_returns(result)
        assert any("Pikachu" in out for out in tool_outputs)

    async def test_get_market_data_delegates_to_market_analyst(self, monkeypatch, sample_collection):
        """get_market_data tool correctly delegates to trade_market_analyst.run()."""
        import sys

        # Import directly from the submodule to avoid __init__.py name shadowing
        from agents.trade_market_analyst import trade_market_analyst as tma_agent

        mock_result = MagicMock()
        mock_result.output = "Eevee demand ratio: 1.8 (Bullish). Strong upward momentum."
        mock_run = AsyncMock(return_value=mock_result)
        monkeypatch.setattr(tma_agent, "run", mock_run)

        # Also patch MarketDependencies so the MagicMock analytics passes validation.
        ta_mod = sys.modules["agents.trade_advisor_tools"]
        monkeypatch.setattr(ta_mod, "MarketDependencies", lambda **kwargs: MagicMock())

        deps = AdvisorDependencies.model_construct(
            vector_store=None,
            analytics=MagicMock(),
            user_collection=sample_collection,
        )

        def mock_model(messages, info):
            if _is_tool_result_in_history(messages):
                return ModelResponse(parts=[TextPart(content="Turn complete.")])
            return ModelResponse(parts=[ToolCallPart(tool_name="get_market_data", args={"pokemon": "eevee"})])

        with trade_advisor.override(model=FunctionModel(mock_model)):
            result = await trade_advisor.run("What is the market for Eevee?", deps=deps)

        mock_run.assert_called_once()
        tool_outputs = _get_tool_returns(result)
        assert any("Eevee" in out or "demand" in out.lower() for out in tool_outputs)

    async def test_get_user_context_returns_collection_data(self, sample_collection):
        """get_user_context tool surfaces the user's goal and owned Pokemon."""
        deps = AdvisorDependencies(
            vector_store=None,
            analytics=None,
            user_collection=sample_collection,
        )

        def mock_model(messages, info):
            if _is_tool_result_in_history(messages):
                return ModelResponse(parts=[TextPart(content="Turn complete.")])
            return ModelResponse(parts=[ToolCallPart(tool_name="get_user_context", args={})])

        with trade_advisor.override(model=FunctionModel(mock_model)):
            result = await trade_advisor.run("What is my trading goal?", deps=deps)

        tool_outputs = _get_tool_returns(result)
        assert any("Complete Gen 1" in out for out in tool_outputs)
        assert any("pikachu" in out.lower() for out in tool_outputs)

    async def test_get_pokemon_info_no_vector_store_graceful_fallback(self, sample_collection):
        """get_pokemon_info returns a graceful message when vector_store is None."""
        deps = AdvisorDependencies(
            vector_store=None,
            analytics=None,
            user_collection=sample_collection,
        )

        def mock_model(messages, info):
            if _is_tool_result_in_history(messages):
                return ModelResponse(parts=[TextPart(content="Turn complete.")])
            return ModelResponse(parts=[ToolCallPart(tool_name="get_pokemon_info", args={"pokemon": "pikachu"})])

        with trade_advisor.override(model=FunctionModel(mock_model)):
            result = await trade_advisor.run("Tell me about Pikachu.", deps=deps)

        tool_outputs = _get_tool_returns(result)
        assert any("not available" in out.lower() for out in tool_outputs)

    async def test_get_market_data_no_analytics_graceful_fallback(self, sample_collection):
        """get_market_data returns a graceful message when analytics is None."""
        deps = AdvisorDependencies(
            vector_store=None,
            analytics=None,
            user_collection=sample_collection,
        )

        def mock_model(messages, info):
            if _is_tool_result_in_history(messages):
                return ModelResponse(parts=[TextPart(content="Turn complete.")])
            return ModelResponse(parts=[ToolCallPart(tool_name="get_market_data", args={"pokemon": "eevee"})])

        with trade_advisor.override(model=FunctionModel(mock_model)):
            result = await trade_advisor.run("Market data for Eevee?", deps=deps)

        tool_outputs = _get_tool_returns(result)
        assert any("not available" in out.lower() for out in tool_outputs)

    async def test_get_user_context_no_collection_graceful_fallback(self):
        """get_user_context returns a graceful message when user_collection is None."""
        deps = AdvisorDependencies(
            vector_store=None,
            analytics=None,
            user_collection=None,
        )

        def mock_model(messages, info):
            if _is_tool_result_in_history(messages):
                return ModelResponse(parts=[TextPart(content="Turn complete.")])
            return ModelResponse(parts=[ToolCallPart(tool_name="get_user_context", args={})])

        with trade_advisor.override(model=FunctionModel(mock_model)):
            result = await trade_advisor.run("What is my context?", deps=deps)

        tool_outputs = _get_tool_returns(result)
        assert any("not available" in out.lower() for out in tool_outputs)
