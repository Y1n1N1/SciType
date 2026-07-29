"""Testable Windows-key mapping and adapter decisions for SciType."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from enum import Enum, auto

from .fraction import FRACTION_TEMPLATE, FractionTabSession
from .input_state import (
    InputAction,
    InputState,
    KeyEvent,
    SymbolInputStateMachine,
)
from .template import render_template


VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_PRIOR = 0x21
VK_NEXT = 0x22
VK_END = 0x23
VK_HOME = 0x24
VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LMENU = 0xA4
VK_RMENU = 0xA5
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_A = 0x41
VK_Q = 0x51
VK_Z = 0x5A
VK_OEM_2 = 0xBF

_SHIFT_KEYS = frozenset((VK_SHIFT, VK_LSHIFT, VK_RSHIFT))
_CONTROL_KEYS = frozenset((VK_CONTROL, VK_LCONTROL, VK_RCONTROL))
_ALT_KEYS = frozenset((VK_MENU, VK_LMENU, VK_RMENU))
_WINDOWS_KEYS = frozenset((VK_LWIN, VK_RWIN))
_FRACTION_CANCEL_NAVIGATION_KEYS = frozenset(
    (
        VK_PRIOR,
        VK_NEXT,
        VK_END,
        VK_HOME,
        VK_LEFT,
        VK_UP,
        VK_RIGHT,
        VK_DOWN,
    ),
)


@dataclass(frozen=True, slots=True)
class ModifierState:
    """Modifier keys reported for one physical Windows keyboard event."""

    shift: bool = False
    control: bool = False
    alt: bool = False
    windows: bool = False


@dataclass(frozen=True, slots=True)
class WindowsKeyEvent:
    """Platform event data needed by the testable adapter."""

    vk_code: int
    is_key_down: bool
    is_scitype_injected: bool = False
    text: str | None = None
    modifiers: ModifierState = field(default_factory=ModifierState)
    foreground_window: int | None = None


@dataclass(frozen=True, slots=True)
class AdapterDecision:
    """Action the Win32 hook must take for the current physical event."""

    action: InputAction
    insert_text: str | None = None
    fallback_text: str | None = None
    cursor_right_moves: int = 0
    start_fraction_session: bool = False
    foreground_window: int | None = None
    exit_requested: bool = False

    @property
    def should_intercept(self) -> bool:
        """Whether the current physical event must be blocked."""
        return self.action is not InputAction.PASS_THROUGH


class InsertionOutcome(Enum):
    """Result of executing an INSERT_TEXT adapter decision."""

    PRIMARY = auto()
    FALLBACK = auto()


class TextInsertionError(RuntimeError):
    """Raised when neither replacement text nor raw text can be inserted."""


class CursorPlacementError(RuntimeError):
    """Raised when text was inserted but its cursor could not be positioned."""


def map_windows_key(event: WindowsKeyEvent) -> KeyEvent | str:
    """Map one key-down event to the existing state-machine event model."""
    modifiers = event.modifiers

    if modifiers.control or modifiers.alt or modifiers.windows:
        return KeyEvent.OTHER

    if event.vk_code == VK_OEM_2 and not modifiers.shift:
        return KeyEvent.SLASH
    if event.vk_code == VK_SPACE:
        return KeyEvent.SPACE
    if event.vk_code == VK_RETURN:
        return KeyEvent.ENTER
    if event.vk_code == VK_ESCAPE:
        return KeyEvent.ESC
    if event.vk_code == VK_BACK:
        return KeyEvent.BACKSPACE

    if VK_A <= event.vk_code <= VK_Z and not modifiers.shift:
        return chr(ord("a") + event.vk_code - VK_A)

    if event.text and event.text.isprintable():
        return event.text

    return KeyEvent.OTHER


class WindowsInputAdapter:
    """Bridge physical key events to ``SymbolInputStateMachine`` decisions."""

    def __init__(
        self,
        state_machine: SymbolInputStateMachine | None = None,
        fraction_session: FractionTabSession | None = None,
    ) -> None:
        self.state_machine = state_machine or SymbolInputStateMachine()
        self.fraction_session = fraction_session or FractionTabSession()
        self._keys_down: set[int] = set()
        self._suppressed_keys: set[int] = set()
        self._injection_depth = 0

    @property
    def is_injecting(self) -> bool:
        """Whether SciType is currently injecting replacement text."""
        return self._injection_depth > 0

    @contextmanager
    def injection_guard(self) -> Iterator[None]:
        """Temporarily bypass SciType processing for its own injected input."""
        self._injection_depth += 1
        try:
            yield
        finally:
            self._injection_depth -= 1

    def handle_event(self, event: WindowsKeyEvent) -> AdapterDecision:
        """Return the action required for one physical key event."""
        if event.is_scitype_injected or self.is_injecting:
            return AdapterDecision(InputAction.PASS_THROUGH)

        self.fraction_session.observe_foreground(event.foreground_window)

        if not event.is_key_down:
            self._keys_down.discard(event.vk_code)
            if event.vk_code in self._suppressed_keys:
                self._suppressed_keys.discard(event.vk_code)
                return AdapterDecision(InputAction.CONSUME)
            return AdapterDecision(InputAction.PASS_THROUGH)

        if event.vk_code in self._keys_down:
            # Auto-repeat is allowed for normal pass-through keys. A key whose
            # first press was consumed remains consumed but is not processed
            # by the state machine again.
            action = (
                InputAction.CONSUME
                if event.vk_code in self._suppressed_keys
                else InputAction.PASS_THROUGH
            )
            return AdapterDecision(action)

        self._keys_down.add(event.vk_code)
        event = replace(event, modifiers=self._effective_modifiers(event))

        if (
            event.vk_code == VK_Q
            and event.modifiers.control
            and event.modifiers.alt
        ):
            self.cancel_fraction_session()
            self._suppressed_keys.add(event.vk_code)
            return AdapterDecision(
                InputAction.CONSUME,
                exit_requested=True,
            )

        if event.vk_code == VK_ESCAPE:
            self.cancel_fraction_session()

        if event.vk_code in _FRACTION_CANCEL_NAVIGATION_KEYS:
            self.cancel_fraction_session()

        if event.vk_code == VK_TAB:
            if (
                event.modifiers.shift
                or event.modifiers.control
                or event.modifiers.alt
                or event.modifiers.windows
            ):
                self.cancel_fraction_session()
            else:
                tab_result = self.fraction_session.handle_tab(
                    event.foreground_window,
                )
                if tab_result.consume_tab:
                    self._suppressed_keys.add(event.vk_code)
                    return AdapterDecision(
                        InputAction.CONSUME,
                        cursor_right_moves=tab_result.cursor_right_moves,
                    )

        abstract_event = map_windows_key(event)
        state_before = self.state_machine.state
        buffer_before = self.state_machine.buffer
        result = self.state_machine.handle_event(abstract_event)

        fallback_text = None
        start_fraction_session = False
        if result.action is InputAction.INSERT_TEXT:
            fallback_text = self._raw_text_before_event(
                state_before,
                buffer_before,
                abstract_event,
            )
            self.cancel_fraction_session()
            start_fraction_session = (
                result.insert_text == FRACTION_TEMPLATE
            )

        decision = AdapterDecision(
            action=result.action,
            insert_text=result.insert_text,
            fallback_text=fallback_text,
            start_fraction_session=start_fraction_session,
            foreground_window=event.foreground_window,
        )
        if decision.should_intercept:
            self._suppressed_keys.add(event.vk_code)
        return decision

    def complete_insertion(
        self,
        decision: AdapterDecision,
        outcome: InsertionOutcome,
    ) -> None:
        """Start the fraction session only after successful primary insertion."""
        if (
            decision.start_fraction_session
            and outcome is InsertionOutcome.PRIMARY
        ):
            self.fraction_session.start(decision.foreground_window)

    def cancel_fraction_session(self) -> None:
        """Cancel pending Tab jumps without inspecting or changing text."""
        self.fraction_session.cancel()

    def _effective_modifiers(self, event: WindowsKeyEvent) -> ModifierState:
        modifiers = event.modifiers
        return ModifierState(
            shift=modifiers.shift or bool(self._keys_down & _SHIFT_KEYS),
            control=modifiers.control or bool(self._keys_down & _CONTROL_KEYS),
            alt=modifiers.alt or bool(self._keys_down & _ALT_KEYS),
            windows=modifiers.windows or bool(self._keys_down & _WINDOWS_KEYS),
        )

    @staticmethod
    def _raw_text_before_event(
        state_before: InputState,
        buffer_before: str,
        event: KeyEvent | str,
    ) -> str | None:
        if state_before is not InputState.SYMBOL:
            return None

        raw_text = f"/{buffer_before}"
        if event is KeyEvent.SLASH:
            return f"{raw_text}/"
        if isinstance(event, str):
            return f"{raw_text}{event}"
        return raw_text


def insert_decision_text(
    decision: AdapterDecision,
    inserter: Callable[[str], None],
    cursor_mover: Callable[[int], None] | None = None,
) -> InsertionOutcome:
    """Render and insert text, then move the cursor or restore raw input."""
    if (
        decision.action is not InputAction.INSERT_TEXT
        or decision.insert_text is None
    ):
        raise ValueError("只有 INSERT_TEXT 决策可以执行文本插入")

    try:
        rendered = render_template(decision.insert_text)
        inserter(rendered.text)
    except Exception as primary_error:
        if decision.fallback_text is None:
            raise TextInsertionError("替换文本插入失败，且没有可恢复的原始文本") from primary_error

        try:
            inserter(decision.fallback_text)
        except Exception as fallback_error:
            raise TextInsertionError("替换文本和原始文本均无法插入") from fallback_error
        return InsertionOutcome.FALLBACK

    if rendered.cursor_left_moves > 0:
        if cursor_mover is None:
            raise CursorPlacementError(
                "文本已插入，但没有可用的光标移动实现",
            )
        try:
            cursor_mover(rendered.cursor_left_moves)
        except Exception as cursor_error:
            raise CursorPlacementError(
                "文本已插入，但光标移动失败",
            ) from cursor_error

    return InsertionOutcome.PRIMARY
