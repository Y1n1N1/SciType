"""Central Quiet Utility design tokens for the Qt Widgets interface."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SpacingTokens:
    xs: int = 4
    sm: int = 8
    md: int = 12
    lg: int = 16
    xl: int = 24
    xxl: int = 32


@dataclass(frozen=True, slots=True)
class RadiusTokens:
    small: int = 8
    control: int = 10
    surface: int = 12


@dataclass(frozen=True, slots=True)
class ColorTokens:
    page: str = "#F6F7F9"
    surface: str = "#FFFFFF"
    text: str = "#1F2937"
    secondary_text: str = "#667085"
    muted_text: str = "#98A2B3"
    border: str = "#E4E7EC"
    divider: str = "#F0F2F5"
    accent: str = "#4F6BED"
    accent_hover: str = "#4059D0"
    accent_soft: str = "#EEF1FF"
    accent_focus: str = "#8094F2"
    danger: str = "#B42318"
    danger_soft: str = "#FEF3F2"
    success: str = "#067647"
    success_soft: str = "#ECFDF3"
    warning: str = "#B54708"
    warning_soft: str = "#FFFAEB"


@dataclass(frozen=True, slots=True)
class TypographyTokens:
    page_title_px: int = 23
    section_title_px: int = 17
    body_px: int = 14
    helper_px: int = 13
    caption_px: int = 12


SPACING = SpacingTokens()
RADII = RadiusTokens()
COLORS = ColorTokens()
TYPE = TypographyTokens()

PAGE_TRANSITION_MS = 168
LIST_SELECTION_TRANSITION_MS = 120
FIELD_ERROR_FADE_MS = 120
TOAST_FADE_MS = 140
TOAST_VISIBLE_MS = 2000
