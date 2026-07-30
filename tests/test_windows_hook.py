"""Focused tests for Win32 cursor-movement input construction."""

import ctypes
import sys
import unittest
from unittest.mock import patch

from scitype.windows_hook import (
    HC_ACTION,
    KEYEVENTF_EXTENDEDKEY,
    KEYEVENTF_KEYUP,
    KEYEVENTF_UNICODE,
    VK_LEFT,
    VK_RETURN,
    VK_RIGHT,
    WM_LBUTTONDOWN,
    Win32KeyboardHook,
    _ARROW_EVENT_INTERVAL_SECONDS,
    _INPUT,
    _SCITYPE_EXTRA_INFO,
    _TEXT_COMMIT_SETTLE_SECONDS,
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


class _DetailedFakeUser32:
    def __init__(self) -> None:
        self.calls: list[
            tuple[int, list[tuple[int, int, int, int]], int]
        ] = []

    def SendInput(
        self,
        event_count: int,
        input_events: ctypes.Array[_INPUT],
        input_size: int,
    ) -> int:
        events = [
            (
                input_events[index].ki.wVk,
                input_events[index].ki.wScan,
                input_events[index].ki.dwFlags,
                input_events[index].ki.dwExtraInfo,
            )
            for index in range(event_count)
        ]
        self.calls.append((event_count, events, input_size))
        return event_count


class _FakeMouseUser32:
    def __init__(self) -> None:
        self.call_next_calls: list[tuple[int, int, int, int]] = []
        self.unhook_calls: list[int] = []

    def CallNextHookEx(
        self,
        hook_handle: int,
        n_code: int,
        w_param: int,
        l_param: int,
    ) -> int:
        self.call_next_calls.append(
            (hook_handle, n_code, w_param, l_param),
        )
        return 73

    def UnhookWindowsHookEx(self, hook_handle: int) -> int:
        self.unhook_calls.append(hook_handle)
        return 1


class _FakeAdapter:
    def __init__(self) -> None:
        self.cancel_count = 0

    def cancel_fraction_session(self) -> None:
        self.cancel_count += 1


class _FakeLogger:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


@unittest.skipUnless(sys.platform == "win32", "requires Win32 ctypes")
class CursorMovementInputTests(unittest.TestCase):
    def test_multiline_unicode_uses_real_enter_key_pair(self) -> None:
        hook = object.__new__(Win32KeyboardHook)
        fake_user32 = _DetailedFakeUser32()
        hook._user32 = fake_user32

        hook._send_unicode_text("甲\n乙")

        self.assertEqual(len(fake_user32.calls), 1)
        event_count, events, input_size = fake_user32.calls[0]
        self.assertEqual(event_count, 6)
        self.assertEqual(input_size, ctypes.sizeof(_INPUT))
        self.assertEqual(
            events,
            [
                (0, ord("甲"), KEYEVENTF_UNICODE, _SCITYPE_EXTRA_INFO),
                (
                    0,
                    ord("甲"),
                    KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
                    _SCITYPE_EXTRA_INFO,
                ),
                (VK_RETURN, 0, 0, _SCITYPE_EXTRA_INFO),
                (
                    VK_RETURN,
                    0,
                    KEYEVENTF_KEYUP,
                    _SCITYPE_EXTRA_INFO,
                ),
                (0, ord("乙"), KEYEVENTF_UNICODE, _SCITYPE_EXTRA_INFO),
                (
                    0,
                    ord("乙"),
                    KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
                    _SCITYPE_EXTRA_INFO,
                ),
            ],
        )

    def test_crlf_is_one_injected_line_break(self) -> None:
        hook = object.__new__(Win32KeyboardHook)
        fake_user32 = _DetailedFakeUser32()
        hook._user32 = fake_user32

        hook._send_unicode_text("甲\r\n乙")

        events = fake_user32.calls[0][1]
        enter_events = [
            event for event in events if event[0] == VK_RETURN
        ]
        self.assertEqual(
            enter_events,
            [
                (VK_RETURN, 0, 0, _SCITYPE_EXTRA_INFO),
                (
                    VK_RETURN,
                    0,
                    KEYEVENTF_KEYUP,
                    _SCITYPE_EXTRA_INFO,
                ),
            ],
        )

    def test_left_moves_send_matching_key_down_and_up_pairs(self) -> None:
        hook = object.__new__(Win32KeyboardHook)
        fake_user32 = _FakeUser32()
        hook._user32 = fake_user32

        hook._send_left_keys(2)

        self.assertEqual(len(fake_user32.calls), 2)
        self.assertTrue(
            all(call[0] == 2 for call in fake_user32.calls),
        )
        self.assertTrue(
            all(
                call[2] == ctypes.sizeof(_INPUT)
                for call in fake_user32.calls
            ),
        )
        events = [
            event
            for _, call_events, _ in fake_user32.calls
            for event in call_events
        ]
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

    @patch("scitype.windows_hook.time.sleep")
    def test_left_moves_wait_for_unicode_commit(self, sleep_mock) -> None:
        hook = object.__new__(Win32KeyboardHook)
        hook._user32 = _FakeUser32()

        hook._send_left_keys(1)

        sleep_mock.assert_called_once_with(_TEXT_COMMIT_SETTLE_SECONDS)

    def test_negative_left_moves_are_rejected(self) -> None:
        hook = object.__new__(Win32KeyboardHook)
        hook._user32 = _FakeUser32()

        with self.assertRaisesRegex(ValueError, "不能为负数"):
            hook._send_left_keys(-1)

    def test_right_moves_send_matching_key_down_and_up_pairs(self) -> None:
        hook = object.__new__(Win32KeyboardHook)
        fake_user32 = _FakeUser32()
        hook._user32 = fake_user32

        hook._send_right_keys(3)

        self.assertEqual(len(fake_user32.calls), 3)
        self.assertTrue(
            all(call[0] == 2 for call in fake_user32.calls),
        )
        self.assertTrue(
            all(
                call[2] == ctypes.sizeof(_INPUT)
                for call in fake_user32.calls
            ),
        )
        events = [
            event
            for _, call_events, _ in fake_user32.calls
            for event in call_events
        ]
        self.assertEqual(
            events,
            [
                (VK_RIGHT, KEYEVENTF_EXTENDEDKEY, _SCITYPE_EXTRA_INFO),
                (
                    VK_RIGHT,
                    KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP,
                    _SCITYPE_EXTRA_INFO,
                ),
                (VK_RIGHT, KEYEVENTF_EXTENDEDKEY, _SCITYPE_EXTRA_INFO),
                (
                    VK_RIGHT,
                    KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP,
                    _SCITYPE_EXTRA_INFO,
                ),
                (VK_RIGHT, KEYEVENTF_EXTENDEDKEY, _SCITYPE_EXTRA_INFO),
                (
                    VK_RIGHT,
                    KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP,
                    _SCITYPE_EXTRA_INFO,
                ),
            ],
        )

    @patch("scitype.windows_hook.time.sleep")
    def test_repeated_arrows_are_spaced_between_key_pairs(
        self,
        sleep_mock,
    ) -> None:
        hook = object.__new__(Win32KeyboardHook)
        hook._user32 = _FakeUser32()

        hook._send_right_keys(3)

        self.assertEqual(
            sleep_mock.call_args_list,
            [
                unittest.mock.call(_ARROW_EVENT_INTERVAL_SECONDS),
                unittest.mock.call(_ARROW_EVENT_INTERVAL_SECONDS),
            ],
        )

    def test_negative_right_moves_are_rejected(self) -> None:
        hook = object.__new__(Win32KeyboardHook)
        hook._user32 = _FakeUser32()

        with self.assertRaisesRegex(ValueError, "不能为负数"):
            hook._send_right_keys(-1)

    def test_mouse_click_cancels_fraction_without_consuming_mouse(self) -> None:
        hook = object.__new__(Win32KeyboardHook)
        hook.adapter = _FakeAdapter()
        hook._user32 = _FakeMouseUser32()
        hook._mouse_hook_handle = 29
        hook._fatal_error = None

        result = hook._mouse_hook_callback(
            HC_ACTION,
            WM_LBUTTONDOWN,
            1234,
        )

        self.assertEqual(hook.adapter.cancel_count, 1)
        self.assertEqual(result, 73)
        self.assertEqual(
            hook._user32.call_next_calls,
            [(29, HC_ACTION, WM_LBUTTONDOWN, 1234)],
        )

    def test_close_releases_mouse_and_keyboard_hooks(self) -> None:
        hook = object.__new__(Win32KeyboardHook)
        hook._user32 = _FakeMouseUser32()
        hook._logger = _FakeLogger()
        hook.adapter = _FakeAdapter()
        hook._hook_handle = 11
        hook._mouse_hook_handle = 22

        hook.close()

        self.assertEqual(hook._user32.unhook_calls, [22, 11])
        self.assertIsNone(hook._mouse_hook_handle)
        self.assertIsNone(hook._hook_handle)
        self.assertEqual(hook.adapter.cancel_count, 1)
        self.assertEqual(hook._logger.messages, ["Hook 已释放"])


if __name__ == "__main__":
    unittest.main()
