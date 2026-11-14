"""Strict ISO calendar dates shared by the CLI, HTTP boundary and activity parser."""

from datetime import date
import re


def parse_as_of(value: str) -> date:
    """Accept exactly YYYY-MM-DD, rejecting timestamps and invalid calendar dates."""
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("as_of must be a valid calendar date in YYYY-MM-DD format")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("as_of must be a valid calendar date in YYYY-MM-DD format") from exc
