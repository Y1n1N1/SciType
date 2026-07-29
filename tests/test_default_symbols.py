"""Table-driven tests for the symbol dictionary packaged with SciType 0.4.0."""

from importlib.resources import files
import json
import unittest

from scitype import parse_text
from scitype.dictionary import (
    load_bindings,
    load_dictionary,
    load_symbol_catalog,
)
from scitype.template import CURSOR_PLACEHOLDER, RenderedTemplate, render_template


EXPECTED_SYMBOLS = {
    "//": "/",
    "/xw": "φ",
    "/jdz": "|${cursor}|",
    "/jf": "∫${cursor}dx",
    "/gh": "√(${cursor})",
    "/fs": "(${cursor})/()",
    "/wq": "∞",
    "/xy": "≤",
    "/dy": "≥",
    "/bd": "≠",
    "/yd": "≈",
    "/zb": "∝",
    "/qy": "→",
    "/yh": "⇒",
    "/dj": "⇔",
    "/qh": "∑",
    "/lc": "∏",
    "/pd": "∂",
    "/td": "∇",
    "/jh": "±",
    "/cheng": "×",
    "/chu": "÷",
    "/dc": "·",
    "/jd": "°",
    "/sy": "∈",
    "/bsy": "∉",
    "/kj": "∅",
    "/jj": "∩",
    "/bj": "∪",
    "/ry": "∀",
    "/cz": "∃",
    "/pi": "π",
    "/gm": "γ",
    "/dgm": "Γ",
    "/sg": "σ",
    "/dsg": "Σ",
    "/fi": "φ",
    "/dfi": "Φ",
    "/og": "ω",
    "/dog": "Ω",
}


class DefaultSymbolDictionaryTests(unittest.TestCase):
    def test_every_requested_command_parses_to_expected_output(self) -> None:
        for trigger, expected_output in EXPECTED_SYMBOLS.items():
            with self.subTest(trigger=trigger):
                self.assertEqual(parse_text(trigger), expected_output)

    def test_packaged_dictionary_contains_exact_requested_entries(self) -> None:
        self.assertEqual(load_dictionary(), EXPECTED_SYMBOLS)

    def test_default_dictionary_has_no_duplicate_triggers(self) -> None:
        bindings = load_bindings()

        # load_bindings() itself rejects duplicates before constructing the
        # mapping; the exact count also guards against accidental omissions.
        self.assertEqual(len(bindings), len(EXPECTED_SYMBOLS))
        self.assertEqual(len(bindings), 40)

    def test_default_entries_have_safe_template_and_whitespace(self) -> None:
        for symbol_id, symbol in load_symbol_catalog().items():
            with self.subTest(symbol_id=symbol_id):
                self.assertEqual(symbol.output, symbol.output.strip())
                self.assertLessEqual(
                    symbol.output.count(CURSOR_PLACEHOLDER),
                    1,
                )

        for trigger in load_bindings():
            with self.subTest(trigger=trigger):
                self.assertTrue(trigger)
                self.assertEqual(trigger, trigger.strip())

    def test_square_root_template_places_cursor_inside_parentheses(self) -> None:
        self.assertEqual(
            render_template(parse_text("/gh")),
            RenderedTemplate(text="√()", cursor_left_moves=1),
        )

    def test_unknown_command_is_still_unchanged(self) -> None:
        self.assertEqual(parse_text("/unknown"), "/unknown")

    def test_catalog_entries_do_not_contain_user_triggers(self) -> None:
        catalog_resource = (
            files("scitype").joinpath("data").joinpath("symbols.json")
        )
        with catalog_resource.open("r", encoding="utf-8") as file:
            raw_catalog = json.load(file)

        self.assertEqual(len(raw_catalog), 39)
        self.assertTrue(all("trigger" not in entry for entry in raw_catalog))

    def test_compatibility_aliases_can_share_one_symbol(self) -> None:
        bindings = load_bindings()

        self.assertEqual(bindings["/xw"], "φ")
        self.assertEqual(bindings["/fi"], "φ")

    def test_professional_semantic_aliases_are_not_added(self) -> None:
        bindings = load_bindings()

        self.assertNotIn("/yl", bindings)
        self.assertNotIn("/bzpc", bindings)


if __name__ == "__main__":
    unittest.main()
