"""Tests for the read-only base and local extension-pack catalog."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scitype.catalog import (
    BASE_SOURCE_ID,
    MAX_PACK_FILE_BYTES,
    SYSTEM_RESERVED_TRIGGERS,
    CatalogConflict,
    CatalogSourceKind,
    CatalogUserState,
    PackErrorCode,
    PackValidationError,
    apply_user_states,
    catalog_preview,
    execute_pack_import,
    enumerate_pack_files,
    load_catalog,
    load_pack,
    prepare_pack_import,
    query_catalog,
)
from scitype.user_bindings import (
    UserBinding,
    create_user_binding_document,
    resolve_effective_bindings,
)


def pack_data(
    pack_id: str,
    name: str,
    entries: list[dict[str, object]],
    *,
    version: str = "1.0.0",
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "pack": {
            "id": pack_id,
            "name": name,
            "version": version,
            "description": "测试扩展包",
            "author": "SciType Test",
        },
        "entries": entries,
    }


def entry(
    trigger: str,
    replacement: str,
    *,
    name: str = "测试词条",
    category: str = "其他",
) -> dict[str, object]:
    return {
        "name": name,
        "category": category,
        "trigger": trigger,
        "replacement": replacement,
    }


class CatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.packs = Path(self.temporary_directory.name, "packs")
        self.packs.mkdir()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_pack(
        self,
        filename: str,
        data: object,
    ) -> Path:
        path = self.packs / filename
        path.write_text(
            json.dumps(data, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def test_base_catalog_loads_with_read_only_source(self) -> None:
        snapshot = load_catalog(self.packs)

        self.assertGreater(len(snapshot.entries), 30)
        self.assertEqual(snapshot.sources[0].source_id, BASE_SOURCE_ID)
        self.assertIs(snapshot.sources[0].kind, CatalogSourceKind.BASE)
        self.assertEqual(snapshot.catalog_bindings["/jf"], "∫${cursor}dx")

    def test_valid_pack_loads_and_participates_in_input(self) -> None:
        self.write_pack(
            "kaomoji.json",
            pack_data(
                "scitype.kaomoji.zh-cn",
                "中文颜文字",
                [
                    entry(
                        "/weixiao",
                        "(＾▽＾)",
                        name="微笑",
                        category="颜文字",
                    ),
                ],
            ),
        )

        snapshot = load_catalog(self.packs)

        self.assertEqual(len(snapshot.sources), 2)
        self.assertEqual(snapshot.sources[1].name, "中文颜文字")
        self.assertEqual(snapshot.catalog_bindings["/weixiao"], "(＾▽＾)")
        found = query_catalog(snapshot, query="微笑")
        self.assertEqual(found[0].source_name, "中文颜文字")

    def test_base_source_id_is_unique_and_reserved_from_packs(self) -> None:
        path = self.write_pack(
            "reserved.json",
            pack_data(
                BASE_SOURCE_ID,
                "伪基础词典",
                [entry("/fakebase", "伪")],
            ),
        )

        with self.assertRaises(PackValidationError) as caught:
            load_pack(path)
        snapshot = load_catalog(self.packs)

        self.assertIs(caught.exception.code, PackErrorCode.INVALID_PACK_ID)
        source_ids = [source.source_id for source in snapshot.sources]
        self.assertEqual(source_ids.count(BASE_SOURCE_ID), 1)
        self.assertEqual(len(source_ids), len(set(source_ids)))
        self.assertIn("/jf", snapshot.catalog_bindings)

    def test_multiple_packs_load_together(self) -> None:
        self.write_pack(
            "a.json",
            pack_data("test.a", "A 包", [entry("/aaa", "甲")]),
        )
        self.write_pack(
            "b.json",
            pack_data("test.b", "B 包", [entry("/bbb", "乙")]),
        )

        snapshot = load_catalog(self.packs)

        self.assertEqual(len(snapshot.sources), 3)
        self.assertEqual(snapshot.catalog_bindings["/aaa"], "甲")
        self.assertEqual(snapshot.catalog_bindings["/bbb"], "乙")

    def test_unsupported_schema_fails_without_deleting_file(self) -> None:
        data = pack_data("test.future", "未来包", [])
        data["schema_version"] = 99
        path = self.write_pack("future.json", data)
        before = path.read_bytes()

        with self.assertRaises(PackValidationError) as caught:
            load_pack(path)

        self.assertIs(
            caught.exception.code,
            PackErrorCode.INVALID_SCHEMA_VERSION,
        )
        self.assertEqual(path.read_bytes(), before)

    def test_missing_required_pack_metadata_is_rejected(self) -> None:
        for missing in ("id", "name", "version"):
            with self.subTest(missing=missing):
                data = pack_data("test.meta", "元数据", [])
                del data["pack"][missing]
                path = self.write_pack(f"missing-{missing}.json", data)
                with self.assertRaises(PackValidationError) as caught:
                    load_pack(path)
                self.assertIs(
                    caught.exception.code,
                    PackErrorCode.MISSING_FIELD,
                )

    def test_invalid_entry_and_multi_cursor_are_rejected(self) -> None:
        cases = (
            {"name": "缺字段"},
            entry("bad", "文本"),
            entry("/bad", "${cursor}${cursor}"),
            entry("/bad", "${1}"),
        )
        for index, invalid_entry in enumerate(cases):
            with self.subTest(index=index):
                path = self.write_pack(
                    f"invalid-{index}.json",
                    pack_data(
                        f"test.invalid{index}",
                        "非法词条",
                        [invalid_entry],
                    ),
                )
                with self.assertRaises(PackValidationError) as caught:
                    load_pack(path)
                self.assertIn(
                    caught.exception.code,
                    {
                        PackErrorCode.MISSING_FIELD,
                        PackErrorCode.INVALID_ENTRY,
                    },
                )

    def test_corrupt_pack_does_not_affect_base_catalog(self) -> None:
        broken = self.packs / "broken.json"
        broken.write_bytes(b'{"schema_version":')

        snapshot = load_catalog(self.packs)

        self.assertIn("/jf", snapshot.catalog_bindings)
        self.assertEqual(len(snapshot.failures), 1)
        self.assertEqual(broken.read_bytes(), b'{"schema_version":')

    def test_deep_and_oversized_json_do_not_block_base_catalog(self) -> None:
        deep = self.packs / "deep.JSON"
        deep.write_text(
            "[" * 5000 + "0" + "]" * 5000,
            encoding="utf-8",
        )
        oversized = self.packs / "oversized.Json"
        with oversized.open("wb") as file:
            file.truncate(MAX_PACK_FILE_BYTES + 1)

        snapshot = load_catalog(self.packs)

        self.assertIn("/jf", snapshot.catalog_bindings)
        self.assertEqual(
            {failure.file_name for failure in snapshot.failures},
            {"deep.JSON", "oversized.Json"},
        )
        self.assertTrue(
            all(
                failure.code is PackErrorCode.INVALID_JSON
                for failure in snapshot.failures
            ),
        )

    def test_pack_enumeration_is_case_insensitive_direct_and_deterministic(
        self,
    ) -> None:
        upper = self.write_pack(
            "B.JSON",
            pack_data("test.b", "B 包", [entry("/bbb", "乙")]),
        )
        mixed = self.write_pack(
            "a.Json",
            pack_data("test.a", "A 包", [entry("/aaa", "甲")]),
        )
        nested = self.packs / "nested"
        nested.mkdir()
        (nested / "ignored.json").write_text(
            json.dumps(
                pack_data(
                    "test.ignored",
                    "忽略",
                    [entry("/ignored", "忽略")],
                ),
            ),
            encoding="utf-8",
        )

        paths = enumerate_pack_files(self.packs)
        snapshot = load_catalog(self.packs)

        self.assertEqual(paths, (mixed, upper))
        self.assertEqual(
            [source.source_id for source in snapshot.sources[1:]],
            ["test.a", "test.b"],
        )
        self.assertNotIn("/ignored", snapshot.catalog_bindings)

    def test_pack_trigger_conflicts_are_order_independent(self) -> None:
        self.write_pack(
            "z.json",
            pack_data("test.z", "Z 包", [entry("/same", "Z")]),
        )
        self.write_pack(
            "a.json",
            pack_data("test.a", "A 包", [entry("/same", "A")]),
        )

        first = load_catalog(self.packs)
        (self.packs / "z.json").rename(self.packs / "00.json")
        second = load_catalog(self.packs)

        for snapshot in (first, second):
            conflicts = query_catalog(snapshot, query="/same")
            self.assertEqual(len(conflicts), 2)
            self.assertTrue(
                all(
                    item.conflict is CatalogConflict.PACK_TRIGGER
                    for item in conflicts
                ),
            )
            self.assertNotIn("/same", snapshot.catalog_bindings)

    def test_base_and_reserved_triggers_cannot_be_overridden_by_pack(
        self,
    ) -> None:
        reserved = sorted(SYSTEM_RESERVED_TRIGGERS)
        self.write_pack(
            "conflicts.json",
            pack_data(
                "test.conflicts",
                "冲突包",
                [
                    entry("/jf", "覆盖基础"),
                    *(entry(trigger, "覆盖系统") for trigger in reserved),
                ],
            ),
        )

        snapshot = load_catalog(self.packs)
        extension_entries = [
            item
            for item in snapshot.entries
            if item.source_id == "test.conflicts"
        ]

        self.assertIs(
            extension_entries[0].conflict,
            CatalogConflict.BASE_TRIGGER,
        )
        self.assertTrue(
            all(
                item.conflict is CatalogConflict.RESERVED_TRIGGER
                for item in extension_entries[1:]
            ),
        )
        self.assertEqual(snapshot.catalog_bindings["/jf"], "∫${cursor}dx")

    def test_user_override_and_disabled_mask_extension_entry(self) -> None:
        self.write_pack(
            "local.json",
            pack_data(
                "test.local",
                "本地包",
                [entry("/local", "扩展内容")],
            ),
        )
        snapshot = load_catalog(self.packs)

        overridden = apply_user_states(
            snapshot,
            [UserBinding("/local", "用户内容", True)],
        )
        disabled = apply_user_states(
            snapshot,
            [UserBinding("/local", "停用说明", False)],
        )
        extension = query_catalog(overridden, query="/local")[0]
        disabled_entry = query_catalog(disabled, query="/local")[0]
        self.assertIs(
            extension.user_state,
            CatalogUserState.OVERRIDDEN,
        )
        self.assertIs(
            disabled_entry.user_state,
            CatalogUserState.DISABLED,
        )

        enabled_document = create_user_binding_document(
            [UserBinding("/local", "用户内容", True)],
        )
        disabled_document = create_user_binding_document(
            [UserBinding("/local", "停用说明", False)],
        )
        self.assertEqual(
            resolve_effective_bindings(
                snapshot.catalog_bindings,
                enabled_document,
            )["/local"],
            "用户内容",
        )
        self.assertNotIn(
            "/local",
            resolve_effective_bindings(
                snapshot.catalog_bindings,
                disabled_document,
            ),
        )

    def test_searches_name_trigger_output_and_category(self) -> None:
        self.write_pack(
            "search.json",
            pack_data(
                "test.search",
                "搜索包",
                [
                    entry(
                        "/smile",
                        "(＾▽＾)",
                        name="微笑",
                        category="颜文字",
                    ),
                ],
            ),
        )
        snapshot = load_catalog(self.packs)

        for query in ("微笑", "/smile", "＾▽＾", "颜文字"):
            with self.subTest(query=query):
                self.assertEqual(
                    query_catalog(snapshot, query=query)[0].trigger,
                    "/smile",
                )
        self.assertEqual(
            query_catalog(snapshot, source_id="test.search")[0].name,
            "微笑",
        )
        self.assertEqual(
            query_catalog(snapshot, category="颜文字")[0].trigger,
            "/smile",
        )

    def test_cursor_preview_is_plain_text(self) -> None:
        self.assertEqual(catalog_preview("∫${cursor}dx"), "∫│dx")

    def test_import_requires_confirmation_for_same_pack_id(self) -> None:
        installed = self.write_pack(
            "installed.json",
            pack_data("test.import", "导入包", [entry("/old", "旧")]),
        )
        incoming_directory = Path(self.temporary_directory.name, "incoming")
        incoming_directory.mkdir()
        incoming = incoming_directory / "incoming.json"
        incoming.write_text(
            json.dumps(
                pack_data(
                    "test.import",
                    "导入包",
                    [entry("/new", "新")],
                ),
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        before = installed.read_bytes()
        plan = prepare_pack_import(incoming, self.packs)

        self.assertTrue(plan.requires_replacement_confirmation)
        with self.assertRaises(PackValidationError) as caught:
            execute_pack_import(plan)
        self.assertIs(
            caught.exception.code,
            PackErrorCode.REPLACEMENT_CONFIRMATION_REQUIRED,
        )
        self.assertEqual(installed.read_bytes(), before)

        destination = execute_pack_import(plan, allow_replace=True)
        self.assertEqual(destination, installed)
        self.assertEqual(load_pack(installed).entries[0].trigger, "/new")

    def test_import_finds_same_pack_id_with_uppercase_json_suffix(self) -> None:
        installed = self.write_pack(
            "installed.JSON",
            pack_data(
                "test.uppercase",
                "已安装包",
                [entry("/oldcase", "旧")],
            ),
        )
        incoming = Path(self.temporary_directory.name, "incoming.json")
        incoming.write_text(
            json.dumps(
                pack_data(
                    "test.uppercase",
                    "已安装包",
                    [entry("/newcase", "新")],
                ),
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        plan = prepare_pack_import(incoming, self.packs)

        self.assertTrue(plan.requires_replacement_confirmation)
        self.assertEqual(plan.destination_path, installed)


if __name__ == "__main__":
    unittest.main()
