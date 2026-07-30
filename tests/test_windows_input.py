"""Tests for the testable part of the Windows input adapter."""

from dataclasses import replace
import unittest

from scitype.fraction import FRACTION_TEMPLATE, FractionStage
from scitype.input_state import (
    InputAction,
    InputState,
    KeyEvent,
    SymbolInputStateMachine,
)
from scitype.windows_input import (
    AdapterDecision,
    CursorPlacementError,
    InsertionOutcome,
    ModifierState,
    TextInsertionError,
    VK_A,
    VK_BACK,
    VK_CONTROL,
    VK_DOWN,
    VK_END,
    VK_ESCAPE,
    VK_HOME,
    VK_LEFT,
    VK_MENU,
    VK_NEXT,
    VK_OEM_2,
    VK_PRIOR,
    VK_Q,
    VK_RETURN,
    VK_RIGHT,
    VK_SPACE,
    VK_TAB,
    VK_UP,
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
    foreground_window: int | None = None,
) -> tuple[AdapterDecision, AdapterDecision]:
    """Press and release one physical key."""
    key_down = WindowsKeyEvent(
        vk_code,
        is_key_down=True,
        text=text,
        modifiers=modifiers or ModifierState(),
        foreground_window=foreground_window,
    )
    down_result = adapter.handle_event(key_down)
    up_result = adapter.handle_event(
        replace(key_down, is_key_down=False, text=None),
    )
    return down_result, up_result


def submit_fraction(
    adapter: WindowsInputAdapter,
    *,
    foreground_window: int = 101,
) -> AdapterDecision:
    """Submit /fs and mark its primary insertion as complete."""
    tap_key(adapter, VK_OEM_2, foreground_window=foreground_window)
    tap_key(adapter, 0x46, foreground_window=foreground_window)
    tap_key(adapter, 0x53, foreground_window=foreground_window)
    decision, _ = tap_key(
        adapter,
        VK_SPACE,
        foreground_window=foreground_window,
    )
    adapter.complete_insertion(decision, InsertionOutcome.PRIMARY)
    return decision


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
    def test_user_dictionary_flows_through_windows_adapter(self) -> None:
        adapter = WindowsInputAdapter(
            state_machine=SymbolInputStateMachine({"/my": "★"}),
        )

        tap_key(adapter, VK_OEM_2)
        tap_key(adapter, 0x4D)
        tap_key(adapter, 0x59)
        commit, commit_up = tap_key(adapter, VK_SPACE)

        self.assertEqual(commit.action, InputAction.INSERT_TEXT)
        self.assertEqual(commit.insert_text, "★")
        self.assertEqual(commit.fallback_text, "/my")
        self.assertEqual(commit_up.action, InputAction.CONSUME)
        self.assertEqual(adapter.state_machine.state, InputState.NORMAL)

    def test_matched_enter_is_fully_consumed_and_preserves_multiline_text(
        self,
    ) -> None:
        replacement = "第一段\n第二段\n第三段"
        adapter = WindowsInputAdapter(
            state_machine=SymbolInputStateMachine(
                {"/wzhl": replacement},
            ),
        )
        tap_key(adapter, VK_OEM_2)
        for vk_code in (0x57, 0x5A, 0x48, 0x4C):
            tap_key(adapter, vk_code)

        enter_event = WindowsKeyEvent(VK_RETURN, is_key_down=True)
        key_down = adapter.handle_event(enter_event)
        with adapter.injection_guard():
            key_up = adapter.handle_event(
                replace(enter_event, is_key_down=False),
            )
        inserted: list[str] = []
        outcome = insert_decision_text(key_down, inserted.append)
        next_enter_down, next_enter_up = tap_key(adapter, VK_RETURN)

        self.assertIs(key_down.action, InputAction.INSERT_TEXT)
        self.assertTrue(key_down.should_intercept)
        self.assertIs(key_up.action, InputAction.CONSUME)
        self.assertIs(outcome, InsertionOutcome.PRIMARY)
        self.assertEqual(inserted, [replacement])
        self.assertFalse(inserted[0].endswith("\n"))
        self.assertEqual(inserted[0].count("\n"), 2)
        self.assertIs(
            next_enter_down.action,
            InputAction.PASS_THROUGH,
        )
        self.assertIs(
            next_enter_up.action,
            InputAction.PASS_THROUGH,
        )

    def test_unknown_trigger_enter_keeps_existing_raw_fallback_behavior(
        self,
    ) -> None:
        adapter = WindowsInputAdapter(
            state_machine=SymbolInputStateMachine(
                {"/known": "已知"},
            ),
        )
        tap_key(adapter, VK_OEM_2)
        for vk_code in (VK_A, 0x42, 0x43):
            tap_key(adapter, vk_code)

        key_down, key_up = tap_key(adapter, VK_RETURN)

        self.assertIs(key_down.action, InputAction.INSERT_TEXT)
        self.assertEqual(key_down.insert_text, "/abc")
        self.assertEqual(key_down.fallback_text, "/abc")
        self.assertIs(key_up.action, InputAction.CONSUME)

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
        punctuation, punctuation_up = tap_key(
            adapter,
            0xBD,
            text="-",
        )

        self.assertEqual(punctuation.action, InputAction.INSERT_TEXT)
        self.assertEqual(punctuation.insert_text, "/x-")
        self.assertEqual(punctuation.fallback_text, "/x-")
        self.assertTrue(punctuation.should_intercept)
        self.assertEqual(punctuation_up.action, InputAction.CONSUME)

    def test_digit_trigger_flows_through_windows_adapter(self) -> None:
        adapter = WindowsInputAdapter(
            state_machine=SymbolInputStateMachine({"/x1": "数字命令"}),
        )

        tap_key(adapter, VK_OEM_2)
        tap_key(adapter, 0x58)
        tap_key(adapter, 0x31, text="1")
        commit, _ = tap_key(adapter, VK_SPACE)

        self.assertEqual(commit.action, InputAction.INSERT_TEXT)
        self.assertEqual(commit.insert_text, "数字命令")
        self.assertEqual(commit.fallback_text, "/x1")

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

    def test_fraction_insertion_starts_session_after_primary_success(
        self,
    ) -> None:
        adapter = WindowsInputAdapter()
        window = 101
        inserted: list[str] = []
        left_moves: list[int] = []

        tap_key(adapter, VK_OEM_2, foreground_window=window)
        tap_key(adapter, 0x46, foreground_window=window)
        tap_key(adapter, 0x53, foreground_window=window)
        decision, _ = tap_key(
            adapter,
            VK_SPACE,
            foreground_window=window,
        )
        outcome = insert_decision_text(
            decision,
            inserted.append,
            left_moves.append,
        )
        self.assertFalse(adapter.fraction_session.is_active)
        adapter.complete_insertion(decision, outcome)

        self.assertEqual(decision.insert_text, FRACTION_TEMPLATE)
        self.assertTrue(decision.start_fraction_session)
        self.assertEqual(inserted, ["()/()"])
        self.assertEqual(left_moves, [4])
        self.assertIs(outcome, InsertionOutcome.PRIMARY)
        self.assertTrue(adapter.fraction_session.is_active)
        self.assertEqual(
            adapter.fraction_session.stage,
            FractionStage.NUMERATOR,
        )

    def test_fraction_session_does_not_start_after_fallback(self) -> None:
        adapter = WindowsInputAdapter()
        window = 101
        tap_key(adapter, VK_OEM_2, foreground_window=window)
        tap_key(adapter, 0x46, foreground_window=window)
        tap_key(adapter, 0x53, foreground_window=window)
        decision, _ = tap_key(
            adapter,
            VK_SPACE,
            foreground_window=window,
        )

        adapter.complete_insertion(decision, InsertionOutcome.FALLBACK)

        self.assertFalse(adapter.fraction_session.is_active)

    def test_two_fraction_tabs_move_then_third_passes_through(self) -> None:
        adapter = WindowsInputAdapter()
        window = 101
        submit_fraction(adapter, foreground_window=window)

        first, first_up = tap_key(
            adapter,
            VK_TAB,
            foreground_window=window,
        )
        second, second_up = tap_key(
            adapter,
            VK_TAB,
            foreground_window=window,
        )
        third, third_up = tap_key(
            adapter,
            VK_TAB,
            foreground_window=window,
        )

        self.assertEqual(first.action, InputAction.CONSUME)
        self.assertEqual(first.cursor_right_moves, 3)
        self.assertEqual(first_up.action, InputAction.CONSUME)
        self.assertEqual(second.action, InputAction.CONSUME)
        self.assertEqual(second.cursor_right_moves, 1)
        self.assertEqual(second_up.action, InputAction.CONSUME)
        self.assertEqual(third.action, InputAction.PASS_THROUGH)
        self.assertEqual(third.cursor_right_moves, 0)
        self.assertEqual(third_up.action, InputAction.PASS_THROUGH)
        self.assertFalse(adapter.fraction_session.is_active)

    def test_tab_without_fraction_session_passes_through(self) -> None:
        adapter = WindowsInputAdapter()

        tab, tab_up = tap_key(
            adapter,
            VK_TAB,
            foreground_window=101,
        )

        self.assertEqual(tab.action, InputAction.PASS_THROUGH)
        self.assertEqual(tab_up.action, InputAction.PASS_THROUGH)

    def test_tab_auto_repeat_does_not_skip_fraction_stage(self) -> None:
        adapter = WindowsInputAdapter()
        window = 101
        submit_fraction(adapter, foreground_window=window)
        tab_down = WindowsKeyEvent(
            VK_TAB,
            is_key_down=True,
            foreground_window=window,
        )

        first = adapter.handle_event(tab_down)
        repeated = adapter.handle_event(tab_down)

        self.assertEqual(first.cursor_right_moves, 3)
        self.assertEqual(repeated.action, InputAction.CONSUME)
        self.assertEqual(repeated.cursor_right_moves, 0)
        self.assertEqual(
            adapter.fraction_session.stage,
            FractionStage.DENOMINATOR,
        )

    def test_escape_cancels_fraction_but_preserves_app_behavior(self) -> None:
        adapter = WindowsInputAdapter()
        window = 101
        submit_fraction(adapter, foreground_window=window)

        escape, escape_up = tap_key(
            adapter,
            VK_ESCAPE,
            foreground_window=window,
        )

        self.assertEqual(escape.action, InputAction.PASS_THROUGH)
        self.assertEqual(escape_up.action, InputAction.PASS_THROUGH)
        self.assertFalse(adapter.fraction_session.is_active)

    def test_navigation_keys_cancel_fraction_and_pass_through(self) -> None:
        navigation_keys = (
            VK_LEFT,
            VK_RIGHT,
            VK_UP,
            VK_DOWN,
            VK_HOME,
            VK_END,
            VK_PRIOR,
            VK_NEXT,
        )

        for vk_code in navigation_keys:
            with self.subTest(vk_code=vk_code):
                adapter = WindowsInputAdapter()
                window = 101
                submit_fraction(adapter, foreground_window=window)

                navigation, navigation_up = tap_key(
                    adapter,
                    vk_code,
                    foreground_window=window,
                )

                self.assertEqual(
                    navigation.action,
                    InputAction.PASS_THROUGH,
                )
                self.assertEqual(
                    navigation_up.action,
                    InputAction.PASS_THROUGH,
                )
                self.assertFalse(adapter.fraction_session.is_active)

    def test_foreground_window_change_cancels_fraction(self) -> None:
        adapter = WindowsInputAdapter()
        submit_fraction(adapter, foreground_window=101)

        normal_key, _ = tap_key(
            adapter,
            VK_A,
            foreground_window=202,
        )

        self.assertEqual(normal_key.action, InputAction.PASS_THROUGH)
        self.assertFalse(adapter.fraction_session.is_active)

    def test_backspace_and_normal_character_keep_session_active(self) -> None:
        adapter = WindowsInputAdapter()
        window = 101
        submit_fraction(adapter, foreground_window=window)

        letter, _ = tap_key(
            adapter,
            VK_A,
            foreground_window=window,
        )
        backspace, _ = tap_key(
            adapter,
            VK_BACK,
            foreground_window=window,
        )

        self.assertEqual(letter.action, InputAction.PASS_THROUGH)
        self.assertEqual(backspace.action, InputAction.PASS_THROUGH)
        self.assertTrue(adapter.fraction_session.is_active)

    def test_shift_tab_is_not_implemented_and_cancels_session(self) -> None:
        adapter = WindowsInputAdapter()
        window = 101
        submit_fraction(adapter, foreground_window=window)

        shifted_tab, shifted_tab_up = tap_key(
            adapter,
            VK_TAB,
            modifiers=ModifierState(shift=True),
            foreground_window=window,
        )

        self.assertEqual(shifted_tab.action, InputAction.PASS_THROUGH)
        self.assertEqual(shifted_tab_up.action, InputAction.PASS_THROUGH)
        self.assertFalse(adapter.fraction_session.is_active)

    def test_ctrl_alt_q_clears_fraction_session(self) -> None:
        adapter = WindowsInputAdapter()
        window = 101
        submit_fraction(adapter, foreground_window=window)

        adapter.handle_event(
            WindowsKeyEvent(
                VK_CONTROL,
                is_key_down=True,
                foreground_window=window,
            ),
        )
        adapter.handle_event(
            WindowsKeyEvent(
                VK_MENU,
                is_key_down=True,
                foreground_window=window,
            ),
        )
        quit_result = adapter.handle_event(
            WindowsKeyEvent(
                VK_Q,
                is_key_down=True,
                foreground_window=window,
            ),
        )

        self.assertTrue(quit_result.exit_requested)
        self.assertFalse(adapter.fraction_session.is_active)


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
