"""Tests that runtime hashes represent the final effective dictionary."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scitype.catalog import load_catalog
from scitype.catalog_masks import (
    create_catalog_mask_document,
    save_catalog_masks,
)
from scitype.runtime_status import effective_bindings_hash
from scitype.user_bindings import (
    UserBinding,
    create_user_binding_document,
    load_active_bindings,
    save_user_bindings,
)


class EffectiveBindingsHashTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name, "SciType")
        self.packs = self.root / "packs"
        self.user_path = self.root / "user_bindings.json"
        self.mask_path = self.root / "catalog_masks.json"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _write_pack(
        self,
        *,
        trigger: str,
        replacement: str,
        pack_id: str = "test.hash",
    ) -> Path:
        self.packs.mkdir(parents=True, exist_ok=True)
        path = self.packs / "hash.JSON"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "pack": {
                        "id": pack_id,
                        "name": "哈希测试包",
                        "version": "1.0.0",
                    },
                    "entries": [
                        {
                            "name": "哈希词条",
                            "category": "测试",
                            "trigger": trigger,
                            "replacement": replacement,
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return path

    def _current_hash(self) -> str:
        catalog = load_catalog(self.packs)
        snapshot = load_active_bindings(
            self.user_path,
            catalog_masks_path=self.mask_path,
            default_bindings=catalog.catalog_bindings,
        )
        return effective_bindings_hash(snapshot.effective_bindings)

    def test_adding_and_removing_effective_pack_entry_changes_hash(self) -> None:
        before = self._current_hash()
        pack_path = self._write_pack(
            trigger="/hashpack",
            replacement="扩展值",
        )
        added = self._current_hash()
        pack_path.unlink()
        removed = self._current_hash()

        self.assertNotEqual(before, added)
        self.assertEqual(before, removed)

    def test_catalog_mask_and_user_override_change_final_hash(self) -> None:
        baseline = self._current_hash()
        save_catalog_masks(
            create_catalog_mask_document(("/jf",)),
            self.mask_path,
        )
        masked = self._current_hash()
        save_catalog_masks(
            create_catalog_mask_document(()),
            self.mask_path,
        )
        unmasked = self._current_hash()
        save_user_bindings(
            create_user_binding_document(
                (UserBinding("/jf", "用户积分", True),),
            ),
            self.user_path,
        )
        overridden = self._current_hash()

        self.assertNotEqual(baseline, masked)
        self.assertEqual(baseline, unmasked)
        self.assertNotEqual(baseline, overridden)

    def test_conflicting_pack_content_does_not_change_hash(self) -> None:
        self._write_pack(trigger="/jf", replacement="冲突值一")
        first = self._current_hash()
        self._write_pack(trigger="/jf", replacement="冲突值二")
        second = self._current_hash()

        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
