"""Tests for the fixed two-step V0.5a fraction Tab session."""

import unittest

from scitype.fraction import (
    FIRST_TAB_RIGHT_MOVES,
    SECOND_TAB_RIGHT_MOVES,
    FractionStage,
    FractionTabSession,
)


class FractionTabSessionTests(unittest.TestCase):
    def test_first_and_second_tabs_move_then_end_session(self) -> None:
        session = FractionTabSession()

        self.assertTrue(session.start(101))
        first = session.handle_tab(101)
        second = session.handle_tab(101)
        third = session.handle_tab(101)

        self.assertTrue(first.consume_tab)
        self.assertEqual(first.cursor_right_moves, FIRST_TAB_RIGHT_MOVES)
        self.assertTrue(first.session_active)
        self.assertTrue(second.consume_tab)
        self.assertEqual(second.cursor_right_moves, SECOND_TAB_RIGHT_MOVES)
        self.assertFalse(second.session_active)
        self.assertFalse(third.consume_tab)
        self.assertEqual(third.cursor_right_moves, 0)
        self.assertEqual(session.stage, FractionStage.INACTIVE)

    def test_session_requires_a_foreground_window(self) -> None:
        session = FractionTabSession()

        self.assertFalse(session.start(None))
        self.assertFalse(session.is_active)
        self.assertFalse(session.handle_tab(None).consume_tab)

    def test_cancel_preserves_only_in_memory_session_state(self) -> None:
        session = FractionTabSession()
        session.start(101)

        session.cancel()

        self.assertFalse(session.is_active)
        self.assertEqual(session.stage, FractionStage.INACTIVE)
        self.assertFalse(session.handle_tab(101).consume_tab)

    def test_foreground_window_change_cancels_session(self) -> None:
        session = FractionTabSession()
        session.start(101)

        self.assertFalse(session.observe_foreground(202))
        self.assertFalse(session.is_active)
        self.assertFalse(session.handle_tab(202).consume_tab)


if __name__ == "__main__":
    unittest.main()
