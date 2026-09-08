"""PII detection and filtering for privacy protection."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cached_property
from typing import Any, ClassVar


@dataclass(frozen=True)
class PIIMatch:
    """A detected PII match."""

    pii_type: str
    original: str
    start: int
    end: int


class PIIPatterns:
    """PII pattern constants."""

    PATTERNS: ClassVar[dict[str, str]] = {
        "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "phone": r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
        "ssn": r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b",
        "credit_card": r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
        "ip_address": r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
        "username": r"@[A-Za-z0-9_]+",
    }

    PLACEHOLDERS: ClassVar[dict[str, str]] = {
        "email": "[EMAIL]",
        "phone": "[PHONE]",
        "ssn": "[SSN]",
        "credit_card": "[CREDIT_CARD]",
        "ip_address": "[IP_ADDRESS]",
        "name": "[NAME]",
        "username": "[USERNAME]",
    }

    NAME_PREFIXES: ClassVar[str] = r"(?:my friend|my buddy|user|trader|person named|someone called)"


# Common Pokemon names to avoid false positives
POKEMON_NAMES: frozenset[str] = frozenset(
    {
        "pikachu",
        "charizard",
        "blastoise",
        "venusaur",
        "dragonite",
        "alakazam",
        "machamp",
        "gengar",
        "gyarados",
        "mewtwo",
        "mew",
        "eevee",
        "snorlax",
        "lapras",
        "articuno",
        "zapdos",
        "moltres",
        "tyranitar",
        "salamence",
        "metagross",
        "garchomp",
        "lucario",
        "absol",
        "gardevoir",
        "aggron",
        "flygon",
        "milotic",
        "geodude",
        "machop",
        "abra",
        "gastly",
        "magikarp",
        "dratini",
        "larvitar",
        "bagon",
        "beldum",
        "gible",
        "vaporeon",
        "jolteon",
        "flareon",
        "espeon",
        "umbreon",
    }
)


class PIIFilter:
    """Detect and filter PII from text."""

    def __init__(self) -> None:
        """Initialize the PII filter."""
        pass  # Patterns compiled lazily via cached_property

    @cached_property
    def _combined_pattern(self) -> re.Pattern[str]:
        """Single compiled pattern for all PII types."""
        named_groups = "|".join(f"(?P<{name}>{pattern})" for name, pattern in PIIPatterns.PATTERNS.items())
        return re.compile(named_groups, re.IGNORECASE)

    @cached_property
    def _name_pattern(self) -> re.Pattern[str]:
        """Compiled pattern for name detection."""
        # Match capitalized words (first name, optional last name)
        # but not followed by common words
        return re.compile(
            rf"{PIIPatterns.NAME_PREFIXES}\s+([A-Z][a-z]+)(?:\s+([A-Z][a-z]+))?",
            re.IGNORECASE,
        )

    def _find_pattern_matches(self, text: str) -> Iterator[PIIMatch]:
        """Find all pattern-based PII matches."""
        for match in self._combined_pattern.finditer(text):
            pii_type = match.lastgroup
            if pii_type:
                yield PIIMatch(
                    pii_type=pii_type,
                    original=match.group(),
                    start=match.start(),
                    end=match.end(),
                )

    def _find_name_matches(self, text: str) -> Iterator[PIIMatch]:
        """Find name PII matches."""
        for match in self._name_pattern.finditer(text):
            first_name = match.group(1)
            last_name = match.group(2)

            # Check if first name is a Pokemon
            if first_name.lower() in POKEMON_NAMES:
                continue

            # Build full name
            if last_name:
                full_name = f"{first_name} {last_name}"
                end_pos = match.end(2)
            else:
                full_name = first_name
                end_pos = match.end(1)

            yield PIIMatch(
                pii_type="name",
                original=full_name,
                start=match.start(1),
                end=end_pos,
            )

    def detect_pii(self, text: str) -> list[PIIMatch]:
        """Detect PII in text and return matches."""
        matches = list(self._find_pattern_matches(text))
        matches.extend(self._find_name_matches(text))
        return matches

    def filter_pii(self, text: str) -> str:
        """Remove PII from text, replacing with placeholders."""
        matches = self.detect_pii(text)

        if not matches:
            return text

        # Sort by position descending for safe replacement
        matches.sort(key=lambda m: m.start, reverse=True)

        result = text
        for match in matches:
            placeholder = PIIPatterns.PLACEHOLDERS.get(match.pii_type, "[REDACTED]")
            result = f"{result[: match.start]}{placeholder}{result[match.end :]}"

        return result

    def has_pii(self, text: str) -> bool:
        """Check if text contains any PII."""
        # Early exit on first match using iterator
        return (
            next(self._find_pattern_matches(text), None) is not None
            or next(self._find_name_matches(text), None) is not None
        )

    def get_pii_report(self, text: str) -> dict[str, Any]:
        """Get a report of PII found in text."""
        matches = self.detect_pii(text)

        return {
            "has_pii": len(matches) > 0,
            "pii_count": len(matches),
            "pii_types": list({m.pii_type for m in matches}),
            "matches": [{"type": m.pii_type, "position": (m.start, m.end)} for m in matches],
        }


# Module-level instance for convenience functions
_filter = PIIFilter()


def filter_pii(text: str) -> str:
    """Filter PII from text (convenience function)."""
    return _filter.filter_pii(text)


def has_pii(text: str) -> bool:
    """Check if text has PII (convenience function)."""
    return _filter.has_pii(text)


def detect_pii(text: str) -> list[PIIMatch]:
    """Detect PII in text (convenience function)."""
    return _filter.detect_pii(text)


def get_pii_report(text: str) -> dict[str, Any]:
    """Get PII report for text (convenience function)."""
    return _filter.get_pii_report(text)
