"""Tests for the operating-system-independent V0.2a input state."""

import unittest

from scitype.input_state import (
    InputAction,
    InputResult,
    InputState,
    KeyEvent,
    SymbolInputStateMachine,
)


def run_events(
    machine: SymbolInputStateMachine,
    events: list[KeyEvent | str],
) -> list[InputResult]:
    """Process a sequence of abstract events in order."""
    return [machine.handle_event(event) for event in events]


class SymbolInputStateMachineTests(unittest.TestCase):
    def test_legacy_phi_alias_commits_on_space(self) -> None:
        machine = SymbolInputStateMachine()

        results = run_events(
            machine,
            [KeyEvent.SLASH, "x", "w", KeyEvent.SPACE],
        )

        self.assertTrue(all(result.should_intercept for result in results))
        self.assertEqual(results[-1].action, InputAction.INSERT_TEXT)
        self.assertEqual(results[-1].insert_text, "φ")
        self.assertEqual(machine.state, InputState.NORMAL)
        self.assertEqual(machine.buffer, "")

    def test_absolute_value_command_commits_on_enter(self) -> None:
        machine = SymbolInputStateMachine()

        result = run_events(
            machine,
            [KeyEvent.SLASH, "j", "d", "z", KeyEvent.ENTER],
        )[-1]

        self.assertTrue(result.should_insert)
        self.assertEqual(result.insert_text, "|${cursor}|")
        self.assertEqual(result.state, InputState.NORMAL)
        self.assertEqual(machine.buffer, "")

    def test_unknown_command_is_inserted_unchanged(self) -> None:
        machine = SymbolInputStateMachine()

        result = run_events(
            machine,
            [KeyEvent.SLASH, "a", "b", "c", KeyEvent.SPACE],
        )[-1]

        self.assertEqual(result.action, InputAction.INSERT_TEXT)
        self.assertEqual(result.insert_text, "/abc")
        self.assertEqual(machine.state, InputState.NORMAL)

    def test_double_slash_inserts_literal_slash(self) -> None:
        machine = SymbolInputStateMachine()

        result = run_events(
            machine,
            [KeyEvent.SLASH, KeyEvent.SLASH],
        )[-1]

        self.assertEqual(result.action, InputAction.INSERT_TEXT)
        self.assertEqual(result.insert_text, "/")
        self.assertEqual(machine.state, InputState.NORMAL)
        self.assertEqual(machine.buffer, "")

    def test_escape_cancels_symbol_input(self) -> None:
        machine = SymbolInputStateMachine()

        result = run_events(
            machine,
            [KeyEvent.SLASH, "x", "w", KeyEvent.ESC],
        )[-1]

        self.assertEqual(result.action, InputAction.CONSUME)
        self.assertFalse(result.should_insert)
        self.assertIsNone(result.insert_text)
        self.assertEqual(machine.state, InputState.NORMAL)
        self.assertEqual(machine.buffer, "")

    def test_backspace_edits_buffer_before_commit(self) -> None:
        machine = SymbolInputStateMachine()

        run_events(
            machine,
            [KeyEvent.SLASH, "x", "w"],
        )
        backspace_result = machine.handle_event(KeyEvent.BACKSPACE)

        self.assertEqual(backspace_result.state, InputState.SYMBOL)
        self.assertEqual(machine.buffer, "x")

        commit_result = machine.handle_event(KeyEvent.SPACE)

        self.assertEqual(commit_result.insert_text, "/x")
        self.assertEqual(machine.state, InputState.NORMAL)
        self.assertEqual(machine.buffer, "")

    def test_backspace_on_empty_buffer_exits_symbol_state(self) -> None:
        machine = SymbolInputStateMachine()

        result = run_events(
            machine,
            [KeyEvent.SLASH, KeyEvent.BACKSPACE],
        )[-1]

        self.assertEqual(result.action, InputAction.CONSUME)
        self.assertFalse(result.should_insert)
        self.assertEqual(machine.state, InputState.NORMAL)
        self.assertEqual(machine.buffer, "")

    def test_two_commands_do_not_share_buffer_state(self) -> None:
        machine = SymbolInputStateMachine()

        first = run_events(
            machine,
            [KeyEvent.SLASH, "x", "w", KeyEvent.SPACE],
        )[-1]
        self.assertEqual(machine.buffer, "")

        second = run_events(
            machine,
            [KeyEvent.SLASH, "j", "f", KeyEvent.SPACE],
        )[-1]

        self.assertEqual(first.insert_text, "φ")
        self.assertEqual(second.insert_text, "∫${cursor}dx")
        self.assertEqual(machine.state, InputState.NORMAL)
        self.assertEqual(machine.buffer, "")

    def test_normal_letter_is_passed_through(self) -> None:
        machine = SymbolInputStateMachine()

        result = machine.handle_event("a")

        self.assertEqual(result.action, InputAction.PASS_THROUGH)
        self.assertFalse(result.should_intercept)
        self.assertFalse(result.should_insert)
        self.assertIsNone(result.insert_text)
        self.assertEqual(machine.state, InputState.NORMAL)
        self.assertEqual(machine.buffer, "")

    def test_buffer_is_empty_after_all_terminal_transitions(self) -> None:
        sequences = [
            [KeyEvent.SLASH, "x", "w", KeyEvent.SPACE],
            [KeyEvent.SLASH, "x", KeyEvent.ESC],
            [KeyEvent.SLASH, KeyEvent.SLASH],
        ]

        for events in sequences:
            with self.subTest(events=events):
                machine = SymbolInputStateMachine()
                run_events(machine, events)

                self.assertEqual(machine.state, InputState.NORMAL)
                self.assertEqual(machine.buffer, "")

    def test_repeated_backspace_follows_each_state_rule(self) -> None:
        machine = SymbolInputStateMachine()

        results = run_events(
            machine,
            [
                KeyEvent.SLASH,
                "x",
                KeyEvent.BACKSPACE,
                KeyEvent.BACKSPACE,
                KeyEvent.BACKSPACE,
            ],
        )
        enter_symbol, add_letter, remove_letter, exit_symbol, pass_normal = results

        self.assertEqual(enter_symbol.state, InputState.SYMBOL)
        self.assertEqual(add_letter.state, InputState.SYMBOL)
        self.assertEqual(remove_letter.state, InputState.SYMBOL)
        self.assertEqual(exit_symbol.action, InputAction.CONSUME)
        self.assertEqual(exit_symbol.state, InputState.NORMAL)
        self.assertEqual(pass_normal.action, InputAction.PASS_THROUGH)
        self.assertEqual(machine.buffer, "")

    def test_digit_restores_pending_text_without_duplication(self) -> None:
        machine = SymbolInputStateMachine()

        result = run_events(
            machine,
            [KeyEvent.SLASH, "x", "1"],
        )[-1]

        self.assertEqual(result.action, InputAction.INSERT_TEXT)
        self.assertTrue(result.should_intercept)
        self.assertEqual(result.insert_text, "/x1")
        self.assertEqual(result.insert_text.count("1"), 1)
        self.assertEqual(result.state, InputState.NORMAL)
        self.assertEqual(machine.buffer, "")

    def test_punctuation_restores_pending_text_without_duplication(self) -> None:
        machine = SymbolInputStateMachine()

        result = run_events(
            machine,
            [KeyEvent.SLASH, "a", "b", "-"],
        )[-1]

        self.assertEqual(result.action, InputAction.INSERT_TEXT)
        self.assertTrue(result.should_intercept)
        self.assertEqual(result.insert_text, "/ab-")
        self.assertEqual(result.insert_text.count("-"), 1)
        self.assertEqual(result.state, InputState.NORMAL)
        self.assertEqual(machine.buffer, "")

    def test_slash_after_buffer_is_restored_as_text(self) -> None:
        machine = SymbolInputStateMachine()

        result = run_events(
            machine,
            [KeyEvent.SLASH, "x", KeyEvent.SLASH],
        )[-1]

        self.assertEqual(result.action, InputAction.INSERT_TEXT)
        self.assertTrue(result.should_intercept)
        self.assertEqual(result.insert_text, "/x/")
        self.assertEqual(result.state, InputState.NORMAL)
        self.assertEqual(machine.buffer, "")

    def test_non_text_event_restores_prefix_and_is_consumed(self) -> None:
        machine = SymbolInputStateMachine()

        result = run_events(
            machine,
            [KeyEvent.SLASH, "x", KeyEvent.OTHER],
        )[-1]

        self.assertEqual(result.action, InputAction.INSERT_TEXT)
        self.assertTrue(result.should_intercept)
        self.assertEqual(result.insert_text, "/x")
        self.assertEqual(result.state, InputState.NORMAL)
        self.assertEqual(machine.buffer, "")


if __name__ == "__main__":
    unittest.main()
