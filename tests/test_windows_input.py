"""Tests for the testable part of the Windows input adapter."""

from dataclasses import replace
import unittest

from scitype.input_state import InputAction, InputState, KeyEvent
from scitype.windows_input import (
    AdapterDecision,
    CursorPlacementError,
    InsertionOutcome,
    ModifierState,
    TextInsertionError,
    VK_A,
    VK_BACK,
    VK_CONTROL,
    VK_ESCAPE,
    VK_MENU,
    VK_OEM_2,
    VK_Q,
    VK_RETURN,
    VK_SPACE,
    VK_Z,
    WindowsInputAdapter,
    WindowsKeyEvent,
    insert_decision_text,
    map_windows_key,
)


def tap_key(
    adapter: WindowsInputAdapter,
    vk_code: int,
    *,
    text: str | None = None,
    modifiers: ModifierState | None = None,
) -> tuple[AdapterDecision, AdapterDecision]:
    """Press and release one physical key."""
    key_down = WindowsKeyEvent(
        vk_code,
        is_key_down=True,
        text=text,
        modifiers=modifiers or ModifierState(),
    )
    down_result = adapter.handle_event(key_down)
    up_result = adapter.handle_event(
        replace(key_down, is_key_down=False, text=None),
    )
    return down_result, up_result


class WindowsKeyMappingTests(unittest.TestCase):
    def test_letters_map_to_lowercase_strings(self) -> None:
        for vk_code in range(VK_A, VK_Z + 1):
            with self.subTest(vk_code=vk_code):
                event = WindowsKeyEvent(vk_code, is_key_down=True)

                self.assertEqual(
                    map_windows_key(event),
                    chr(ord("a") + vk_code - VK_A),
                )

    def test_named_keys_map_to_state_machine_events(self) -> None:
        cases = [
            (VK_OEM_2, KeyEvent.SLASH),
            (VK_SPACE, KeyEvent.SPACE),
            (VK_RETURN, KeyEvent.ENTER),
            (VK_ESCAPE, KeyEvent.ESC),
            (VK_BACK, KeyEvent.BACKSPACE),
        ]

        for vk_code, expected in cases:
            with self.subTest(vk_code=vk_code):
                event = WindowsKeyEvent(vk_code, is_key_down=True)

                self.assertEqual(map_windows_key(event), expected)

    def test_printable_unsupported_key_uses_translated_text(self) -> None:
        digit = WindowsKeyEvent(0x31, is_key_down=True, text="1")
        punctuation = WindowsKeyEvent(0xBD, is_key_down=True, text="-")

        self.assertEqual(map_windows_key(digit), "1")
        self.assertEqual(map_windows_key(punctuation), "-")

    def test_unknown_non_text_key_maps_to_other(self) -> None:
        f1_key = WindowsKeyEvent(0x70, is_key_down=True)

        self.assertIs(map_windows_key(f1_key), KeyEvent.OTHER)

    def test_modified_key_is_not_treated_as_command_letter(self) -> None:
        shifted_x = WindowsKeyEvent(
            0x58,
            is_key_down=True,
            text="X",
            modifiers=ModifierState(shift=True),
        )

        self.assertEqual(map_windows_key(shifted_x), "X")


class WindowsInputAdapterTests(unittest.TestCase):
    def test_pass_consume_and_insert_actions(self) -> None:
        adapter = WindowsInputAdapter()

        normal_letter, _ = tap_key(adapter, VK_A)
        slash, slash_up = tap_key(adapter, VK_OEM_2)
        tap_key(adapter, 0x58)
        tap_key(adapter, 0x57)
        commit, commit_up = tap_key(adapter, VK_SPACE)

        self.assertEqual(normal_letter.action, InputAction.PASS_THROUGH)
        self.assertEqual(slash.action, InputAction.CONSUME)
        self.assertEqual(slash_up.action, InputAction.CONSUME)
        self.assertEqual(commit.action, InputAction.INSERT_TEXT)
        self.assertEqual(commit.insert_text, "φ")
        self.assertEqual(commit.fallback_text, "/xw")
        self.assertEqual(commit_up.action, InputAction.CONSUME)
        self.assertEqual(adapter.state_machine.state, InputState.NORMAL)

    def test_printable_fallback_is_inserted_once(self) -> None:
        adapter = WindowsInputAdapter()

        tap_key(adapter, VK_OEM_2)
        tap_key(adapter, 0x58)
        digit, digit_up = tap_key(adapter, 0x31, text="1")

        self.assertEqual(digit.action, InputAction.INSERT_TEXT)
        self.assertEqual(digit.insert_text, "/x1")
        self.assertEqual(digit.fallback_text, "/x1")
        self.assertTrue(digit.should_intercept)
        self.assertEqual(digit_up.action, InputAction.CONSUME)

    def test_adapter_integrates_absolute_value_and_literal_slash(self) -> None:
        adapter = WindowsInputAdapter()

        tap_key(adapter, VK_OEM_2)
        for vk_code in (0x4A, 0x44, 0x5A):
            tap_key(adapter, vk_code)
        absolute_value, _ = tap_key(adapter, VK_SPACE)

        tap_key(adapter, VK_OEM_2)
        literal_slash, _ = tap_key(adapter, VK_OEM_2)

        self.assertEqual(absolute_value.insert_text, "|${cursor}|")
        self.assertEqual(absolute_value.fallback_text, "/jdz")
        self.assertEqual(literal_slash.insert_text, "/")
        self.assertEqual(literal_slash.fallback_text, "//")
        self.assertEqual(adapter.state_machine.state, InputState.NORMAL)

    def test_injection_guard_bypasses_state_machine(self) -> None:
        adapter = WindowsInputAdapter()
        slash = WindowsKeyEvent(VK_OEM_2, is_key_down=True)

        with adapter.injection_guard():
            result = adapter.handle_event(slash)

        self.assertEqual(result.action, InputAction.PASS_THROUGH)
        self.assertEqual(adapter.state_machine.state, InputState.NORMAL)
        self.assertFalse(adapter.is_injecting)

    def test_scitype_injected_event_bypasses_state_machine(self) -> None:
        adapter = WindowsInputAdapter()
        event = WindowsKeyEvent(
            VK_OEM_2,
            is_key_down=True,
            is_scitype_injected=True,
        )

        result = adapter.handle_event(event)

        self.assertEqual(result.action, InputAction.PASS_THROUGH)
        self.assertEqual(adapter.state_machine.state, InputState.NORMAL)

    def test_consumed_auto_repeat_is_not_processed_twice(self) -> None:
        adapter = WindowsInputAdapter()
        slash_down = WindowsKeyEvent(VK_OEM_2, is_key_down=True)

        first = adapter.handle_event(slash_down)
        repeated = adapter.handle_event(slash_down)

        self.assertEqual(first.action, InputAction.CONSUME)
        self.assertEqual(repeated.action, InputAction.CONSUME)
        self.assertEqual(adapter.state_machine.state, InputState.SYMBOL)
        self.assertFalse(repeated.insert_text)

    def test_ctrl_alt_q_requests_emergency_exit(self) -> None:
        adapter = WindowsInputAdapter()

        control = adapter.handle_event(
            WindowsKeyEvent(VK_CONTROL, is_key_down=True),
        )
        alt = adapter.handle_event(
            WindowsKeyEvent(VK_MENU, is_key_down=True),
        )
        quit_result = adapter.handle_event(
            WindowsKeyEvent(VK_Q, is_key_down=True),
        )

        self.assertEqual(control.action, InputAction.PASS_THROUGH)
        self.assertEqual(alt.action, InputAction.PASS_THROUGH)
        self.assertEqual(quit_result.action, InputAction.CONSUME)
        self.assertTrue(quit_result.exit_requested)


class TextInsertionTests(unittest.TestCase):
    def test_primary_text_is_inserted(self) -> None:
        inserted: list[str] = []
        decision = AdapterDecision(
            InputAction.INSERT_TEXT,
            insert_text="φ",
            fallback_text="/xw",
        )

        outcome = insert_decision_text(decision, inserted.append)

        self.assertIs(outcome, InsertionOutcome.PRIMARY)
        self.assertEqual(inserted, ["φ"])

    def test_raw_text_is_retried_after_replacement_failure(self) -> None:
        attempts: list[str] = []
        decision = AdapterDecision(
            InputAction.INSERT_TEXT,
            insert_text="φ",
            fallback_text="/xw",
        )

        def fail_replacement_once(text: str) -> None:
            attempts.append(text)
            if len(attempts) == 1:
                raise OSError("simulated primary failure")

        outcome = insert_decision_text(decision, fail_replacement_once)

        self.assertIs(outcome, InsertionOutcome.FALLBACK)
        self.assertEqual(attempts, ["φ", "/xw"])

    def test_double_insertion_failure_is_reported(self) -> None:
        decision = AdapterDecision(
            InputAction.INSERT_TEXT,
            insert_text="φ",
            fallback_text="/xw",
        )

        def always_fail(text: str) -> None:
            raise OSError("simulated failure")

        with self.assertRaises(TextInsertionError):
            insert_decision_text(decision, always_fail)

    def test_template_is_inserted_before_cursor_movement_under_guard(
        self,
    ) -> None:
        adapter = WindowsInputAdapter()
        operations: list[tuple[str, object, bool]] = []
        recursive_actions: list[InputAction] = []
        decision = AdapterDecision(
            InputAction.INSERT_TEXT,
            insert_text="∫${cursor}dx",
            fallback_text="/jf",
        )

        def insert_text(text: str) -> None:
            operations.append(("insert", text, adapter.is_injecting))
            recursive_actions.append(
                adapter.handle_event(
                    WindowsKeyEvent(VK_OEM_2, is_key_down=True),
                ).action,
            )

        def move_cursor(left_moves: int) -> None:
            operations.append(("left", left_moves, adapter.is_injecting))
            recursive_actions.append(
                adapter.handle_event(
                    WindowsKeyEvent(VK_OEM_2, is_key_down=True),
                ).action,
            )

        with adapter.injection_guard():
            outcome = insert_decision_text(
                decision,
                insert_text,
                move_cursor,
            )

        self.assertIs(outcome, InsertionOutcome.PRIMARY)
        self.assertEqual(
            operations,
            [
                ("insert", "∫dx", True),
                ("left", 2, True),
            ],
        )
        self.assertEqual(
            recursive_actions,
            [InputAction.PASS_THROUGH, InputAction.PASS_THROUGH],
        )
        self.assertFalse(adapter.is_injecting)
        self.assertEqual(adapter.state_machine.state, InputState.NORMAL)

    def test_template_failure_restores_raw_command(self) -> None:
        inserted: list[str] = []
        cursor_moves: list[int] = []
        decision = AdapterDecision(
            InputAction.INSERT_TEXT,
            insert_text="${cursor}${cursor}",
            fallback_text="/bad",
        )

        outcome = insert_decision_text(
            decision,
            inserted.append,
            cursor_moves.append,
        )

        self.assertIs(outcome, InsertionOutcome.FALLBACK)
        self.assertEqual(inserted, ["/bad"])
        self.assertEqual(cursor_moves, [])

    def test_cursor_movement_failure_is_reported_without_fallback(self) -> None:
        inserted: list[str] = []
        decision = AdapterDecision(
            InputAction.INSERT_TEXT,
            insert_text="|${cursor}|",
            fallback_text="/jdz",
        )

        def fail_cursor_movement(left_moves: int) -> None:
            raise OSError("simulated cursor failure")

        with self.assertRaisesRegex(
            CursorPlacementError,
            "文本已插入.*光标移动失败",
        ):
            insert_decision_text(
                decision,
                inserted.append,
                fail_cursor_movement,
            )

        self.assertEqual(inserted, ["||"])


if __name__ == "__main__":
    unittest.main()
