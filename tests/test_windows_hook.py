"""Focused tests for Win32 cursor-movement input construction."""

import ctypes
import sys
import unittest

from scitype.windows_hook import (
    KEYEVENTF_EXTENDEDKEY,
    KEYEVENTF_KEYUP,
    VK_LEFT,
    Win32KeyboardHook,
    _INPUT,
    _SCITYPE_EXTRA_INFO,
)


class _FakeUser32:
    def __init__(self) -> None:
        self.calls: list[tuple[int, list[tuple[int, int, int]], int]] = []

    def SendInput(
        self,
        event_count: int,
        input_events: ctypes.Array[_INPUT],
        input_size: int,
    ) -> int:
        events = [
            (
                input_events[index].ki.wVk,
                input_events[index].ki.dwFlags,
                input_events[index].ki.dwExtraInfo,
            )
            for index in range(event_count)
        ]
        self.calls.append((event_count, events, input_size))
        return event_count


@unittest.skipUnless(sys.platform == "win32", "requires Win32 ctypes")
class CursorMovementInputTests(unittest.TestCase):
    def test_left_moves_send_matching_key_down_and_up_pairs(self) -> None:
        hook = object.__new__(Win32KeyboardHook)
        fake_user32 = _FakeUser32()
        hook._user32 = fake_user32

        hook._send_left_keys(2)

        self.assertEqual(len(fake_user32.calls), 1)
        event_count, events, input_size = fake_user32.calls[0]
        self.assertEqual(event_count, 4)
        self.assertEqual(input_size, ctypes.sizeof(_INPUT))
        self.assertEqual(
            events,
            [
                (VK_LEFT, KEYEVENTF_EXTENDEDKEY, _SCITYPE_EXTRA_INFO),
                (
                    VK_LEFT,
                    KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP,
                    _SCITYPE_EXTRA_INFO,
                ),
                (VK_LEFT, KEYEVENTF_EXTENDEDKEY, _SCITYPE_EXTRA_INFO),
                (
                    VK_LEFT,
                    KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP,
                    _SCITYPE_EXTRA_INFO,
                ),
            ],
        )

    def test_zero_left_moves_send_no_input(self) -> None:
        hook = object.__new__(Win32KeyboardHook)
        fake_user32 = _FakeUser32()
        hook._user32 = fake_user32

        hook._send_left_keys(0)

        self.assertEqual(fake_user32.calls, [])

    def test_negative_left_moves_are_rejected(self) -> None:
        hook = object.__new__(Win32KeyboardHook)
        hook._user32 = _FakeUser32()

        with self.assertRaisesRegex(ValueError, "不能为负数"):
            hook._send_left_keys(-1)


if __name__ == "__main__":
    unittest.main()
