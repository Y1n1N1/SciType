"""Versioned user-binding configuration and effective-binding snapshots."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum, auto
import json
import os
from pathlib import Path
import tempfile
from types import MappingProxyType

from .binding_rules import (
    ReplacementIssue,
    TriggerIssue,
    check_replacement,
    check_trigger,
)
from .dictionary import load_dictionary


CURRENT_SCHEMA_VERSION = 1
USER_CONFIG_DIRECTORY_NAME = "SciType"
USER_BINDINGS_FILE_NAME = "user_bindings.json"


class UserBindingErrorCode(Enum):
    """Non-content error codes safe to map in a GUI or write to a log."""

    PATH_UNAVAILABLE = auto()
    READ_FAILED = auto()
    INVALID_UTF8 = auto()
    INVALID_JSON = auto()
    DUPLICATE_JSON_FIELD = auto()
    INVALID_ROOT = auto()
    MISSING_FIELD = auto()
    UNKNOWN_FIELD = auto()
    INVALID_SCHEMA_VERSION_TYPE = auto()
    UNSUPPORTED_SCHEMA_VERSION = auto()
    INVALID_BINDINGS_TYPE = auto()
    INVALID_BINDING_TYPE = auto()
    INVALID_TRIGGER_TYPE = auto()
    EMPTY_TRIGGER = auto()
    MISSING_TRIGGER_SLASH = auto()
    INVALID_TRIGGER_CHARACTERS = auto()
    INVALID_REPLACEMENT_TYPE = auto()
    EMPTY_REPLACEMENT = auto()
    MULTIPLE_CURSOR_PLACEHOLDERS = auto()
    UNSUPPORTED_PLACEHOLDER = auto()
    INVALID_ENABLED_TYPE = auto()
    DUPLICATE_TRIGGER = auto()
    SAVE_FAILED = auto()
    TEMPORARY_VALIDATION_FAILED = auto()


class UserBindingsError(RuntimeError):
    """One content-safe user-configuration error."""

    def __init__(
        self,
        message: str,
        *,
        code: UserBindingErrorCode,
        field: str | None = None,
        binding_index: int | None = None,
        exception_type: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.field = field
        self.binding_index = binding_index
        self.exception_type = exception_type


class UserBindingLoadStatus(Enum):
    """Result category for one optional user configuration load."""

    MISSING = auto()
    LOADED = auto()
    FAILED = auto()


class ReloadStatus(Enum):
    """Whether a reload produced a new valid snapshot."""

    APPLIED = auto()
    RETAINED_AFTER_FAILURE = auto()


@dataclass(frozen=True, slots=True)
class UserBinding:
    """One direct static text replacement owned by the user."""

    trigger: str
    replacement: str
    enabled: bool


@dataclass(frozen=True, slots=True)
class UserBindingDocument:
    """The complete versioned user configuration file."""

    schema_version: int
    bindings: tuple[UserBinding, ...]


@dataclass(frozen=True, slots=True)
class UserBindingLoadResult:
    """Safe load result that preserves failure state for a future GUI."""

    status: UserBindingLoadStatus
    document: UserBindingDocument
    path: Path | None
    error: UserBindingsError | None = None

    @property
    def succeeded(self) -> bool:
        """Whether the optional file was absent or loaded successfully."""
        return self.status is not UserBindingLoadStatus.FAILED


@dataclass(frozen=True, slots=True)
class ActiveBindingsSnapshot:
    """Immutable defaults, user document and resolved effective bindings."""

    default_bindings: Mapping[str, str]
    effective_bindings: Mapping[str, str]
    user_document: UserBindingDocument
    load_result: UserBindingLoadResult


@dataclass(frozen=True, slots=True)
class ReloadResult:
    """Result of explicitly reloading without mutating the old snapshot."""

    status: ReloadStatus
    snapshot: ActiveBindingsSnapshot
    load_result: UserBindingLoadResult
    restart_required: bool


class _DuplicateJsonField(ValueError):
    """Internal signal raised by the JSON object-pairs hook."""


def empty_user_binding_document() -> UserBindingDocument:
    """Return a valid empty document using the current schema."""
    return UserBindingDocument(
        schema_version=CURRENT_SCHEMA_VERSION,
        bindings=(),
    )


def get_user_bindings_path(
    local_app_data: str | os.PathLike[str] | None = None,
) -> Path:
    """Return ``LOCALAPPDATA/SciType/user_bindings.json``."""
    base_directory = (
        os.fspath(local_app_data)
        if local_app_data is not None
        else os.environ.get("LOCALAPPDATA")
    )
    if not base_directory:
        raise UserBindingsError(
            "无法确定用户配置目录。",
            code=UserBindingErrorCode.PATH_UNAVAILABLE,
        )

    return Path(
        base_directory,
        USER_CONFIG_DIRECTORY_NAME,
        USER_BINDINGS_FILE_NAME,
    )


def validate_trigger(
    trigger: object,
    *,
    binding_index: int | None = None,
) -> str:
    """Validate one trigger without returning or logging its content."""
    issue = check_trigger(trigger)
    if issue is None:
        assert isinstance(trigger, str)
        return trigger

    details = {
        TriggerIssue.NOT_STRING: (
            UserBindingErrorCode.INVALID_TRIGGER_TYPE,
            "触发词必须是字符串。",
        ),
        TriggerIssue.EMPTY: (
            UserBindingErrorCode.EMPTY_TRIGGER,
            "触发词不能为空。",
        ),
        TriggerIssue.MISSING_SLASH: (
            UserBindingErrorCode.MISSING_TRIGGER_SLASH,
            "触发词必须以 / 开头。",
        ),
        TriggerIssue.INVALID_CHARACTERS: (
            UserBindingErrorCode.INVALID_TRIGGER_CHARACTERS,
            "触发词只能是 / 后跟小写 ASCII 字母或数字，或为 //。",
        ),
    }
    code, message = details[issue]
    raise UserBindingsError(
        message,
        code=code,
        field="trigger",
        binding_index=binding_index,
    )


def validate_replacement(
    replacement: object,
    *,
    binding_index: int | None = None,
) -> str:
    """Validate one static replacement without executing any content."""
    issue = check_replacement(replacement)
    if issue is None:
        assert isinstance(replacement, str)
        return replacement

    details = {
        ReplacementIssue.NOT_STRING: (
            UserBindingErrorCode.INVALID_REPLACEMENT_TYPE,
            "输出内容必须是字符串。",
        ),
        ReplacementIssue.EMPTY: (
            UserBindingErrorCode.EMPTY_REPLACEMENT,
            "输出内容不能为空。",
        ),
        ReplacementIssue.MULTIPLE_CURSOR_PLACEHOLDERS: (
            UserBindingErrorCode.MULTIPLE_CURSOR_PLACEHOLDERS,
            "最多只能设置一个光标位置。",
        ),
        ReplacementIssue.UNSUPPORTED_PLACEHOLDER: (
            UserBindingErrorCode.UNSUPPORTED_PLACEHOLDER,
            "当前配置包含不支持的占位符。",
        ),
    }
    code, message = details[issue]
    raise UserBindingsError(
        message,
        code=code,
        field="replacement",
        binding_index=binding_index,
    )


def has_trigger_conflict(
    bindings: Sequence[UserBinding],
    trigger: str,
    *,
    exclude_index: int | None = None,
) -> bool:
    """Return whether another user binding already owns ``trigger``."""
    return any(
        index != exclude_index and binding.trigger == trigger
        for index, binding in enumerate(bindings)
    )


def validate_user_binding_document(
    document: UserBindingDocument,
) -> UserBindingDocument:
    """Validate schema, fields, templates and duplicate triggers."""
    if (
        not isinstance(document.schema_version, int)
        or isinstance(document.schema_version, bool)
    ):
        raise UserBindingsError(
            "schema_version 必须是整数。",
            code=UserBindingErrorCode.INVALID_SCHEMA_VERSION_TYPE,
            field="schema_version",
        )
    if document.schema_version != CURRENT_SCHEMA_VERSION:
        raise UserBindingsError(
            "当前配置版本暂不支持。",
            code=UserBindingErrorCode.UNSUPPORTED_SCHEMA_VERSION,
            field="schema_version",
        )
    if not isinstance(document.bindings, tuple):
        raise UserBindingsError(
            "bindings 必须是绑定数组。",
            code=UserBindingErrorCode.INVALID_BINDINGS_TYPE,
            field="bindings",
        )

    seen_triggers: set[str] = set()
    for index, binding in enumerate(document.bindings):
        if not isinstance(binding, UserBinding):
            raise UserBindingsError(
                "绑定项格式无效。",
                code=UserBindingErrorCode.INVALID_BINDING_TYPE,
                binding_index=index,
            )

        trigger = validate_trigger(
            binding.trigger,
            binding_index=index,
        )
        validate_replacement(
            binding.replacement,
            binding_index=index,
        )
        if not isinstance(binding.enabled, bool):
            raise UserBindingsError(
                "enabled 必须是布尔值。",
                code=UserBindingErrorCode.INVALID_ENABLED_TYPE,
                field="enabled",
                binding_index=index,
            )
        if trigger in seen_triggers:
            raise UserBindingsError(
                "用户配置包含重复触发词。",
                code=UserBindingErrorCode.DUPLICATE_TRIGGER,
                field="trigger",
                binding_index=index,
            )
        seen_triggers.add(trigger)

    return document


def create_user_binding_document(
    bindings: Iterable[UserBinding],
) -> UserBindingDocument:
    """Create and validate one current-schema document."""
    document = UserBindingDocument(
        schema_version=CURRENT_SCHEMA_VERSION,
        bindings=tuple(bindings),
    )
    return validate_user_binding_document(document)


def _reject_duplicate_json_fields(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonField
        result[key] = value
    return result


def _load_raw_json(path: Path) -> object:
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(
                file,
                object_pairs_hook=_reject_duplicate_json_fields,
            )
    except _DuplicateJsonField as error:
        raise UserBindingsError(
            "用户配置包含重复的 JSON 字段。",
            code=UserBindingErrorCode.DUPLICATE_JSON_FIELD,
            exception_type=type(error).__name__,
        ) from error
    except json.JSONDecodeError as error:
        raise UserBindingsError(
            "用户配置 JSON 格式损坏。",
            code=UserBindingErrorCode.INVALID_JSON,
            exception_type=type(error).__name__,
        ) from error
    except UnicodeDecodeError as error:
        raise UserBindingsError(
            "用户配置不是有效的 UTF-8 文本。",
            code=UserBindingErrorCode.INVALID_UTF8,
            exception_type=type(error).__name__,
        ) from error
    except OSError as error:
        raise UserBindingsError(
            "无法读取用户配置文件。",
            code=UserBindingErrorCode.READ_FAILED,
            exception_type=type(error).__name__,
        ) from error


def _require_exact_fields(
    entry: Mapping[str, object],
    required: frozenset[str],
    *,
    binding_index: int | None = None,
) -> None:
    missing = required.difference(entry)
    if missing:
        field = sorted(missing)[0]
        raise UserBindingsError(
            "用户配置缺少必需字段。",
            code=UserBindingErrorCode.MISSING_FIELD,
            field=field,
            binding_index=binding_index,
        )

    unknown = set(entry).difference(required)
    if unknown:
        field = sorted(unknown)[0]
        raise UserBindingsError(
            "用户配置包含当前版本不支持的字段。",
            code=UserBindingErrorCode.UNKNOWN_FIELD,
            field=field,
            binding_index=binding_index,
        )


def _parse_document(raw_data: object) -> UserBindingDocument:
    if not isinstance(raw_data, dict):
        raise UserBindingsError(
            "用户配置顶层必须是 JSON 对象。",
            code=UserBindingErrorCode.INVALID_ROOT,
        )

    _require_exact_fields(
        raw_data,
        frozenset(("schema_version", "bindings")),
    )
    schema_version = raw_data["schema_version"]
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
    ):
        raise UserBindingsError(
            "schema_version 必须是整数。",
            code=UserBindingErrorCode.INVALID_SCHEMA_VERSION_TYPE,
            field="schema_version",
        )
    if schema_version != CURRENT_SCHEMA_VERSION:
        raise UserBindingsError(
            "当前配置版本暂不支持。",
            code=UserBindingErrorCode.UNSUPPORTED_SCHEMA_VERSION,
            field="schema_version",
        )

    raw_bindings = raw_data["bindings"]
    if not isinstance(raw_bindings, list):
        raise UserBindingsError(
            "bindings 必须是 JSON 数组。",
            code=UserBindingErrorCode.INVALID_BINDINGS_TYPE,
            field="bindings",
        )

    bindings: list[UserBinding] = []
    required_fields = frozenset(("trigger", "replacement", "enabled"))
    for index, raw_binding in enumerate(raw_bindings):
        if not isinstance(raw_binding, dict):
            raise UserBindingsError(
                "绑定项必须是 JSON 对象。",
                code=UserBindingErrorCode.INVALID_BINDING_TYPE,
                binding_index=index,
            )
        _require_exact_fields(
            raw_binding,
            required_fields,
            binding_index=index,
        )
        enabled = raw_binding["enabled"]
        if not isinstance(enabled, bool):
            raise UserBindingsError(
                "enabled 必须是布尔值。",
                code=UserBindingErrorCode.INVALID_ENABLED_TYPE,
                field="enabled",
                binding_index=index,
            )

        bindings.append(
            UserBinding(
                trigger=validate_trigger(
                    raw_binding["trigger"],
                    binding_index=index,
                ),
                replacement=validate_replacement(
                    raw_binding["replacement"],
                    binding_index=index,
                ),
                enabled=enabled,
            ),
        )

    document = UserBindingDocument(
        schema_version=schema_version,
        bindings=tuple(bindings),
    )
    return validate_user_binding_document(document)


def _load_document_strict(path: Path) -> UserBindingDocument:
    return _parse_document(_load_raw_json(path))


def load_user_bindings(
    path: str | os.PathLike[str] | None = None,
) -> UserBindingLoadResult:
    """Load an optional user file without making invalid data fatal."""
    try:
        binding_path = (
            Path(path) if path is not None else get_user_bindings_path()
        )
    except UserBindingsError as error:
        return UserBindingLoadResult(
            status=UserBindingLoadStatus.FAILED,
            document=empty_user_binding_document(),
            path=None,
            error=error,
        )

    try:
        binding_exists = binding_path.exists()
    except OSError as error:
        read_error = UserBindingsError(
            "无法检查用户配置文件。",
            code=UserBindingErrorCode.READ_FAILED,
            exception_type=type(error).__name__,
        )
        return UserBindingLoadResult(
            status=UserBindingLoadStatus.FAILED,
            document=empty_user_binding_document(),
            path=binding_path,
            error=read_error,
        )

    if not binding_exists:
        return UserBindingLoadResult(
            status=UserBindingLoadStatus.MISSING,
            document=empty_user_binding_document(),
            path=binding_path,
        )

    try:
        document = _load_document_strict(binding_path)
    except UserBindingsError as error:
        return UserBindingLoadResult(
            status=UserBindingLoadStatus.FAILED,
            document=empty_user_binding_document(),
            path=binding_path,
            error=error,
        )

    return UserBindingLoadResult(
        status=UserBindingLoadStatus.LOADED,
        document=document,
        path=binding_path,
    )


def resolve_effective_bindings(
    default_bindings: Mapping[str, str],
    document: UserBindingDocument,
) -> dict[str, str]:
    """Apply enabled overrides and disabled masks to packaged defaults."""
    validate_user_binding_document(document)
    effective = dict(default_bindings)
    for binding in document.bindings:
        if binding.enabled:
            effective[binding.trigger] = binding.replacement
        else:
            effective.pop(binding.trigger, None)
    return effective


def _freeze_mapping(bindings: Mapping[str, str]) -> Mapping[str, str]:
    return MappingProxyType(dict(bindings))


def _snapshot_from_result(
    default_bindings: Mapping[str, str],
    load_result: UserBindingLoadResult,
) -> ActiveBindingsSnapshot:
    document = load_result.document
    effective = resolve_effective_bindings(default_bindings, document)
    return ActiveBindingsSnapshot(
        default_bindings=_freeze_mapping(default_bindings),
        effective_bindings=_freeze_mapping(effective),
        user_document=document,
        load_result=load_result,
    )


def load_active_bindings(
    user_bindings_path: str | os.PathLike[str] | None = None,
    *,
    default_bindings: Mapping[str, str] | None = None,
) -> ActiveBindingsSnapshot:
    """Load strict core defaults and safely overlay optional user data."""
    defaults = (
        load_dictionary()
        if default_bindings is None
        else dict(default_bindings)
    )
    load_result = load_user_bindings(user_bindings_path)
    return _snapshot_from_result(defaults, load_result)


def load_active_dictionary(
    user_bindings_path: str | os.PathLike[str] | None = None,
    *,
    default_bindings: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Compatibility helper returning only the effective dictionary."""
    snapshot = load_active_bindings(
        user_bindings_path,
        default_bindings=default_bindings,
    )
    return dict(snapshot.effective_bindings)


def reload_user_bindings(
    current_snapshot: ActiveBindingsSnapshot,
    path: str | os.PathLike[str] | None = None,
) -> ReloadResult:
    """Reload explicitly, retaining the old valid snapshot on failure."""
    reload_path = (
        path if path is not None else current_snapshot.load_result.path
    )
    load_result = load_user_bindings(reload_path)
    if load_result.status is UserBindingLoadStatus.FAILED:
        return ReloadResult(
            status=ReloadStatus.RETAINED_AFTER_FAILURE,
            snapshot=current_snapshot,
            load_result=load_result,
            restart_required=False,
        )

    snapshot = _snapshot_from_result(
        current_snapshot.default_bindings,
        load_result,
    )
    return ReloadResult(
        status=ReloadStatus.APPLIED,
        snapshot=snapshot,
        load_result=load_result,
        restart_required=True,
    )


def _document_to_json_data(
    document: UserBindingDocument,
) -> dict[str, object]:
    validate_user_binding_document(document)
    return {
        "schema_version": document.schema_version,
        "bindings": [
            {
                "trigger": binding.trigger,
                "replacement": binding.replacement,
                "enabled": binding.enabled,
            }
            for binding in document.bindings
        ],
    }


def save_user_bindings(
    document: UserBindingDocument,
    path: str | os.PathLike[str] | None = None,
) -> Path:
    """Validate, verify and atomically save one UTF-8 user document."""
    binding_path = (
        Path(path) if path is not None else get_user_bindings_path()
    )
    json_data = _document_to_json_data(document)
    serialized = json.dumps(
        json_data,
        ensure_ascii=False,
        indent=2,
    ) + "\n"

    temporary_path: Path | None = None
    try:
        binding_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{binding_path.name}.",
            suffix=".tmp",
            dir=binding_path.parent,
            delete=False,
        ) as temporary_file:
            temporary_file.write(serialized)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)

        try:
            verified_document = _load_document_strict(temporary_path)
        except UserBindingsError as error:
            raise UserBindingsError(
                "临时用户配置校验失败。",
                code=UserBindingErrorCode.TEMPORARY_VALIDATION_FAILED,
                exception_type=type(error).__name__,
            ) from error
        if verified_document != document:
            raise UserBindingsError(
                "临时用户配置校验结果不一致。",
                code=UserBindingErrorCode.TEMPORARY_VALIDATION_FAILED,
            )

        os.replace(temporary_path, binding_path)
        temporary_path = None
    except UserBindingsError:
        raise
    except OSError as error:
        raise UserBindingsError(
            "无法保存用户配置文件，原配置未被修改。",
            code=UserBindingErrorCode.SAVE_FAILED,
            exception_type=type(error).__name__,
        ) from error
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass

    return binding_path
