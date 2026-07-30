"""Operating-system-independent symbol input state machine."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum, auto

from .binding_rules import is_trigger_body_character
from .engine import parse_text


class InputState(Enum):
    """States supported by the V0.2a input core."""

    NORMAL = auto()
    SYMBOL = auto()


class KeyEvent(Enum):
    """Abstract non-letter key events understood by the state machine."""

    SLASH = auto()
    SPACE = auto()
    ENTER = auto()
    ESC = auto()
    BACKSPACE = auto()
    OTHER = auto()


class InputAction(Enum):
    """What an eventual keyboard adapter should do with the current event."""

    PASS_THROUGH = auto()
    CONSUME = auto()
    INSERT_TEXT = auto()


@dataclass(frozen=True, slots=True)
class InputResult:
    """Result returned after one abstract key event is processed."""

    action: InputAction
    state: InputState
    insert_text: str | None = None

    @property
    def should_intercept(self) -> bool:
        """Whether the current key event should be hidden from the target app."""
        return self.action is not InputAction.PASS_THROUGH

    @property
    def should_insert(self) -> bool:
        """Whether ``insert_text`` should be inserted into the target app."""
        return self.action is InputAction.INSERT_TEXT


class SymbolInputStateMachine:
    """Collect one slash command while temporarily in SYMBOL state."""

    def __init__(
        self,
        dictionary: Mapping[str, str] | None = None,
    ) -> None:
        self.state = InputState.NORMAL
        self._buffer = ""
        self._dictionary = (
            None if dictionary is None else dict(dictionary)
        )

    @property
    def buffer(self) -> str:
        """Return the currently collected abbreviation characters."""
        return self._buffer

    def handle_event(self, event: KeyEvent | str) -> InputResult:
        """Process one abstract event and return the required action."""
        if self.state is InputState.NORMAL:
            return self._handle_normal(event)
        return self._handle_symbol(event)

    def _handle_normal(self, event: KeyEvent | str) -> InputResult:
        if event is KeyEvent.SLASH:
            self.state = InputState.SYMBOL
            self._buffer = ""
            return self._result(InputAction.CONSUME)

        return self._result(InputAction.PASS_THROUGH)

    def _handle_symbol(self, event: KeyEvent | str) -> InputResult:
        if is_trigger_body_character(event):
            assert isinstance(event, str)
            self._buffer += event
            return self._result(InputAction.CONSUME)

        if event is KeyEvent.SLASH and not self._buffer:
            return self._commit("//")

        if event in (KeyEvent.SPACE, KeyEvent.ENTER):
            return self._commit(f"/{self._buffer}")

        if event is KeyEvent.BACKSPACE:
            if self._buffer:
                self._buffer = self._buffer[:-1]
            else:
                self._reset()
            return self._result(InputAction.CONSUME)

        if event is KeyEvent.ESC:
            self._reset()
            return self._result(InputAction.CONSUME)

        event_text = self._event_text(event)
        if event_text is not None:
            return self._restore_pending_text(event_text)

        # A non-text event cannot be reproduced by this abstract model. Restore
        # the printable prefix already consumed, and explicitly consume the
        # current event instead of silently losing the prefix.
        return self._restore_pending_text()

    def _commit(self, command: str) -> InputResult:
        output = parse_text(command, self._dictionary)
        self._reset()
        return self._result(InputAction.INSERT_TEXT, output)

    def _restore_pending_text(self, event_text: str = "") -> InputResult:
        output = f"/{self._buffer}{event_text}"
        self._reset()
        return self._result(InputAction.INSERT_TEXT, output)

    def _reset(self) -> None:
        self.state = InputState.NORMAL
        self._buffer = ""

    def _result(
        self,
        action: InputAction,
        insert_text: str | None = None,
    ) -> InputResult:
        return InputResult(
            action=action,
            state=self.state,
            insert_text=insert_text,
        )

    @staticmethod
    def _event_text(event: KeyEvent | str) -> str | None:
        if isinstance(event, str):
            return event
        if event is KeyEvent.SLASH:
            return "/"
        return None
