"""Load and validate SciType symbol catalogs and shortcut bindings."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
import json
from pathlib import Path
import re
from typing import Any

from .binding_rules import TriggerIssue, check_trigger
from .template import CURSOR_PLACEHOLDER


class DictionaryError(ValueError):
    """Raised when SciType catalog or binding data is invalid."""


@dataclass(frozen=True, slots=True)
class SymbolDefinition:
    """One trigger-independent symbol or output template."""

    symbol_id: str
    name: str
    category: str
    output: str


_SYMBOL_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]*$")


def _reject_duplicate_fields(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    """Reject repeated field names inside one JSON object."""
    result: dict[str, object] = {}

    for key, value in pairs:
        if key in result:
            raise DictionaryError(f"JSON 对象包含重复字段“{key}”。")
        result[key] = value

    return result


def _read_json(
    path: str | Path | None,
    *,
    default_resource: str,
    label: str,
) -> object:
    """Read UTF-8 JSON from a path or an installed package resource."""
    source = (
        Path(path)
        if path is not None
        else files("scitype").joinpath("data").joinpath(default_resource)
    )

    try:
        with source.open("r", encoding="utf-8") as file:
            return json.load(file, object_pairs_hook=_reject_duplicate_fields)
    except json.JSONDecodeError as error:
        raise DictionaryError(
            f"{label} JSON 格式损坏："
            f"第 {error.lineno} 行，第 {error.colno} 列：{error.msg}。"
        ) from error
    except UnicodeDecodeError as error:
        raise DictionaryError(f"{label}必须是有效的 UTF-8 文本。") from error
    except OSError as error:
        raise DictionaryError(f"无法读取{label}“{source}”：{error}。") from error


def _require_entries(raw_data: object, *, label: str) -> list[Any]:
    if not isinstance(raw_data, list):
        raise DictionaryError(f"{label}顶层必须是 JSON 数组。")
    return raw_data


def _missing_fields(
    entry: dict[str, object],
    required_fields: tuple[str, ...],
) -> list[str]:
    return [field for field in required_fields if field not in entry]


def _validate_trigger(trigger: object, *, position: int, label: str) -> str:
    issue = check_trigger(trigger)
    if issue is TriggerIssue.NOT_STRING:
        raise DictionaryError(f"{label}第 {position} 项的 trigger 必须是字符串。")
    if issue is TriggerIssue.EMPTY:
        raise DictionaryError(f"{label}第 {position} 项的 trigger 不能为空。")
    if issue is TriggerIssue.MISSING_SLASH:
        assert isinstance(trigger, str)
        raise DictionaryError(
            f"{label}第 {position} 项的 trigger“{trigger}”必须以 / 开头。",
        )
    if issue is TriggerIssue.INVALID_CHARACTERS:
        assert isinstance(trigger, str)
        raise DictionaryError(
            f"{label}第 {position} 项的 trigger“{trigger}”格式非法："
            "应为 / 加一个或多个小写 ASCII 字母或数字，或为 //。",
        )
    assert isinstance(trigger, str)
    return trigger


def load_symbol_catalog(
    path: str | Path | None = None,
) -> dict[str, SymbolDefinition]:
    """Load the trigger-independent packaged symbol catalog."""
    entries = _require_entries(
        _read_json(
            path,
            default_resource="symbols.json",
            label="符号目录",
        ),
        label="符号目录",
    )
    catalog: dict[str, SymbolDefinition] = {}
    first_positions: dict[str, int] = {}
    required_fields = ("id", "name", "category", "output")

    for position, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise DictionaryError(f"符号目录第 {position} 项必须是 JSON 对象。")

        missing_fields = _missing_fields(entry, required_fields)
        if missing_fields:
            fields = "、".join(missing_fields)
            raise DictionaryError(
                f"符号目录第 {position} 项缺少必需字段：{fields}。",
            )

        symbol_id = entry["id"]
        name = entry["name"]
        category = entry["category"]
        output = entry["output"]

        for field_name, value in (
            ("id", symbol_id),
            ("name", name),
            ("category", category),
            ("output", output),
        ):
            if not isinstance(value, str):
                raise DictionaryError(
                    f"符号目录第 {position} 项的 {field_name} 必须是字符串。",
                )
            if not value:
                raise DictionaryError(
                    f"符号目录第 {position} 项的 {field_name} 不能为空。",
                )
            if value != value.strip():
                raise DictionaryError(
                    f"符号目录第 {position} 项的 {field_name} "
                    "不得包含意外的前后空格。",
                )

        assert isinstance(symbol_id, str)
        assert isinstance(name, str)
        assert isinstance(category, str)
        assert isinstance(output, str)

        if _SYMBOL_ID_PATTERN.fullmatch(symbol_id) is None:
            raise DictionaryError(
                f"符号目录第 {position} 项的 id“{symbol_id}”格式非法。",
            )
        if output.count(CURSOR_PLACEHOLDER) > 1:
            raise DictionaryError(
                f"符号目录第 {position} 项“{symbol_id}”包含多个 "
                f"{CURSOR_PLACEHOLDER}。",
            )
        if symbol_id in catalog:
            first_position = first_positions[symbol_id]
            raise DictionaryError(
                f"符号目录第 {position} 项的 id“{symbol_id}”重复；"
                f"它已在第 {first_position} 项定义。",
            )

        catalog[symbol_id] = SymbolDefinition(
            symbol_id=symbol_id,
            name=name,
            category=category,
            output=output,
        )
        first_positions[symbol_id] = position

    return catalog


def load_bindings(
    path: str | Path | None = None,
    *,
    catalog: dict[str, SymbolDefinition] | None = None,
) -> dict[str, str]:
    """Load trigger-to-symbol bindings and resolve their output templates."""
    active_catalog = load_symbol_catalog() if catalog is None else catalog
    entries = _require_entries(
        _read_json(
            path,
            default_resource="default_bindings.json",
            label="快捷绑定",
        ),
        label="快捷绑定",
    )
    bindings: dict[str, str] = {}
    first_positions: dict[str, int] = {}

    for position, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise DictionaryError(f"快捷绑定第 {position} 项必须是 JSON 对象。")

        missing_fields = _missing_fields(entry, ("trigger", "symbol_id"))
        if missing_fields:
            fields = "、".join(missing_fields)
            raise DictionaryError(
                f"快捷绑定第 {position} 项缺少必需字段：{fields}。",
            )

        trigger = _validate_trigger(
            entry["trigger"],
            position=position,
            label="快捷绑定",
        )
        symbol_id = entry["symbol_id"]
        if not isinstance(symbol_id, str):
            raise DictionaryError(
                f"快捷绑定第 {position} 项的 symbol_id 必须是字符串。",
            )
        if not symbol_id:
            raise DictionaryError(
                f"快捷绑定第 {position} 项的 symbol_id 不能为空。",
            )
        if trigger in bindings:
            first_position = first_positions[trigger]
            raise DictionaryError(
                f"快捷绑定第 {position} 项的 trigger“{trigger}”重复；"
                f"它已在第 {first_position} 项定义。",
            )
        if symbol_id not in active_catalog:
            raise DictionaryError(
                f"快捷绑定第 {position} 项引用了不存在的符号 "
                f"id“{symbol_id}”。",
            )

        bindings[trigger] = active_catalog[symbol_id].output
        first_positions[trigger] = position

    return bindings


def validate_direct_bindings(raw_data: object) -> dict[str, str]:
    """Validate direct ``trigger``-to-``output`` binding entries."""
    entries = _require_entries(raw_data, label="词库")
    symbols: dict[str, str] = {}
    first_positions: dict[str, int] = {}

    for position, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise DictionaryError(
                f"词库第 {position} 项必须是包含 trigger 和 output 的 JSON 对象。",
            )

        missing_fields = _missing_fields(entry, ("trigger", "output"))
        if missing_fields:
            fields = "、".join(missing_fields)
            raise DictionaryError(f"词库第 {position} 项缺少必需字段：{fields}。")

        trigger = _validate_trigger(
            entry["trigger"],
            position=position,
            label="词库",
        )
        output = entry["output"]
        if not isinstance(output, str):
            raise DictionaryError(f"词库第 {position} 项的 output 必须是字符串。")
        if output == "":
            raise DictionaryError(f"词库第 {position} 项的 output 不能为空。")
        if trigger in symbols:
            first_position = first_positions[trigger]
            raise DictionaryError(
                f"词库第 {position} 项的 trigger“{trigger}”重复；"
                f"它已在第 {first_position} 项定义。",
            )

        symbols[trigger] = output
        first_positions[trigger] = position

    return symbols


def load_dictionary(path: str | Path | None = None) -> dict[str, str]:
    """Load compatibility bindings or validate a legacy direct dictionary."""
    if path is not None:
        return validate_direct_bindings(
            _read_json(
                path,
                default_resource="default_bindings.json",
                label="词库",
            ),
        )

    return load_bindings()
