"""Quiet Utility page for managing user-owned A-to-B bindings."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .binding_editor import BindingEditor
from .design_tokens import SPACING


class BindingPage(QWidget):
    """Compose navigation-independent binding list and editor regions."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("bindingPage")

        title = QLabel("我的绑定")
        title.setObjectName("pageTitle")
        subtitle = QLabel("管理你自己的 A → B 快捷输入")
        subtitle.setObjectName("secondaryText")
        subtitle.setWordWrap(True)

        header = QVBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(SPACING.sm)
        header.addWidget(title)
        header.addWidget(subtitle)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(SPACING.sm)
        splitter.addWidget(self._create_list_surface())
        splitter.addWidget(self._create_editor_stack())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 480])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            SPACING.xl,
            SPACING.xl,
            SPACING.xl,
            SPACING.xl,
        )
        layout.setSpacing(SPACING.xl)
        layout.addLayout(header)
        layout.addWidget(splitter, 1)

    def _create_list_surface(self) -> QWidget:
        surface = QWidget()
        surface.setObjectName("surface")
        surface.setMinimumWidth(250)
        surface.setMaximumWidth(380)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("bindingSearch")
        self.search_input.setPlaceholderText("搜索触发词或输出")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setAccessibleName("搜索用户绑定")

        self.new_button = QPushButton("新建绑定")
        self.new_button.setObjectName("primaryButton")
        self.new_button.setToolTip("新建绑定（Ctrl+N）")

        search_row = QHBoxLayout()
        search_row.setContentsMargins(0, 0, 0, 0)
        search_row.setSpacing(SPACING.sm)
        search_row.addWidget(self.search_input, 1)
        search_row.addWidget(self.new_button)

        self.list_view = QListView()
        self.list_view.setObjectName("bindingList")
        self.list_view.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection,
        )
        self.list_view.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers,
        )
        self.list_view.setUniformItemSizes(True)
        self.list_view.setAccessibleName("用户绑定列表")

        self.list_empty = self._create_empty_state()
        self.list_stack = QStackedWidget()
        self.list_stack.addWidget(self.list_empty)
        self.list_stack.addWidget(self.list_view)

        surface_layout = QVBoxLayout(surface)
        surface_layout.setContentsMargins(
            SPACING.lg,
            SPACING.lg,
            SPACING.lg,
            SPACING.lg,
        )
        surface_layout.setSpacing(SPACING.md)
        surface_layout.addLayout(search_row)
        surface_layout.addWidget(self.list_stack, 1)
        return surface

    def _create_empty_state(self) -> QFrame:
        state = QFrame()
        state.setObjectName("emptyState")
        state.setFrameShape(QFrame.Shape.NoFrame)

        self.empty_title = QLabel("还没有用户绑定")
        self.empty_title.setObjectName("emptyTitle")
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_title.setWordWrap(True)

        self.empty_description = QLabel(
            "创建一个自己记得住的触发词，\n"
            "快速输入难打或经常重复的内容。",
        )
        self.empty_description.setObjectName("emptyHint")
        self.empty_description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_description.setWordWrap(True)

        self.empty_example = QLabel("/weixiao  →  (＾▽＾)")
        self.empty_example.setObjectName("sourceMeta")
        self.empty_example.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_example.setWordWrap(True)

        self.empty_new_button = QPushButton("新建第一个绑定")
        self.empty_new_button.setObjectName("primaryButton")

        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(SPACING.md)
        content.addWidget(self.empty_title)
        content.addWidget(self.empty_description)
        content.addWidget(self.empty_example)
        content.addSpacing(SPACING.xs)
        content.addWidget(
            self.empty_new_button,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )

        layout = QVBoxLayout(state)
        layout.setContentsMargins(
            SPACING.lg,
            SPACING.xl,
            SPACING.lg,
            SPACING.xl,
        )
        layout.addStretch(1)
        layout.addLayout(content)
        layout.addStretch(1)
        return state

    def _create_editor_stack(self) -> QStackedWidget:
        self.editor_stack = QStackedWidget()
        self.editor_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        placeholder = QWidget()
        placeholder.setObjectName("editorPlaceholder")
        placeholder_title = QLabel("选择一个绑定，或新建绑定")
        placeholder_title.setObjectName("sectionTitle")
        placeholder_title.setWordWrap(True)
        placeholder_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder_hint = QLabel("在右侧编辑并预览，保存后查看顶部应用状态。")
        placeholder_hint.setObjectName("emptyHint")
        placeholder_hint.setWordWrap(True)
        placeholder_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        placeholder_layout = QVBoxLayout(placeholder)
        placeholder_layout.setContentsMargins(
            SPACING.xl,
            SPACING.xl,
            SPACING.xl,
            SPACING.xl,
        )
        placeholder_layout.addStretch(2)
        placeholder_layout.addWidget(placeholder_title)
        placeholder_layout.addWidget(placeholder_hint)
        placeholder_layout.addStretch(3)

        self.editor = BindingEditor()

        self.editor_stack.addWidget(placeholder)
        self.editor_stack.addWidget(self.editor)
        return self.editor_stack

    def show_list_state(
        self,
        *,
        total_count: int,
        filtered_count: int,
        editable: bool,
    ) -> None:
        """Switch between list, first-use state, and no-search-result state."""
        has_rows = filtered_count > 0
        self.list_stack.setCurrentIndex(1 if has_rows else 0)
        self.new_button.setVisible(total_count > 0)
        self.new_button.setEnabled(editable)
        self.empty_new_button.setEnabled(editable)
        if total_count == 0:
            self.empty_title.setText("还没有用户绑定")
            self.empty_description.setText(
                "创建一个自己记得住的触发词，\n"
                "快速输入难打或经常重复的内容。",
            )
            self.empty_example.setText("/weixiao  →  (＾▽＾)")
            self.empty_example.show()
            self.empty_new_button.setText("新建第一个绑定")
            self.empty_new_button.show()
        else:
            self.empty_title.setText("没有匹配的绑定")
            self.empty_description.setText("换一个关键词试试。")
            self.empty_example.hide()
            self.empty_new_button.hide()

    def set_editor_active(self, active: bool) -> None:
        """Keep save as the only dominant action while editing."""
        self.new_button.setObjectName(
            "quietButton" if active else "primaryButton",
        )
        self.new_button.style().unpolish(self.new_button)
        self.new_button.style().polish(self.new_button)
