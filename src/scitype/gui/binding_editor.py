"""Reusable, keyboard-first editor for one SciType user binding."""

from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from scitype.gui.design_tokens import SPACING
from scitype.gui.animations import RevealController
from scitype.gui.view_model import BindingDraft, ValidationResult


class BindingEditor(QWidget):
    """Collect fields while leaving validation and persistence to services."""

    draftChanged = Signal(str, str, bool)
    saveRequested = Signal()
    cancelRequested = Signal()
    deleteRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("bindingEditor")

        self.heading = QLabel("绑定详情")
        self.heading.setObjectName("editorTitle")

        intro = QLabel("设置一个容易记住的触发词，以及它要输入的内容。")
        intro.setObjectName("secondaryText")
        intro.setWordWrap(True)

        trigger_label = QLabel("触发词 A")
        trigger_label.setObjectName("fieldLabel")
        self.trigger_input = QLineEdit()
        self.trigger_input.setObjectName("triggerInput")
        self.trigger_input.setPlaceholderText("例如 /weixiao")
        self.trigger_input.setClearButtonEnabled(True)
        self.trigger_input.setAccessibleName("触发词")
        for clear_button in self.trigger_input.findChildren(QToolButton):
            clear_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        trigger_hint = QLabel("以 / 开头，只使用小写英文字母和数字")
        trigger_hint.setObjectName("fieldHint")
        trigger_hint.setWordWrap(True)
        self.trigger_error = QLabel()
        self.trigger_error.setObjectName("fieldError")
        self.trigger_error.setWordWrap(True)
        self.trigger_error.hide()

        replacement_label = QLabel("输出内容 B")
        replacement_label.setObjectName("fieldLabel")
        self.replacement_input = QPlainTextEdit()
        self.replacement_input.setObjectName("replacementInput")
        self.replacement_input.setPlaceholderText(
            "例如：(＾▽＾) 或 ∫${cursor}dx",
        )
        self.replacement_input.setTabChangesFocus(True)
        editor_height = self.fontMetrics().lineSpacing() * 6 + 28
        self.replacement_input.setMinimumHeight(editor_height)
        self.replacement_input.setAccessibleName("输出内容")

        replacement_hint = QLabel(
            "支持中文、符号、换行；可选使用一个 ${cursor} 标记光标位置",
        )
        replacement_hint.setObjectName("fieldHint")
        replacement_hint.setWordWrap(True)
        self.replacement_error = QLabel()
        self.replacement_error.setObjectName("fieldError")
        self.replacement_error.setWordWrap(True)
        self.replacement_error.hide()
        self._error_reveals = {
            self.trigger_error: RevealController(self.trigger_error),
            self.replacement_error: RevealController(
                self.replacement_error,
            ),
        }

        self.enabled_checkbox = QCheckBox("启用此绑定")
        self.enabled_checkbox.setObjectName("enabledCheckbox")

        preview_label = QLabel("纯文本预览")
        preview_label.setObjectName("fieldLabel")
        self.preview = QPlainTextEdit()
        self.preview.setObjectName("bindingPreview")
        self.preview.setReadOnly(True)
        self.preview.setTabChangesFocus(True)
        preview_height = self.fontMetrics().lineSpacing() * 3 + 26
        self.preview.setMinimumHeight(preview_height)
        self.preview.setMaximumHeight(preview_height * 2)
        self.preview.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.preview.setAccessibleName("绑定预览")

        self.status_label = QLabel()
        self.status_label.setObjectName("operationStatus")
        self.status_label.setWordWrap(True)
        self.status_label.hide()

        self.delete_button = QPushButton("删除绑定")
        self.delete_button.setObjectName("dangerButton")
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setObjectName("quietButton")
        self.save_button = QPushButton("保存")
        self.save_button.setObjectName("primaryButton")
        self.save_button.setDefault(True)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(SPACING.sm)
        button_row.addWidget(self.delete_button)
        button_row.addStretch(1)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.save_button)

        form = QWidget()
        form.setObjectName("bindingEditorForm")
        form_layout = QVBoxLayout(form)
        form_layout.setContentsMargins(
            SPACING.xl,
            SPACING.xl,
            SPACING.xl,
            SPACING.md,
        )
        form_layout.setSpacing(SPACING.md)
        form_layout.addWidget(self.heading)
        form_layout.addWidget(intro)
        form_layout.addSpacing(SPACING.xs)
        form_layout.addWidget(trigger_label)
        form_layout.addWidget(self.trigger_input)
        form_layout.addWidget(trigger_hint)
        form_layout.addWidget(self.trigger_error)
        form_layout.addSpacing(SPACING.xs)
        form_layout.addWidget(replacement_label)
        form_layout.addWidget(self.replacement_input)
        form_layout.addWidget(replacement_hint)
        form_layout.addWidget(self.replacement_error)
        form_layout.addWidget(self.enabled_checkbox)
        form_layout.addSpacing(SPACING.xs)
        form_layout.addWidget(preview_label)
        form_layout.addWidget(self.preview)
        form_layout.addWidget(self.status_label)
        form_layout.addStretch(1)

        form_scroll = QScrollArea()
        form_scroll.setObjectName("editorScroll")
        form_scroll.setWidgetResizable(True)
        form_scroll.setFrameShape(QFrame.Shape.NoFrame)
        form_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        form_scroll.setWidget(form)

        footer = QWidget()
        footer.setObjectName("editorFooter")
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(
            SPACING.xl,
            SPACING.sm,
            SPACING.xl,
            SPACING.xl,
        )
        footer_layout.addLayout(button_row)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(form_scroll, 1)
        layout.addWidget(footer)

        self.trigger_input.textChanged.connect(self._emit_draft)
        self.replacement_input.textChanged.connect(self._emit_draft)
        self.enabled_checkbox.toggled.connect(self._emit_draft)
        self.save_button.clicked.connect(self.saveRequested)
        self.cancel_button.clicked.connect(self.cancelRequested)
        self.delete_button.clicked.connect(self.deleteRequested)

    def set_draft(
        self,
        draft: BindingDraft,
        *,
        is_new: bool,
        editable: bool,
    ) -> None:
        """Populate controls without treating the load as a user edit."""
        blockers = (
            QSignalBlocker(self.trigger_input),
            QSignalBlocker(self.replacement_input),
            QSignalBlocker(self.enabled_checkbox),
        )
        self.trigger_input.setText(draft.trigger)
        self.replacement_input.setPlainText(draft.replacement)
        self.enabled_checkbox.setChecked(draft.enabled)
        del blockers

        self.heading.setText("新建绑定" if is_new else "编辑绑定")
        self.set_editable(editable)
        self.delete_button.setVisible(not is_new)
        self.clear_status()
        if is_new and editable:
            self.trigger_input.setFocus()
            self.trigger_input.selectAll()

    def set_editable(self, editable: bool) -> None:
        for widget in (
            self.trigger_input,
            self.replacement_input,
            self.enabled_checkbox,
            self.save_button,
            self.cancel_button,
            self.delete_button,
        ):
            widget.setEnabled(editable)

    def set_validation(
        self,
        validation: ValidationResult,
        *,
        show_errors: bool = True,
    ) -> None:
        """Display field messages returned by the ViewModel."""
        trigger_message = validation.field_errors.get("trigger", "")
        replacement_message = validation.field_errors.get(
            "replacement",
            "",
        )
        self._set_error(
            self.trigger_input,
            self.trigger_error,
            trigger_message if show_errors else "",
        )
        self._set_error(
            self.replacement_input,
            self.replacement_error,
            replacement_message if show_errors else "",
        )
        self.save_button.setEnabled(
            self.trigger_input.isEnabled() and validation.is_valid,
        )

    def set_preview(self, text: str) -> None:
        self.preview.setPlainText(text)

    def show_status(self, message: str, *, success: bool) -> None:
        self.status_label.setText(message)
        self.status_label.setProperty("success", success)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.status_label.show()

    def clear_status(self) -> None:
        self.status_label.clear()
        self.status_label.hide()

    def _emit_draft(self, *_args: object) -> None:
        self.clear_status()
        self.draftChanged.emit(
            self.trigger_input.text(),
            self.replacement_input.toPlainText(),
            self.enabled_checkbox.isChecked(),
        )

    def _set_error(
        self,
        field: QWidget,
        label: QLabel,
        message: str,
    ) -> None:
        field.setProperty("invalid", bool(message))
        field.style().unpolish(field)
        field.style().polish(field)
        label.setText(message)
        self._error_reveals[label].set_visible(bool(message))
