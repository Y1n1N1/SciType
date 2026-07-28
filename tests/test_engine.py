"""Tests for the SciType V0.1 single-command engine."""

import unittest

from scitype import parse_text


class ParseTextTests(unittest.TestCase):
    def test_legacy_phi_alias(self) -> None:
        self.assertEqual(parse_text("/xw"), "φ")

    def test_absolute_value_command(self) -> None:
        self.assertEqual(parse_text("/jdz"), "|${cursor}|")

    def test_integral_command(self) -> None:
        self.assertEqual(parse_text("/jf"), "∫${cursor}dx")

    def test_square_root_command(self) -> None:
        self.assertEqual(parse_text("/gh"), "√(${cursor})")

    def test_unknown_abbreviation_is_unchanged(self) -> None:
        self.assertEqual(parse_text("/abc"), "/abc")

    def test_literal_slash(self) -> None:
        self.assertEqual(parse_text("//"), "/")

    def test_empty_string(self) -> None:
        self.assertEqual(parse_text(""), "")

    def test_plain_chinese_text_is_unchanged(self) -> None:
        self.assertEqual(parse_text("这是一段普通中文文本"), "这是一段普通中文文本")

    def test_cursor_placeholder_is_preserved(self) -> None:
        result = parse_text("/jdz")

        self.assertEqual(result, "|${cursor}|")
        self.assertIn("${cursor}", result)


if __name__ == "__main__":
    unittest.main()
