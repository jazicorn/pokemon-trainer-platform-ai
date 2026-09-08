"""Tests for MCP server."""

from mcp_server.tools import (
    TOOL_EVALUATE_TRADE,
    TOOL_MARKET,
    TOOL_POKEDEX,
    TOOL_SUGGESTIONS,
    VALID_TOOLS,
    get_tools,
)


class TestMCPTools:
    """Tests for MCP tool definitions."""

    def test_get_tools_returns_tuple(self):
        tools = get_tools()
        assert isinstance(tools, tuple)

    def test_get_tools_has_four_tools(self):
        tools = get_tools()
        assert len(tools) == 4

    def test_all_tools_have_name(self):
        tools = get_tools()
        for tool in tools:
            assert tool.name
            assert isinstance(tool.name, str)

    def test_all_tools_have_description(self):
        tools = get_tools()
        for tool in tools:
            assert tool.description
            assert len(tool.description) > 10

    def test_all_tools_have_schema(self):
        tools = get_tools()
        for tool in tools:
            assert tool.inputSchema
            assert "type" in tool.inputSchema
            assert tool.inputSchema["type"] == "object"

    def test_tool_names_match_constants(self):
        tools = get_tools()
        tool_names = {t.name for t in tools}

        assert TOOL_EVALUATE_TRADE in tool_names
        assert TOOL_SUGGESTIONS in tool_names
        assert TOOL_POKEDEX in tool_names
        assert TOOL_MARKET in tool_names

    def test_valid_tools_frozenset(self):
        assert isinstance(VALID_TOOLS, frozenset)
        assert len(VALID_TOOLS) == 4


class TestToolSchemas:
    """Tests for tool input schemas."""

    def test_evaluate_trade_requires_pokemon(self):
        tools = get_tools()
        trade_tool = next(t for t in tools if t.name == "evaluate_trade")

        required = trade_tool.inputSchema.get("required", [])
        assert "offered_pokemon" in required
        assert "requested_pokemon" in required

    def test_query_tools_require_question(self):
        tools = get_tools()

        for name in ("query_pokedex", "query_market"):
            tool = next(t for t in tools if t.name == name)
            required = tool.inputSchema.get("required", [])
            assert "question" in required

    def test_suggestions_has_optional_user_id(self):
        tools = get_tools()
        suggestions_tool = next(t for t in tools if t.name == "get_trade_suggestions")

        required = suggestions_tool.inputSchema.get("required", [])
        assert "user_id" not in required

        props = suggestions_tool.inputSchema.get("properties", {})
        assert "user_id" in props

    def test_query_pokedex_has_optional_user_id(self):
        tools = get_tools()
        pokedex_tool = next(t for t in tools if t.name == "query_pokedex")

        required = pokedex_tool.inputSchema.get("required", [])
        assert "question" in required
        assert "user_id" not in required

        props = pokedex_tool.inputSchema.get("properties", {})
        assert "user_id" in props
