"""Tests for versioned, persistent user-defined text bindings."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scitype.catalog_masks import (
    CatalogMaskLoadStatus,
    load_catalog_masks,
)
from scitype.dictionary import DictionaryError
from scitype.user_bindings import (
    CURRENT_SCHEMA_VERSION,
    MAX_USER_BINDINGS_FILE_BYTES,
    ReloadStatus,
    USER_BINDINGS_FILE_NAME,
    ActiveBindingsSnapshot,
    UserBinding,
    UserBindingDocument,
    UserBindingErrorCode,
    UserBindingLoadStatus,
    UserBindingsError,
    create_user_binding_document,
    empty_user_binding_document,
    get_user_bindings_path,
    has_trigger_conflict,
    load_active_bindings,
    load_active_dictionary,
    load_user_bindings,
    reload_user_bindings,
    resolve_effective_bindings,
    save_user_bindings,
    validate_replacement,
    validate_trigger,
)


_TEST_DIRECTORY = Path(__file__).resolve().parent


def binding(
    trigger: str,
    replacement: str,
    *,
    enabled: bool = True,
) -> UserBinding:
    return UserBinding(
        trigger=trigger,
        replacement=replacement,
        enabled=enabled,
    )


def document(*bindings: UserBinding) -> UserBindingDocument:
    return create_user_binding_document(bindings)


def json_document(
    bindings: list[dict[str, object]],
    *,
    schema_version: object = CURRENT_SCHEMA_VERSION,
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "bindings": bindings,
    }


class UserBindingsTests(unittest.TestCase):
    def test_default_path_is_outside_the_package(self) -> None:
        path = get_user_bindings_path("D:/example/LocalAppData")

        self.assertEqual(
            path,
            Path(
                "D:/example/LocalAppData",
                "SciType",
                USER_BINDINGS_FILE_NAME,
            ),
        )

    def test_missing_local_app_data_has_safe_error_code(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            self.assertRaises(UserBindingsError) as raised,
        ):
            get_user_bindings_path()

        self.assertIs(
            raised.exception.code,
            UserBindingErrorCode.PATH_UNAVAILABLE,
        )

    def test_missing_user_file_returns_empty_current_schema(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=_TEST_DIRECTORY,
        ) as temporary_directory:
            path = Path(temporary_directory, USER_BINDINGS_FILE_NAME)

            result = load_user_bindings(path)

            self.assertIs(result.status, UserBindingLoadStatus.MISSING)
            self.assertTrue(result.succeeded)
            self.assertEqual(result.document, empty_user_binding_document())
            self.assertFalse(path.exists())

    def test_deep_json_is_reported_as_invalid_without_becoming_fatal(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=_TEST_DIRECTORY,
        ) as temporary_directory:
            path = Path(temporary_directory, USER_BINDINGS_FILE_NAME)
            path.write_text(
                "[" * 5000 + "0" + "]" * 5000,
                encoding="utf-8",
            )

            result = load_user_bindings(path)
            active = load_active_bindings(
                path,
                default_bindings={"/fi": "φ"},
            )

        self.assertIs(result.status, UserBindingLoadStatus.FAILED)
        self.assertIs(
            result.error.code if result.error is not None else None,
            UserBindingErrorCode.INVALID_JSON,
        )
        self.assertEqual(dict(active.effective_bindings), {"/fi": "φ"})

    def test_oversized_json_is_rejected_before_parsing(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=_TEST_DIRECTORY,
        ) as temporary_directory:
            path = Path(temporary_directory, USER_BINDINGS_FILE_NAME)
            with path.open("wb") as file:
                file.truncate(MAX_USER_BINDINGS_FILE_BYTES + 1)

            result = load_user_bindings(path)

        self.assertIs(result.status, UserBindingLoadStatus.FAILED)
        self.assertIs(
            result.error.code if result.error is not None else None,
            UserBindingErrorCode.INVALID_JSON,
        )

    def test_supported_replacements_round_trip_in_formal_schema(self) -> None:
        expected = document(
            binding("/zhongwen", "示例文本"),
            binding("/shuxue2", "∫${cursor}dx"),
            binding("/weixiao", "(＾▽＾)"),
            binding("/duohang", "第一行\n  第二行"),
            binding("/tingyong", "保留但停用", enabled=False),
        )

        with tempfile.TemporaryDirectory(
            dir=_TEST_DIRECTORY,
        ) as temporary_directory:
            path = Path(temporary_directory, USER_BINDINGS_FILE_NAME)
            save_user_bindings(expected, path)
            raw_data = json.loads(path.read_text(encoding="utf-8"))
            loaded = load_user_bindings(path)

        self.assertEqual(raw_data["schema_version"], 1)
        self.assertEqual(
            set(raw_data["bindings"][0]),
            {"trigger", "replacement", "enabled"},
        )
        self.assertIs(loaded.status, UserBindingLoadStatus.LOADED)
        self.assertEqual(loaded.document, expected)

    def test_catalog_mask_is_not_part_of_the_strict_user_schema(self) -> None:
        raw_data = json_document(
            [
                {
                    "trigger": "/jf",
                    "replacement": "∫${cursor}dx",
                    "enabled": False,
                    "catalog_mask": True,
                },
            ],
        )
        with tempfile.TemporaryDirectory(
            dir=_TEST_DIRECTORY,
        ) as temporary_directory:
            path = Path(temporary_directory, USER_BINDINGS_FILE_NAME)
            path.write_text(
                json.dumps(raw_data, ensure_ascii=False),
                encoding="utf-8",
            )
            loaded = load_user_bindings(path)

        self.assertIs(loaded.status, UserBindingLoadStatus.FAILED)
        self.assertIs(
            loaded.error.code if loaded.error is not None else None,
            UserBindingErrorCode.UNKNOWN_FIELD,
        )

    def test_development_catalog_masks_migrate_without_losing_bindings(
        self,
    ) -> None:
        raw_data = json_document(
            [
                {
                    "trigger": "/jf",
                    "replacement": "∫${cursor}dx",
                    "enabled": False,
                    "catalog_mask": True,
                },
                {
                    "trigger": "/mine",
                    "replacement": "用户内容",
                    "enabled": True,
                },
                {
                    "trigger": "/fi",
                    "replacement": "φ",
                    "enabled": True,
                },
            ],
        )
        with tempfile.TemporaryDirectory(
            dir=_TEST_DIRECTORY,
        ) as temporary_directory:
            root = Path(temporary_directory)
            user_path = root / USER_BINDINGS_FILE_NAME
            mask_path = root / "catalog_masks.json"
            user_path.write_text(
                json.dumps(raw_data, ensure_ascii=False),
                encoding="utf-8",
            )

            snapshot = load_active_bindings(
                user_path,
                catalog_masks_path=mask_path,
                default_bindings={
                    "/jf": "∫${cursor}dx",
                    "/fi": "φ",
                },
            )
            rewritten = json.loads(
                user_path.read_text(encoding="utf-8"),
            )
            masks = load_catalog_masks(mask_path)

        self.assertIsNone(snapshot.migration_error)
        self.assertEqual(
            snapshot.user_document.bindings,
            (
                UserBinding("/mine", "用户内容", True),
                UserBinding("/fi", "φ", True),
            ),
        )
        self.assertTrue(
            all(
                set(item) == {"trigger", "replacement", "enabled"}
                for item in rewritten["bindings"]
            ),
        )
        self.assertIs(masks.status, CatalogMaskLoadStatus.LOADED)
        self.assertEqual(masks.document.disabled_triggers, ("/jf",))
        self.assertNotIn("/jf", snapshot.effective_bindings)
        self.assertEqual(snapshot.effective_bindings["/fi"], "φ")

    def test_duplicate_development_masks_are_deduplicated(self) -> None:
        raw_data = json_document(
            [
                {
                    "trigger": "/jf",
                    "replacement": "旧值一",
                    "enabled": False,
                    "catalog_mask": True,
                },
                {
                    "trigger": "/jf",
                    "replacement": "旧值二",
                    "enabled": False,
                    "catalog_mask": True,
                },
            ],
        )
        with tempfile.TemporaryDirectory(
            dir=_TEST_DIRECTORY,
        ) as temporary_directory:
            root = Path(temporary_directory)
            user_path = root / USER_BINDINGS_FILE_NAME
            mask_path = root / "catalog_masks.json"
            user_path.write_text(
                json.dumps(raw_data, ensure_ascii=False),
                encoding="utf-8",
            )

            snapshot = load_active_bindings(
                user_path,
                catalog_masks_path=mask_path,
                default_bindings={"/jf": "新值"},
            )

        self.assertIsNone(snapshot.migration_error)
        self.assertEqual(
            snapshot.catalog_mask_document.disabled_triggers,
            ("/jf",),
        )
        self.assertEqual(snapshot.user_document.bindings, ())

    def test_migration_failure_preserves_both_original_files(self) -> None:
        raw_data = json_document(
            [
                {
                    "trigger": "/jf",
                    "replacement": "旧值",
                    "enabled": False,
                    "catalog_mask": True,
                },
                {
                    "trigger": "/mine",
                    "replacement": "用户内容",
                    "enabled": True,
                },
            ],
        )
        with tempfile.TemporaryDirectory(
            dir=_TEST_DIRECTORY,
        ) as temporary_directory:
            root = Path(temporary_directory)
            user_path = root / USER_BINDINGS_FILE_NAME
            mask_path = root / "catalog_masks.json"
            user_path.write_text(
                json.dumps(raw_data, ensure_ascii=False),
                encoding="utf-8",
            )
            mask_path.write_text(
                '{"schema_version":1,"disabled_triggers":["/gh"]}',
                encoding="utf-8",
            )
            original_user = user_path.read_bytes()
            original_masks = mask_path.read_bytes()
            failure = UserBindingsError(
                "simulated",
                code=UserBindingErrorCode.SAVE_FAILED,
            )

            with patch(
                "scitype.user_bindings.save_user_bindings",
                side_effect=failure,
            ):
                snapshot = load_active_bindings(
                    user_path,
                    catalog_masks_path=mask_path,
                    default_bindings={
                        "/jf": "新值",
                        "/gh": "√${cursor}",
                    },
                )

            self.assertEqual(user_path.read_bytes(), original_user)
            self.assertEqual(mask_path.read_bytes(), original_masks)

        self.assertIsNotNone(snapshot.migration_error)
        self.assertEqual(
            snapshot.user_document.bindings,
            (UserBinding("/mine", "用户内容", True),),
        )
        self.assertEqual(
            snapshot.catalog_mask_document.disabled_triggers,
            ("/gh", "/jf"),
        )
        self.assertNotIn("/jf", snapshot.effective_bindings)
        self.assertNotIn("/gh", snapshot.effective_bindings)

    def test_unsupported_schema_version_fails_without_rewriting(self) -> None:
        raw_data = json_document([], schema_version=2)

        with tempfile.TemporaryDirectory(
            dir=_TEST_DIRECTORY,
        ) as temporary_directory:
            path = Path(temporary_directory, USER_BINDINGS_FILE_NAME)
            original = json.dumps(raw_data).encode("utf-8")
            path.write_bytes(original)

            result = load_user_bindings(path)

            self.assertIs(result.status, UserBindingLoadStatus.FAILED)
            self.assertIsNotNone(result.error)
            self.assertIs(
                result.error.code,
                UserBindingErrorCode.UNSUPPORTED_SCHEMA_VERSION,
            )
            self.assertEqual(path.read_bytes(), original)

    def test_missing_schema_version_is_reported(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=_TEST_DIRECTORY,
        ) as temporary_directory:
            path = Path(temporary_directory, USER_BINDINGS_FILE_NAME)
            path.write_text('{"bindings": []}', encoding="utf-8")

            result = load_user_bindings(path)

        self.assertIs(result.status, UserBindingLoadStatus.FAILED)
        self.assertIs(result.error.code, UserBindingErrorCode.MISSING_FIELD)
        self.assertEqual(result.error.field, "schema_version")

    def test_invalid_json_and_utf8_are_content_safe_failures(self) -> None:
        invalid_cases = (
            (
                b'{"schema_version": 1, "bindings": [',
                UserBindingErrorCode.INVALID_JSON,
            ),
            (
                b"\xff\xfe\xfa",
                UserBindingErrorCode.INVALID_UTF8,
            ),
        )

        with tempfile.TemporaryDirectory(
            dir=_TEST_DIRECTORY,
        ) as temporary_directory:
            path = Path(temporary_directory, USER_BINDINGS_FILE_NAME)
            for content, expected_code in invalid_cases:
                with self.subTest(expected_code=expected_code):
                    path.write_bytes(content)
                    result = load_user_bindings(path)

                    self.assertIs(
                        result.status,
                        UserBindingLoadStatus.FAILED,
                    )
                    self.assertIs(result.error.code, expected_code)
                    self.assertEqual(path.read_bytes(), content)

    def test_duplicate_json_fields_are_rejected(self) -> None:
        raw_text = (
            '{"schema_version":1,"schema_version":1,"bindings":[]}'
        )

        with tempfile.TemporaryDirectory(
            dir=_TEST_DIRECTORY,
        ) as temporary_directory:
            path = Path(temporary_directory, USER_BINDINGS_FILE_NAME)
            path.write_text(raw_text, encoding="utf-8")

            result = load_user_bindings(path)

        self.assertIs(result.status, UserBindingLoadStatus.FAILED)
        self.assertIs(
            result.error.code,
            UserBindingErrorCode.DUPLICATE_JSON_FIELD,
        )

    def test_unknown_fields_are_rejected_for_schema_migration_safety(
        self,
    ) -> None:
        raw_data = json_document([])
        raw_data["future"] = True

        with tempfile.TemporaryDirectory(
            dir=_TEST_DIRECTORY,
        ) as temporary_directory:
            path = Path(temporary_directory, USER_BINDINGS_FILE_NAME)
            path.write_text(json.dumps(raw_data), encoding="utf-8")

            result = load_user_bindings(path)

        self.assertIs(result.status, UserBindingLoadStatus.FAILED)
        self.assertIs(
            result.error.code,
            UserBindingErrorCode.UNKNOWN_FIELD,
        )

    def test_trigger_rules_allow_lowercase_ascii_letters_and_digits(
        self,
    ) -> None:
        for trigger in ("/a", "/abc", "/a1", "/123", "//"):
            with self.subTest(trigger=trigger):
                self.assertEqual(validate_trigger(trigger), trigger)

    def test_invalid_triggers_have_specific_error_codes(self) -> None:
        cases = (
            ("", UserBindingErrorCode.EMPTY_TRIGGER),
            ("abc", UserBindingErrorCode.MISSING_TRIGGER_SLASH),
            ("/ABC", UserBindingErrorCode.INVALID_TRIGGER_CHARACTERS),
            ("/a-b", UserBindingErrorCode.INVALID_TRIGGER_CHARACTERS),
            ("/a b", UserBindingErrorCode.INVALID_TRIGGER_CHARACTERS),
            ("/a\nb", UserBindingErrorCode.INVALID_TRIGGER_CHARACTERS),
        )

        for trigger, expected_code in cases:
            with self.subTest(trigger=trigger):
                with self.assertRaises(UserBindingsError) as raised:
                    validate_trigger(trigger)
                self.assertIs(raised.exception.code, expected_code)

    def test_empty_replacement_is_invalid_but_whitespace_is_static_text(
        self,
    ) -> None:
        with self.assertRaises(UserBindingsError) as raised:
            validate_replacement("")

        self.assertIs(
            raised.exception.code,
            UserBindingErrorCode.EMPTY_REPLACEMENT,
        )
        self.assertEqual(validate_replacement(" \n "), " \n ")

    def test_multiple_cursor_placeholders_are_rejected(self) -> None:
        with self.assertRaises(UserBindingsError) as raised:
            validate_replacement("${cursor}+${cursor}")

        self.assertIs(
            raised.exception.code,
            UserBindingErrorCode.MULTIPLE_CURSOR_PLACEHOLDERS,
        )

    def test_numbered_and_unknown_placeholders_are_rejected(self) -> None:
        for replacement in ("${0}", "${1}", "${2}", "${date}"):
            with self.subTest(replacement=replacement):
                with self.assertRaises(UserBindingsError) as raised:
                    validate_replacement(replacement)
                self.assertIs(
                    raised.exception.code,
                    UserBindingErrorCode.UNSUPPORTED_PLACEHOLDER,
                )

    def test_duplicate_triggers_fail_regardless_of_order_or_enabled(self) -> None:
        first = {
            "trigger": "/chongfu",
            "replacement": "甲",
            "enabled": True,
        }
        second = {
            "trigger": "/chongfu",
            "replacement": "乙",
            "enabled": False,
        }

        with tempfile.TemporaryDirectory(
            dir=_TEST_DIRECTORY,
        ) as temporary_directory:
            path = Path(temporary_directory, USER_BINDINGS_FILE_NAME)
            for bindings in ([first, second], [second, first]):
                with self.subTest(bindings=bindings):
                    path.write_text(
                        json.dumps(
                            json_document(bindings),
                            ensure_ascii=False,
                        ),
                        encoding="utf-8",
                    )
                    result = load_user_bindings(path)

                    self.assertIs(
                        result.status,
                        UserBindingLoadStatus.FAILED,
                    )
                    self.assertIs(
                        result.error.code,
                        UserBindingErrorCode.DUPLICATE_TRIGGER,
                    )

    def test_user_enabled_binding_overrides_default(self) -> None:
        defaults = {"/fi": "φ", "/jf": "∫${cursor}dx"}
        users = document(binding("/fi", "用户斐"))

        effective = resolve_effective_bindings(defaults, users)

        self.assertEqual(
            effective,
            {"/fi": "用户斐", "/jf": "∫${cursor}dx"},
        )
        self.assertEqual(defaults["/fi"], "φ")

    def test_disabled_binding_masks_same_named_default(self) -> None:
        defaults = {"/fi": "φ", "/jf": "∫${cursor}dx"}
        users = document(binding("/fi", "不会使用", enabled=False))

        effective = resolve_effective_bindings(defaults, users)

        self.assertNotIn("/fi", effective)
        self.assertEqual(effective["/jf"], "∫${cursor}dx")

    def test_disabled_non_default_binding_does_not_expand(self) -> None:
        effective = resolve_effective_bindings(
            {"/fi": "φ"},
            document(binding("/zidingyi", "不应展开", enabled=False)),
        )

        self.assertEqual(effective, {"/fi": "φ"})

    def test_trigger_conflict_service_can_exclude_edited_row(self) -> None:
        bindings = (
            binding("/first", "一"),
            binding("/second", "二"),
        )

        self.assertTrue(has_trigger_conflict(bindings, "/first"))
        self.assertFalse(
            has_trigger_conflict(
                bindings,
                "/first",
                exclude_index=0,
            ),
        )

    def test_corrupt_user_file_keeps_defaults_and_original_bytes(self) -> None:
        defaults = {"/fi": "φ", "//": "/"}

        with tempfile.TemporaryDirectory(
            dir=_TEST_DIRECTORY,
        ) as temporary_directory:
            path = Path(temporary_directory, USER_BINDINGS_FILE_NAME)
            original = b'{"schema_version":1,"bindings":['
            path.write_bytes(original)

            snapshot = load_active_bindings(
                path,
                default_bindings=defaults,
            )

            self.assertIs(
                snapshot.load_result.status,
                UserBindingLoadStatus.FAILED,
            )
            self.assertEqual(
                dict(snapshot.effective_bindings),
                defaults,
            )
            self.assertEqual(path.read_bytes(), original)

    def test_missing_user_file_keeps_defaults(self) -> None:
        defaults = {"/fi": "φ", "//": "/"}

        with tempfile.TemporaryDirectory(
            dir=_TEST_DIRECTORY,
        ) as temporary_directory:
            path = Path(temporary_directory, USER_BINDINGS_FILE_NAME)
            snapshot = load_active_bindings(
                path,
                default_bindings=defaults,
            )

        self.assertIs(
            snapshot.load_result.status,
            UserBindingLoadStatus.MISSING,
        )
        self.assertEqual(dict(snapshot.effective_bindings), defaults)

    def test_default_dictionary_failure_remains_fatal(self) -> None:
        with (
            patch(
                "scitype.user_bindings.load_dictionary",
                side_effect=DictionaryError("默认词库损坏"),
            ),
            self.assertRaisesRegex(DictionaryError, "默认词库损坏"),
        ):
            load_active_bindings("unused.json")

    def test_active_dictionary_compatibility_helper_returns_mapping(
        self,
    ) -> None:
        defaults = {"/fi": "φ"}

        with tempfile.TemporaryDirectory(
            dir=_TEST_DIRECTORY,
        ) as temporary_directory:
            path = Path(temporary_directory, USER_BINDINGS_FILE_NAME)
            save_user_bindings(document(binding("/ceshi", "示例")), path)

            active = load_active_dictionary(
                path,
                default_bindings=defaults,
            )

        self.assertEqual(active, {"/fi": "φ", "/ceshi": "示例"})

    def test_reload_success_returns_new_snapshot_and_restart_signal(
        self,
    ) -> None:
        defaults = {"/fi": "φ"}

        with tempfile.TemporaryDirectory(
            dir=_TEST_DIRECTORY,
        ) as temporary_directory:
            path = Path(temporary_directory, USER_BINDINGS_FILE_NAME)
            save_user_bindings(document(binding("/ceshi", "旧值")), path)
            current = load_active_bindings(
                path,
                default_bindings=defaults,
            )
            save_user_bindings(document(binding("/ceshi", "新值")), path)

            result = reload_user_bindings(current)

        self.assertIs(result.status, ReloadStatus.APPLIED)
        self.assertIsNot(result.snapshot, current)
        self.assertEqual(
            result.snapshot.effective_bindings["/ceshi"],
            "新值",
        )
        self.assertEqual(current.effective_bindings["/ceshi"], "旧值")
        self.assertTrue(result.restart_required)

    def test_reload_failure_retains_exact_valid_snapshot(self) -> None:
        defaults = {"/fi": "φ"}

        with tempfile.TemporaryDirectory(
            dir=_TEST_DIRECTORY,
        ) as temporary_directory:
            path = Path(temporary_directory, USER_BINDINGS_FILE_NAME)
            save_user_bindings(document(binding("/ceshi", "有效值")), path)
            current = load_active_bindings(
                path,
                default_bindings=defaults,
            )
            path.write_text("{broken", encoding="utf-8")

            result = reload_user_bindings(current)

        self.assertIs(
            result.status,
            ReloadStatus.RETAINED_AFTER_FAILURE,
        )
        self.assertIs(result.snapshot, current)
        self.assertEqual(
            result.snapshot.effective_bindings["/ceshi"],
            "有效值",
        )
        self.assertIs(
            result.load_result.status,
            UserBindingLoadStatus.FAILED,
        )
        self.assertFalse(result.restart_required)

    def test_atomic_replace_failure_preserves_old_file_and_cleans_temp(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            dir=_TEST_DIRECTORY,
        ) as temporary_directory:
            path = Path(temporary_directory, USER_BINDINGS_FILE_NAME)
            save_user_bindings(document(binding("/ceshi", "旧配置")), path)
            old_bytes = path.read_bytes()

            with (
                patch(
                    "scitype.user_bindings.os.replace",
                    side_effect=OSError("simulated replace failure"),
                ),
                self.assertRaises(UserBindingsError) as raised,
            ):
                save_user_bindings(
                    document(binding("/ceshi", "新配置")),
                    path,
                )

            self.assertIs(
                raised.exception.code,
                UserBindingErrorCode.SAVE_FAILED,
            )
            self.assertEqual(path.read_bytes(), old_bytes)
            self.assertEqual(
                list(path.parent.glob(f".{path.name}.*.tmp")),
                [],
            )

    def test_temporary_validation_failure_preserves_old_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            dir=_TEST_DIRECTORY,
        ) as temporary_directory:
            path = Path(temporary_directory, USER_BINDINGS_FILE_NAME)
            save_user_bindings(document(binding("/ceshi", "旧配置")), path)
            old_bytes = path.read_bytes()

            validation_error = UserBindingsError(
                "simulated validation failure",
                code=UserBindingErrorCode.INVALID_JSON,
            )
            with (
                patch(
                    "scitype.user_bindings._load_document_strict",
                    side_effect=validation_error,
                ),
                self.assertRaises(UserBindingsError) as raised,
            ):
                save_user_bindings(
                    document(binding("/ceshi", "新配置")),
                    path,
                )

            self.assertIs(
                raised.exception.code,
                UserBindingErrorCode.TEMPORARY_VALIDATION_FAILED,
            )
            self.assertEqual(path.read_bytes(), old_bytes)
            self.assertEqual(
                list(path.parent.glob(f".{path.name}.*.tmp")),
                [],
            )


if __name__ == "__main__":
    unittest.main()
