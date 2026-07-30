"""Shared validation rules for SciType shortcut bindings."""

from __future__ import annotations

from enum import Enum, auto
import re

from .template import CURSOR_PLACEHOLDER


_TRIGGER_PATTERN = re.compile(r"^/(?:/|[a-z0-9]+)$")
_PLACEHOLDER_PATTERN = re.compile(r"\$\{[^{}]*\}")


class TriggerIssue(Enum):
    """Non-content trigger validation outcomes."""

    NOT_STRING = auto()
    EMPTY = auto()
    MISSING_SLASH = auto()
    INVALID_CHARACTERS = auto()


class ReplacementIssue(Enum):
    """Non-content replacement validation outcomes."""

    NOT_STRING = auto()
    EMPTY = auto()
    MULTIPLE_CURSOR_PLACEHOLDERS = auto()
    UNSUPPORTED_PLACEHOLDER = auto()


def is_trigger_body_character(value: object) -> bool:
    """Return whether one event can belong to a slash-command body."""
    return (
        isinstance(value, str)
        and len(value) == 1
        and ("a" <= value <= "z" or "0" <= value <= "9")
    )


def check_trigger(value: object) -> TriggerIssue | None:
    """Return a validation issue, or ``None`` for one supported trigger."""
    if not isinstance(value, str):
        return TriggerIssue.NOT_STRING
    if value == "":
        return TriggerIssue.EMPTY
    if not value.startswith("/"):
        return TriggerIssue.MISSING_SLASH
    if _TRIGGER_PATTERN.fullmatch(value) is None:
        return TriggerIssue.INVALID_CHARACTERS
    return None


def check_replacement(value: object) -> ReplacementIssue | None:
    """Return a validation issue for one static replacement string."""
    if not isinstance(value, str):
        return ReplacementIssue.NOT_STRING
    if value == "":
        return ReplacementIssue.EMPTY

    cursor_count = value.count(CURSOR_PLACEHOLDER)
    if cursor_count > 1:
        return ReplacementIssue.MULTIPLE_CURSOR_PLACEHOLDERS

    without_cursor = value.replace(CURSOR_PLACEHOLDER, "")
    if _PLACEHOLDER_PATTERN.search(without_cursor) is not None:
        return ReplacementIssue.UNSUPPORTED_PLACEHOLDER
    return None
