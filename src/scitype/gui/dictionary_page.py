"""Read-only base and local-extension dictionary page."""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from scitype.catalog import (
    BASE_SOURCE_ID,
    CatalogEntry,
    CatalogSnapshot,
    CatalogSource,
    CatalogSourceKind,
    CatalogUserState,
    catalog_preview,
)
from scitype.gui.catalog_list_model import (
    CatalogListModel,
    catalog_status_text,
)
from scitype.gui.animations import SelectionTransitionController
from scitype.gui.design_tokens import COLORS, SPACING


class CatalogItemDelegate(QStyledItemDelegate):
    """Paint three compact text lines using current font metrics."""

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> QSize:
        line = option.fontMetrics.lineSpacing()
        return QSize(option.rect.width(), line * 3 + SPACING.lg)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        painter.save()
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        row_rect = option.rect.adjusted(
            SPACING.xs,
            2,
            -SPACING.xs,
            -2,
        )
        if selected or hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            background = QColor(
                COLORS.accent_soft if selected else COLORS.page,
            )
            if selected and self.parent() is not None:
                progress = float(
                    self.parent().property(
                        SelectionTransitionController.PROPERTY_NAME,
                    )
                    or 1.0,
                )
                background.setAlphaF(0.35 + 0.65 * progress)
            painter.setBrush(background)
            painter.drawRoundedRect(row_rect, 8, 8)

        name = str(index.data(CatalogListModel.NameRole) or "")
        trigger = str(index.data(CatalogListModel.TriggerRole) or "")
        preview = str(index.data(CatalogListModel.PreviewRole) or "")
        category = str(index.data(CatalogListModel.CategoryRole) or "")
        source = str(index.data(CatalogListModel.SourceRole) or "")
        status = str(index.data(CatalogListModel.StatusRole) or "")

        left = row_rect.left() + SPACING.md
        width = max(0, row_rect.width() - SPACING.xl)
        line = option.fontMetrics.lineSpacing()
        top = row_rect.top() + SPACING.sm

        heading_font = QFont(option.font)
        heading_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(heading_font)
        painter.setPen(QColor(COLORS.text))
        painter.drawText(
            QRect(left, top, width, line),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            option.fontMetrics.elidedText(
                f"{name}    {trigger}",
                Qt.TextElideMode.ElideRight,
                width,
            ),
        )

        painter.setFont(option.font)
        painter.setPen(QColor(COLORS.secondary_text))
        painter.drawText(
            QRect(left, top + line, width, line),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            option.fontMetrics.elidedText(
                preview,
                Qt.TextElideMode.ElideRight,
                width,
            ),
        )
        footer = f"{category} · {source}"
        if status:
            footer = f"{footer} · {status}"
        painter.setPen(
            QColor(COLORS.warning if status else COLORS.muted_text),
        )
        painter.drawText(
            QRect(left, top + line * 2, width, line),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            option.fontMetrics.elidedText(
                footer,
                Qt.TextElideMode.ElideRight,
                width,
            ),
        )
        painter.restore()


class DictionaryPage(QWidget):
    """Search and inspect immutable catalog sources."""

    copyRequested = Signal(str)
    createCustomRequested = Signal(object)
    openPacksRequested = Signal()
    importPackRequested = Signal()
    enabledChangeRequested = Signal(object, bool)

    def __init__(
        self,
        snapshot: CatalogSnapshot,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("dictionaryPage")
        self._selected_entry: CatalogEntry | None = None

        title = QLabel("词典")
        title.setObjectName("pageTitle")
        subtitle = QLabel("查找内置命令与本地只读扩展包")
        subtitle.setObjectName("secondaryText")
        subtitle.setWordWrap(True)

        self.open_packs_button = QPushButton("打开扩展包文件夹")
        self.open_packs_button.setObjectName("quietButton")
        self.import_pack_button = QPushButton("导入 JSON 扩展包")

        header_actions = QHBoxLayout()
        header_actions.setContentsMargins(0, 0, 0, 0)
        header_actions.setSpacing(SPACING.sm)
        header_actions.addStretch(1)
        header_actions.addWidget(self.open_packs_button)
        header_actions.addWidget(self.import_pack_button)

        heading_row = QHBoxLayout()
        heading_row.setContentsMargins(0, 0, 0, 0)
        heading_text = QVBoxLayout()
        heading_text.setContentsMargins(0, 0, 0, 0)
        heading_text.setSpacing(SPACING.sm)
        heading_text.addWidget(title)
        heading_text.addWidget(subtitle)
        heading_row.addLayout(heading_text, 1)
        heading_row.addLayout(header_actions)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("catalogSearch")
        self.search_input.setPlaceholderText("搜索名称、触发词、输出或分类")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setAccessibleName("搜索词典")

        self.category_filter = QComboBox()
        self.category_filter.setAccessibleName("词典分类")
        self.source_filter = QComboBox()
        self.source_filter.setAccessibleName("词典来源")

        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(0, 0, 0, 0)
        filter_row.setSpacing(SPACING.sm)
        filter_row.addWidget(self.search_input, 1)
        filter_row.addWidget(self.category_filter)
        filter_row.addWidget(self.source_filter)

        self.source_metadata = QLabel()
        self.source_metadata.setObjectName("sourceMeta")
        self.source_metadata.setWordWrap(True)
        self.source_metadata.setTextFormat(Qt.TextFormat.PlainText)
        self.pack_failure_notice = QLabel()
        self.pack_failure_notice.setObjectName("inlineNotice")
        self.pack_failure_notice.setWordWrap(True)
        self.pack_failure_notice.setTextFormat(Qt.TextFormat.PlainText)

        self.model = CatalogListModel(snapshot)
        self.list_view = QListView()
        self.list_view.setObjectName("catalogList")
        self.list_view.setModel(self.model)
        self.list_view.setItemDelegate(CatalogItemDelegate(self.list_view))
        self.list_view.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection,
        )
        self.list_view.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers,
        )
        self.list_view.setAccessibleName("词典条目列表")

        self.no_results = QLabel("没有匹配的词条")
        self.no_results.setObjectName("emptyHint")
        self.no_results.setWordWrap(True)
        self.no_results.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.list_stack = QStackedWidget()
        self.list_stack.addWidget(self.no_results)
        self.list_stack.addWidget(self.list_view)

        list_surface = QWidget()
        list_surface.setObjectName("surface")
        list_surface.setMinimumWidth(350)
        list_layout = QVBoxLayout(list_surface)
        list_layout.setContentsMargins(
            SPACING.lg,
            SPACING.lg,
            SPACING.lg,
            SPACING.lg,
        )
        list_layout.setSpacing(SPACING.md)
        list_layout.addLayout(filter_row)
        list_layout.addWidget(self.source_metadata)
        list_layout.addWidget(self.pack_failure_notice)
        list_layout.addWidget(self.list_stack, 1)

        self.detail_stack = QStackedWidget()
        self.detail_stack.addWidget(self._create_detail_placeholder())
        self.detail_stack.addWidget(self._create_detail())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(SPACING.sm)
        splitter.addWidget(list_surface)
        splitter.addWidget(self.detail_stack)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([520, 340])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            SPACING.xl,
            SPACING.xl,
            SPACING.xl,
            SPACING.xl,
        )
        layout.setSpacing(SPACING.xl)
        layout.addLayout(heading_row)
        layout.addWidget(splitter, 1)

        self.search_input.textChanged.connect(self._apply_filters)
        self.category_filter.currentIndexChanged.connect(
            self._apply_filters,
        )
        self.source_filter.currentIndexChanged.connect(
            self._on_source_changed,
        )
        self.list_view.selectionModel().currentChanged.connect(
            self._on_selection_changed,
        )
        self.copy_button.clicked.connect(self._copy_selected)
        self.custom_button.clicked.connect(self._create_custom)
        self.open_packs_button.clicked.connect(self.openPacksRequested)
        self.import_pack_button.clicked.connect(self.importPackRequested)
        self.enabled_checkbox.toggled.connect(self._toggle_selected)

        self.refresh_snapshot(snapshot)

    def _create_detail_placeholder(self) -> QWidget:
        placeholder = QWidget()
        placeholder.setObjectName("editorPlaceholder")
        title = QLabel("选择一个词条查看详情")
        title.setObjectName("sectionTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)
        hint = QLabel("词典是只读的；需要修改时可创建自己的版本。")
        hint.setObjectName("emptyHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        layout = QVBoxLayout(placeholder)
        layout.setContentsMargins(
            SPACING.xl,
            SPACING.xl,
            SPACING.xl,
            SPACING.xl,
        )
        layout.addStretch(2)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addStretch(3)
        return placeholder

    def _create_detail(self) -> QWidget:
        detail = QWidget()
        detail.setObjectName("dictionaryDetail")

        self.detail_name = QLabel()
        self.detail_name.setObjectName("sectionTitle")
        self.detail_name.setWordWrap(True)
        self.detail_name.setTextFormat(Qt.TextFormat.PlainText)
        self.detail_trigger = self._detail_value()
        self.detail_category = self._detail_value()
        self.detail_source = self._detail_value()
        self.detail_status = self._detail_value()
        self.detail_status.setWordWrap(True)

        self.detail_preview = QPlainTextEdit()
        self.detail_preview.setObjectName("catalogPreview")
        self.detail_preview.setReadOnly(True)
        self.detail_preview.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.detail_preview.setMinimumHeight(
            self.fontMetrics().lineSpacing() * 2 + 26,
        )
        self.detail_preview.setAccessibleName("词典输出预览")

        self.copy_button = QPushButton("复制触发词")
        self.custom_button = QPushButton("创建自定义版本")
        self.custom_button.setObjectName("primaryButton")
        self.enabled_checkbox = QCheckBox("启用此快捷输入")
        self.enabled_checkbox.setObjectName("catalogEnabledCheckbox")
        self.conflict_toggle_notice = QLabel(
            "因触发词冲突，当前不可用于输入。",
        )
        self.conflict_toggle_notice.setObjectName("inlineNotice")
        self.conflict_toggle_notice.setWordWrap(True)
        self.conflict_toggle_notice.hide()

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(SPACING.sm)
        actions.addWidget(self.copy_button)
        actions.addStretch(1)
        actions.addWidget(self.custom_button)

        layout = QVBoxLayout(detail)
        layout.setContentsMargins(
            SPACING.xl,
            SPACING.xl,
            SPACING.xl,
            SPACING.xl,
        )
        layout.setSpacing(SPACING.md)
        layout.addWidget(self.detail_name)
        layout.addSpacing(SPACING.xs)
        self._add_detail_row(layout, "触发词", self.detail_trigger)
        self._add_detail_row(layout, "分类", self.detail_category)
        self._add_detail_row(layout, "来源", self.detail_source)
        self._add_detail_row(layout, "状态", self.detail_status)
        layout.addSpacing(SPACING.xs)
        preview_label = QLabel("输出预览")
        preview_label.setObjectName("detailLabel")
        layout.addWidget(preview_label)
        layout.addWidget(self.detail_preview)
        layout.addWidget(self.enabled_checkbox)
        layout.addWidget(self.conflict_toggle_notice)
        layout.addStretch(1)
        layout.addLayout(actions)
        return detail

    @staticmethod
    def _detail_value() -> QLabel:
        value = QLabel()
        value.setObjectName("detailValue")
        value.setTextFormat(Qt.TextFormat.PlainText)
        value.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse,
        )
        return value

    @staticmethod
    def _add_detail_row(
        layout: QVBoxLayout,
        label_text: str,
        value: QLabel,
    ) -> None:
        label = QLabel(label_text)
        label.setObjectName("detailLabel")
        layout.addWidget(label)
        layout.addWidget(value)

    def refresh_snapshot(self, snapshot: CatalogSnapshot) -> None:
        """Refresh rows and filter choices after a safe pack import."""
        category = self.category_filter.currentData()
        source = self.source_filter.currentData()
        self.model.set_snapshot(snapshot)

        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem("全部分类", None)
        for value in snapshot.categories:
            self.category_filter.addItem(value, value)
        category_index = self.category_filter.findData(category)
        self.category_filter.setCurrentIndex(max(0, category_index))
        self.category_filter.blockSignals(False)

        self.source_filter.blockSignals(True)
        self.source_filter.clear()
        self.source_filter.addItem("全部来源", None)
        for source_item in snapshot.sources:
            self.source_filter.addItem(
                source_item.name,
                source_item.source_id,
            )
        source_index = self.source_filter.findData(source)
        self.source_filter.setCurrentIndex(max(0, source_index))
        self.source_filter.blockSignals(False)

        self._selected_entry = None
        self.detail_stack.setCurrentIndex(0)
        self._update_source_metadata()
        self._update_failure_notice()
        self._apply_filters()

    def focus_search(self) -> None:
        self.search_input.setFocus()
        self.search_input.selectAll()

    def _apply_filters(self, *_args: object) -> None:
        self.model.set_filters(
            query=self.search_input.text(),
            category=self.category_filter.currentData(),
            source_id=self.source_filter.currentData(),
        )
        self.list_stack.setCurrentIndex(
            1 if self.model.rowCount() else 0,
        )
        self.list_view.clearSelection()
        self._selected_entry = None
        self.detail_stack.setCurrentIndex(0)

    def _on_source_changed(self, *_args: object) -> None:
        self._update_source_metadata()
        self._apply_filters()

    def _update_source_metadata(self) -> None:
        source_id = self.source_filter.currentData()
        sources = self.model.snapshot.sources
        if source_id is None:
            local_count = sum(
                source.kind is CatalogSourceKind.LOCAL_PACK
                for source in sources
            )
            self.source_metadata.setText(
                f"SciType 基础词典 · {local_count} 个本地扩展包",
            )
            return
        source = next(
            (
                candidate
                for candidate in sources
                if candidate.source_id == source_id
            ),
            None,
        )
        self.source_metadata.setText(
            self._source_summary(source) if source is not None else "",
        )

    @staticmethod
    def _source_summary(source: CatalogSource) -> str:
        parts = [source.name, source.version]
        if source.author:
            parts.append(source.author)
        parts.append(f"{source.entry_count} 项")
        return " · ".join(parts)

    def _update_failure_notice(self) -> None:
        failures = self.model.snapshot.failures
        if not failures:
            self.pack_failure_notice.clear()
            self.pack_failure_notice.hide()
            return
        details = "、".join(
            f"{failure.file_name}（{_failure_label(failure.code.name)}）"
            for failure in failures[:4]
        )
        if len(failures) > 4:
            details = f"{details}，另有 {len(failures) - 4} 个"
        self.pack_failure_notice.setText(
            f"扩展包加载失败：{details}。原文件已保留。",
        )
        self.pack_failure_notice.show()

    def _on_selection_changed(
        self,
        current: QModelIndex,
        _previous: QModelIndex,
    ) -> None:
        entry = self.model.entry_at(current.row()) if current.isValid() else None
        self._selected_entry = entry
        if entry is None:
            self.detail_stack.setCurrentIndex(0)
            return
        self.detail_name.setText(entry.name)
        self.detail_trigger.setText(entry.trigger)
        self.detail_category.setText(entry.category)
        self.detail_source.setText(entry.source_name)
        self.detail_status.setText(
            catalog_status_text(entry) or "可用",
        )
        self.detail_preview.setPlainText(
            catalog_preview(entry.replacement),
        )
        self.enabled_checkbox.blockSignals(True)
        self.enabled_checkbox.setChecked(
            entry.user_state is not CatalogUserState.DISABLED,
        )
        self.enabled_checkbox.blockSignals(False)
        has_conflict = entry.conflict is not None
        self.enabled_checkbox.setVisible(not has_conflict)
        self.conflict_toggle_notice.setVisible(has_conflict)
        self.detail_stack.setCurrentIndex(1)

    def _copy_selected(self) -> None:
        if self._selected_entry is not None:
            self.copyRequested.emit(self._selected_entry.trigger)

    def _create_custom(self) -> None:
        if self._selected_entry is not None:
            self.createCustomRequested.emit(self._selected_entry)

    def _toggle_selected(self, enabled: bool) -> None:
        if (
            self._selected_entry is not None
            and self._selected_entry.conflict is None
        ):
            self.enabledChangeRequested.emit(
                self._selected_entry,
                enabled,
            )

    def select_trigger(self, trigger: str) -> bool:
        """Select the first visible trigger, used by tests and manual checks."""
        for row in range(self.model.rowCount()):
            index = self.model.index(row, 0)
            if index.data(CatalogListModel.TriggerRole) == trigger:
                self.list_view.setCurrentIndex(index)
                return True
        return False


def _failure_label(code_name: str) -> str:
    labels = {
        "INVALID_JSON": "JSON 损坏",
        "INVALID_UTF8": "不是 UTF-8",
        "INVALID_SCHEMA_VERSION": "版本不支持",
        "DUPLICATE_PACK_ID": "pack id 重复",
        "INVALID_ENTRY": "词条无效",
        "READ_FAILED": "无法读取",
    }
    return labels.get(code_name, "格式无效")
