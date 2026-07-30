"""Tests for SciType dictionary loading and validation."""

import json
import os
from pathlib import Path
import tempfile
import unittest

from scitype.dictionary import (
    DictionaryError,
    load_bindings,
    load_dictionary,
    load_symbol_catalog,
)


_TEST_DIRECTORY = Path(__file__).resolve().parent


class DictionaryTests(unittest.TestCase):
    @staticmethod
    def _write_dictionary(directory: str, content: str) -> Path:
        path = Path(directory, "symbols.json")
        path.write_text(content, encoding="utf-8")
        return path

    def test_default_dictionary_loads_outside_project_root(self) -> None:
        original_directory = Path.cwd()

        with tempfile.TemporaryDirectory(dir=_TEST_DIRECTORY) as temporary_directory:
            try:
                os.chdir(temporary_directory)
                symbols = load_dictionary()
            finally:
                os.chdir(original_directory)

        self.assertEqual(symbols["/xw"], "φ")
        self.assertEqual(symbols["/jf"], "∫${cursor}dx")

    def test_utf8_symbols_are_loaded(self) -> None:
        entries = [{"trigger": "/xw", "output": "符号 φ，根号 √"}]

        with tempfile.TemporaryDirectory(dir=_TEST_DIRECTORY) as temporary_directory:
            path = self._write_dictionary(
                temporary_directory,
                json.dumps(entries, ensure_ascii=False),
            )

            self.assertEqual(load_dictionary(path)["/xw"], "符号 φ，根号 √")

    def test_duplicate_trigger_is_rejected(self) -> None:
        entries = [
            {"trigger": "/xw", "output": "φ"},
            {"trigger": "/xw", "output": "θ"},
        ]

        with tempfile.TemporaryDirectory(dir=_TEST_DIRECTORY) as temporary_directory:
            path = self._write_dictionary(
                temporary_directory,
                json.dumps(entries, ensure_ascii=False),
            )

            with self.assertRaisesRegex(DictionaryError, "trigger“/xw”重复"):
                load_dictionary(path)

    def test_missing_required_fields_are_rejected(self) -> None:
        cases = [
            ([{"output": "φ"}], "trigger"),
            ([{"trigger": "/xw"}], "output"),
        ]

        with tempfile.TemporaryDirectory(dir=_TEST_DIRECTORY) as temporary_directory:
            for entries, missing_field in cases:
                with self.subTest(missing_field=missing_field):
                    path = self._write_dictionary(
                        temporary_directory,
                        json.dumps(entries, ensure_ascii=False),
                    )

                    with self.assertRaisesRegex(
                        DictionaryError,
                        f"缺少必需字段：{missing_field}",
                    ):
                        load_dictionary(path)

    def test_empty_trigger_is_rejected(self) -> None:
        entries = [{"trigger": "", "output": "φ"}]

        with tempfile.TemporaryDirectory(dir=_TEST_DIRECTORY) as temporary_directory:
            path = self._write_dictionary(
                temporary_directory,
                json.dumps(entries, ensure_ascii=False),
            )

            with self.assertRaisesRegex(DictionaryError, "trigger 不能为空"):
                load_dictionary(path)

    def test_invalid_trigger_formats_are_rejected(self) -> None:
        cases = [
            ("xw", "必须以 / 开头"),
            ("/XW", "格式非法"),
        ]

        with tempfile.TemporaryDirectory(dir=_TEST_DIRECTORY) as temporary_directory:
            for trigger, expected_message in cases:
                with self.subTest(trigger=trigger):
                    entries = [{"trigger": trigger, "output": "φ"}]
                    path = self._write_dictionary(
                        temporary_directory,
                        json.dumps(entries, ensure_ascii=False),
                    )

                    with self.assertRaisesRegex(DictionaryError, expected_message):
                        load_dictionary(path)

    def test_trigger_body_can_include_ascii_digits(self) -> None:
        entries = [{"trigger": "/a12", "output": "数字触发"}]

        with tempfile.TemporaryDirectory(dir=_TEST_DIRECTORY) as temporary_directory:
            path = self._write_dictionary(
                temporary_directory,
                json.dumps(entries, ensure_ascii=False),
            )

            self.assertEqual(load_dictionary(path)["/a12"], "数字触发")

    def test_malformed_json_is_rejected(self) -> None:
        malformed_json = '[{"trigger": "/xw", "output": "φ"}'

        with tempfile.TemporaryDirectory(dir=_TEST_DIRECTORY) as temporary_directory:
            path = self._write_dictionary(temporary_directory, malformed_json)

            with self.assertRaisesRegex(DictionaryError, "JSON 格式损坏"):
                load_dictionary(path)

    def test_non_object_entry_is_rejected(self) -> None:
        entries = ["/xw"]

        with tempfile.TemporaryDirectory(dir=_TEST_DIRECTORY) as temporary_directory:
            path = self._write_dictionary(
                temporary_directory,
                json.dumps(entries, ensure_ascii=False),
            )

            with self.assertRaisesRegex(DictionaryError, "必须是.*JSON 对象"):
                load_dictionary(path)

    def test_duplicate_default_binding_trigger_is_rejected(self) -> None:
        entries = [
            {"trigger": "/fi", "symbol_id": "greek.phi.lower"},
            {"trigger": "/fi", "symbol_id": "greek.phi.lower"},
        ]

        with tempfile.TemporaryDirectory(dir=_TEST_DIRECTORY) as temporary_directory:
            path = self._write_dictionary(
                temporary_directory,
                json.dumps(entries, ensure_ascii=False),
            )

            with self.assertRaisesRegex(DictionaryError, "trigger“/fi”重复"):
                load_bindings(path)

    def test_binding_with_unknown_symbol_id_is_rejected(self) -> None:
        entries = [{"trigger": "/bad", "symbol_id": "missing.symbol"}]

        with tempfile.TemporaryDirectory(dir=_TEST_DIRECTORY) as temporary_directory:
            path = self._write_dictionary(
                temporary_directory,
                json.dumps(entries, ensure_ascii=False),
            )

            with self.assertRaisesRegex(DictionaryError, "不存在的符号"):
                load_bindings(path)

    def test_duplicate_catalog_id_is_rejected(self) -> None:
        entry = {
            "id": "greek.phi.lower",
            "name": "小写斐",
            "category": "希腊字母",
            "output": "φ",
        }

        with tempfile.TemporaryDirectory(dir=_TEST_DIRECTORY) as temporary_directory:
            path = self._write_dictionary(
                temporary_directory,
                json.dumps([entry, entry], ensure_ascii=False),
            )

            with self.assertRaisesRegex(DictionaryError, "id.*重复"):
                load_symbol_catalog(path)

    def test_catalog_rejects_multiple_cursor_placeholders(self) -> None:
        entries = [
            {
                "id": "structure.invalid",
                "name": "非法模板",
                "category": "结构输入",
                "output": "${cursor}+${cursor}",
            },
        ]

        with tempfile.TemporaryDirectory(dir=_TEST_DIRECTORY) as temporary_directory:
            path = self._write_dictionary(
                temporary_directory,
                json.dumps(entries, ensure_ascii=False),
            )

            with self.assertRaisesRegex(DictionaryError, "包含多个.*cursor"):
                load_symbol_catalog(path)


if __name__ == "__main__":
    unittest.main()
