"""Tests for the pure-Python SciType settings ViewModel."""

from __future__ import annotations

from io import StringIO
import json
import logging
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scitype.catalog import CatalogSourceKind
from scitype.gui.view_model import BindingSettingsViewModel
from scitype.runtime_status import (
    RuntimeApplicationState,
    RuntimeStatusRecord,
    configuration_hash,
    write_runtime_status,
)
from scitype.user_bindings import (
    UserBinding,
    UserBindingErrorCode,
    UserBindingsError,
    load_user_bindings,
)


def update(
    view_model: BindingSettingsViewModel,
    trigger: str,
    replacement: str,
    *,
    enabled: bool = True,
) -> None:
    view_model.update_draft(
        trigger=trigger,
        replacement=replacement,
        enabled=enabled,
    )


class BindingSettingsViewModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.config_path = Path(
            self.temporary_directory.name,
            "SciType",
            "user_bindings.json",
        )
        self.defaults = {
            "/fi": "φ",
            "/jf": "∫${cursor}dx",
            "//": "/",
        }

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def create_view_model(
        self,
        *,
        logger: logging.Logger | None = None,
        process_start_lookup=None,
        instance_probe=lambda: False,
    ) -> BindingSettingsViewModel:
        return BindingSettingsViewModel(
            config_path=self.config_path,
            default_bindings=self.defaults,
            process_start_lookup=process_start_lookup,
            instance_probe=instance_probe,
            logger=logger,
        )

    @staticmethod
    def catalog_entry(
        view_model: BindingSettingsViewModel,
        trigger: str,
        *,
        source_kind: CatalogSourceKind | None = None,
    ):
        return next(
            entry
            for entry in view_model.catalog.entries
            if entry.trigger == trigger
            and (
                source_kind is None
                or entry.source_kind is source_kind
            )
        )

    def save_binding(
        self,
        trigger: str,
        replacement: str,
        *,
        enabled: bool = True,
    ) -> BindingSettingsViewModel:
        view_model = self.create_view_model()
        view_model.begin_new()
        update(
            view_model,
            trigger,
            replacement,
            enabled=enabled,
        )
        result = view_model.save_current()
        self.assertTrue(result.success, result.message)
        return view_model

    def test_missing_configuration_opens_as_empty_editable_list(self) -> None:
        view_model = self.create_view_model()

        self.assertEqual(view_model.bindings, ())
        self.assertTrue(view_model.can_edit)
        self.assertFalse(view_model.has_load_error)
        self.assertEqual(view_model.config_path, self.config_path)

    def test_valid_configuration_loads_user_list(self) -> None:
        self.save_binding("/ceshi", "示例文本")

        reopened = self.create_view_model()

        self.assertEqual(
            reopened.bindings,
            (UserBinding("/ceshi", "示例文本", True),),
        )

    def test_new_binding_round_trips_chinese_unicode_and_emoticon(self) -> None:
        view_model = self.save_binding(
            "/ceshi1",
            "示例 ∫φ (＾▽＾)",
        )

        self.assertTrue(view_model.snapshot.effective_bindings["/ceshi1"])
        reopened = self.create_view_model()
        self.assertEqual(
            reopened.bindings[0].replacement,
            "示例 ∫φ (＾▽＾)",
        )

    def test_multiline_and_single_cursor_round_trip(self) -> None:
        replacement = "第一行\n∫${cursor}dx\n第三行"
        self.save_binding("/gongshi", replacement)

        reopened = self.create_view_model()

        self.assertEqual(reopened.bindings[0].replacement, replacement)

    def test_edit_binding_and_enabled_state(self) -> None:
        view_model = self.save_binding("/ceshi", "旧值")
        view_model.select_binding(0)
        update(view_model, "/ceshi2", "新值", enabled=False)

        result = view_model.save_current()

        self.assertTrue(result.success)
        self.assertEqual(
            view_model.bindings,
            (UserBinding("/ceshi2", "新值", False),),
        )
        self.assertNotIn("/ceshi2", view_model.snapshot.effective_bindings)

    def test_delete_binding(self) -> None:
        view_model = self.save_binding("/ceshi", "示例")
        view_model.select_binding(0)

        result = view_model.delete_selected()

        self.assertTrue(result.success)
        self.assertEqual(view_model.bindings, ())
        self.assertIsNone(view_model.draft)
        self.assertEqual(load_user_bindings(self.config_path).document.bindings, ())

    def test_invalid_trigger_and_empty_replacement_block_save(self) -> None:
        view_model = self.create_view_model()
        view_model.begin_new()
        update(view_model, "Bad Trigger", "")

        validation = view_model.validate_current_draft()
        result = view_model.save_current()

        self.assertIn("trigger", validation.field_errors)
        self.assertIn("replacement", validation.field_errors)
        self.assertFalse(result.success)
        self.assertFalse(self.config_path.exists())

    def test_duplicate_user_trigger_is_reported_inline(self) -> None:
        view_model = self.save_binding("/ceshi", "第一项")
        view_model.begin_new()
        update(view_model, "/ceshi", "第二项")

        validation = view_model.validate_current_draft()

        self.assertEqual(
            validation.field_errors["trigger"],
            "该触发词已经存在。",
        )
        self.assertFalse(view_model.save_current().success)

    def test_editing_a_row_does_not_conflict_with_itself(self) -> None:
        view_model = self.save_binding("/ceshi", "示例")
        view_model.select_binding(0)

        self.assertTrue(view_model.validate_current_draft().is_valid)

    def test_user_can_override_and_disable_default_binding(self) -> None:
        enabled = self.save_binding("/fi", "自定义斐")
        self.assertEqual(
            enabled.snapshot.effective_bindings["/fi"],
            "自定义斐",
        )

        enabled.select_binding(0)
        update(enabled, "/fi", "保留说明", enabled=False)
        self.assertTrue(enabled.save_current().success)
        self.assertNotIn("/fi", enabled.snapshot.effective_bindings)

    def test_base_catalog_disable_creates_mask_and_reenable_deletes_it(
        self,
    ) -> None:
        view_model = self.create_view_model()
        entry = self.catalog_entry(view_model, "/jf")

        disabled = view_model.set_catalog_entry_enabled(
            entry,
            enabled=False,
        )

        self.assertTrue(disabled.success)
        self.assertEqual(view_model.bindings, ())
        self.assertFalse(self.config_path.exists())
        masks_path = self.config_path.with_name("catalog_masks.json")
        raw_data = json.loads(masks_path.read_text(encoding="utf-8"))
        self.assertEqual(raw_data["disabled_triggers"], ["/jf"])
        self.assertNotIn("/jf", view_model.snapshot.effective_bindings)

        refreshed = self.catalog_entry(view_model, "/jf")
        enabled = view_model.set_catalog_entry_enabled(
            refreshed,
            enabled=True,
        )

        self.assertTrue(enabled.success)
        self.assertEqual(view_model.bindings, ())
        self.assertEqual(
            view_model.snapshot.effective_bindings["/jf"],
            "∫${cursor}dx",
        )
        masks = json.loads(masks_path.read_text(encoding="utf-8"))
        self.assertEqual(masks["disabled_triggers"], [])
        self.assertEqual(load_user_bindings(self.config_path).document.bindings, ())

    def test_existing_user_override_is_disabled_and_restored(self) -> None:
        view_model = self.save_binding("/jf", "自定义积分")
        entry = self.catalog_entry(view_model, "/jf")

        self.assertTrue(
            view_model.set_catalog_entry_enabled(
                entry,
                enabled=False,
            ).success,
        )
        self.assertEqual(
            view_model.bindings,
            (UserBinding("/jf", "自定义积分", False),),
        )

        entry = self.catalog_entry(view_model, "/jf")
        self.assertTrue(
            view_model.set_catalog_entry_enabled(
                entry,
                enabled=True,
            ).success,
        )
        self.assertEqual(
            view_model.bindings,
            (UserBinding("/jf", "自定义积分", True),),
        )
        self.assertEqual(
            view_model.snapshot.effective_bindings["/jf"],
            "自定义积分",
        )

    def test_user_override_equal_to_catalog_output_is_not_a_mask(
        self,
    ) -> None:
        view_model = self.save_binding("/jf", "∫${cursor}dx")
        entry = self.catalog_entry(view_model, "/jf")

        self.assertTrue(
            view_model.set_catalog_entry_enabled(
                entry,
                enabled=False,
            ).success,
        )
        self.assertEqual(
            view_model.bindings,
            (UserBinding("/jf", "∫${cursor}dx", False),),
        )

        entry = self.catalog_entry(view_model, "/jf")
        self.assertTrue(
            view_model.set_catalog_entry_enabled(
                entry,
                enabled=True,
            ).success,
        )
        self.assertEqual(
            view_model.bindings,
            (UserBinding("/jf", "∫${cursor}dx", True),),
        )

    def test_catalog_masks_never_appear_in_my_bindings(
        self,
    ) -> None:
        view_model = self.create_view_model()
        entry = self.catalog_entry(view_model, "/jf")
        self.assertTrue(
            view_model.set_catalog_entry_enabled(
                entry,
                enabled=False,
            ).success,
        )

        self.assertEqual(view_model.bindings, ())
        self.assertIsNone(view_model.draft)

    def test_extension_entry_can_be_masked_without_modifying_pack(self) -> None:
        packs = self.config_path.parent / "packs"
        packs.mkdir(parents=True)
        pack_path = packs / "local.JSON"
        pack_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "pack": {
                        "id": "test.local-toggle",
                        "name": "本地测试包",
                        "version": "1.0.0",
                    },
                    "entries": [
                        {
                            "name": "本地词条",
                            "category": "其他",
                            "trigger": "/localtoggle",
                            "replacement": "扩展内容",
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        before = pack_path.read_bytes()
        view_model = BindingSettingsViewModel(
            config_path=self.config_path,
            packs_directory=packs,
        )
        entry = self.catalog_entry(view_model, "/localtoggle")

        self.assertTrue(
            view_model.set_catalog_entry_enabled(
                entry,
                enabled=False,
            ).success,
        )
        self.assertNotIn(
            "/localtoggle",
            view_model.snapshot.effective_bindings,
        )
        entry = self.catalog_entry(view_model, "/localtoggle")
        self.assertTrue(
            view_model.set_catalog_entry_enabled(
                entry,
                enabled=True,
            ).success,
        )

        self.assertEqual(pack_path.read_bytes(), before)
        self.assertIn(
            "/localtoggle",
            view_model.snapshot.effective_bindings,
        )
        self.assertEqual(view_model.bindings, ())

    def test_conflicting_pack_entry_cannot_be_enabled_by_toggle(self) -> None:
        packs = self.config_path.parent / "packs"
        packs.mkdir(parents=True)
        (packs / "conflict.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "pack": {
                        "id": "test.conflict-toggle",
                        "name": "冲突包",
                        "version": "1.0.0",
                    },
                    "entries": [
                        {
                            "name": "冲突积分",
                            "category": "其他",
                            "trigger": "/jf",
                            "replacement": "冲突内容",
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        view_model = BindingSettingsViewModel(
            config_path=self.config_path,
            packs_directory=packs,
        )
        entry = self.catalog_entry(
            view_model,
            "/jf",
            source_kind=CatalogSourceKind.LOCAL_PACK,
        )

        result = view_model.set_catalog_entry_enabled(
            entry,
            enabled=True,
        )

        self.assertFalse(result.success)
        self.assertIn("冲突", result.message)
        self.assertFalse(self.config_path.exists())

    def test_runtime_feedback_tracks_saved_stale_and_restarted_states(
        self,
    ) -> None:
        started_at = 123456
        view_model = self.create_view_model(
            process_start_lookup=lambda _pid: started_at,
        )
        assert view_model.runtime_status_path is not None
        write_runtime_status(
            RuntimeStatusRecord(
                pid=42,
                started_at=started_at,
                config_hash=configuration_hash(
                    view_model.snapshot.effective_bindings,
                ),
            ),
            view_model.runtime_status_path,
        )
        self.assertIs(
            view_model.runtime_application_status().state,
            RuntimeApplicationState.RUNNING_APPLIED,
        )

        view_model.begin_new()
        update(view_model, "/ceshi", "示例")
        saved = view_model.save_current()

        self.assertTrue(saved.restart_required)
        self.assertIn("尚未应用", saved.message)
        self.assertIs(
            view_model.runtime_application_status().state,
            RuntimeApplicationState.RUNNING_RESTART_REQUIRED,
        )

        write_runtime_status(
            RuntimeStatusRecord(
                pid=43,
                started_at=started_at,
                config_hash=configuration_hash(
                    view_model.snapshot.effective_bindings,
                ),
            ),
            view_model.runtime_status_path,
        )
        self.assertIn("当前配置已应用", view_model.runtime_status_message())

    def test_residual_runtime_file_with_dead_pid_reports_not_running(self) -> None:
        view_model = self.create_view_model(
            process_start_lookup=lambda _pid: None,
        )
        assert view_model.runtime_status_path is not None
        write_runtime_status(
            RuntimeStatusRecord(
                pid=42,
                started_at=123456,
                config_hash=configuration_hash(
                    view_model.snapshot.effective_bindings,
                ),
            ),
            view_model.runtime_status_path,
        )

        self.assertIs(
            view_model.runtime_application_status().state,
            RuntimeApplicationState.NOT_RUNNING,
        )
        self.assertIn("未运行", view_model.runtime_status_message())

    def test_existing_instance_without_new_status_is_unverified(self) -> None:
        view_model = self.create_view_model(instance_probe=lambda: True)

        self.assertIs(
            view_model.runtime_application_status().state,
            RuntimeApplicationState.RUNNING_UNVERIFIED,
        )
        self.assertIn("无法确认", view_model.runtime_status_message())
        self.assertIn("旧版本", view_model.runtime_status_message())

    def test_runtime_hash_reloads_changed_extension_pack(self) -> None:
        packs = self.config_path.parent / "packs"
        packs.mkdir(parents=True)
        started_at = 123456
        view_model = BindingSettingsViewModel(
            config_path=self.config_path,
            packs_directory=packs,
            process_start_lookup=lambda _pid: started_at,
            instance_probe=lambda: False,
        )
        assert view_model.runtime_status_path is not None
        write_runtime_status(
            RuntimeStatusRecord(
                pid=42,
                started_at=started_at,
                config_hash=configuration_hash(
                    view_model.snapshot.effective_bindings,
                ),
            ),
            view_model.runtime_status_path,
        )
        self.assertIs(
            view_model.runtime_application_status().state,
            RuntimeApplicationState.RUNNING_APPLIED,
        )
        (packs / "new.JSON").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "pack": {
                        "id": "test.runtime-hash",
                        "name": "哈希包",
                        "version": "1.0.0",
                    },
                    "entries": [
                        {
                            "name": "新词条",
                            "category": "测试",
                            "trigger": "/newpack",
                            "replacement": "新增值",
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        self.assertIs(
            view_model.runtime_application_status().state,
            RuntimeApplicationState.RUNNING_RESTART_REQUIRED,
        )

    def test_multiple_or_numbered_placeholders_are_rejected(self) -> None:
        cases = (
            ("${cursor}+${cursor}", "最多只能设置一个光标位置。"),
            ("${1}", "多槽位模板尚未支持。"),
        )
        for replacement, expected in cases:
            with self.subTest(replacement=replacement):
                view_model = self.create_view_model()
                view_model.begin_new()
                update(view_model, "/gongshi", replacement)
                validation = view_model.validate_current_draft()
                self.assertEqual(
                    validation.field_errors["replacement"],
                    expected,
                )

    def test_dirty_state_cancel_and_plain_preview(self) -> None:
        view_model = self.save_binding("/gongshi", "∫${cursor}dx")
        view_model.select_binding(0)
        update(view_model, "/gongshi", "∫${cursor}dt")

        self.assertTrue(view_model.is_dirty)
        self.assertEqual(
            view_model.preview_text(),
            "/gongshi → ∫⟨光标位置⟩dt",
        )
        view_model.cancel_changes()
        self.assertFalse(view_model.is_dirty)
        self.assertEqual(view_model.draft.replacement, "∫${cursor}dx")

    def test_search_matches_trigger_or_replacement(self) -> None:
        view_model = self.save_binding("/ceshi", "示例文本")
        view_model.begin_new()
        update(view_model, "/weixiao", "(＾▽＾)")
        self.assertTrue(view_model.save_current().success)

        self.assertEqual(view_model.filtered_indices("weixiao"), (1,))
        self.assertEqual(view_model.filtered_indices("示例"), (0,))

    def test_save_failure_keeps_file_and_in_memory_data(self) -> None:
        view_model = self.save_binding("/ceshi", "旧值")
        old_bytes = self.config_path.read_bytes()
        view_model.select_binding(0)
        update(view_model, "/ceshi", "新值")
        simulated = UserBindingsError(
            "simulated",
            code=UserBindingErrorCode.SAVE_FAILED,
            exception_type="OSError",
        )

        with patch(
            "scitype.gui.view_model.save_user_bindings",
            side_effect=simulated,
        ):
            result = view_model.save_current()

        self.assertFalse(result.success)
        self.assertEqual(self.config_path.read_bytes(), old_bytes)
        self.assertEqual(view_model.bindings[0].replacement, "旧值")
        self.assertEqual(view_model.draft.replacement, "新值")
        self.assertTrue(view_model.is_dirty)

    def test_corrupt_configuration_is_read_only_and_preserved(self) -> None:
        self.config_path.parent.mkdir(parents=True)
        original = b'{"schema_version":1,"bindings":['
        self.config_path.write_bytes(original)

        view_model = self.create_view_model()

        self.assertTrue(view_model.has_load_error)
        self.assertFalse(view_model.can_edit)
        self.assertIn("原文件已保留", view_model.load_error_message)
        self.assertEqual(self.config_path.read_bytes(), original)
        self.assertEqual(
            dict(view_model.snapshot.effective_bindings),
            self.defaults,
        )

    def test_unsupported_schema_has_specific_safe_message(self) -> None:
        self.config_path.parent.mkdir(parents=True)
        self.config_path.write_text(
            json.dumps({"schema_version": 999, "bindings": []}),
            encoding="utf-8",
        )

        view_model = self.create_view_model()

        self.assertIs(
            view_model.load_error_code,
            UserBindingErrorCode.UNSUPPORTED_SCHEMA_VERSION,
        )
        self.assertEqual(
            view_model.load_error_message,
            "当前配置版本暂不支持，原文件已保留。",
        )

    def test_gui_logger_never_receives_trigger_or_replacement(self) -> None:
        stream = StringIO()
        logger = logging.getLogger(
            f"scitype.settings.test.{id(self)}",
        )
        logger.handlers = [logging.StreamHandler(stream)]
        logger.setLevel(logging.INFO)
        logger.propagate = False

        view_model = self.create_view_model(logger=logger)
        view_model.begin_new()
        update(view_model, "/mimi123", "不应出现在日志的虚构内容")
        self.assertTrue(view_model.save_current().success)

        log_text = stream.getvalue()
        self.assertNotIn("/mimi123", log_text)
        self.assertNotIn("不应出现在日志的虚构内容", log_text)
        self.assertIn("保存成功", log_text)


if __name__ == "__main__":
    unittest.main()
