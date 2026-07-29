"""Minimal two-step Tab session for the V0.5a fraction experiment."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


FRACTION_TEMPLATE = "(${cursor})/()"
FIRST_TAB_RIGHT_MOVES = 3
SECOND_TAB_RIGHT_MOVES = 1


class FractionStage(Enum):
    """The only two cursor slots supported by the fraction experiment."""

    INACTIVE = auto()
    NUMERATOR = auto()
    DENOMINATOR = auto()


@dataclass(frozen=True, slots=True)
class FractionTabResult:
    """Whether to consume Tab and how far to move the real cursor."""

    consume_tab: bool
    cursor_right_moves: int = 0
    session_active: bool = False


class FractionTabSession:
    """Track two fixed Tab jumps without inspecting user-entered formula text."""

    def __init__(self) -> None:
        self._stage = FractionStage.INACTIVE
        self._foreground_window: int | None = None

    @property
    def stage(self) -> FractionStage:
        """Return the current fixed fraction slot."""
        return self._stage

    @property
    def is_active(self) -> bool:
        """Whether one or two fraction jumps are still available."""
        return self._stage is not FractionStage.INACTIVE

    def start(self, foreground_window: int | None) -> bool:
        """Start only when a stable foreground-window token is available."""
        if foreground_window is None:
            self.cancel()
            return False

        self._foreground_window = foreground_window
        self._stage = FractionStage.NUMERATOR
        return True

    def cancel(self) -> None:
        """End the session without changing text in the target application."""
        self._stage = FractionStage.INACTIVE
        self._foreground_window = None

    def observe_foreground(self, foreground_window: int | None) -> bool:
        """Cancel if focus left the window that received the fraction."""
        if not self.is_active:
            return False
        if (
            foreground_window is None
            or foreground_window != self._foreground_window
        ):
            self.cancel()
            return False
        return True

    def handle_tab(self, foreground_window: int | None) -> FractionTabResult:
        """Consume at most two Tabs in the original foreground window."""
        if not self.observe_foreground(foreground_window):
            return FractionTabResult(consume_tab=False)

        if self._stage is FractionStage.NUMERATOR:
            self._stage = FractionStage.DENOMINATOR
            return FractionTabResult(
                consume_tab=True,
                cursor_right_moves=FIRST_TAB_RIGHT_MOVES,
                session_active=True,
            )

        self.cancel()
        return FractionTabResult(
            consume_tab=True,
            cursor_right_moves=SECOND_TAB_RIGHT_MOVES,
            session_active=False,
        )
