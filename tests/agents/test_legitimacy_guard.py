import pytest
from pydantic_ai import AgentRunResult
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from src.agents.legitimacy_guard import LegitimacyDependencies, legitimacy_guard

# Mark the whole module for asyncio to handle await calls
pytestmark = pytest.mark.asyncio


def is_tool_result_in_history(messages: list[ModelMessage]) -> bool:
    """Helper to check if the conversation history already contains a tool result."""
    for msg in messages:
        # Pydantic AI stores tool results inside ModelRequest parts
        # as it passes them back to the model for the next turn.
        if isinstance(msg, ModelRequest) and any(isinstance(part, ToolReturnPart) for part in msg.parts):
            return True
    return False


def get_tool_returns(result: AgentRunResult[str]) -> list[str]:
    """Helper to extract all tool return values from the full conversation history."""
    returns: list[str] = []
    for msg in result.all_messages():
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, ToolReturnPart):
                    returns.append(str(part.content))
    return returns


async def test_legitimacy_scam_detection():
    """Test that the agent correctly triggers the tool and returns illegal status."""
    deps = LegitimacyDependencies(legal_ball_map={"mew": ["cherish"]})

    def mock_scam_logic(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        # 1. Break the loop if the tool has already executed
        if is_tool_result_in_history(messages):
            return ModelResponse(parts=[TextPart(content="Turn complete.")])

        # 2. Otherwise, tell the agent to call the tool with suspicious data
        return ModelResponse(
            parts=[ToolCallPart(tool_name="verify_provenance", args={"pokemon": "mew", "ball": "great"})]
        )

    with legitimacy_guard.override(model=FunctionModel(mock_scam_logic)):
        result = await legitimacy_guard.run("Is a Mew in a Great Ball legal?", deps=deps)

        # Inspect the message history for the specific tool output
        tool_outputs = get_tool_returns(result)
        assert any("🚨 ILLEGAL BALL" in out for out in tool_outputs)
        assert any("Mew" in out for out in tool_outputs)


async def test_rarity_classification():
    """Test that the agent correctly processes a Shiny Celebi through the tool."""
    deps = LegitimacyDependencies()

    def mock_rarity_logic(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if is_tool_result_in_history(messages):
            return ModelResponse(parts=[TextPart(content="Turn complete.")])

        return ModelResponse(
            parts=[ToolCallPart(tool_name="verify_provenance", args={"pokemon": "celebi", "is_shiny": True})]
        )

    with legitimacy_guard.override(model=FunctionModel(mock_rarity_logic)):
        result = await legitimacy_guard.run("What is the rarity of a Shiny Celebi?", deps=deps)

        tool_outputs = get_tool_returns(result)
        assert any("Celebi" in out for out in tool_outputs)
        assert any("Mythical" in out for out in tool_outputs)
        assert any("Shiny" in out for out in tool_outputs)


async def test_agent_tool_routing():
    """Verify the agent identifies the need for the verify_provenance tool."""
    deps = LegitimacyDependencies()

    def mock_routing_logic(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if is_tool_result_in_history(messages):
            return ModelResponse(parts=[TextPart(content="Done.")])

        return ModelResponse(parts=[ToolCallPart(tool_name="verify_provenance", args={"pokemon": "pikachu"})])

    with legitimacy_guard.override(model=FunctionModel(mock_routing_logic)):
        result = await legitimacy_guard.run("Check this Pikachu.", deps=deps)

        # Check that the tool call was actually generated during the run
        tool_invoked = any(
            isinstance(part, ToolCallPart) and part.tool_name == "verify_provenance"
            for msg in result.new_messages()
            if isinstance(msg, ModelResponse)
            for part in msg.parts
        )

        assert tool_invoked
