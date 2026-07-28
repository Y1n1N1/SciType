"""Minimal Win32 keyboard hook and cursor-aware injector for SciType."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import sys

from .input_state import InputAction, InputState
from .windows_input import (
    AdapterDecision,
    CursorPlacementError,
    InsertionOutcome,
    ModifierState,
    TextInsertionError,
    VK_CONTROL,
    VK_LCONTROL,
    VK_LMENU,
    VK_LSHIFT,
    VK_LWIN,
    VK_MENU,
    VK_RCONTROL,
    VK_RMENU,
    VK_RSHIFT,
    VK_RWIN,
    VK_SHIFT,
    WindowsInputAdapter,
    WindowsKeyEvent,
    insert_decision_text,
)


WH_KEYBOARD_LL = 13
HC_ACTION = 0
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

LLKHF_INJECTED = 0x00000010
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_CAPITAL = 0x14
VK_LEFT = 0x25

_SCITYPE_EXTRA_INFO = 0x53434954
_NO_STATE_CHANGE = 0x0004

_ULONG_PTR = ctypes.c_size_t
_LRESULT = ctypes.c_ssize_t


def _print_error(message: str) -> None:
    """Write diagnostics only when a foreground console is available."""
    if sys.stderr is not None:
        print(message, file=sys.stderr)


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", _ULONG_PTR),
    ]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", _ULONG_PTR),
    ]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", _ULONG_PTR),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [
        ("mi", _MOUSEINPUT),
        ("ki", _KEYBDINPUT),
        ("hi", _HARDWAREINPUT),
    ]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("data", _INPUTUNION),
    ]


class Win32KeyboardHook:
    """Run a global low-level keyboard hook on the current Windows desktop."""

    def __init__(
        self,
        adapter: WindowsInputAdapter | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        if sys.platform != "win32":
            raise OSError("SciType V0.2b Windows 输入仅支持 Windows")

        self.adapter = adapter or WindowsInputAdapter()
        self._logger = logger or logging.getLogger("scitype")
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._hook_handle: int | None = None
        self._fatal_error: BaseException | None = None

        hook_proc_type = ctypes.WINFUNCTYPE(
            _LRESULT,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        self._hook_proc_type = hook_proc_type
        self._callback = hook_proc_type(self._hook_callback)
        self._configure_api()

    def run(self) -> None:
        """Install the hook and run its message loop until exit is requested."""
        message = wintypes.MSG()

        try:
            self._install()
            while True:
                result = self._user32.GetMessageW(
                    ctypes.byref(message),
                    None,
                    0,
                    0,
                )
                if result == -1:
                    raise ctypes.WinError(ctypes.get_last_error())
                if result == 0:
                    break

                self._user32.TranslateMessage(ctypes.byref(message))
                self._user32.DispatchMessageW(ctypes.byref(message))
        finally:
            self.close()

        if self._fatal_error is not None:
            raise RuntimeError(
                "Windows 输入接入发生异常，监听已停止并恢复正常键盘输入",
            ) from self._fatal_error

    def close(self) -> None:
        """Release the global hook; safe to call more than once."""
        if self._hook_handle is None:
            return

        hook_handle = self._hook_handle
        self._hook_handle = None
        if not self._user32.UnhookWindowsHookEx(hook_handle):
            raise ctypes.WinError(ctypes.get_last_error())
        self._logger.info("Hook 已释放")

    def _install(self) -> None:
        if self._hook_handle is not None:
            return

        module_handle = self._kernel32.GetModuleHandleW(None)
        hook_handle = self._user32.SetWindowsHookExW(
            WH_KEYBOARD_LL,
            self._callback,
            module_handle,
            0,
        )
        if not hook_handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self._hook_handle = hook_handle
        self._logger.info("Hook 已安装")

    def _hook_callback(
        self,
        n_code: int,
        w_param: int,
        l_param: int,
    ) -> int:
        if n_code < HC_ACTION:
            return self._call_next(n_code, w_param, l_param)
        if w_param not in (
            WM_KEYDOWN,
            WM_KEYUP,
            WM_SYSKEYDOWN,
            WM_SYSKEYUP,
        ):
            return self._call_next(n_code, w_param, l_param)

        try:
            hook_data = ctypes.cast(
                l_param,
                ctypes.POINTER(_KBDLLHOOKSTRUCT),
            ).contents
            is_key_down = w_param in (WM_KEYDOWN, WM_SYSKEYDOWN)
            is_scitype_injected = bool(
                hook_data.flags & LLKHF_INJECTED,
            ) and (
                hook_data.dwExtraInfo == _SCITYPE_EXTRA_INFO
            )
            modifiers = self._modifier_state()
            translated_text = None
            if (
                is_key_down
                and not is_scitype_injected
                and self.adapter.state_machine.state is InputState.SYMBOL
            ):
                translated_text = self._translate_text(
                    hook_data.vkCode,
                    hook_data.scanCode,
                    modifiers,
                )

            decision = self.adapter.handle_event(
                WindowsKeyEvent(
                    vk_code=hook_data.vkCode,
                    is_key_down=is_key_down,
                    is_scitype_injected=is_scitype_injected,
                    text=translated_text,
                    modifiers=modifiers,
                ),
            )
            return self._execute_decision(
                decision,
                n_code,
                w_param,
                l_param,
            )
        except BaseException as error:
            return self._fail_open(error, n_code, w_param, l_param)

    def _execute_decision(
        self,
        decision: AdapterDecision,
        n_code: int,
        w_param: int,
        l_param: int,
    ) -> int:
        if decision.exit_requested:
            self._user32.PostQuitMessage(0)
            return 1

        if decision.action is InputAction.PASS_THROUGH:
            return self._call_next(n_code, w_param, l_param)

        if decision.action is InputAction.INSERT_TEXT:
            try:
                with self.adapter.injection_guard():
                    outcome = insert_decision_text(
                        decision,
                        self._send_unicode_text,
                        self._send_left_keys,
                    )
            except CursorPlacementError as error:
                _print_error(
                    "SciType：文本已插入，但真实光标定位失败；"
                    "监听将安全停止。"
                )
                return self._stop_and_consume(error)
            except TextInsertionError as error:
                return self._fail_open(error, n_code, w_param, l_param)

            if outcome is InsertionOutcome.FALLBACK:
                _print_error(
                    "SciType：符号替换失败，已恢复原始命令。"
                )

        return 1

    def _stop_and_consume(self, error: BaseException) -> int:
        if self._fatal_error is None:
            self._fatal_error = error
        self._user32.PostQuitMessage(1)
        return 1

    def _fail_open(
        self,
        error: BaseException,
        n_code: int,
        w_param: int,
        l_param: int,
    ) -> int:
        if self._fatal_error is None:
            self._fatal_error = error
        self._user32.PostQuitMessage(1)
        return self._call_next(n_code, w_param, l_param)

    def _call_next(self, n_code: int, w_param: int, l_param: int) -> int:
        return self._user32.CallNextHookEx(
            self._hook_handle,
            n_code,
            w_param,
            l_param,
        )

    def _modifier_state(self) -> ModifierState:
        return ModifierState(
            shift=self._any_key_down(VK_SHIFT, VK_LSHIFT, VK_RSHIFT),
            control=self._any_key_down(
                VK_CONTROL,
                VK_LCONTROL,
                VK_RCONTROL,
            ),
            alt=self._any_key_down(VK_MENU, VK_LMENU, VK_RMENU),
            windows=self._any_key_down(VK_LWIN, VK_RWIN),
        )

    def _any_key_down(self, *vk_codes: int) -> bool:
        return any(
            self._user32.GetAsyncKeyState(vk_code) & 0x8000
            for vk_code in vk_codes
        )

    def _translate_text(
        self,
        vk_code: int,
        scan_code: int,
        modifiers: ModifierState,
    ) -> str | None:
        keyboard_state = (ctypes.c_ubyte * 256)()
        keyboard_state[vk_code] = 0x80
        self._set_modifier_bytes(keyboard_state, modifiers)
        if self._user32.GetKeyState(VK_CAPITAL) & 0x0001:
            keyboard_state[VK_CAPITAL] = 0x01

        foreground_window = self._user32.GetForegroundWindow()
        foreground_thread = (
            self._user32.GetWindowThreadProcessId(
                foreground_window,
                None,
            )
            if foreground_window
            else 0
        )
        keyboard_layout = self._user32.GetKeyboardLayout(foreground_thread)
        buffer = ctypes.create_unicode_buffer(8)
        translated_count = self._user32.ToUnicodeEx(
            vk_code,
            scan_code,
            keyboard_state,
            buffer,
            len(buffer),
            _NO_STATE_CHANGE,
            keyboard_layout,
        )
        if translated_count == 0:
            return None

        unit_count = min(abs(translated_count), len(buffer))
        text = "".join(buffer[index] for index in range(unit_count))
        return text if text and text.isprintable() else None

    @staticmethod
    def _set_modifier_bytes(
        keyboard_state: ctypes.Array[ctypes.c_ubyte],
        modifiers: ModifierState,
    ) -> None:
        if modifiers.shift:
            keyboard_state[VK_SHIFT] = 0x80
        if modifiers.control:
            keyboard_state[VK_CONTROL] = 0x80
        if modifiers.alt:
            keyboard_state[VK_MENU] = 0x80

    def _send_unicode_text(self, text: str) -> None:
        utf16 = text.encode("utf-16-le", errors="surrogatepass")
        code_units = [
            int.from_bytes(utf16[index : index + 2], "little")
            for index in range(0, len(utf16), 2)
        ]
        if not code_units:
            return

        input_events = (_INPUT * (len(code_units) * 2))()
        event_index = 0
        for code_unit in code_units:
            input_events[event_index].type = INPUT_KEYBOARD
            input_events[event_index].ki = _KEYBDINPUT(
                wVk=0,
                wScan=code_unit,
                dwFlags=KEYEVENTF_UNICODE,
                time=0,
                dwExtraInfo=_SCITYPE_EXTRA_INFO,
            )
            event_index += 1

            input_events[event_index].type = INPUT_KEYBOARD
            input_events[event_index].ki = _KEYBDINPUT(
                wVk=0,
                wScan=code_unit,
                dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
                time=0,
                dwExtraInfo=_SCITYPE_EXTRA_INFO,
            )
            event_index += 1

        self._send_input_events(input_events, operation="文本插入")

    def _send_left_keys(self, left_moves: int) -> None:
        if left_moves < 0:
            raise ValueError("光标左移次数不能为负数")
        if left_moves == 0:
            return

        input_events = (_INPUT * (left_moves * 2))()
        event_index = 0
        for _ in range(left_moves):
            input_events[event_index].type = INPUT_KEYBOARD
            input_events[event_index].ki = _KEYBDINPUT(
                wVk=VK_LEFT,
                wScan=0,
                dwFlags=KEYEVENTF_EXTENDEDKEY,
                time=0,
                dwExtraInfo=_SCITYPE_EXTRA_INFO,
            )
            event_index += 1

            input_events[event_index].type = INPUT_KEYBOARD
            input_events[event_index].ki = _KEYBDINPUT(
                wVk=VK_LEFT,
                wScan=0,
                dwFlags=KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP,
                time=0,
                dwExtraInfo=_SCITYPE_EXTRA_INFO,
            )
            event_index += 1

        self._send_input_events(input_events, operation="光标移动")

    def _send_input_events(
        self,
        input_events: ctypes.Array[_INPUT],
        *,
        operation: str,
    ) -> None:
        event_count = len(input_events)
        ctypes.set_last_error(0)
        inserted_count = self._user32.SendInput(
            event_count,
            input_events,
            ctypes.sizeof(_INPUT),
        )
        if inserted_count == event_count:
            return

        error_code = ctypes.get_last_error()
        if error_code:
            raise ctypes.WinError(error_code)
        raise OSError(
            f"SendInput 在{operation}时只插入了 "
            f"{inserted_count}/{event_count} 个事件",
        )

    def _configure_api(self) -> None:
        hook_handle = wintypes.HANDLE
        module_handle = wintypes.HMODULE

        self._kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        self._kernel32.GetModuleHandleW.restype = module_handle

        self._user32.SetWindowsHookExW.argtypes = [
            ctypes.c_int,
            self._hook_proc_type,
            module_handle,
            wintypes.DWORD,
        ]
        self._user32.SetWindowsHookExW.restype = hook_handle

        self._user32.CallNextHookEx.argtypes = [
            hook_handle,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        self._user32.CallNextHookEx.restype = _LRESULT

        self._user32.UnhookWindowsHookEx.argtypes = [hook_handle]
        self._user32.UnhookWindowsHookEx.restype = wintypes.BOOL

        self._user32.GetMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG),
            wintypes.HWND,
            wintypes.UINT,
            wintypes.UINT,
        ]
        self._user32.GetMessageW.restype = ctypes.c_int
        self._user32.TranslateMessage.argtypes = [
            ctypes.POINTER(wintypes.MSG),
        ]
        self._user32.TranslateMessage.restype = wintypes.BOOL
        self._user32.DispatchMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG),
        ]
        self._user32.DispatchMessageW.restype = _LRESULT
        self._user32.PostQuitMessage.argtypes = [ctypes.c_int]
        self._user32.PostQuitMessage.restype = None

        self._user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self._user32.GetAsyncKeyState.restype = wintypes.SHORT
        self._user32.GetKeyState.argtypes = [ctypes.c_int]
        self._user32.GetKeyState.restype = wintypes.SHORT
        self._user32.GetForegroundWindow.argtypes = []
        self._user32.GetForegroundWindow.restype = wintypes.HWND
        self._user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self._user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        self._user32.GetKeyboardLayout.argtypes = [wintypes.DWORD]
        self._user32.GetKeyboardLayout.restype = wintypes.HANDLE
        self._user32.ToUnicodeEx.argtypes = [
            wintypes.UINT,
            wintypes.UINT,
            ctypes.POINTER(ctypes.c_ubyte),
            wintypes.LPWSTR,
            ctypes.c_int,
            wintypes.UINT,
            wintypes.HANDLE,
        ]
        self._user32.ToUnicodeEx.restype = ctypes.c_int

        self._user32.SendInput.argtypes = [
            wintypes.UINT,
            ctypes.POINTER(_INPUT),
            ctypes.c_int,
        ]
        self._user32.SendInput.restype = wintypes.UINT
