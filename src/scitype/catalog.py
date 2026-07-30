"""Read-only SciType catalog and local JSON extension-pack services."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum, auto
import json
import os
from pathlib import Path
import re
import tempfile
from types import MappingProxyType

from .dictionary import (
    ShortcutBindingDefinition,
    SymbolDefinition,
    load_binding_definitions,
    load_symbol_catalog,
)
from .template import CURSOR_PLACEHOLDER
from .user_bindings import (
    UserBinding,
    UserBindingsError,
    validate_replacement,
    validate_trigger,
)


PACK_SCHEMA_VERSION = 1
PACK_DIRECTORY_NAME = "packs"
BASE_SOURCE_ID = "scitype.base"
BASE_SOURCE_NAME = "SciType 基础词典"
MAX_PACK_FILE_BYTES = 8 * 1024 * 1024
RESERVED_SOURCE_IDS = frozenset((BASE_SOURCE_ID,))

# These commands have behavior beyond ordinary static replacement. Extension
# packs may display colliding entries, but cannot activate them.
SYSTEM_RESERVED_TRIGGERS = frozenset(("//", "/fs"))

_PACK_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_PACK_ROOT_FIELDS = frozenset(("schema_version", "pack", "entries"))
_PACK_REQUIRED_FIELDS = frozenset(("id", "name", "version"))
_PACK_OPTIONAL_FIELDS = frozenset(("description", "author"))
_ENTRY_FIELDS = frozenset(("name", "category", "trigger", "replacement"))


class CatalogSourceKind(Enum):
    """Origin of one read-only catalog source."""

    BASE = auto()
    LOCAL_PACK = auto()


class CatalogConflict(Enum):
    """Why a local-pack entry is excluded from effective input."""

    RESERVED_TRIGGER = auto()
    BASE_TRIGGER = auto()
    PACK_TRIGGER = auto()


class CatalogUserState(Enum):
    """How a user binding affects one read-only catalog entry."""

    NONE = auto()
    OVERRIDDEN = auto()
    DISABLED = auto()


class PackErrorCode(Enum):
    """Content-safe extension-pack failure categories."""

    PATH_UNAVAILABLE = auto()
    DIRECTORY_READ_FAILED = auto()
    READ_FAILED = auto()
    INVALID_UTF8 = auto()
    INVALID_JSON = auto()
    DUPLICATE_JSON_FIELD = auto()
    INVALID_ROOT = auto()
    MISSING_FIELD = auto()
    UNKNOWN_FIELD = auto()
    INVALID_SCHEMA_VERSION = auto()
    INVALID_PACK_METADATA = auto()
    INVALID_PACK_ID = auto()
    INVALID_ENTRIES = auto()
    INVALID_ENTRY = auto()
    DUPLICATE_PACK_ID = auto()
    DESTINATION_CONFLICT = auto()
    REPLACEMENT_CONFIRMATION_REQUIRED = auto()
    IMPORT_FAILED = auto()
    TEMPORARY_VALIDATION_FAILED = auto()


class PackValidationError(RuntimeError):
    """One safe local-pack validation or import failure."""

    def __init__(
        self,
        message: str,
        *,
        code: PackErrorCode,
        exception_type: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.exception_type = exception_type


class _DuplicateJsonField(ValueError):
    """Internal JSON parser signal."""


@dataclass(frozen=True, slots=True)
class PackMetadata:
    """User-visible metadata for one validated local pack."""

    pack_id: str
    name: str
    version: str
    description: str = ""
    author: str = ""


@dataclass(frozen=True, slots=True)
class PackEntry:
    """One validated static entry from a local pack."""

    name: str
    category: str
    trigger: str
    replacement: str


@dataclass(frozen=True, slots=True)
class PackDocument:
    """Complete validated schema-versioned extension pack."""

    schema_version: int
    metadata: PackMetadata
    entries: tuple[PackEntry, ...]


@dataclass(frozen=True, slots=True)
class CatalogSource:
    """Summary of one successfully loaded read-only source."""

    source_id: str
    name: str
    kind: CatalogSourceKind
    version: str
    description: str
    author: str
    entry_count: int


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    """One visible catalog row with effective-input status."""

    name: str
    category: str
    trigger: str
    replacement: str
    source_id: str
    source_name: str
    source_kind: CatalogSourceKind
    conflict: CatalogConflict | None = None
    user_state: CatalogUserState = CatalogUserState.NONE

    @property
    def participates_in_catalog_input(self) -> bool:
        """Whether the catalog itself contributes this trigger."""
        return self.conflict is None


@dataclass(frozen=True, slots=True)
class PackLoadFailure:
    """One pack that could not join the catalog."""

    file_name: str
    code: PackErrorCode
    exception_type: str | None = None


@dataclass(frozen=True, slots=True)
class CatalogSnapshot:
    """Immutable base-plus-pack catalog for UI and runtime input."""

    entries: tuple[CatalogEntry, ...]
    sources: tuple[CatalogSource, ...]
    failures: tuple[PackLoadFailure, ...]
    catalog_bindings: Mapping[str, str]
    packs_directory: Path | None

    @property
    def categories(self) -> tuple[str, ...]:
        return tuple(sorted({entry.category for entry in self.entries}))


@dataclass(frozen=True, slots=True)
class PackImportPlan:
    """Validated import decision awaiting optional replacement consent."""

    source_path: Path
    destination_path: Path
    document: PackDocument
    requires_replacement_confirmation: bool


def get_packs_directory(
    local_app_data: str | os.PathLike[str] | None = None,
) -> Path:
    """Return ``LOCALAPPDATA/SciType/packs``."""
    base_directory = (
        os.fspath(local_app_data)
        if local_app_data is not None
        else os.environ.get("LOCALAPPDATA")
    )
    if not base_directory:
        raise PackValidationError(
            "无法确定本地扩展包目录。",
            code=PackErrorCode.PATH_UNAVAILABLE,
        )
    return Path(base_directory, "SciType", PACK_DIRECTORY_NAME)


def _reject_duplicate_fields(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonField
        result[key] = value
    return result


def _read_pack_json(path: Path) -> object:
    try:
        if path.stat().st_size > MAX_PACK_FILE_BYTES:
            raise PackValidationError(
                "扩展包 JSON 文件过大。",
                code=PackErrorCode.INVALID_JSON,
            )
        with path.open("r", encoding="utf-8") as file:
            return json.load(
                file,
                object_pairs_hook=_reject_duplicate_fields,
            )
    except _DuplicateJsonField as error:
        raise PackValidationError(
            "扩展包包含重复的 JSON 字段。",
            code=PackErrorCode.DUPLICATE_JSON_FIELD,
            exception_type=type(error).__name__,
        ) from error
    except json.JSONDecodeError as error:
        raise PackValidationError(
            "扩展包 JSON 格式损坏。",
            code=PackErrorCode.INVALID_JSON,
            exception_type=type(error).__name__,
        ) from error
    except RecursionError as error:
        raise PackValidationError(
            "扩展包 JSON 嵌套过深。",
            code=PackErrorCode.INVALID_JSON,
            exception_type=type(error).__name__,
        ) from error
    except UnicodeDecodeError as error:
        raise PackValidationError(
            "扩展包必须是有效的 UTF-8 文本。",
            code=PackErrorCode.INVALID_UTF8,
            exception_type=type(error).__name__,
        ) from error
    except OSError as error:
        raise PackValidationError(
            "无法读取扩展包。",
            code=PackErrorCode.READ_FAILED,
            exception_type=type(error).__name__,
        ) from error


def _require_fields(
    value: Mapping[str, object],
    *,
    required: frozenset[str],
    allowed: frozenset[str],
) -> None:
    if required.difference(value):
        raise PackValidationError(
            "扩展包缺少必需字段。",
            code=PackErrorCode.MISSING_FIELD,
        )
    if set(value).difference(allowed):
        raise PackValidationError(
            "扩展包包含当前版本不支持的字段。",
            code=PackErrorCode.UNKNOWN_FIELD,
        )


def _nonempty_text(
    value: object,
    *,
    message: str,
    code: PackErrorCode,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PackValidationError(message, code=code)
    if value != value.strip():
        raise PackValidationError(message, code=code)
    return value


def parse_pack_document(raw_data: object) -> PackDocument:
    """Validate pure-data pack JSON without executing any content."""
    if not isinstance(raw_data, dict):
        raise PackValidationError(
            "扩展包顶层必须是 JSON 对象。",
            code=PackErrorCode.INVALID_ROOT,
        )
    _require_fields(
        raw_data,
        required=_PACK_ROOT_FIELDS,
        allowed=_PACK_ROOT_FIELDS,
    )

    schema_version = raw_data["schema_version"]
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != PACK_SCHEMA_VERSION
    ):
        raise PackValidationError(
            "当前扩展包 schema_version 不受支持。",
            code=PackErrorCode.INVALID_SCHEMA_VERSION,
        )

    metadata_data = raw_data["pack"]
    if not isinstance(metadata_data, dict):
        raise PackValidationError(
            "扩展包 pack 元数据必须是 JSON 对象。",
            code=PackErrorCode.INVALID_PACK_METADATA,
        )
    _require_fields(
        metadata_data,
        required=_PACK_REQUIRED_FIELDS,
        allowed=_PACK_REQUIRED_FIELDS | _PACK_OPTIONAL_FIELDS,
    )

    pack_id = _nonempty_text(
        metadata_data["id"],
        message="扩展包 id 必须是非空文本。",
        code=PackErrorCode.INVALID_PACK_ID,
    )
    if _PACK_ID_PATTERN.fullmatch(pack_id) is None:
        raise PackValidationError(
            "扩展包 id 格式无效。",
            code=PackErrorCode.INVALID_PACK_ID,
        )
    if pack_id in RESERVED_SOURCE_IDS:
        raise PackValidationError(
            "扩展包 id 属于 SciType 保留 source id。",
            code=PackErrorCode.INVALID_PACK_ID,
        )
    name = _nonempty_text(
        metadata_data["name"],
        message="扩展包 name 必须是非空文本。",
        code=PackErrorCode.INVALID_PACK_METADATA,
    )
    version = _nonempty_text(
        metadata_data["version"],
        message="扩展包 version 必须是非空文本。",
        code=PackErrorCode.INVALID_PACK_METADATA,
    )
    description = metadata_data.get("description", "")
    author = metadata_data.get("author", "")
    if not isinstance(description, str) or not isinstance(author, str):
        raise PackValidationError(
            "扩展包 description 和 author 必须是文本。",
            code=PackErrorCode.INVALID_PACK_METADATA,
        )

    raw_entries = raw_data["entries"]
    if not isinstance(raw_entries, list):
        raise PackValidationError(
            "扩展包 entries 必须是 JSON 数组。",
            code=PackErrorCode.INVALID_ENTRIES,
        )

    entries: list[PackEntry] = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            raise PackValidationError(
                "扩展包词条必须是 JSON 对象。",
                code=PackErrorCode.INVALID_ENTRY,
            )
        _require_fields(
            raw_entry,
            required=_ENTRY_FIELDS,
            allowed=_ENTRY_FIELDS,
        )
        entry_name = _nonempty_text(
            raw_entry["name"],
            message="扩展包词条 name 必须是非空文本。",
            code=PackErrorCode.INVALID_ENTRY,
        )
        category = _nonempty_text(
            raw_entry["category"],
            message="扩展包词条 category 必须是非空文本。",
            code=PackErrorCode.INVALID_ENTRY,
        )
        try:
            trigger = validate_trigger(raw_entry["trigger"])
            replacement_text = validate_replacement(
                raw_entry["replacement"],
            )
        except UserBindingsError as error:
            raise PackValidationError(
                "扩展包词条 trigger 或 replacement 无效。",
                code=PackErrorCode.INVALID_ENTRY,
                exception_type=error.code.name,
            ) from error
        entries.append(
            PackEntry(
                name=entry_name,
                category=category,
                trigger=trigger,
                replacement=replacement_text,
            ),
        )

    return PackDocument(
        schema_version=schema_version,
        metadata=PackMetadata(
            pack_id=pack_id,
            name=name,
            version=version,
            description=description,
            author=author,
        ),
        entries=tuple(entries),
    )


def load_pack(path: str | os.PathLike[str]) -> PackDocument:
    """Read and strictly validate one UTF-8 JSON extension pack."""
    return parse_pack_document(_read_pack_json(Path(path)))


def _base_catalog() -> tuple[
    tuple[CatalogEntry, ...],
    CatalogSource,
    dict[str, str],
]:
    symbols: dict[str, SymbolDefinition] = load_symbol_catalog()
    bindings: tuple[
        ShortcutBindingDefinition, ...
    ] = load_binding_definitions(catalog=symbols)
    entries = tuple(
        CatalogEntry(
            name=symbols[binding.symbol_id].name,
            category=symbols[binding.symbol_id].category,
            trigger=binding.trigger,
            replacement=symbols[binding.symbol_id].output,
            source_id=BASE_SOURCE_ID,
            source_name=BASE_SOURCE_NAME,
            source_kind=CatalogSourceKind.BASE,
        )
        for binding in bindings
    )
    source = CatalogSource(
        source_id=BASE_SOURCE_ID,
        name=BASE_SOURCE_NAME,
        kind=CatalogSourceKind.BASE,
        version="随程序发布",
        description="SciType 随程序提供的只读符号与兼容默认绑定。",
        author="SciType",
        entry_count=len(entries),
    )
    return entries, source, {
        entry.trigger: entry.replacement for entry in entries
    }


def enumerate_pack_files(
    packs_directory: str | os.PathLike[str],
) -> tuple[Path, ...]:
    """Enumerate direct JSON children case-insensitively and deterministically."""
    directory = Path(packs_directory)
    try:
        if not directory.exists():
            return ()
        return tuple(
            sorted(
                (
                    path
                    for path in directory.iterdir()
                    if path.is_file() and path.suffix.casefold() == ".json"
                ),
                key=lambda path: (path.name.casefold(), path.name),
            ),
        )
    except OSError as error:
        raise PackValidationError(
            "无法检查扩展包目录。",
            code=PackErrorCode.DIRECTORY_READ_FAILED,
            exception_type=type(error).__name__,
        ) from error


def _load_pack_documents(
    packs_directory: Path | None,
) -> tuple[
    list[tuple[Path, PackDocument]],
    list[PackLoadFailure],
]:
    if packs_directory is None:
        return [], []
    try:
        paths = enumerate_pack_files(packs_directory)
    except PackValidationError as error:
        return [], [
            PackLoadFailure(
                file_name="扩展包目录",
                code=error.code,
                exception_type=error.exception_type,
            ),
        ]

    documents: list[tuple[Path, PackDocument]] = []
    failures: list[PackLoadFailure] = []
    for path in paths:
        try:
            documents.append((path, load_pack(path)))
        except PackValidationError as error:
            failures.append(
                PackLoadFailure(
                    file_name=path.name,
                    code=error.code,
                    exception_type=error.exception_type,
                ),
            )

    id_counts = Counter(
        document.metadata.pack_id for _, document in documents
    )
    unique_documents: list[tuple[Path, PackDocument]] = []
    for path, document in documents:
        if id_counts[document.metadata.pack_id] > 1:
            failures.append(
                PackLoadFailure(
                    file_name=path.name,
                    code=PackErrorCode.DUPLICATE_PACK_ID,
                ),
            )
        else:
            unique_documents.append((path, document))
    unique_documents.sort(
        key=lambda item: (
            item[1].metadata.pack_id.casefold(),
            item[0].name.casefold(),
        ),
    )
    return unique_documents, failures


def load_catalog(
    packs_directory: str | os.PathLike[str] | None = None,
) -> CatalogSnapshot:
    """Load packaged entries and deterministic, non-executable local packs."""
    base_entries, base_source, bindings = _base_catalog()

    resolved_packs_directory: Path | None
    failures: list[PackLoadFailure] = []
    if packs_directory is not None:
        resolved_packs_directory = Path(packs_directory)
    else:
        try:
            resolved_packs_directory = get_packs_directory()
        except PackValidationError as error:
            resolved_packs_directory = None
            failures.append(
                PackLoadFailure(
                    file_name="扩展包目录",
                    code=error.code,
                    exception_type=error.exception_type,
                ),
            )

    documents, load_failures = _load_pack_documents(
        resolved_packs_directory,
    )
    failures.extend(load_failures)

    sources: list[CatalogSource] = [base_source]
    raw_pack_entries: list[CatalogEntry] = []
    for _path, document in documents:
        metadata = document.metadata
        sources.append(
            CatalogSource(
                source_id=metadata.pack_id,
                name=metadata.name,
                kind=CatalogSourceKind.LOCAL_PACK,
                version=metadata.version,
                description=metadata.description,
                author=metadata.author,
                entry_count=len(document.entries),
            ),
        )
        raw_pack_entries.extend(
            CatalogEntry(
                name=entry.name,
                category=entry.category,
                trigger=entry.trigger,
                replacement=entry.replacement,
                source_id=metadata.pack_id,
                source_name=metadata.name,
                source_kind=CatalogSourceKind.LOCAL_PACK,
            )
            for entry in document.entries
        )

    base_triggers = {entry.trigger for entry in base_entries}
    pack_trigger_counts = Counter(
        entry.trigger for entry in raw_pack_entries
    )
    pack_entries: list[CatalogEntry] = []
    for entry in raw_pack_entries:
        conflict: CatalogConflict | None = None
        if entry.trigger in SYSTEM_RESERVED_TRIGGERS:
            conflict = CatalogConflict.RESERVED_TRIGGER
        elif entry.trigger in base_triggers:
            conflict = CatalogConflict.BASE_TRIGGER
        elif pack_trigger_counts[entry.trigger] > 1:
            conflict = CatalogConflict.PACK_TRIGGER

        resolved_entry = replace(entry, conflict=conflict)
        pack_entries.append(resolved_entry)
        if conflict is None:
            bindings[entry.trigger] = entry.replacement

    return CatalogSnapshot(
        entries=tuple((*base_entries, *pack_entries)),
        sources=tuple(sources),
        failures=tuple(failures),
        catalog_bindings=MappingProxyType(bindings),
        packs_directory=resolved_packs_directory,
    )


def apply_user_states(
    snapshot: CatalogSnapshot,
    bindings: Sequence[UserBinding],
    disabled_catalog_triggers: Sequence[str] = (),
) -> CatalogSnapshot:
    """Annotate rows using user rules followed by catalog-mask precedence."""
    user_by_trigger = {binding.trigger: binding for binding in bindings}
    disabled = frozenset(disabled_catalog_triggers)
    entries = tuple(
        replace(
            entry,
            user_state=(
                CatalogUserState.DISABLED
                if entry.trigger in disabled
                else (
                    CatalogUserState.OVERRIDDEN
                    if user_by_trigger[entry.trigger].enabled
                    else CatalogUserState.DISABLED
                )
            )
            if entry.trigger in user_by_trigger or entry.trigger in disabled
            else CatalogUserState.NONE,
        )
        for entry in snapshot.entries
    )
    return replace(snapshot, entries=entries)


def query_catalog(
    snapshot: CatalogSnapshot,
    *,
    query: str = "",
    category: str | None = None,
    source_id: str | None = None,
) -> tuple[CatalogEntry, ...]:
    """Search catalog text and apply optional exact category/source filters."""
    needle = query.casefold().strip()
    return tuple(
        entry
        for entry in snapshot.entries
        if (category is None or entry.category == category)
        and (source_id is None or entry.source_id == source_id)
        and (
            not needle
            or needle in entry.name.casefold()
            or needle in entry.trigger.casefold()
            or needle in entry.replacement.casefold()
            or needle in entry.category.casefold()
        )
    )


def catalog_preview(replacement: str) -> str:
    """Render the single cursor placeholder as a plain-text caret marker."""
    return replacement.replace(CURSOR_PLACEHOLDER, "│")


def prepare_pack_import(
    source_path: str | os.PathLike[str],
    packs_directory: str | os.PathLike[str],
) -> PackImportPlan:
    """Validate an import and determine whether replacement consent is needed."""
    source = Path(source_path)
    destination_directory = Path(packs_directory)
    document = load_pack(source)

    existing_paths: list[Path] = []
    candidates = enumerate_pack_files(destination_directory)
    for candidate in candidates:
        try:
            installed = load_pack(candidate)
        except PackValidationError:
            continue
        if installed.metadata.pack_id == document.metadata.pack_id:
            existing_paths.append(candidate)

    if len(existing_paths) > 1:
        raise PackValidationError(
            "扩展包目录中存在重复 pack id，请先人工处理。",
            code=PackErrorCode.DUPLICATE_PACK_ID,
        )

    if existing_paths:
        destination = existing_paths[0]
        needs_confirmation = True
    else:
        target_name = f"{document.metadata.pack_id}.json"
        destination = next(
            (
                candidate
                for candidate in candidates
                if candidate.name.casefold() == target_name.casefold()
            ),
            destination_directory / target_name,
        )
        needs_confirmation = destination.exists()
        if needs_confirmation:
            try:
                occupant = load_pack(destination)
            except PackValidationError:
                occupant = None
            if (
                occupant is not None
                and occupant.metadata.pack_id
                != document.metadata.pack_id
            ):
                raise PackValidationError(
                    "目标文件名已被另一个扩展包占用。",
                    code=PackErrorCode.DESTINATION_CONFLICT,
                )

    return PackImportPlan(
        source_path=source,
        destination_path=destination,
        document=document,
        requires_replacement_confirmation=needs_confirmation,
    )


def execute_pack_import(
    plan: PackImportPlan,
    *,
    allow_replace: bool = False,
) -> Path:
    """Safely copy a validated pack into the local same-filesystem directory."""
    if plan.requires_replacement_confirmation and not allow_replace:
        raise PackValidationError(
            "同名扩展包需要明确确认后才能替换。",
            code=PackErrorCode.REPLACEMENT_CONFIRMATION_REQUIRED,
        )
    if plan.destination_path.exists():
        try:
            current = load_pack(plan.destination_path)
        except PackValidationError:
            current = None
        if (
            current is not None
            and current.metadata.pack_id != plan.document.metadata.pack_id
        ):
            raise PackValidationError(
                "目标文件名已被另一个扩展包占用。",
                code=PackErrorCode.DESTINATION_CONFLICT,
            )
        if not plan.requires_replacement_confirmation and not allow_replace:
            raise PackValidationError(
                "目标扩展包在验证后出现，需要重新确认。",
                code=PackErrorCode.REPLACEMENT_CONFIRMATION_REQUIRED,
            )

    try:
        source_bytes = plan.source_path.read_bytes()
    except OSError as error:
        raise PackValidationError(
            "无法读取待导入扩展包。",
            code=PackErrorCode.READ_FAILED,
            exception_type=type(error).__name__,
        ) from error

    temporary_path: Path | None = None
    try:
        plan.destination_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{plan.destination_path.name}.",
            suffix=".tmp",
            dir=plan.destination_path.parent,
            delete=False,
        ) as temporary_file:
            temporary_file.write(source_bytes)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)

        try:
            verified = load_pack(temporary_path)
        except PackValidationError as error:
            raise PackValidationError(
                "临时扩展包验证失败。",
                code=PackErrorCode.TEMPORARY_VALIDATION_FAILED,
                exception_type=error.code.name,
            ) from error
        if verified != plan.document:
            raise PackValidationError(
                "临时扩展包验证结果不一致。",
                code=PackErrorCode.TEMPORARY_VALIDATION_FAILED,
            )

        os.replace(temporary_path, plan.destination_path)
        temporary_path = None
    except PackValidationError:
        raise
    except OSError as error:
        raise PackValidationError(
            "无法导入扩展包，原文件未被修改。",
            code=PackErrorCode.IMPORT_FAILED,
            exception_type=type(error).__name__,
        ) from error
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass

    return plan.destination_path
