"""Offscreen Qt widget tests for the SciType settings window."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from scitype.gui.app import create_application
from scitype.gui.binding_list_model import BindingListModel
from scitype.gui.main_window import MainWindow, UnsavedDecision
from scitype.gui.view_model import BindingSettingsViewModel
from scitype.user_bindings import (
    UserBinding,
    create_user_binding_document,
    save_user_bindings,
)


class SettingsWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = create_application(["scitype-gui-test"])

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.config_path = Path(
            self.temporary_directory.name,
            "SciType",
            "user_bindings.json",
        )
        self.defaults = {"/fi": "φ", "//": "/"}
        self.windows: list[MainWindow] = []

    def tearDown(self) -> None:
        for window in self.windows:
            window.hide()
            window.deleteLater()
        QCoreApplication.processEvents()
        self.temporary_directory.cleanup()

    def make_window(
        self,
        *,
        decisions: list[UnsavedDecision] | None = None,
        confirm_delete: bool = True,
    ) -> MainWindow:
        queue = decisions if decisions is not None else []

        def prompt(_parent: object) -> UnsavedDecision:
            return queue.pop(0)

        view_model = BindingSettingsViewModel(
            config_path=self.config_path,
            default_bindings=self.defaults,
            instance_probe=lambda: False,
        )
        window = MainWindow(
            view_model,
            unsaved_prompt=prompt,
            delete_prompt=lambda _parent: confirm_delete,
            open_directory=lambda _path: True,
        )
        self.windows.append(window)
        window.show()
        QCoreApplication.processEvents()
        return window

    def seed(self, *bindings: UserBinding) -> None:
        save_user_bindings(
            create_user_binding_document(bindings),
            self.config_path,
        )

    def fill_new(
        self,
        window: MainWindow,
        trigger: str,
        replacement: str,
        *,
        enabled: bool = True,
    ) -> None:
        window.new_button.click()
        window.editor.trigger_input.setText(trigger)
        window.editor.replacement_input.setPlainText(replacement)
        window.editor.enabled_checkbox.setChecked(enabled)
        QCoreApplication.processEvents()

    def test_empty_window_has_clear_new_binding_flow(self) -> None:
        window = self.make_window()

        self.assertEqual(window.size().width(), 960)
        self.assertEqual(window.size().height(), 640)
        self.assertEqual(window.list_model.rowCount(), 0)
        self.assertTrue(window.new_button.isEnabled())

        window.new_button.click()

        self.assertTrue(window.view_model.is_new)
        self.assertEqual(window.editor_stack.currentIndex(), 1)
        self.assertTrue(window.editor.trigger_input.hasFocus())

    def test_create_binding_updates_list_and_file(self) -> None:
        window = self.make_window()
        self.fill_new(window, "/ceshi", "示例 ∫ (＾▽＾)")

        window.editor.save_button.click()
        QCoreApplication.processEvents()

        self.assertEqual(window.list_model.rowCount(), 1)
        self.assertEqual(
            window.list_model.index(0, 0).data(
                BindingListModel.TriggerRole,
            ),
            "/ceshi",
        )
        self.assertIn("保存成功", window.editor.status_label.text())
        self.assertTrue(self.config_path.is_file())

    def test_edit_disable_and_delete_binding(self) -> None:
        self.seed(UserBinding("/ceshi", "旧值", True))
        window = self.make_window()
        window.list_view.setCurrentIndex(window.list_model.index(0, 0))
        QCoreApplication.processEvents()

        window.editor.replacement_input.setPlainText("新值")
        window.editor.enabled_checkbox.setChecked(False)
        window.editor.save_button.click()
        QCoreApplication.processEvents()

        self.assertEqual(window.view_model.bindings[0].replacement, "新值")
        self.assertFalse(window.view_model.bindings[0].enabled)

        window.editor.delete_button.click()
        QCoreApplication.processEvents()
        self.assertEqual(window.view_model.bindings, ())
        self.assertEqual(window.list_model.rowCount(), 0)

    def test_realtime_conflict_and_placeholder_errors_block_save(self) -> None:
        self.seed(UserBinding("/ceshi", "第一项", True))
        window = self.make_window()
        self.fill_new(window, "/ceshi", "${cursor}+${cursor}")

        self.assertIn("已经存在", window.editor.trigger_error.text())
        self.assertIn("最多只能", window.editor.replacement_error.text())
        self.assertFalse(window.editor.save_button.isEnabled())

    def test_preview_is_plain_text_and_marks_cursor(self) -> None:
        window = self.make_window()
        self.fill_new(
            window,
            "/gongshi",
            "第一行\n∫${cursor}dx",
        )

        self.assertEqual(
            window.editor.preview.toPlainText(),
            "/gongshi → 第一行\n∫⟨光标位置⟩dx",
        )
        self.assertEqual(
            window.editor.preview.__class__.__name__,
            "QPlainTextEdit",
        )

    def test_search_filters_without_mutating_configuration(self) -> None:
        self.seed(
            UserBinding("/ceshi", "示例", True),
            UserBinding("/weixiao", "(＾▽＾)", False),
        )
        before = self.config_path.read_bytes()
        window = self.make_window()

        window.search_input.setText("weixiao")
        QCoreApplication.processEvents()

        self.assertEqual(window.list_model.rowCount(), 1)
        self.assertEqual(
            window.list_model.index(0, 0).data(
                BindingListModel.TriggerRole,
            ),
            "/weixiao",
        )
        self.assertEqual(self.config_path.read_bytes(), before)

    def test_unsaved_switch_can_cancel_or_discard(self) -> None:
        self.seed(
            UserBinding("/first", "一", True),
            UserBinding("/second", "二", True),
        )
        decisions = [
            UnsavedDecision.CANCEL,
            UnsavedDecision.DISCARD,
        ]
        window = self.make_window(decisions=decisions)
        first = window.list_model.index(0, 0)
        second = window.list_model.index(1, 0)
        window.list_view.setCurrentIndex(first)
        window.editor.replacement_input.setPlainText("未保存")

        window.list_view.setCurrentIndex(second)
        QCoreApplication.processEvents()
        self.assertEqual(window.view_model.selected_index, 0)
        self.assertEqual(window.editor.replacement_input.toPlainText(), "未保存")

        window.list_view.setCurrentIndex(second)
        QCoreApplication.processEvents()
        self.assertEqual(window.view_model.selected_index, 1)
        self.assertEqual(window.editor.replacement_input.toPlainText(), "二")

    def test_unsaved_switch_can_save_before_selecting_next_item(self) -> None:
        self.seed(
            UserBinding("/first", "一", True),
            UserBinding("/second", "二", True),
        )
        window = self.make_window(decisions=[UnsavedDecision.SAVE])
        first = window.list_model.index(0, 0)
        second = window.list_model.index(1, 0)
        window.list_view.setCurrentIndex(first)
        window.editor.replacement_input.setPlainText("已保存修改")

        window.list_view.setCurrentIndex(second)
        QCoreApplication.processEvents()

        self.assertEqual(window.view_model.selected_index, 1)
        self.assertEqual(window.editor.replacement_input.toPlainText(), "二")
        saved = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(
            saved["bindings"][0]["replacement"],
            "已保存修改",
        )

    def test_delete_prompt_can_cancel_without_writing(self) -> None:
        self.seed(UserBinding("/ceshi", "保留内容", True))
        before = self.config_path.read_bytes()
        window = self.make_window(confirm_delete=False)
        window.list_view.setCurrentIndex(window.list_model.index(0, 0))

        window.editor.delete_button.click()
        QCoreApplication.processEvents()

        self.assertEqual(window.view_model.bindings[0].trigger, "/ceshi")
        self.assertEqual(self.config_path.read_bytes(), before)

    def test_close_with_cancel_keeps_window_and_does_not_write(self) -> None:
        self.seed(UserBinding("/ceshi", "原值", True))
        before = self.config_path.read_bytes()
        window = self.make_window(
            decisions=[UnsavedDecision.CANCEL],
        )
        window.list_view.setCurrentIndex(window.list_model.index(0, 0))
        window.editor.replacement_input.setPlainText("未保存")

        closed = window.close()
        QCoreApplication.processEvents()

        self.assertFalse(closed)
        self.assertTrue(window.isVisible())
        self.assertEqual(self.config_path.read_bytes(), before)

    def test_closing_clean_window_does_not_modify_configuration(self) -> None:
        self.seed(UserBinding("/ceshi", "原值", True))
        before = self.config_path.read_bytes()
        window = self.make_window()

        self.assertTrue(window.close())

        self.assertEqual(self.config_path.read_bytes(), before)

    def test_corrupt_configuration_shows_banner_and_is_read_only(self) -> None:
        self.config_path.parent.mkdir(parents=True)
        original = b"{broken"
        self.config_path.write_bytes(original)

        window = self.make_window()

        self.assertTrue(window.error_banner.isVisible())
        self.assertIn("原文件已保留", window.error_message.text())
        self.assertFalse(window.new_button.isEnabled())
        self.assertEqual(self.config_path.read_bytes(), original)

    def test_unsupported_schema_has_specific_banner(self) -> None:
        self.config_path.parent.mkdir(parents=True)
        self.config_path.write_text(
            json.dumps({"schema_version": 99, "bindings": []}),
            encoding="utf-8",
        )

        window = self.make_window()

        self.assertIn("版本暂不支持", window.error_message.text())
        self.assertFalse(window.new_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
