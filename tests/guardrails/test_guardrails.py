"""Tests for PII guardrails."""

import pytest

from guardrails.middleware import (
    GuardrailMiddleware,
    ProcessedInput,
    create_safe_input,
)
from guardrails.pii_filter import (
    POKEMON_NAMES,
    PIIFilter,
    PIIPatterns,
    filter_pii,
    has_pii,
)


class TestPIIPatterns:
    """Tests for PII pattern configuration."""

    def test_patterns_dict_not_empty(self):
        assert len(PIIPatterns.PATTERNS) > 0

    def test_placeholders_cover_all_patterns(self):
        for pii_type in PIIPatterns.PATTERNS:
            assert pii_type in PIIPatterns.PLACEHOLDERS

    def test_pokemon_names_is_frozenset(self):
        assert isinstance(POKEMON_NAMES, frozenset)

    def test_pokemon_names_contains_common_pokemon(self):
        assert "pikachu" in POKEMON_NAMES
        assert "charizard" in POKEMON_NAMES
        assert "mewtwo" in POKEMON_NAMES


class TestPIIDetection:
    """Tests for PII detection."""

    @pytest.fixture
    def pii_filter(self) -> PIIFilter:
        return PIIFilter()

    def test_detect_email(self, pii_filter: PIIFilter):
        text = "Contact me at john.doe@example.com"
        matches = pii_filter.detect_pii(text)

        assert len(matches) == 1
        assert matches[0].pii_type == "email"
        assert "john.doe@example.com" in matches[0].original

    def test_detect_phone(self, pii_filter: PIIFilter):
        text = "Call me at 555-123-4567"
        matches = pii_filter.detect_pii(text)

        assert len(matches) == 1
        assert matches[0].pii_type == "phone"

    def test_detect_ssn(self, pii_filter: PIIFilter):
        text = "My SSN is 123-45-6789"
        matches = pii_filter.detect_pii(text)

        assert len(matches) == 1
        assert matches[0].pii_type == "ssn"

    def test_detect_username(self, pii_filter: PIIFilter):
        text = "Message @pokemon_trader"
        matches = pii_filter.detect_pii(text)

        assert len(matches) == 1
        assert matches[0].pii_type == "username"

    def test_detect_name_after_prefix(self, pii_filter: PIIFilter):
        text = "My friend John Smith wants to trade"
        matches = pii_filter.detect_pii(text)

        assert len(matches) == 1
        assert matches[0].pii_type == "name"
        assert matches[0].original == "John Smith"

    def test_no_false_positive_for_pokemon_names(self, pii_filter: PIIFilter):
        text = "My friend Pikachu is the best"
        matches = pii_filter.detect_pii(text)

        # Should not detect "Pikachu" as a name
        name_matches = [m for m in matches if m.pii_type == "name"]
        assert len(name_matches) == 0

    def test_no_pii_in_clean_text(self, pii_filter: PIIFilter):
        text = "Should I trade my Charizard for Dragonite?"
        matches = pii_filter.detect_pii(text)

        assert len(matches) == 0

    def test_detect_multiple_pii(self, pii_filter: PIIFilter):
        text = "Email john@example.com or call 555-123-4567"
        matches = pii_filter.detect_pii(text)

        types = {m.pii_type for m in matches}
        assert "email" in types
        assert "phone" in types


class TestPIIFiltering:
    """Tests for PII filtering."""

    def test_filter_email(self):
        text = "Contact john@example.com"
        filtered = filter_pii(text)

        assert "[EMAIL]" in filtered
        assert "john@example.com" not in filtered

    def test_filter_phone(self):
        text = "Call 555-123-4567"
        filtered = filter_pii(text)

        assert "[PHONE]" in filtered
        assert "555-123-4567" not in filtered

    def test_filter_multiple_pii(self):
        text = "Email john@example.com or call 555-123-4567"
        filtered = filter_pii(text)

        assert "[EMAIL]" in filtered
        assert "[PHONE]" in filtered
        assert "john@example.com" not in filtered

    def test_filter_preserves_clean_text(self):
        text = "Trade my Charizard for Dragonite"
        filtered = filter_pii(text)

        assert filtered == text

    def test_has_pii_returns_true(self):
        assert has_pii("Contact john@example.com") is True

    def test_has_pii_returns_false(self):
        assert has_pii("Trade Charizard for Dragonite") is False


class TestGuardrailMiddleware:
    """Tests for GuardrailMiddleware."""

    def test_process_input_filters_pii(self):
        middleware = GuardrailMiddleware(filter_input=True)
        text = "Email john@example.com"

        filtered, report = middleware.process_input(text)

        assert "[EMAIL]" in filtered
        assert report["has_pii"] is True

    def test_process_input_no_filter_when_disabled(self):
        middleware = GuardrailMiddleware(filter_input=False)
        text = "Email john@example.com"

        filtered, report = middleware.process_input(text)

        assert filtered == text
        assert report == {}

    def test_process_output_filters_when_enabled(self):
        middleware = GuardrailMiddleware(filter_output=True)
        text = "Contact john@example.com"

        filtered = middleware.process_output(text)

        assert "[EMAIL]" in filtered

    def test_process_output_no_filter_by_default(self):
        middleware = GuardrailMiddleware()
        text = "Contact john@example.com"

        filtered = middleware.process_output(text)

        assert filtered == text


class TestCreateSafeInput:
    """Tests for create_safe_input function."""

    def test_returns_processed_input(self):
        result = create_safe_input("Hello")
        assert isinstance(result, ProcessedInput)

    def test_no_pii_returns_original(self):
        result = create_safe_input("Trade Charizard")

        assert result.text == "Trade Charizard"
        assert result.had_pii is False
        assert result.warning == ""

    def test_pii_returns_filtered_with_warning(self):
        result = create_safe_input("Email john@example.com")

        assert "[EMAIL]" in result.text
        assert result.had_pii is True
        assert "privacy" in result.warning.lower()
