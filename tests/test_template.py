"""Tests for single-cursor template rendering."""

import unittest

from scitype.template import (
    RenderedTemplate,
    TemplateRenderError,
    render_template,
)


class RenderTemplateTests(unittest.TestCase):
    def test_plain_text_is_unchanged(self) -> None:
        self.assertEqual(
            render_template("φ"),
            RenderedTemplate(text="φ", cursor_left_moves=0),
        )

    def test_absolute_value_places_cursor_between_bars(self) -> None:
        self.assertEqual(
            render_template("|${cursor}|"),
            RenderedTemplate(text="||", cursor_left_moves=1),
        )

    def test_integral_places_cursor_before_dx(self) -> None:
        self.assertEqual(
            render_template("∫${cursor}dx"),
            RenderedTemplate(text="∫dx", cursor_left_moves=2),
        )

    def test_trailing_cursor_needs_no_movement(self) -> None:
        self.assertEqual(
            render_template("√${cursor}"),
            RenderedTemplate(text="√", cursor_left_moves=0),
        )

    def test_placeholder_only_renders_empty_text(self) -> None:
        self.assertEqual(
            render_template("${cursor}"),
            RenderedTemplate(text="", cursor_left_moves=0),
        )

    def test_empty_template_is_valid(self) -> None:
        self.assertEqual(
            render_template(""),
            RenderedTemplate(text="", cursor_left_moves=0),
        )

    def test_multiple_cursor_placeholders_are_rejected(self) -> None:
        with self.assertRaisesRegex(
            TemplateRenderError,
            "最多支持一个.*实际发现 2 个",
        ):
            render_template("${cursor}x${cursor}")


if __name__ == "__main__":
    unittest.main()
