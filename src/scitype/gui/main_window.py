"""Three-page Quiet Utility window for SciType settings."""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum, auto
from pathlib import Path
import sys

from PySide6.QtCore import QModelIndex, QRect, QSize, Qt, QUrl
from PySide6.QtGui import (
    QColor,
    QCloseEvent,
    QDesktopServices,
    QFont,
    QKeySequence,
    QPainter,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from scitype.catalog import CatalogEntry, PackValidationError
from scitype.gui.animations import (
    PageTransitionController,
    SelectionTransitionController,
    ToastController,
)
from scitype.gui.binding_list_model import BindingListModel
from scitype.gui.binding_page import BindingPage
from scitype.gui.design_tokens import COLORS, SPACING
from scitype.gui.dictionary_page import DictionaryPage
from scitype.gui.settings_page import SettingsPage
from scitype.gui.view_model import BindingSettingsViewModel


APPLICATION_VERSION = "0.6.0"


class UnsavedDecision(Enum):
    """Possible responses to an unsaved-change prompt."""

    SAVE = auto()
    DISCARD = auto()
    CANCEL = auto()


UnsavedPrompt = Callable[[QWidget], UnsavedDecision]
DeletePrompt = Callable[[QWidget], bool]
ReplacePackPrompt = Callable[[QWidget, str], bool]
OpenDirectory = Callable[[Path], bool]
SelectPackFile = Callable[[QWidget], Path | None]


class BindingItemDelegate(QStyledItemDelegate):
    """Paint a quiet two-line binding row with explicit enabled state."""

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> QSize:
        line = option.fontMetrics.lineSpacing()
        return QSize(option.rect.width(), line * 2 + SPACING.lg)

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

        trigger = str(index.data(BindingListModel.TriggerRole) or "")
        preview = str(index.data(BindingListModel.PreviewRole) or "")
        enabled = bool(index.data(BindingListModel.EnabledRole))
        line = option.fontMetrics.lineSpacing()
        top = row_rect.top() + SPACING.sm
        left = row_rect.left() + SPACING.md
        status_width = option.fontMetrics.horizontalAdvance("已停用") + 8
        text_width = max(0, row_rect.width() - SPACING.xl - status_width)

        trigger_font = QFont(option.font)
        trigger_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(trigger_font)
        painter.setPen(
            QColor(COLORS.text if enabled else COLORS.secondary_text),
        )
        painter.drawText(
            QRect(left, top, text_width, line),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            option.fontMetrics.elidedText(
                trigger,
                Qt.TextElideMode.ElideRight,
                text_width,
            ),
        )

        painter.setFont(option.font)
        painter.setPen(QColor(COLORS.muted_text))
        painter.drawText(
            QRect(left, top + line, text_width, line),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            option.fontMetrics.elidedText(
                preview,
                Qt.TextElideMode.ElideRight,
                text_width,
            ),
        )
        if not enabled:
            painter.drawText(
                QRect(
                    row_rect.right() - status_width,
                    top,
                    status_width,
                    line,
                ),
                Qt.AlignmentFlag.AlignCenter,
                "已停用",
            )
        painter.restore()


class MainWindow(QMainWindow):
    """Coordinate pages while all data rules remain in service layers."""

    BINDINGS_PAGE = 0
    DICTIONARY_PAGE = 1
    SETTINGS_PAGE = 2

    def __init__(
        self,
        view_model: BindingSettingsViewModel,
        *,
        unsaved_prompt: UnsavedPrompt | None = None,
        delete_prompt: DeletePrompt | None = None,
        replace_pack_prompt: ReplacePackPrompt | None = None,
        open_directory: OpenDirectory | None = None,
        select_pack_file: SelectPackFile | None = None,
        animations_enabled: bool | None = None,
    ) -> None:
        super().__init__()
        self.view_model = view_model
        self._unsaved_prompt = unsaved_prompt or self._default_unsaved_prompt
        self._delete_prompt = delete_prompt or self._default_delete_prompt
        self._replace_pack_prompt = (
            replace_pack_prompt or self._default_replace_pack_prompt
        )
        self._open_directory = (
            open_directory or self._default_open_directory
        )
        self._select_pack_file = (
            select_pack_file or self._default_select_pack_file
        )
        self._syncing_selection = False
        self._syncing_navigation = False
        self._last_page_index = self.BINDINGS_PAGE

        self.setWindowTitle("SciType 设置")
        self.resize(960, 640)
        self.setMinimumSize(780, 520)

        self.binding_page = BindingPage()
        self.dictionary_page = DictionaryPage(view_model.catalog)
        self.settings_page = SettingsPage(version=APPLICATION_VERSION)
        self.page_stack = QStackedWidget()
        self.page_stack.setObjectName("pageStack")
        self.page_stack.addWidget(self.binding_page)
        self.page_stack.addWidget(self.dictionary_page)
        self.page_stack.addWidget(self.settings_page)

        content = QWidget()
        content.setObjectName("pageRoot")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        self.error_banner = self._create_error_banner()
        self.runtime_status_banner = self._create_runtime_status_banner()
        content_layout.addWidget(self.error_banner)
        content_layout.addWidget(self.runtime_status_banner)
        content_layout.addWidget(self.page_stack, 1)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._create_navigation())
        root.addWidget(content, 1)
        self.setCentralWidget(central)

        self.page_transition = PageTransitionController(
            self.page_stack,
            enabled=animations_enabled,
        )
        self.toast_label = QLabel()
        self.toast_label.setObjectName("operationStatus")
        self.toast_label.hide()
        self.statusBar().addPermanentWidget(self.toast_label)
        self.toast = ToastController(
            self.toast_label,
            enabled=animations_enabled,
        )
        self.statusBar().showMessage("设置程序已就绪")

        self._install_binding_model()
        self.binding_selection_transition = SelectionTransitionController(
            self.binding_page.list_view,
            enabled=animations_enabled,
        )
        self.catalog_selection_transition = SelectionTransitionController(
            self.dictionary_page.list_view,
            enabled=animations_enabled,
        )
        self._publish_compatibility_attributes()
        self._connect_signals()
        self._install_shortcuts()
        self._set_tab_order()
        self._refresh_empty_state()
        self._refresh_runtime_status()
        self._show_navigation_page(self.BINDINGS_PAGE, animate=False)

    def _create_navigation(self) -> QWidget:
        rail = QWidget()
        rail.setObjectName("navigationRail")
        rail.setFixedWidth(176)

        brand = QLabel("SciType")
        brand.setObjectName("brandTitle")
        caption = QLabel("Quiet Utility")
        caption.setObjectName("brandCaption")

        self.bindings_nav_button = self._nav_button("我的绑定")
        self.dictionary_nav_button = self._nav_button("词典")
        self.settings_nav_button = self._nav_button("设置")
        self.nav_buttons = (
            self.bindings_nav_button,
            self.dictionary_nav_button,
            self.settings_nav_button,
        )
        group = QButtonGroup(self)
        group.setExclusive(True)
        for index, button in enumerate(self.nav_buttons):
            group.addButton(button, index)
        self._navigation_group = group

        layout = QVBoxLayout(rail)
        layout.setContentsMargins(
            SPACING.lg,
            SPACING.xl,
            SPACING.lg,
            SPACING.lg,
        )
        layout.setSpacing(SPACING.sm)
        layout.addWidget(brand)
        layout.addWidget(caption)
        layout.addSpacing(SPACING.xl)
        for button in self.nav_buttons:
            layout.addWidget(button)
        layout.addStretch(1)
        return rail

    @staticmethod
    def _nav_button(text: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("navButton")
        button.setCheckable(True)
        return button

    def _install_binding_model(self) -> None:
        self.list_model = BindingListModel(self.view_model)
        self.binding_page.list_view.setModel(self.list_model)
        self.binding_page.list_view.setItemDelegate(
            BindingItemDelegate(self.binding_page.list_view),
        )

    def _publish_compatibility_attributes(self) -> None:
        """Keep the original V0.6 test and integration surface stable."""
        self.search_input = self.binding_page.search_input
        self.new_button = self.binding_page.new_button
        self.list_view = self.binding_page.list_view
        self.list_stack = self.binding_page.list_stack
        self.list_empty_label = self.binding_page.empty_description
        self.editor_stack = self.binding_page.editor_stack
        self.editor = self.binding_page.editor

    def _connect_signals(self) -> None:
        for index, button in enumerate(self.nav_buttons):
            button.clicked.connect(
                lambda _checked=False, target=index: (
                    self._on_navigation_requested(target)
                ),
            )

        self.search_input.textChanged.connect(self._on_search_changed)
        self.new_button.clicked.connect(self._on_new_requested)
        self.binding_page.empty_new_button.clicked.connect(
            self._on_new_requested,
        )
        self.list_view.selectionModel().currentChanged.connect(
            self._on_current_row_changed,
        )
        self.editor.draftChanged.connect(self._on_draft_changed)
        self.editor.saveRequested.connect(self._save_current)
        self.editor.cancelRequested.connect(self._cancel_current)
        self.editor.deleteRequested.connect(self._delete_current)

        self.dictionary_page.copyRequested.connect(
            self._copy_catalog_trigger,
        )
        self.dictionary_page.createCustomRequested.connect(
            self._create_custom_from_catalog,
        )
        self.dictionary_page.openPacksRequested.connect(
            self._open_packs_directory,
        )
        self.dictionary_page.importPackRequested.connect(
            self._import_pack,
        )
        self.dictionary_page.enabledChangeRequested.connect(
            self._set_catalog_entry_enabled,
        )

        self.settings_page.openConfigRequested.connect(
            self._open_config_directory,
        )
        self.settings_page.openLogsRequested.connect(
            self._open_log_directory,
        )
        self.settings_page.openLicensesRequested.connect(
            self._open_third_party_notices,
        )
        self.settings_page.refreshStatusRequested.connect(
            self._refresh_runtime_status,
        )

    def _install_shortcuts(self) -> None:
        self.shortcut_new = QShortcut(QKeySequence.StandardKey.New, self)
        self.shortcut_new.activated.connect(self._shortcut_new)
        self.shortcut_save = QShortcut(QKeySequence.StandardKey.Save, self)
        self.shortcut_save.activated.connect(self._shortcut_save)
        self.shortcut_find = QShortcut(QKeySequence.StandardKey.Find, self)
        self.shortcut_find.activated.connect(self._focus_page_search)
        self.shortcut_save_complete = QShortcut(
            QKeySequence("Ctrl+Return"),
            self,
        )
        self.shortcut_save_complete.activated.connect(self._shortcut_save)
        self.shortcut_save_complete_keypad = QShortcut(
            QKeySequence("Ctrl+Enter"),
            self,
        )
        self.shortcut_save_complete_keypad.activated.connect(
            self._shortcut_save,
        )
        self.shortcut_escape = QShortcut(QKeySequence("Escape"), self)
        self.shortcut_escape.activated.connect(self._shortcut_escape)
        self.shortcut_delete = QShortcut(
            QKeySequence("Delete"),
            self.list_view,
        )
        self.shortcut_delete.setContext(Qt.ShortcutContext.WidgetShortcut)
        self.shortcut_delete.activated.connect(self._delete_current)

    def _set_tab_order(self) -> None:
        QWidget.setTabOrder(
            self.editor.trigger_input,
            self.editor.replacement_input,
        )
        QWidget.setTabOrder(
            self.editor.replacement_input,
            self.editor.enabled_checkbox,
        )
        QWidget.setTabOrder(
            self.editor.enabled_checkbox,
            self.editor.save_button,
        )

    def _create_error_banner(self) -> QFrame:
        banner = QFrame()
        banner.setObjectName("errorBanner")
        banner.setVisible(self.view_model.has_load_error)

        self.error_message = QLabel(self.view_model.load_error_message)
        self.error_message.setWordWrap(True)
        self.open_folder_button = QPushButton("打开配置文件夹")
        self.open_folder_button.clicked.connect(self._open_config_directory)
        self.dismiss_error_button = QPushButton("取消")
        self.dismiss_error_button.setObjectName("quietButton")
        self.dismiss_error_button.clicked.connect(banner.hide)

        layout = QHBoxLayout(banner)
        layout.setContentsMargins(
            SPACING.lg,
            SPACING.md,
            SPACING.lg,
            SPACING.md,
        )
        layout.setSpacing(SPACING.sm)
        layout.addWidget(self.error_message, 1)
        layout.addWidget(self.open_folder_button)
        layout.addWidget(self.dismiss_error_button)
        return banner

    def _create_runtime_status_banner(self) -> QFrame:
        banner = QFrame()
        banner.setObjectName("runtimeStatusBanner")
        self.runtime_status_message = QLabel()
        self.runtime_status_message.setObjectName("runtimeStatusMessage")
        self.runtime_status_message.setWordWrap(True)
        layout = QHBoxLayout(banner)
        layout.setContentsMargins(
            SPACING.lg,
            SPACING.sm,
            SPACING.lg,
            SPACING.sm,
        )
        layout.addWidget(self.runtime_status_message, 1)
        return banner

    def _on_navigation_requested(self, target: int) -> None:
        if self._syncing_navigation:
            return
        if (
            self.page_stack.currentIndex() == self.BINDINGS_PAGE
            and target != self.BINDINGS_PAGE
            and not self._resolve_unsaved_changes()
        ):
            self._sync_navigation_button(self.BINDINGS_PAGE)
            return
        self._show_navigation_page(target)

    def _show_navigation_page(
        self,
        index: int,
        *,
        animate: bool = True,
    ) -> None:
        self._refresh_runtime_status()
        self._last_page_index = index
        self._sync_navigation_button(index)
        if animate:
            self.page_transition.show(index)
        else:
            self.page_stack.setCurrentIndex(index)

    def _sync_navigation_button(self, index: int) -> None:
        self._syncing_navigation = True
        try:
            self.nav_buttons[index].setChecked(True)
        finally:
            self._syncing_navigation = False

    def _on_search_changed(self, text: str) -> None:
        self.list_model.set_query(text)
        self._refresh_empty_state()
        self._sync_list_selection()

    def _on_new_requested(self) -> None:
        if not self._resolve_unsaved_changes():
            return
        if not self.view_model.can_edit:
            self._show_feedback(
                self.view_model.load_error_message,
                success=False,
            )
            return
        self.view_model.begin_new()
        self._clear_list_selection()
        self._show_current_draft()

    def _on_current_row_changed(
        self,
        current: QModelIndex,
        _previous: QModelIndex,
    ) -> None:
        if self._syncing_selection or not current.isValid():
            return
        source_index = self.list_model.source_index_for_row(current.row())
        if source_index is None:
            return
        if source_index == self.view_model.selected_index:
            return
        if not self._resolve_unsaved_changes():
            self._sync_list_selection()
            return
        self.view_model.select_binding(source_index)
        self._show_current_draft()

    def _on_draft_changed(
        self,
        trigger: str,
        replacement: str,
        enabled: bool,
    ) -> None:
        self.view_model.update_draft(
            trigger=trigger,
            replacement=replacement,
            enabled=enabled,
        )
        self._render_validation(show_errors=True)
        self.editor.set_preview(self.view_model.preview_text())

    def _save_current(self) -> bool:
        result = self.view_model.save_current()
        if not result.success:
            self.editor.set_validation(
                self.view_model.validate_current_draft(),
                show_errors=True,
            )
            self.editor.show_status(result.message, success=False)
            return False

        self.list_model.refresh()
        self.dictionary_page.refresh_snapshot(self.view_model.catalog)
        self._refresh_empty_state()
        self._show_current_draft()
        self._sync_list_selection()
        self.editor.show_status(result.message, success=True)
        self._refresh_runtime_status(saved=True)
        self._show_feedback(result.message, success=True)
        return True

    def _cancel_current(self) -> None:
        self.view_model.cancel_changes()
        self._show_current_draft()
        self._sync_list_selection()

    def _delete_current(self) -> None:
        if self.view_model.selected_index is None:
            return
        if not self._delete_prompt(self):
            return
        result = self.view_model.delete_selected()
        if not result.success:
            self.editor.show_status(result.message, success=False)
            return
        self.list_model.refresh()
        self.dictionary_page.refresh_snapshot(self.view_model.catalog)
        self._refresh_empty_state()
        self._show_current_draft()
        self._refresh_runtime_status(saved=True)
        self._show_feedback(result.message, success=True)

    def _resolve_unsaved_changes(self) -> bool:
        if not self.view_model.is_dirty:
            return True
        decision = self._unsaved_prompt(self)
        if decision is UnsavedDecision.CANCEL:
            return False
        if decision is UnsavedDecision.SAVE:
            return self._save_current()
        self.view_model.cancel_changes()
        return True

    def _show_current_draft(self) -> None:
        draft = self.view_model.draft
        if draft is None:
            self.editor_stack.setCurrentIndex(0)
            self.binding_page.set_editor_active(False)
            return
        self.editor_stack.setCurrentIndex(1)
        self.binding_page.set_editor_active(True)
        self.editor.set_draft(
            draft,
            is_new=self.view_model.is_new,
            editable=self.view_model.can_edit,
        )
        self.editor.set_preview(self.view_model.preview_text())
        self._render_validation(show_errors=False)

    def _render_validation(self, *, show_errors: bool) -> None:
        self.editor.set_validation(
            self.view_model.validate_current_draft(),
            show_errors=show_errors,
        )

    def _refresh_empty_state(self) -> None:
        self.binding_page.show_list_state(
            total_count=len(self.view_model.bindings),
            filtered_count=self.list_model.rowCount(),
            editable=self.view_model.can_edit,
        )

    def _clear_list_selection(self) -> None:
        self._syncing_selection = True
        try:
            self.list_view.clearSelection()
            self.list_view.setCurrentIndex(QModelIndex())
        finally:
            self._syncing_selection = False

    def _sync_list_selection(self) -> None:
        source_index = self.view_model.selected_index
        self._syncing_selection = True
        try:
            if source_index is None:
                self.list_view.clearSelection()
                self.list_view.setCurrentIndex(QModelIndex())
                return
            row = self.list_model.row_for_source_index(source_index)
            if row is None:
                self.list_view.clearSelection()
                self.list_view.setCurrentIndex(QModelIndex())
                return
            self.list_view.setCurrentIndex(self.list_model.index(row, 0))
        finally:
            self._syncing_selection = False

    def _shortcut_new(self) -> None:
        self._show_navigation_page(self.BINDINGS_PAGE)
        self._on_new_requested()

    def _shortcut_save(self) -> None:
        if (
            self.page_stack.currentIndex() == self.BINDINGS_PAGE
            and self.view_model.draft is not None
        ):
            self._save_current()

    def _shortcut_escape(self) -> None:
        if (
            self.page_stack.currentIndex() == self.BINDINGS_PAGE
            and self.view_model.draft is not None
        ):
            self._cancel_current()

    def _focus_page_search(self) -> None:
        if self.page_stack.currentIndex() == self.BINDINGS_PAGE:
            self.search_input.setFocus()
            self.search_input.selectAll()
        elif self.page_stack.currentIndex() == self.DICTIONARY_PAGE:
            self.dictionary_page.focus_search()

    def _copy_catalog_trigger(self, trigger: str) -> None:
        QApplication.clipboard().setText(trigger)
        self._show_feedback("已复制触发词", success=True)

    def _create_custom_from_catalog(self, entry: CatalogEntry) -> None:
        if not self._resolve_unsaved_changes():
            return
        if not self.view_model.can_edit:
            self._show_feedback(
                self.view_model.load_error_message,
                success=False,
            )
            return
        self.view_model.begin_new(
            trigger=entry.trigger,
            replacement=entry.replacement,
            enabled=True,
        )
        self._clear_list_selection()
        self._show_navigation_page(self.BINDINGS_PAGE)
        self._show_current_draft()

    def _set_catalog_entry_enabled(
        self,
        entry: CatalogEntry,
        enabled: bool,
    ) -> None:
        result = self.view_model.set_catalog_entry_enabled(
            entry,
            enabled=enabled,
        )
        self.dictionary_page.refresh_snapshot(self.view_model.catalog)
        if not result.success:
            self._show_feedback(result.message, success=False)
            return

        self.list_model.refresh()
        self._clear_list_selection()
        self._show_current_draft()
        self._refresh_empty_state()
        self._refresh_runtime_status(saved=True)
        self._show_feedback(result.message, success=True)

    def _refresh_runtime_status(
        self,
        *_args: object,
        saved: bool = False,
    ) -> None:
        message = self.view_model.runtime_status_message(saved=saved)
        self.runtime_status_message.setText(message)
        self.runtime_status_message.setMinimumHeight(
            self.runtime_status_message.sizeHint().height(),
        )
        self.settings_page.set_runtime_status(message)

    def _import_pack(self) -> None:
        source = self._select_pack_file(self)
        if source is None:
            return
        try:
            plan = self.view_model.prepare_pack_import(source)
            allow_replace = False
            if plan.requires_replacement_confirmation:
                allow_replace = self._replace_pack_prompt(
                    self,
                    plan.document.metadata.name,
                )
                if not allow_replace:
                    return
            self.view_model.import_pack(
                plan,
                allow_replace=allow_replace,
            )
        except PackValidationError as error:
            self._show_feedback(
                _pack_error_message(error),
                success=False,
            )
            return
        self.dictionary_page.refresh_snapshot(self.view_model.catalog)
        self._show_feedback("扩展包已导入", success=True)

    def _open_config_directory(self) -> None:
        self._open_directory_with_feedback(
            self.view_model.config_directory,
            success_message="已打开用户配置文件夹",
        )

    def _open_log_directory(self) -> None:
        self._open_directory_with_feedback(
            self.view_model.config_directory,
            success_message="已打开日志文件夹",
        )

    def _open_packs_directory(self) -> None:
        self._open_directory_with_feedback(
            self.view_model.catalog.packs_directory,
            success_message="已打开扩展包文件夹",
        )

    def _open_third_party_notices(self) -> None:
        path = _third_party_notice_path()
        if path is None or not path.is_file():
            self._show_feedback("未找到第三方许可证说明", success=False)
            return
        if self._default_open_path(path):
            self._show_feedback("已打开第三方许可证说明", success=True)
        else:
            self._show_feedback("无法打开第三方许可证说明", success=False)

    def _open_directory_with_feedback(
        self,
        directory: Path | None,
        *,
        success_message: str,
    ) -> None:
        if directory is None:
            self._show_feedback("无法确定本地目录", success=False)
            return
        if self._open_directory(directory):
            self._show_feedback(success_message, success=True)
        else:
            self._show_feedback("无法打开本地目录", success=False)

    def _show_feedback(self, message: str, *, success: bool) -> None:
        self.statusBar().showMessage(message, 2400)
        self.toast.show(message, success=success)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._resolve_unsaved_changes():
            event.accept()
        else:
            event.ignore()

    @staticmethod
    def _default_unsaved_prompt(parent: QWidget) -> UnsavedDecision:
        box = QMessageBox(parent)
        box.setWindowTitle("未保存的修改")
        box.setText("当前绑定有未保存的修改。")
        box.setInformativeText("保存后再继续，还是放弃这些修改？")
        save_button = box.addButton(
            "保存",
            QMessageBox.ButtonRole.AcceptRole,
        )
        discard_button = box.addButton(
            "放弃",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save_button)
        box.exec()
        if box.clickedButton() is save_button:
            return UnsavedDecision.SAVE
        if box.clickedButton() is discard_button:
            return UnsavedDecision.DISCARD
        return UnsavedDecision.CANCEL

    @staticmethod
    def _default_delete_prompt(parent: QWidget) -> bool:
        box = QMessageBox(parent)
        box.setWindowTitle("删除绑定")
        box.setText("确定删除当前用户绑定吗？")
        box.setInformativeText("此操作会立即保存。")
        delete_button = box.addButton(
            "删除",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return box.clickedButton() is delete_button

    @staticmethod
    def _default_replace_pack_prompt(parent: QWidget, pack_name: str) -> bool:
        box = QMessageBox(parent)
        box.setWindowTitle("替换扩展包")
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText("已存在同一 pack id 的扩展包。")
        box.setInformativeText(
            f"是否用所选文件替换“{pack_name}”？原文件将被替换。",
        )
        replace_button = box.addButton(
            "替换",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return box.clickedButton() is replace_button

    @staticmethod
    def _default_open_directory(directory: Path) -> bool:
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            return False
        return QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(directory.resolve())),
        )

    @staticmethod
    def _default_open_path(path: Path) -> bool:
        return QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(path.resolve())),
        )

    @staticmethod
    def _default_select_pack_file(parent: QWidget) -> Path | None:
        filename, _selected_filter = QFileDialog.getOpenFileName(
            parent,
            "导入本地扩展包",
            "",
            "JSON 扩展包 (*.json)",
        )
        return Path(filename) if filename else None


def _third_party_notice_path() -> Path | None:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "THIRD_PARTY_NOTICES.txt"
    project_root = Path(__file__).resolve().parents[3]
    return project_root / "packaging" / "THIRD_PARTY_NOTICES.txt"


def _pack_error_message(error: PackValidationError) -> str:
    if error.code.name == "INVALID_SCHEMA_VERSION":
        return "扩展包版本暂不支持，未导入。"
    if error.code.name == "DUPLICATE_PACK_ID":
        return "扩展包目录存在重复 pack id，请先人工处理。"
    if error.code.name == "DESTINATION_CONFLICT":
        return "目标文件名已被其他扩展包占用，未导入。"
    return "扩展包验证或导入失败，原文件未被修改。"
