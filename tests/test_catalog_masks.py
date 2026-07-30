"""Tests for independent, crash-safe read-only catalog masks."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scitype.catalog_masks import (
    CATALOG_MASKS_FILE_NAME,
    MAX_CATALOG_MASKS_FILE_BYTES,
    CatalogMaskErrorCode,
    CatalogMaskLoadStatus,
    CatalogMasksError,
    create_catalog_mask_document,
    get_catalog_masks_path,
    load_catalog_masks,
    save_catalog_masks,
)
from scitype.user_bindings import (
    UserBinding,
    create_user_binding_document,
    load_active_bindings,
    save_user_bindings,
)


class CatalogMasksTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name, "SciType")
        self.path = self.root / CATALOG_MASKS_FILE_NAME
        self.user_path = self.root / "user_bindings.json"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_default_path_is_outside_the_package(self) -> None:
        self.assertEqual(
            get_catalog_masks_path("D:/example/LocalAppData"),
            Path(
                "D:/example/LocalAppData",
                "SciType",
                CATALOG_MASKS_FILE_NAME,
            ),
        )

    def test_missing_file_returns_empty_document(self) -> None:
        result = load_catalog_masks(self.path)

        self.assertIs(result.status, CatalogMaskLoadStatus.MISSING)
        self.assertEqual(result.document.disabled_triggers, ())
        self.assertFalse(self.path.exists())

    def test_valid_file_round_trips_utf8_and_canonical_order(self) -> None:
        document = create_catalog_mask_document(
            ("/jf", "/abc", "/jf"),
        )

        save_catalog_masks(document, self.path)
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        loaded = load_catalog_masks(self.path)

        self.assertEqual(
            set(raw),
            {"schema_version", "disabled_triggers"},
        )
        self.assertEqual(raw["disabled_triggers"], ["/abc", "/jf"])
        self.assertIs(loaded.status, CatalogMaskLoadStatus.LOADED)
        self.assertEqual(loaded.document, document)

    def test_duplicate_json_fields_are_rejected(self) -> None:
        self.root.mkdir(parents=True)
        self.path.write_text(
            '{"schema_version":1,"schema_version":1,'
            '"disabled_triggers":[]}',
            encoding="utf-8",
        )

        result = load_catalog_masks(self.path)

        self.assertIs(result.status, CatalogMaskLoadStatus.FAILED)
        self.assertIs(
            result.error.code if result.error is not None else None,
            CatalogMaskErrorCode.DUPLICATE_JSON_FIELD,
        )

    def test_corrupt_deep_and_oversized_json_are_safe_failures(self) -> None:
        cases = ("corrupt", "deep", "oversized")
        for case in cases:
            with self.subTest(case=case):
                self.root.mkdir(parents=True, exist_ok=True)
                if case == "corrupt":
                    self.path.write_text("{broken", encoding="utf-8")
                elif case == "deep":
                    self.path.write_text(
                        "[" * 5000 + "0" + "]" * 5000,
                        encoding="utf-8",
                    )
                else:
                    with self.path.open("wb") as file:
                        file.truncate(MAX_CATALOG_MASKS_FILE_BYTES + 1)

                result = load_catalog_masks(self.path)
                self.assertIs(
                    result.status,
                    CatalogMaskLoadStatus.FAILED,
                )
                self.assertIs(
                    result.error.code if result.error is not None else None,
                    CatalogMaskErrorCode.INVALID_JSON,
                )

    def test_unknown_fields_and_invalid_triggers_are_rejected(self) -> None:
        invalid_documents = (
            {
                "schema_version": 1,
                "disabled_triggers": [],
                "future": True,
            },
            {
                "schema_version": 1,
                "disabled_triggers": ["not-a-trigger"],
            },
        )
        for raw in invalid_documents:
            with self.subTest(raw=raw):
                self.root.mkdir(parents=True, exist_ok=True)
                self.path.write_text(
                    json.dumps(raw),
                    encoding="utf-8",
                )
                result = load_catalog_masks(self.path)
                self.assertIs(
                    result.status,
                    CatalogMaskLoadStatus.FAILED,
                )

    def test_corrupt_masks_do_not_block_user_or_catalog_bindings(self) -> None:
        self.root.mkdir(parents=True)
        self.path.write_text("{broken", encoding="utf-8")
        save_user_bindings(
            create_user_binding_document(
                (UserBinding("/mine", "用户值", True),),
            ),
            self.user_path,
        )

        snapshot = load_active_bindings(
            self.user_path,
            catalog_masks_path=self.path,
            default_bindings={"/jf": "∫${cursor}dx"},
        )

        self.assertEqual(
            dict(snapshot.effective_bindings),
            {"/jf": "∫${cursor}dx", "/mine": "用户值"},
        )
        self.assertIs(
            snapshot.catalog_mask_load_result.status,
            CatalogMaskLoadStatus.FAILED,
        )

    def test_atomic_replace_failure_preserves_original_and_cleans_temp(
        self,
    ) -> None:
        save_catalog_masks(
            create_catalog_mask_document(("/jf",)),
            self.path,
        )
        original = self.path.read_bytes()

        with (
            patch(
                "scitype.catalog_masks.os.replace",
                side_effect=OSError("simulated"),
            ),
            self.assertRaises(CatalogMasksError) as raised,
        ):
            save_catalog_masks(
                create_catalog_mask_document(("/gh",)),
                self.path,
            )

        self.assertIs(
            raised.exception.code,
            CatalogMaskErrorCode.SAVE_FAILED,
        )
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(
            list(self.root.glob(f".{self.path.name}.*.tmp")),
            [],
        )

    def test_temporary_validation_failure_preserves_original(self) -> None:
        save_catalog_masks(
            create_catalog_mask_document(("/jf",)),
            self.path,
        )
        original = self.path.read_bytes()
        validation_error = CatalogMasksError(
            "simulated",
            code=CatalogMaskErrorCode.INVALID_JSON,
        )

        with (
            patch(
                "scitype.catalog_masks._load_document_strict",
                side_effect=validation_error,
            ),
            self.assertRaises(CatalogMasksError) as raised,
        ):
            save_catalog_masks(
                create_catalog_mask_document(("/gh",)),
                self.path,
            )

        self.assertIs(
            raised.exception.code,
            CatalogMaskErrorCode.TEMPORARY_VALIDATION_FAILED,
        )
        self.assertEqual(self.path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
