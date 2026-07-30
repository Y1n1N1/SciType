"""Strict, persistent masks for read-only catalog triggers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum, auto
import json
import os
from pathlib import Path
import tempfile

from .binding_rules import check_trigger


CATALOG_MASK_SCHEMA_VERSION = 1
CATALOG_MASKS_FILE_NAME = "catalog_masks.json"
MAX_CATALOG_MASKS_FILE_BYTES = 8 * 1024 * 1024
_CONFIG_DIRECTORY_NAME = "SciType"


class CatalogMaskErrorCode(Enum):
    """Content-safe catalog-mask failure categories."""

    PATH_UNAVAILABLE = auto()
    READ_FAILED = auto()
    INVALID_UTF8 = auto()
    INVALID_JSON = auto()
    DUPLICATE_JSON_FIELD = auto()
    INVALID_ROOT = auto()
    MISSING_FIELD = auto()
    UNKNOWN_FIELD = auto()
    INVALID_SCHEMA_VERSION = auto()
    INVALID_DISABLED_TRIGGERS = auto()
    INVALID_TRIGGER = auto()
    SAVE_FAILED = auto()
    TEMPORARY_VALIDATION_FAILED = auto()


class CatalogMasksError(RuntimeError):
    """One error that can be reported without exposing trigger content."""

    def __init__(
        self,
        message: str,
        *,
        code: CatalogMaskErrorCode,
        exception_type: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.exception_type = exception_type


class CatalogMaskLoadStatus(Enum):
    """Result category for the optional catalog-mask file."""

    MISSING = auto()
    LOADED = auto()
    FAILED = auto()


@dataclass(frozen=True, slots=True)
class CatalogMaskDocument:
    """Canonical set of disabled read-only catalog triggers."""

    schema_version: int
    disabled_triggers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CatalogMaskLoadResult:
    """Safe load result that preserves a damaged source file."""

    status: CatalogMaskLoadStatus
    document: CatalogMaskDocument
    path: Path | None
    error: CatalogMasksError | None = None

    @property
    def succeeded(self) -> bool:
        return self.status is not CatalogMaskLoadStatus.FAILED


class _DuplicateJsonField(ValueError):
    """Internal JSON object-pairs hook signal."""


def empty_catalog_mask_document() -> CatalogMaskDocument:
    """Return an empty document in the current schema."""
    return CatalogMaskDocument(
        schema_version=CATALOG_MASK_SCHEMA_VERSION,
        disabled_triggers=(),
    )


def get_catalog_masks_path(
    local_app_data: str | os.PathLike[str] | None = None,
) -> Path:
    """Return ``LOCALAPPDATA/SciType/catalog_masks.json``."""
    base_directory = (
        os.fspath(local_app_data)
        if local_app_data is not None
        else os.environ.get("LOCALAPPDATA")
    )
    if not base_directory:
        raise CatalogMasksError(
            "无法确定词典屏蔽配置目录。",
            code=CatalogMaskErrorCode.PATH_UNAVAILABLE,
        )
    return Path(
        base_directory,
        _CONFIG_DIRECTORY_NAME,
        CATALOG_MASKS_FILE_NAME,
    )


def create_catalog_mask_document(
    disabled_triggers: Iterable[str],
) -> CatalogMaskDocument:
    """Validate and deterministically de-duplicate disabled triggers."""
    canonical: set[str] = set()
    for trigger in disabled_triggers:
        if not isinstance(trigger, str) or check_trigger(trigger) is not None:
            raise CatalogMasksError(
                "词典屏蔽项包含无效触发词。",
                code=CatalogMaskErrorCode.INVALID_TRIGGER,
            )
        canonical.add(trigger)
    return CatalogMaskDocument(
        schema_version=CATALOG_MASK_SCHEMA_VERSION,
        disabled_triggers=tuple(sorted(canonical)),
    )


def validate_catalog_mask_document(
    document: CatalogMaskDocument,
) -> CatalogMaskDocument:
    """Validate a document and require canonical ordering."""
    if document.schema_version != CATALOG_MASK_SCHEMA_VERSION:
        raise CatalogMasksError(
            "当前词典屏蔽配置版本不受支持。",
            code=CatalogMaskErrorCode.INVALID_SCHEMA_VERSION,
        )
    if not isinstance(document.disabled_triggers, tuple):
        raise CatalogMasksError(
            "disabled_triggers 必须是触发词数组。",
            code=CatalogMaskErrorCode.INVALID_DISABLED_TRIGGERS,
        )
    canonical = create_catalog_mask_document(document.disabled_triggers)
    if canonical != document:
        raise CatalogMasksError(
            "词典屏蔽项必须按确定顺序保存且不能重复。",
            code=CatalogMaskErrorCode.INVALID_DISABLED_TRIGGERS,
        )
    return document


def _reject_duplicate_json_fields(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonField
        result[key] = value
    return result


def _read_raw_json(path: Path) -> object:
    try:
        if path.stat().st_size > MAX_CATALOG_MASKS_FILE_BYTES:
            raise CatalogMasksError(
                "词典屏蔽配置 JSON 文件过大。",
                code=CatalogMaskErrorCode.INVALID_JSON,
            )
        with path.open("r", encoding="utf-8") as file:
            return json.load(
                file,
                object_pairs_hook=_reject_duplicate_json_fields,
            )
    except _DuplicateJsonField as error:
        raise CatalogMasksError(
            "词典屏蔽配置包含重复的 JSON 字段。",
            code=CatalogMaskErrorCode.DUPLICATE_JSON_FIELD,
            exception_type=type(error).__name__,
        ) from error
    except json.JSONDecodeError as error:
        raise CatalogMasksError(
            "词典屏蔽配置 JSON 格式损坏。",
            code=CatalogMaskErrorCode.INVALID_JSON,
            exception_type=type(error).__name__,
        ) from error
    except RecursionError as error:
        raise CatalogMasksError(
            "词典屏蔽配置 JSON 嵌套过深。",
            code=CatalogMaskErrorCode.INVALID_JSON,
            exception_type=type(error).__name__,
        ) from error
    except UnicodeDecodeError as error:
        raise CatalogMasksError(
            "词典屏蔽配置不是有效的 UTF-8 文本。",
            code=CatalogMaskErrorCode.INVALID_UTF8,
            exception_type=type(error).__name__,
        ) from error
    except OSError as error:
        raise CatalogMasksError(
            "无法读取词典屏蔽配置。",
            code=CatalogMaskErrorCode.READ_FAILED,
            exception_type=type(error).__name__,
        ) from error


def _parse_document(raw_data: object) -> CatalogMaskDocument:
    if not isinstance(raw_data, dict):
        raise CatalogMasksError(
            "词典屏蔽配置顶层必须是 JSON 对象。",
            code=CatalogMaskErrorCode.INVALID_ROOT,
        )
    required = frozenset(("schema_version", "disabled_triggers"))
    missing = required.difference(raw_data)
    if missing:
        raise CatalogMasksError(
            "词典屏蔽配置缺少必需字段。",
            code=CatalogMaskErrorCode.MISSING_FIELD,
        )
    if set(raw_data).difference(required):
        raise CatalogMasksError(
            "词典屏蔽配置包含当前版本不支持的字段。",
            code=CatalogMaskErrorCode.UNKNOWN_FIELD,
        )
    schema_version = raw_data["schema_version"]
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != CATALOG_MASK_SCHEMA_VERSION
    ):
        raise CatalogMasksError(
            "当前词典屏蔽配置版本不受支持。",
            code=CatalogMaskErrorCode.INVALID_SCHEMA_VERSION,
        )
    disabled_triggers = raw_data["disabled_triggers"]
    if not isinstance(disabled_triggers, list):
        raise CatalogMasksError(
            "disabled_triggers 必须是 JSON 数组。",
            code=CatalogMaskErrorCode.INVALID_DISABLED_TRIGGERS,
        )
    return create_catalog_mask_document(disabled_triggers)


def _load_document_strict(path: Path) -> CatalogMaskDocument:
    return _parse_document(_read_raw_json(path))


def load_catalog_masks(
    path: str | os.PathLike[str] | None = None,
) -> CatalogMaskLoadResult:
    """Load optional masks without making invalid data fatal."""
    try:
        mask_path = (
            Path(path) if path is not None else get_catalog_masks_path()
        )
    except CatalogMasksError as error:
        return CatalogMaskLoadResult(
            status=CatalogMaskLoadStatus.FAILED,
            document=empty_catalog_mask_document(),
            path=None,
            error=error,
        )
    try:
        exists = mask_path.exists()
    except OSError as error:
        read_error = CatalogMasksError(
            "无法检查词典屏蔽配置。",
            code=CatalogMaskErrorCode.READ_FAILED,
            exception_type=type(error).__name__,
        )
        return CatalogMaskLoadResult(
            status=CatalogMaskLoadStatus.FAILED,
            document=empty_catalog_mask_document(),
            path=mask_path,
            error=read_error,
        )
    if not exists:
        return CatalogMaskLoadResult(
            status=CatalogMaskLoadStatus.MISSING,
            document=empty_catalog_mask_document(),
            path=mask_path,
        )
    try:
        document = _load_document_strict(mask_path)
    except CatalogMasksError as error:
        return CatalogMaskLoadResult(
            status=CatalogMaskLoadStatus.FAILED,
            document=empty_catalog_mask_document(),
            path=mask_path,
            error=error,
        )
    return CatalogMaskLoadResult(
        status=CatalogMaskLoadStatus.LOADED,
        document=document,
        path=mask_path,
    )


def _document_to_json_data(
    document: CatalogMaskDocument,
) -> dict[str, object]:
    validate_catalog_mask_document(document)
    return {
        "schema_version": document.schema_version,
        "disabled_triggers": list(document.disabled_triggers),
    }


def save_catalog_masks(
    document: CatalogMaskDocument,
    path: str | os.PathLike[str] | None = None,
) -> Path:
    """Validate, verify and atomically save a UTF-8 mask document."""
    mask_path = (
        Path(path) if path is not None else get_catalog_masks_path()
    )
    serialized = json.dumps(
        _document_to_json_data(document),
        ensure_ascii=False,
        indent=2,
    ) + "\n"
    temporary_path: Path | None = None
    try:
        mask_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{mask_path.name}.",
            suffix=".tmp",
            dir=mask_path.parent,
            delete=False,
        ) as temporary_file:
            temporary_file.write(serialized)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)

        try:
            verified = _load_document_strict(temporary_path)
        except CatalogMasksError as error:
            raise CatalogMasksError(
                "临时词典屏蔽配置校验失败。",
                code=CatalogMaskErrorCode.TEMPORARY_VALIDATION_FAILED,
                exception_type=type(error).__name__,
            ) from error
        if verified != document:
            raise CatalogMasksError(
                "临时词典屏蔽配置校验结果不一致。",
                code=CatalogMaskErrorCode.TEMPORARY_VALIDATION_FAILED,
            )
        os.replace(temporary_path, mask_path)
        temporary_path = None
    except CatalogMasksError:
        raise
    except OSError as error:
        raise CatalogMasksError(
            "无法保存词典屏蔽配置，原配置未被修改。",
            code=CatalogMaskErrorCode.SAVE_FAILED,
            exception_type=type(error).__name__,
        ) from error
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
    return mask_path
