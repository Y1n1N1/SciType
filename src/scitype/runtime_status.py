"""Lightweight runtime-state file shared by the backend and settings UI."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from enum import Enum, auto
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sys
import tempfile

from .single_instance import probe_existing_instance


RUNTIME_STATUS_SCHEMA_VERSION = 1
RUNTIME_STATUS_FILE_NAME = "runtime_status.json"
_MAX_RUNTIME_STATUS_BYTES = 64 * 1024
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class RuntimeStatusError(RuntimeError):
    """A content-safe runtime-state read or write failure."""


class RuntimeApplicationState(Enum):
    """How the current configuration relates to the background process."""

    NOT_RUNNING = auto()
    RUNNING_APPLIED = auto()
    RUNNING_RESTART_REQUIRED = auto()
    RUNNING_UNVERIFIED = auto()


@dataclass(frozen=True, slots=True)
class RuntimeStatusRecord:
    """Minimal process identity and loaded-configuration fingerprint."""

    pid: int
    started_at: int
    config_hash: str


@dataclass(frozen=True, slots=True)
class RuntimeApplicationStatus:
    """Result returned to the settings layer."""

    state: RuntimeApplicationState
    record: RuntimeStatusRecord | None = None


def get_runtime_status_path(
    local_app_data: str | os.PathLike[str] | None = None,
) -> Path:
    """Return ``LOCALAPPDATA/SciType/runtime_status.json``."""
    base_directory = (
        os.fspath(local_app_data)
        if local_app_data is not None
        else os.environ.get("LOCALAPPDATA")
    )
    if not base_directory:
        raise RuntimeStatusError("无法确定运行状态文件目录。")
    return Path(base_directory, "SciType", RUNTIME_STATUS_FILE_NAME)


def effective_bindings_hash(bindings: Mapping[str, str]) -> str:
    """Hash the final trigger/replacement mapping deterministically."""
    serialized = json.dumps(
        sorted(bindings.items()),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def configuration_hash(bindings: Mapping[str, str]) -> str:
    """Backward-compatible alias for ``effective_bindings_hash``."""
    return effective_bindings_hash(bindings)


def _record_to_json(record: RuntimeStatusRecord) -> dict[str, object]:
    _validate_record(record)
    return {
        "schema_version": RUNTIME_STATUS_SCHEMA_VERSION,
        "pid": record.pid,
        "started_at": record.started_at,
        "config_hash": record.config_hash,
    }


def _validate_record(record: RuntimeStatusRecord) -> None:
    if (
        not isinstance(record.pid, int)
        or isinstance(record.pid, bool)
        or record.pid <= 0
    ):
        raise RuntimeStatusError("运行状态 PID 无效。")
    if (
        not isinstance(record.started_at, int)
        or isinstance(record.started_at, bool)
        or record.started_at <= 0
    ):
        raise RuntimeStatusError("运行状态启动时间无效。")
    if (
        not isinstance(record.config_hash, str)
        or _SHA256_PATTERN.fullmatch(record.config_hash) is None
    ):
        raise RuntimeStatusError("运行状态配置哈希无效。")


def _parse_record(raw_data: object) -> RuntimeStatusRecord:
    if not isinstance(raw_data, dict):
        raise RuntimeStatusError("运行状态文件格式无效。")
    required = frozenset(
        ("schema_version", "pid", "started_at", "config_hash"),
    )
    if set(raw_data) != required:
        raise RuntimeStatusError("运行状态文件字段无效。")
    if raw_data["schema_version"] != RUNTIME_STATUS_SCHEMA_VERSION:
        raise RuntimeStatusError("运行状态文件版本不受支持。")
    record = RuntimeStatusRecord(
        pid=raw_data["pid"],  # type: ignore[arg-type]
        started_at=raw_data["started_at"],  # type: ignore[arg-type]
        config_hash=raw_data["config_hash"],  # type: ignore[arg-type]
    )
    _validate_record(record)
    return record


def read_runtime_status(path: str | os.PathLike[str]) -> RuntimeStatusRecord:
    """Read one small, strict UTF-8 runtime-state file."""
    status_path = Path(path)
    try:
        if status_path.stat().st_size > _MAX_RUNTIME_STATUS_BYTES:
            raise RuntimeStatusError("运行状态文件过大。")
        with status_path.open("r", encoding="utf-8") as file:
            return _parse_record(json.load(file))
    except RuntimeStatusError:
        raise
    except (
        json.JSONDecodeError,
        UnicodeDecodeError,
        RecursionError,
        OSError,
    ) as error:
        raise RuntimeStatusError("无法读取运行状态文件。") from error


def write_runtime_status(
    record: RuntimeStatusRecord,
    path: str | os.PathLike[str],
) -> Path:
    """Atomically publish a runtime record beside other local state."""
    status_path = Path(path)
    serialized = json.dumps(
        _record_to_json(record),
        ensure_ascii=True,
        indent=2,
    ) + "\n"
    temporary_path: Path | None = None
    try:
        status_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{status_path.name}.",
            suffix=".tmp",
            dir=status_path.parent,
            delete=False,
        ) as temporary_file:
            temporary_file.write(serialized)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)

        verified = read_runtime_status(temporary_path)
        if verified != record:
            raise RuntimeStatusError("临时运行状态验证失败。")
        os.replace(temporary_path, status_path)
        temporary_path = None
    except RuntimeStatusError:
        raise
    except OSError as error:
        raise RuntimeStatusError("无法写入运行状态文件。") from error
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
    return status_path


def clear_runtime_status(
    path: str | os.PathLike[str],
    *,
    expected_record: RuntimeStatusRecord,
) -> None:
    """Remove only the record published by the current backend instance."""
    status_path = Path(path)
    try:
        current = read_runtime_status(status_path)
    except RuntimeStatusError:
        return
    if current != expected_record:
        return
    try:
        status_path.unlink(missing_ok=True)
    except OSError:
        pass


def process_start_time(pid: int) -> int | None:
    """Return a stable process-start identifier, or ``None`` if not alive."""
    if pid <= 0:
        return None
    if sys.platform == "win32":
        return _windows_process_start_time(pid)
    return _proc_process_start_time(pid)


def _windows_process_start_time(pid: int) -> int | None:
    process_query_limited_information = 0x1000
    still_active = 259
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    open_process.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    get_exit_code = kernel32.GetExitCodeProcess
    get_exit_code.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    get_exit_code.restype = wintypes.BOOL
    get_process_times = kernel32.GetProcessTimes
    get_process_times.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    ]
    get_process_times.restype = wintypes.BOOL

    handle = open_process(process_query_limited_information, False, pid)
    if not handle:
        return None
    try:
        exit_code = wintypes.DWORD()
        if not get_exit_code(handle, ctypes.byref(exit_code)):
            return None
        if exit_code.value != still_active:
            return None

        creation = wintypes.FILETIME()
        exit_time = wintypes.FILETIME()
        kernel_time = wintypes.FILETIME()
        user_time = wintypes.FILETIME()
        if not get_process_times(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel_time),
            ctypes.byref(user_time),
        ):
            return None
        return (creation.dwHighDateTime << 32) | creation.dwLowDateTime
    finally:
        close_handle(handle)


def _proc_process_start_time(pid: int) -> int | None:
    """Best-effort non-Windows support used by automated tests and tooling."""
    try:
        stat_text = Path("/proc", str(pid), "stat").read_text(
            encoding="ascii",
        )
    except (OSError, UnicodeDecodeError):
        return None
    closing_parenthesis = stat_text.rfind(")")
    if closing_parenthesis < 0:
        return None
    fields_after_name = stat_text[closing_parenthesis + 2 :].split()
    try:
        # Field 22 is process start time; this slice begins at field 3.
        started_at = int(fields_after_name[19])
    except (IndexError, ValueError):
        return None
    return started_at if started_at > 0 else None


def inspect_runtime_status(
    current_bindings: Mapping[str, str],
    *,
    path: str | os.PathLike[str] | None,
    process_start_lookup: Callable[[int], int | None] | None = None,
    instance_probe: Callable[[], bool | None] | None = None,
) -> RuntimeApplicationStatus:
    """Classify a verified status, falling back to the shared mutex probe."""
    lookup = process_start_lookup or process_start_time
    probe = instance_probe or probe_existing_instance
    try:
        if path is None:
            raise RuntimeStatusError("运行状态文件路径不可用。")
        record = read_runtime_status(path)
    except RuntimeStatusError:
        try:
            detected = probe()
        except Exception:
            detected = None
        state = (
            RuntimeApplicationState.RUNNING_UNVERIFIED
            if detected is True
            else RuntimeApplicationState.NOT_RUNNING
        )
        return RuntimeApplicationStatus(state)

    live_start = lookup(record.pid)
    if live_start is None or live_start != record.started_at:
        try:
            detected = probe()
        except Exception:
            detected = None
        state = (
            RuntimeApplicationState.RUNNING_UNVERIFIED
            if detected is True
            else RuntimeApplicationState.NOT_RUNNING
        )
        return RuntimeApplicationStatus(state)
    state = (
        RuntimeApplicationState.RUNNING_APPLIED
        if record.config_hash == effective_bindings_hash(current_bindings)
        else RuntimeApplicationState.RUNNING_RESTART_REQUIRED
    )
    return RuntimeApplicationStatus(state, record)


@contextmanager
def published_runtime_status(
    bindings: Mapping[str, str],
    *,
    path: str | os.PathLike[str] | None = None,
    logger: logging.Logger | None = None,
    pid: int | None = None,
    started_at: int | None = None,
) -> Iterator[None]:
    """Publish state for one backend lifetime without making startup depend on it."""
    active_pid = os.getpid() if pid is None else pid
    active_start = (
        process_start_time(active_pid)
        if started_at is None
        else started_at
    )
    record: RuntimeStatusRecord | None = None
    status_path: Path | None = None
    try:
        status_path = (
            get_runtime_status_path() if path is None else Path(path)
        )
        if active_start is None:
            raise RuntimeStatusError("无法确认后台进程启动时间。")
        record = RuntimeStatusRecord(
            pid=active_pid,
            started_at=active_start,
            config_hash=effective_bindings_hash(bindings),
        )
        write_runtime_status(record, status_path)
        if logger is not None:
            logger.info("运行状态已发布")
    except RuntimeStatusError as error:
        if logger is not None:
            logger.warning(
                "运行状态发布失败 exception=%s",
                type(error).__name__,
            )
        record = None
        status_path = None

    try:
        yield
    finally:
        if record is not None and status_path is not None:
            clear_runtime_status(
                status_path,
                expected_record=record,
            )
            if logger is not None:
                logger.info("运行状态已清理")
