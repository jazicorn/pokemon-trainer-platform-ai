"""Tests for CLI module."""

from cli.commands import (
    CommandType,
    OfferParams,
    ParsedCommand,
    TradeParams,
    _parse_offer,
    _parse_trade,
    parse_command,
)


class TestParseCommand:
    """Tests for command parsing."""

    def test_parse_quit_commands(self):
        for cmd in ("quit", "exit", "q", "QUIT", "Exit"):
            result = parse_command(cmd)
            assert result.command_type == CommandType.QUIT

    def test_parse_help_commands(self):
        for cmd in ("help", "h", "?", "HELP"):
            result = parse_command(cmd)
            assert result.command_type == CommandType.HELP

    def test_parse_simple_commands(self):
        cases = {
            "suggest": CommandType.SUGGEST,
            "prefs": CommandType.PREFS,
            "history": CommandType.HISTORY,
            "index": CommandType.INDEX,
        }
        for cmd, expected in cases.items():
            result = parse_command(cmd)
            assert result.command_type == expected

    def test_parse_trade_command(self):
        result = parse_command("trade pikachu for eevee")

        assert result.command_type == CommandType.TRADE
        assert result.trade_params is not None
        assert result.trade_params.offered == "pikachu"
        assert result.trade_params.requested == "eevee"

    def test_parse_trade_with_my_their(self):
        result = parse_command("trade my Charizard for their Dragonite")

        assert result.command_type == CommandType.TRADE
        assert result.trade_params is not None
        assert result.trade_params.offered == "charizard"
        assert result.trade_params.requested == "dragonite"

    def test_parse_pokedex_with_query(self):
        result = parse_command("pokedex What type is Pikachu?")

        assert result.command_type == CommandType.POKEDEX
        assert result.args == "What type is Pikachu?"

    def test_parse_pokedex_without_query(self):
        result = parse_command("pokedex")

        assert result.command_type == CommandType.POKEDEX
        assert result.args == ""

    def test_parse_market_with_query(self):
        result = parse_command("market trending pokemon")

        assert result.command_type == CommandType.MARKET
        assert result.args == "trending pokemon"

    def test_parse_empty_input(self):
        result = parse_command("")

        assert result.command_type == CommandType.UNKNOWN

    def test_parse_unknown_command(self):
        result = parse_command("random text here")

        assert result.command_type == CommandType.UNKNOWN
        assert result.args == "random text here"


class TestParseTrade:
    """Tests for trade parsing."""

    def test_valid_trade(self):
        result = _parse_trade("trade alakazam for gengar")

        assert result is not None
        assert result.offered == "alakazam"
        assert result.requested == "gengar"

    def test_trade_without_for(self):
        result = _parse_trade("trade pikachu eevee")

        assert result is None

    def test_trade_missing_pokemon(self):
        result = _parse_trade("trade for eevee")

        assert result is None

    def test_trade_with_my_their(self):
        result = _parse_trade("trade my pikachu for their eevee")

        assert result is not None
        assert result.offered == "pikachu"
        assert result.requested == "eevee"


class TestParseCommandPerformance:
    """Performance tests for command parsing."""

    def test_parse_command_is_fast(self):
        """Verify parsing is O(1) for simple commands."""
        import time

        commands = ["quit", "help", "suggest", "prefs", "history"]
        iterations = 10000

        start = time.perf_counter()
        for _ in range(iterations):
            for cmd in commands:
                parse_command(cmd)
        elapsed = time.perf_counter() - start

        # Should complete 50k parses in under 100ms
        assert elapsed < 0.1, f"Parsing too slow: {elapsed:.3f}s"

    def test_frozenset_lookup_is_used(self):
        """Verify module uses frozenset for O(1) lookup."""
        from cli import commands

        assert hasattr(commands, "_QUIT_COMMANDS")
        assert hasattr(commands, "_HELP_COMMANDS")
        assert isinstance(commands._QUIT_COMMANDS, frozenset)
        assert isinstance(commands._HELP_COMMANDS, frozenset)


class TestTradeParams:
    """Tests for TradeParams."""

    def test_trade_params_is_named_tuple(self):
        params = TradeParams(offered="a", requested="b")

        assert params.offered == "a"
        assert params.requested == "b"
        assert params[0] == "a"
        assert params[1] == "b"


class TestParseOffers:
    """Tests for offer-related command parsing."""

    def test_parse_offers_inbox(self):
        result = parse_command("offers")
        assert result.command_type == CommandType.OFFERS
        assert result.args == ""

    def test_parse_offers_sent(self):
        result = parse_command("offers sent")
        assert result.command_type == CommandType.OFFERS
        assert result.args == "sent"

    def test_parse_offer_send(self):
        result = parse_command("offer pikachu to user_002 for charizard")
        assert result.command_type == CommandType.OFFER_SEND
        assert result.offer_params is not None
        assert result.offer_params.offered == "pikachu"
        assert result.offer_params.recipient == "user_002"
        assert result.offer_params.requested == "charizard"

    def test_parse_offer_send_multi_word_pokemon(self):
        result = parse_command("offer mr mime to user_003 for mr rime")
        assert result.command_type == CommandType.OFFER_SEND
        assert result.offer_params is not None
        assert result.offer_params.offered == "mr mime"
        assert result.offer_params.recipient == "user_003"
        assert result.offer_params.requested == "mr rime"

    def test_parse_accept(self):
        result = parse_command("accept 3")
        assert result.command_type == CommandType.OFFER_ACCEPT
        assert result.args == "3"

    def test_parse_decline(self):
        result = parse_command("decline 5")
        assert result.command_type == CommandType.OFFER_DECLINE
        assert result.args == "5"

    def test_parse_offer_missing_to_returns_unknown(self):
        result = parse_command("offer pikachu for charizard")
        # Missing "to <user>" — falls through to TRADE parsing
        assert result.command_type != CommandType.OFFER_SEND

    def test_parse_offer_missing_for_returns_unknown(self):
        result = parse_command("offer pikachu to user_002")
        # Missing "for <pokemon>"
        assert result.command_type != CommandType.OFFER_SEND


class TestParseOffer:
    """Unit tests for _parse_offer helper."""

    def test_valid_offer(self):
        result = _parse_offer("offer alakazam to user_002 for gengar")
        assert result is not None
        assert result.offered == "alakazam"
        assert result.recipient == "user_002"
        assert result.requested == "gengar"

    def test_missing_to_returns_none(self):
        assert _parse_offer("offer pikachu for charizard") is None

    def test_missing_for_returns_none(self):
        assert _parse_offer("offer pikachu to user_002") is None

    def test_empty_parts_return_none(self):
        assert _parse_offer("offer  to user_002 for charizard") is None


class TestOfferParams:
    """Tests for OfferParams NamedTuple."""

    def test_offer_params_fields(self):
        params = OfferParams(recipient="user_002", offered="pikachu", requested="charizard")
        assert params.recipient == "user_002"
        assert params.offered == "pikachu"
        assert params.requested == "charizard"

    def test_offer_params_positional(self):
        params = OfferParams("user_002", "pikachu", "charizard")
        assert params[0] == "user_002"
        assert params[1] == "pikachu"
        assert params[2] == "charizard"


class TestParsedCommand:
    """Tests for ParsedCommand."""

    def test_default_values(self):
        cmd = ParsedCommand(CommandType.HELP)

        assert cmd.command_type == CommandType.HELP
        assert cmd.args == ""
        assert cmd.trade_params is None
        assert cmd.offer_params is None
