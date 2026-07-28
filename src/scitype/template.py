"""Operating-system-independent template rendering for SciType."""

from dataclasses import dataclass


CURSOR_PLACEHOLDER = "${cursor}"


class TemplateRenderError(ValueError):
    """Raised when a template uses unsupported placeholder syntax."""


@dataclass(frozen=True, slots=True)
class RenderedTemplate:
    """Text ready for insertion and the required left-arrow count."""

    text: str
    cursor_left_moves: int


def render_template(template: str) -> RenderedTemplate:
    """Render one optional cursor placeholder into text and a cursor offset."""
    placeholder_count = template.count(CURSOR_PLACEHOLDER)
    if placeholder_count > 1:
        raise TemplateRenderError(
            "当前版本每个模板最多支持一个 ${cursor}，"
            f"实际发现 {placeholder_count} 个",
        )

    if placeholder_count == 0:
        return RenderedTemplate(text=template, cursor_left_moves=0)

    before_cursor, after_cursor = template.split(CURSOR_PLACEHOLDER)
    return RenderedTemplate(
        text=f"{before_cursor}{after_cursor}",
        cursor_left_moves=len(after_cursor),
    )
