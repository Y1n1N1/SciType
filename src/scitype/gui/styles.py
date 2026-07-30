"""Quiet Utility stylesheet assembled from central design tokens."""

from __future__ import annotations

from .design_tokens import COLORS, RADII, TYPE


APP_STYLE = f"""
QWidget {{
    color: {COLORS.text};
    background: {COLORS.page};
    font-size: {TYPE.body_px}px;
}}
QLabel {{
    background: transparent;
}}
QMainWindow {{
    background: {COLORS.page};
}}
QWidget#navigationRail {{
    background: {COLORS.surface};
    border-right: 1px solid {COLORS.border};
}}
QWidget#pageRoot, QWidget#bindingPage, QWidget#dictionaryPage,
QWidget#settingsPage, QWidget#editorPlaceholder {{
    background: {COLORS.page};
}}
QWidget#surface, QWidget#bindingEditor, QWidget#dictionaryDetail,
QWidget#settingsSurface, QFrame#emptyState {{
    background: {COLORS.surface};
    border: 1px solid {COLORS.border};
    border-radius: {RADII.surface}px;
}}
QWidget#bindingEditorForm, QWidget#editorFooter,
QScrollArea#editorScroll,
QScrollArea#editorScroll QWidget#qt_scrollarea_viewport {{
    background: {COLORS.surface};
    border: none;
}}
QLabel#brandTitle {{
    font-size: 18px;
    font-weight: 600;
    color: {COLORS.text};
}}
QLabel#brandCaption, QLabel#secondaryText, QLabel#emptyHint,
QLabel#fieldHint, QLabel#sourceMeta, QLabel#settingsDescription {{
    color: {COLORS.secondary_text};
    font-size: {TYPE.helper_px}px;
}}
QLabel#pageTitle {{
    font-size: {TYPE.page_title_px}px;
    font-weight: 600;
    color: {COLORS.text};
}}
QLabel#sectionTitle, QLabel#editorTitle {{
    font-size: {TYPE.section_title_px}px;
    font-weight: 600;
    color: {COLORS.text};
}}
QLabel#emptyTitle {{
    font-size: 16px;
    font-weight: 600;
    color: {COLORS.text};
}}
QLabel#fieldLabel, QLabel#detailLabel {{
    color: {COLORS.secondary_text};
    font-size: {TYPE.caption_px}px;
    font-weight: 600;
}}
QLabel#detailValue {{
    color: {COLORS.text};
}}
QLabel#fieldError {{
    color: {COLORS.danger};
    font-size: {TYPE.caption_px}px;
}}
QLabel#operationStatus {{
    color: {COLORS.danger};
    padding: 8px 10px;
    background: {COLORS.danger_soft};
    border: 1px solid #FECDCA;
    border-radius: {RADII.small}px;
}}
QLabel#operationStatus[success="true"] {{
    color: {COLORS.success};
    background: {COLORS.success_soft};
    border-color: #ABEFC6;
}}
QLabel#inlineNotice {{
    color: {COLORS.warning};
    background: {COLORS.warning_soft};
    border: 1px solid #FEDF89;
    border-radius: {RADII.small}px;
    padding: 9px 11px;
}}
QFrame#errorBanner {{
    background: {COLORS.warning_soft};
    border: 1px solid #FEDF89;
    border-radius: {RADII.small}px;
}}
QFrame#runtimeStatusBanner {{
    background: {COLORS.accent_soft};
    border: none;
    border-bottom: 1px solid {COLORS.border};
}}
QLabel#runtimeStatusMessage {{
    color: {COLORS.secondary_text};
}}
QFrame#divider {{
    background: {COLORS.divider};
    border: none;
    max-height: 1px;
}}
QLineEdit, QPlainTextEdit, QComboBox {{
    background: {COLORS.surface};
    border: 1px solid {COLORS.border};
    border-radius: {RADII.control}px;
    padding: 8px 10px;
    selection-background-color: {COLORS.accent};
}}
QLineEdit:hover, QPlainTextEdit:hover, QComboBox:hover {{
    border-color: #CDD2DA;
}}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{
    border-color: {COLORS.accent_focus};
}}
QLineEdit[invalid="true"], QPlainTextEdit[invalid="true"] {{
    border-color: {COLORS.danger};
}}
QLineEdit:disabled, QPlainTextEdit:disabled, QComboBox:disabled {{
    color: {COLORS.muted_text};
    background: {COLORS.divider};
}}
QPlainTextEdit#bindingPreview, QPlainTextEdit#catalogPreview {{
    background: {COLORS.page};
    color: {COLORS.text};
}}
QListView {{
    background: {COLORS.surface};
    border: none;
    outline: none;
}}
QListView::item {{
    border-radius: {RADII.small}px;
    margin: 2px 6px;
}}
QListView::item:hover {{
    background: {COLORS.page};
}}
QListView::item:selected {{
    background: {COLORS.accent_soft};
    color: {COLORS.text};
}}
QPushButton {{
    min-height: 18px;
    background: {COLORS.surface};
    border: 1px solid {COLORS.border};
    border-radius: {RADII.control}px;
    padding: 8px 14px;
}}
QPushButton:hover {{
    background: {COLORS.page};
    border-color: #CDD2DA;
}}
QPushButton:focus {{
    border-color: {COLORS.accent_focus};
}}
QPushButton:pressed {{
    background: {COLORS.divider};
}}
QPushButton:disabled {{
    color: {COLORS.muted_text};
    background: {COLORS.divider};
}}
QPushButton#primaryButton {{
    color: #FFFFFF;
    background: {COLORS.accent};
    border-color: {COLORS.accent};
    font-weight: 600;
}}
QPushButton#primaryButton:hover {{
    background: {COLORS.accent_hover};
    border-color: {COLORS.accent_hover};
}}
QPushButton#quietButton {{
    background: transparent;
    border-color: transparent;
    color: {COLORS.secondary_text};
    padding-left: 10px;
    padding-right: 10px;
}}
QPushButton#quietButton:hover {{
    background: {COLORS.page};
    color: {COLORS.text};
}}
QPushButton#dangerButton {{
    color: {COLORS.danger};
    background: transparent;
    border-color: transparent;
}}
QPushButton#dangerButton:hover {{
    background: {COLORS.danger_soft};
}}
QPushButton#navButton {{
    min-height: 22px;
    text-align: left;
    background: transparent;
    border: 1px solid transparent;
    color: {COLORS.secondary_text};
    padding: 9px 12px;
}}
QPushButton#navButton:hover {{
    background: {COLORS.page};
    color: {COLORS.text};
}}
QPushButton#navButton:checked {{
    background: {COLORS.accent_soft};
    color: {COLORS.text};
    border-color: transparent;
    font-weight: 600;
}}
QCheckBox {{
    spacing: 8px;
}}
QSplitter::handle {{
    background: transparent;
    width: 8px;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #D0D5DD;
    border-radius: 4px;
    min-height: 28px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
    background: transparent;
    border: none;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}
QStatusBar {{
    background: {COLORS.surface};
    border-top: 1px solid {COLORS.border};
    color: {COLORS.secondary_text};
    font-size: {TYPE.caption_px}px;
}}
QToolTip {{
    color: {COLORS.text};
    background: {COLORS.surface};
    border: 1px solid {COLORS.border};
    padding: 5px;
}}
"""
