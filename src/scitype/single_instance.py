"""Current-user single-instance protection for the Windows demo."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import getpass
import hashlib
import os
import sys
from typing import Protocol


ERROR_ALREADY_EXISTS = 183


def build_mutex_name(user_identity: str) -> str:
    """Build a Windows-safe mutex name without exposing the user name."""
    if not user_identity:
        raise ValueError("用户标识不能为空")

    identity_hash = hashlib.sha256(
        user_identity.encode("utf-8"),
    ).hexdigest()[:16]
    return rf"Local\SciType-{identity_hash}"


def current_user_mutex_name() -> str:
    """Return the mutex name for the current interactive Windows user."""
    domain = os.environ.get("USERDOMAIN", "")
    user_identity = f"{domain}\\{getpass.getuser()}"
    return build_mutex_name(user_identity)


def mutex_already_exists(last_error: int) -> bool:
    """Interpret the testable part of the CreateMutexW result."""
    return last_error == ERROR_ALREADY_EXISTS


@dataclass(frozen=True, slots=True)
class MutexCreation:
    """Result returned after opening or creating a named mutex."""

    handle: int
    already_exists: bool


class MutexBackend(Protocol):
    """Minimal backend used by ``SingleInstanceLock``."""

    def create_mutex(self, name: str) -> MutexCreation:
        """Open or create a named mutex."""

    def close_handle(self, handle: int) -> None:
        """Close a mutex handle."""


class Win32MutexBackend:
    """ctypes implementation of the named-mutex operations."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise OSError("SciType Windows 单实例保护仅支持 Windows")

        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32.CreateMutexW.argtypes = [
            wintypes.LPVOID,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        ]
        self._kernel32.CreateMutexW.restype = wintypes.HANDLE
        self._kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._kernel32.CloseHandle.restype = wintypes.BOOL

    def create_mutex(self, name: str) -> MutexCreation:
        """Create the mutex and report whether it was already present."""
        ctypes.set_last_error(0)
        handle = self._kernel32.CreateMutexW(None, False, name)
        last_error = ctypes.get_last_error()
        if not handle:
            raise ctypes.WinError(last_error)

        return MutexCreation(
            handle=int(handle),
            already_exists=mutex_already_exists(last_error),
        )

    def close_handle(self, handle: int) -> None:
        """Release one CreateMutexW handle."""
        if not self._kernel32.CloseHandle(handle):
            raise ctypes.WinError(ctypes.get_last_error())


class SingleInstanceLock:
    """Keep one named mutex handle open for the process lifetime."""

    def __init__(
        self,
        *,
        name: str | None = None,
        backend: MutexBackend | None = None,
    ) -> None:
        self.name = name or current_user_mutex_name()
        self._backend = backend or Win32MutexBackend()
        self._handle: int | None = None
        self._is_primary = False

    @property
    def is_primary(self) -> bool:
        """Whether this process created the first live mutex handle."""
        return self._is_primary

    def acquire(self) -> bool:
        """Acquire the process-lifetime handle and return primary status."""
        if self._handle is not None:
            return self._is_primary

        creation = self._backend.create_mutex(self.name)
        self._handle = creation.handle
        self._is_primary = not creation.already_exists
        return self._is_primary

    def close(self) -> None:
        """Close the mutex handle; safe to call repeatedly."""
        if self._handle is None:
            return

        handle = self._handle
        self._handle = None
        self._is_primary = False
        self._backend.close_handle(handle)

    def __enter__(self) -> SingleInstanceLock:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        self.close()
