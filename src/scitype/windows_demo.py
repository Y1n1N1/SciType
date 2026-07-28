"""Background-capable Windows entry point for SciType V0.3a."""

from __future__ import annotations

import ctypes
from enum import Enum, auto
import logging
from pathlib import Path
import sys
from typing import Callable, ContextManager, Protocol

from .dictionary import load_dictionary
from .logging_config import configure_logging, get_log_path
from .single_instance import SingleInstanceLock
from .windows_hook import Win32KeyboardHook


class HookRunner(Protocol):
    """Minimal keyboard Hook interface used by the startup coordinator."""

    def run(self) -> None:
        """Install, run and release the Hook."""


class InstanceLease(Protocol):
    """Context-managed single-instance decision."""

    @property
    def is_primary(self) -> bool:
        """Whether this process may install the Hook."""


class ApplicationStatus(Enum):
    """Normal outcomes of the testable Windows startup coordinator."""

    STOPPED = auto()
    ALREADY_RUNNING = auto()


def _console_message(message: str = "", *, is_error: bool = False) -> None:
    """Print only when python.exe supplied a foreground console stream."""
    stream = sys.stderr if is_error else sys.stdout
    if stream is not None:
        print(message, file=stream)


def run_windows_application(
    *,
    instance_lock: ContextManager[InstanceLease],
    dictionary_loader: Callable[[], object],
    hook_factory: Callable[[], HookRunner],
    logger: logging.Logger,
) -> ApplicationStatus:
    """Validate startup order and prevent a second Hook installation."""
    with instance_lock as active_instance:
        if not active_instance.is_primary:
            logger.info("第二实例被拒绝")
            return ApplicationStatus.ALREADY_RUNNING

        dictionary_loader()
        hook = hook_factory()
        hook.run()
        return ApplicationStatus.STOPPED


def show_windows_message(
    message: str,
    *,
    title: str = "SciType",
    is_error: bool = False,
) -> None:
    """Show a short Windows message, with a console fallback off Windows."""
    if sys.platform != "win32":
        _console_message(f"{title}: {message}", is_error=True)
        return

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    message_box = user32.MessageBoxW
    message_box.argtypes = [
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_uint,
    ]
    message_box.restype = ctypes.c_int

    icon_flag = 0x00000010 if is_error else 0x00000040
    message_box(None, message, title, icon_flag)


def _report_logging_failure(error: BaseException) -> int:
    message = f"SciType 无法初始化后台日志：{error}"
    _console_message(message, is_error=True)
    show_windows_message(message, is_error=True)
    return 1


def main() -> int:
    """Run the V0.3a Windows background service."""
    try:
        log_path = get_log_path()
        logger = configure_logging(log_path)
    except Exception as error:
        return _report_logging_failure(error)

    exit_code = 0
    try:
        logger.info("程序启动")
        _console_message("SciType V0.3a Windows 理科符号输入")
        _console_message("已启动全局监听；按 Ctrl + Alt + Q 安全退出。")
        _console_message(f"后台日志：{log_path}")
        _console_message("本程序不会记录或打印普通键盘输入。")

        status = run_windows_application(
            instance_lock=SingleInstanceLock(),
            dictionary_loader=load_dictionary,
            hook_factory=lambda: Win32KeyboardHook(logger=logger),
            logger=logger,
        )
        if status is ApplicationStatus.ALREADY_RUNNING:
            show_windows_message("SciType 已在运行")
        else:
            _console_message("SciType 已停止，键盘监听已释放。")
    except KeyboardInterrupt:
        _console_message("\nSciType 已停止，键盘监听已释放。")
    except Exception as error:
        logger.exception("未处理异常")
        message = (
            "SciType 启动或运行失败，键盘监听已优先释放。\n"
            f"请查看日志：{Path(log_path)}"
        )
        _console_message(f"{message}\n错误：{error}", is_error=True)
        show_windows_message(message, is_error=True)
        exit_code = 1
    finally:
        logger.info("程序退出")
        for handler in logger.handlers:
            handler.flush()

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
