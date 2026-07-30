"""Offscreen tests for the Quiet Utility information architecture."""

from __future__ import annotations

from io import StringIO
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SCITYPE_DISABLE_ANIMATIONS", "1")

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from scitype.catalog import CatalogUserState
from scitype.gui.app import create_application
from scitype.gui.catalog_list_model import CatalogListModel
from scitype.gui.design_tokens import COLORS, RADII, SPACING
from scitype.gui.main_window import MainWindow
from scitype.gui.view_model import BindingSettingsViewModel
from scitype.user_bindings import (
    UserBinding,
    create_user_binding_document,
    save_user_bindings,
)


class QuietUtilityWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = create_application(["scitype-layout-test"])

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.local_root = Path(self.temporary_directory.name)
        self.config_path = self.local_root / "SciType" / "user_bindings.json"
        self.packs_directory = self.config_path.parent / "packs"
        self.windows: list[MainWindow] = []
        self.opened_paths: list[Path] = []

    def tearDown(self) -> None:
        for window in self.windows:
            window.hide()
            window.deleteLater()
        QCoreApplication.processEvents()
        self.temporary_directory.cleanup()

    def make_window(
        self,
        *,
        animations_enabled: bool = False,
    ) -> MainWindow:
        view_model = BindingSettingsViewModel(
            config_path=self.config_path,
            packs_directory=self.packs_directory,
            instance_probe=lambda: False,
        )
        window = MainWindow(
            view_model,
            open_directory=self._open_directory,
            animations_enabled=animations_enabled,
        )
        self.windows.append(window)
        window.show()
        QCoreApplication.processEvents()
        return window

    def _open_directory(self, path: Path) -> bool:
        self.opened_paths.append(path)
        return True

    def seed(self, *bindings: UserBinding) -> None:
        save_user_bindings(
            create_user_binding_document(bindings),
            self.config_path,
        )

    def write_pack(self) -> Path:
        self.packs_directory.mkdir(parents=True, exist_ok=True)
        path = self.packs_directory / "kaomoji.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "pack": {
                        "id": "scitype.kaomoji.zh-cn",
                        "name": "中文颜文字",
                        "version": "1.0.0",
                        "author": "SciType Community",
                    },
                    "entries": [
                        {
                            "name": "微笑",
                            "category": "颜文字",
                            "trigger": "/weixiao",
                            "replacement": "(＾▽＾)",
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return path

    @staticmethod
    def catalog_triggers(window: MainWindow) -> list[str]:
        return [
            str(
                window.dictionary_page.model.index(row, 0).data(
                    CatalogListModel.TriggerRole,
                ),
            )
            for row in range(window.dictionary_page.model.rowCount())
        ]

    def test_three_primary_navigation_entries_and_default_page(self) -> None:
        window = self.make_window()

        self.assertEqual(
            [button.text() for button in window.nav_buttons],
            ["我的绑定", "词典", "设置"],
        )
        self.assertEqual(
            window.page_stack.currentIndex(),
            MainWindow.BINDINGS_PAGE,
        )
        self.assertTrue(window.bindings_nav_button.isChecked())

    def test_binding_editor_keeps_primary_action_visible(self) -> None:
        window = self.make_window()
        window.new_button.click()
        for size in (window.size(), window.minimumSize()):
            window.resize(size)
            QCoreApplication.processEvents()
            with self.subTest(size=(size.width(), size.height())):
                self.assertTrue(window.editor.save_button.isVisible())
                self.assertFalse(
                    window.editor.save_button.visibleRegion().isEmpty(),
                )
                button_bottom = window.editor.save_button.mapTo(
                    window,
                    window.editor.save_button.rect().bottomLeft(),
                ).y()
                self.assertLess(
                    button_bottom,
                    window.statusBar().geometry().top(),
                )

    def test_quiet_utility_tokens_are_central_and_low_saturation(self) -> None:
        self.assertEqual(
            (
                SPACING.xs,
                SPACING.sm,
                SPACING.md,
                SPACING.lg,
                SPACING.xl,
                SPACING.xxl,
            ),
            (4, 8, 12, 16, 24, 32),
        )
        self.assertEqual(
            (RADII.small, RADII.control, RADII.surface),
            (8, 10, 12),
        )
        self.assertEqual(COLORS.page, "#F6F7F9")
        self.assertEqual(COLORS.accent, "#4F6BED")

    def test_navigation_switches_pages_without_writing_configuration(
        self,
    ) -> None:
        window = self.make_window()
        self.assertFalse(self.config_path.exists())

        window.dictionary_nav_button.click()
        self.assertEqual(
            window.page_stack.currentIndex(),
            MainWindow.DICTIONARY_PAGE,
        )
        window.settings_nav_button.click()
        self.assertEqual(
            window.page_stack.currentIndex(),
            MainWindow.SETTINGS_PAGE,
        )
        window.bindings_nav_button.click()

        self.assertEqual(
            window.page_stack.currentIndex(),
            MainWindow.BINDINGS_PAGE,
        )
        self.assertFalse(self.config_path.exists())

    def test_empty_state_wraps_without_fixed_text_height(self) -> None:
        window = self.make_window()

        self.assertTrue(window.binding_page.empty_title.wordWrap())
        self.assertTrue(window.binding_page.empty_description.wordWrap())
        self.assertGreater(
            window.binding_page.empty_description.maximumHeight(),
            window.binding_page.empty_description.sizeHint().height(),
        )
        self.assertIn(
            "还没有用户绑定",
            window.binding_page.empty_title.text(),
        )

    def test_new_binding_focus_and_declared_tab_order(self) -> None:
        window = self.make_window()
        window.binding_page.empty_new_button.click()
        QCoreApplication.processEvents()

        editor = window.editor
        self.assertTrue(editor.trigger_input.hasFocus())
        editor.trigger_input.setText("/ceshi")
        editor.replacement_input.setPlainText("示例文本")
        QTest.keyClick(editor.trigger_input, Qt.Key.Key_Tab)
        self.assertTrue(editor.replacement_input.hasFocus())
        QTest.keyClick(editor.replacement_input, Qt.Key.Key_Tab)
        self.assertTrue(editor.enabled_checkbox.hasFocus())
        QTest.keyClick(editor.enabled_checkbox, Qt.Key.Key_Tab)
        self.assertTrue(editor.save_button.hasFocus())

    def test_ctrl_shortcuts_create_save_find_and_escape(self) -> None:
        window = self.make_window()
        window.shortcut_new.activated.emit()
        window.editor.trigger_input.setText("/ceshi")
        window.editor.replacement_input.setPlainText("示例文本")
        window.shortcut_save.activated.emit()

        self.assertTrue(self.config_path.is_file())
        self.assertIn("保存成功", window.toast_label.text())

        window.editor.replacement_input.setPlainText("未保存修改")
        self.assertTrue(window.view_model.is_dirty)
        window.shortcut_escape.activated.emit()
        self.assertFalse(window.view_model.is_dirty)
        self.assertEqual(
            window.editor.replacement_input.toPlainText(),
            "示例文本",
        )

        window.shortcut_find.activated.emit()
        self.assertTrue(window.search_input.hasFocus())
        window.dictionary_nav_button.click()
        window.shortcut_find.activated.emit()
        self.assertTrue(window.dictionary_page.search_input.hasFocus())

    def test_dictionary_searches_name_trigger_output_and_category(self) -> None:
        window = self.make_window()
        window.dictionary_nav_button.click()

        for query, expected in (
            ("积分", "/jf"),
            ("/jf", "/jf"),
            ("∫", "/jf"),
            ("希腊字母", "/fi"),
        ):
            with self.subTest(query=query):
                window.dictionary_page.search_input.setText(query)
                QCoreApplication.processEvents()
                self.assertIn(expected, self.catalog_triggers(window))

    def test_dictionary_category_source_and_cursor_preview(self) -> None:
        self.write_pack()
        window = self.make_window()
        page = window.dictionary_page
        page.search_input.setText("积分")
        self.assertTrue(page.select_trigger("/jf"))

        self.assertEqual(page.detail_preview.toPlainText(), "∫│dx")
        self.assertIn("SciType 基础词典", page.detail_source.text())

        page.search_input.clear()
        category_index = page.category_filter.findData("希腊字母")
        page.category_filter.setCurrentIndex(category_index)
        QCoreApplication.processEvents()
        for row in range(page.model.rowCount()):
            self.assertEqual(
                page.model.index(row, 0).data(
                    CatalogListModel.CategoryRole,
                ),
                "希腊字母",
            )

        source_index = page.source_filter.findData(
            "scitype.kaomoji.zh-cn",
        )
        self.assertGreaterEqual(source_index, 0)
        page.category_filter.setCurrentIndex(0)
        page.source_filter.setCurrentIndex(source_index)
        QCoreApplication.processEvents()
        self.assertEqual(self.catalog_triggers(window), ["/weixiao"])
        self.assertIn("1.0.0", page.source_metadata.text())
        self.assertIn("SciType Community", page.source_metadata.text())
        self.assertIn("1 项", page.source_metadata.text())

    def test_catalog_entries_are_not_editable(self) -> None:
        window = self.make_window()
        index = window.dictionary_page.model.index(0, 0)

        self.assertFalse(
            bool(
                window.dictionary_page.model.flags(index)
                & Qt.ItemFlag.ItemIsEditable
            ),
        )

    def test_create_custom_version_does_not_modify_packaged_dictionary(
        self,
    ) -> None:
        root = Path(__file__).resolve().parents[1]
        symbols_path = root / "src" / "scitype" / "data" / "symbols.json"
        defaults_path = (
            root / "src" / "scitype" / "data" / "default_bindings.json"
        )
        before = (symbols_path.read_bytes(), defaults_path.read_bytes())
        window = self.make_window()
        page = window.dictionary_page
        page.search_input.setText("积分")
        self.assertTrue(page.select_trigger("/jf"))

        page.custom_button.click()
        QCoreApplication.processEvents()

        self.assertEqual(
            window.page_stack.currentIndex(),
            MainWindow.BINDINGS_PAGE,
        )
        self.assertEqual(window.view_model.draft.trigger, "/jf")
        self.assertEqual(
            window.view_model.draft.replacement,
            "∫${cursor}dx",
        )
        self.assertEqual(
            (symbols_path.read_bytes(), defaults_path.read_bytes()),
            before,
        )

    def test_dictionary_toggle_uses_user_mask_and_removes_it_on_reenable(
        self,
    ) -> None:
        window = self.make_window()
        window.dictionary_nav_button.click()
        page = window.dictionary_page
        page.search_input.setText("/jf")
        self.assertTrue(page.select_trigger("/jf"))

        page.enabled_checkbox.setChecked(False)
        QCoreApplication.processEvents()

        masks_path = self.config_path.with_name("catalog_masks.json")
        saved = json.loads(masks_path.read_text(encoding="utf-8"))
        self.assertEqual(
            saved["disabled_triggers"],
            ["/jf"],
        )
        self.assertFalse(self.config_path.exists())
        self.assertIn("已保存到本地", window.runtime_status_message.text())
        self.assertIn("未运行", window.runtime_status_message.text())

        page.search_input.setText("/jf")
        self.assertTrue(page.select_trigger("/jf"))
        page.enabled_checkbox.setChecked(True)
        QCoreApplication.processEvents()

        saved = json.loads(masks_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["disabled_triggers"], [])
        self.assertEqual(
            window.view_model.snapshot.effective_bindings["/jf"],
            "∫${cursor}dx",
        )

    def test_conflicting_pack_entry_shows_notice_without_enable_switch(
        self,
    ) -> None:
        self.packs_directory.mkdir(parents=True)
        (self.packs_directory / "conflict.JSON").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "pack": {
                        "id": "test.gui-conflict",
                        "name": "冲突包",
                        "version": "1.0.0",
                    },
                    "entries": [
                        {
                            "name": "冲突积分",
                            "category": "其他",
                            "trigger": "/jf",
                            "replacement": "冲突",
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        window = self.make_window()
        window.dictionary_nav_button.click()
        page = window.dictionary_page
        source_index = page.source_filter.findData("test.gui-conflict")
        page.source_filter.setCurrentIndex(source_index)
        QCoreApplication.processEvents()
        self.assertTrue(page.select_trigger("/jf"))

        self.assertFalse(page.enabled_checkbox.isVisible())
        self.assertTrue(page.conflict_toggle_notice.isVisible())
        self.assertIn("当前不可用于输入", page.conflict_toggle_notice.text())
        self.assertFalse(self.config_path.exists())

    def test_catalog_user_override_and_disabled_states_are_service_data(
        self,
    ) -> None:
        self.seed(
            UserBinding("/jf", "自定义积分", True),
            UserBinding("/gh", "停用说明", False),
        )
        window = self.make_window()
        entries = {
            entry.trigger: entry
            for entry in window.view_model.catalog.entries
            if entry.trigger in {"/jf", "/gh"}
        }

        self.assertIs(
            entries["/jf"].user_state,
            CatalogUserState.OVERRIDDEN,
        )
        self.assertIs(
            entries["/gh"].user_state,
            CatalogUserState.DISABLED,
        )

    def test_gui_imports_valid_pack_and_refreshes_read_only_catalog(
        self,
    ) -> None:
        incoming = self.local_root / "incoming.json"
        incoming.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "pack": {
                        "id": "test.imported",
                        "name": "导入测试包",
                        "version": "1.0.0",
                    },
                    "entries": [
                        {
                            "name": "测试符号",
                            "category": "其他",
                            "trigger": "/imported",
                            "replacement": "☆",
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        view_model = BindingSettingsViewModel(
            config_path=self.config_path,
            packs_directory=self.packs_directory,
        )
        window = MainWindow(
            view_model,
            select_pack_file=lambda _parent: incoming,
            replace_pack_prompt=lambda _parent, _name: False,
            open_directory=self._open_directory,
            animations_enabled=False,
        )
        self.windows.append(window)
        window.show()

        window.dictionary_page.import_pack_button.click()
        QCoreApplication.processEvents()

        self.assertTrue(
            (self.packs_directory / "test.imported.json").is_file(),
        )
        self.assertIn(
            "test.imported",
            {
                source.source_id
                for source in window.view_model.catalog.sources
            },
        )
        self.assertIn("扩展包已导入", window.toast_label.text())

    def test_broken_pack_is_reported_without_hiding_base_dictionary(
        self,
    ) -> None:
        self.packs_directory.mkdir(parents=True)
        broken = self.packs_directory / "broken.json"
        broken.write_bytes(b'{"schema_version":')
        window = self.make_window()
        window.dictionary_nav_button.click()

        self.assertTrue(
            window.dictionary_page.pack_failure_notice.isVisible(),
        )
        self.assertIn(
            "加载失败",
            window.dictionary_page.pack_failure_notice.text(),
        )
        self.assertIn("/jf", self.catalog_triggers(window))
        self.assertEqual(broken.read_bytes(), b'{"schema_version":')

    def test_settings_page_opens_existing_local_locations(self) -> None:
        window = self.make_window()
        window.settings_nav_button.click()

        self.assertIn(
            "0.6.0",
            [
                label.text()
                for label in window.settings_page.findChildren(QLabel)
            ],
        )
        window.settings_page.open_config_button.click()
        window.settings_page.open_logs_button.click()
        window.dictionary_nav_button.click()
        window.dictionary_page.open_packs_button.click()

        self.assertEqual(
            self.opened_paths,
            [
                self.config_path.parent,
                self.config_path.parent,
                self.packs_directory,
            ],
        )

    def test_settings_status_can_be_refreshed_and_stays_visible(self) -> None:
        window = self.make_window()
        window.settings_nav_button.click()

        self.assertIn(
            "未运行",
            window.settings_page.runtime_status_value.text(),
        )
        window.settings_page.refresh_status_button.click()
        QCoreApplication.processEvents()
        self.assertIn(
            "未运行",
            window.settings_page.runtime_status_value.text(),
        )

    def test_visible_text_controls_fit_at_minimum_window_size(self) -> None:
        window = self.make_window()
        window.resize(window.minimumSize())
        QCoreApplication.processEvents()

        for widget_type in (QLabel, QPushButton):
            for widget in window.findChildren(widget_type):
                if not widget.isVisible() or not widget.text():
                    continue
                with self.subTest(widget=widget.objectName() or widget.text()):
                    self.assertGreaterEqual(
                        widget.height(),
                        min(
                            widget.sizeHint().height(),
                            widget.maximumHeight(),
                        ),
                    )

    def test_focus_style_does_not_change_control_size(self) -> None:
        window = self.make_window()
        window.binding_page.empty_new_button.click()
        field = window.editor.trigger_input
        before = field.size()

        window.editor.replacement_input.setFocus()
        QCoreApplication.processEvents()
        field.setFocus()
        QCoreApplication.processEvents()

        self.assertEqual(field.size(), before)

    def test_animation_disabled_and_rapid_switching_are_safe(self) -> None:
        window = self.make_window(animations_enabled=False)
        for index in (1, 2, 0, 2, 1, 0):
            window._show_navigation_page(index)

        self.assertEqual(window.page_stack.currentIndex(), 0)
        self.assertFalse(window.page_transition.is_running)
        self.assertTrue(
            all(
                window.page_stack.widget(index).graphicsEffect() is None
                for index in range(window.page_stack.count())
            ),
        )

    def test_animation_cleans_temporary_graphics_effect(self) -> None:
        window = self.make_window(animations_enabled=True)
        window._show_navigation_page(MainWindow.DICTIONARY_PAGE)
        QTest.qWait(260)

        self.assertEqual(
            window.page_stack.currentIndex(),
            MainWindow.DICTIONARY_PAGE,
        )
        self.assertFalse(window.page_transition.is_running)
        self.assertTrue(
            all(
                window.page_stack.widget(index).graphicsEffect() is None
                for index in range(window.page_stack.count())
            ),
        )

    def test_inline_error_fade_cleans_temporary_effect(self) -> None:
        window = self.make_window(animations_enabled=True)
        window.binding_page.empty_new_button.click()
        window.editor.trigger_input.setText("bad")
        QTest.qWait(190)

        self.assertTrue(window.editor.trigger_error.isVisible())
        self.assertIsNone(window.editor.trigger_error.graphicsEffect())

    def test_copy_and_search_do_not_write_content_to_gui_log(self) -> None:
        stream = StringIO()
        logger = logging.getLogger(f"scitype.gui.privacy.{id(self)}")
        logger.handlers = [logging.StreamHandler(stream)]
        logger.setLevel(logging.INFO)
        logger.propagate = False
        private_query = "积分隐私搜索"
        private_trigger = "/mimicopy"
        view_model = BindingSettingsViewModel(
            config_path=self.config_path,
            packs_directory=self.packs_directory,
            logger=logger,
        )
        window = MainWindow(
            view_model,
            open_directory=self._open_directory,
            animations_enabled=False,
        )
        self.windows.append(window)
        window.show()
        window.dictionary_page.search_input.setText(private_query)
        window._copy_catalog_trigger(private_trigger)

        log_text = stream.getvalue()
        self.assertNotIn(private_query, log_text)
        self.assertNotIn(private_trigger, log_text)

    def test_extension_pack_content_is_not_written_to_gui_log(self) -> None:
        private_name = "不应记录的私密包名"
        private_trigger = "/packprivate"
        private_replacement = "不应记录的扩展内容"
        self.packs_directory.mkdir(parents=True)
        (self.packs_directory / "private.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "pack": {
                        "id": "test.private",
                        "name": private_name,
                        "version": "1.0.0",
                    },
                    "entries": [
                        {
                            "name": "不应记录的词条名",
                            "category": "其他",
                            "trigger": private_trigger,
                            "replacement": private_replacement,
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        stream = StringIO()
        logger = logging.getLogger(f"scitype.pack.privacy.{id(self)}")
        logger.handlers = [logging.StreamHandler(stream)]
        logger.setLevel(logging.INFO)
        logger.propagate = False

        BindingSettingsViewModel(
            config_path=self.config_path,
            packs_directory=self.packs_directory,
            logger=logger,
        )

        log_text = stream.getvalue()
        self.assertNotIn(private_name, log_text)
        self.assertNotIn(private_trigger, log_text)
        self.assertNotIn(private_replacement, log_text)

    def test_125_and_150_percent_offscreen_processes_construct(self) -> None:
        code = (
            "import os,tempfile;"
            "os.environ['QT_QPA_PLATFORM']='offscreen';"
            "os.environ['SCITYPE_DISABLE_ANIMATIONS']='1';"
            "from pathlib import Path;"
            "from scitype.gui.app import create_application;"
            "from scitype.gui.main_window import MainWindow;"
            "from scitype.gui.view_model import BindingSettingsViewModel;"
            "tmp=tempfile.TemporaryDirectory();"
            "root=Path(tmp.name,'SciType');"
            "app=create_application(['scale-test']);"
            "window=MainWindow(BindingSettingsViewModel("
            "config_path=root/'user_bindings.json',"
            "packs_directory=root/'packs'),animations_enabled=False);"
            "window.show();app.processEvents();"
            "assert window.minimumWidth() <= window.width();"
            "assert window.binding_page.empty_description.sizeHint().height()>0;"
            "window.close();tmp.cleanup()"
        )
        for factor in ("1.25", "1.5"):
            with self.subTest(factor=factor):
                environment = dict(os.environ)
                environment["QT_SCALE_FACTOR"] = factor
                result = subprocess.run(
                    [sys.executable, "-c", code],
                    cwd=Path(__file__).resolve().parents[1],
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                self.assertEqual(
                    result.returncode,
                    0,
                    result.stderr or result.stdout,
                )


if __name__ == "__main__":
    unittest.main()
