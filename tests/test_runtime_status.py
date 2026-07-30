"""Tests for the content-free backend runtime-state file."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scitype.runtime_status import (
    RuntimeApplicationState,
    RuntimeStatusError,
    RuntimeStatusRecord,
    clear_runtime_status,
    configuration_hash,
    effective_bindings_hash,
    inspect_runtime_status,
    published_runtime_status,
    read_runtime_status,
    write_runtime_status,
)


class RuntimeStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.path = Path(
            self.temporary_directory.name,
            "SciType",
            "runtime_status.json",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_hash_is_deterministic_and_order_independent(self) -> None:
        first = {"/a": "甲", "/b": "乙"}
        second = {"/b": "乙", "/a": "甲"}

        self.assertEqual(
            configuration_hash(first),
            configuration_hash(second),
        )
        self.assertNotEqual(
            configuration_hash(first),
            configuration_hash({"/a": "甲", "/b": "变化"}),
        )

    def test_status_file_contains_identity_and_hash_but_not_bindings(self) -> None:
        private_trigger = "/private123"
        private_replacement = "不应写入状态文件"
        record = RuntimeStatusRecord(
            pid=42,
            started_at=123456,
            config_hash=configuration_hash(
                {private_trigger: private_replacement},
            ),
        )

        write_runtime_status(record, self.path)
        raw_text = self.path.read_text(encoding="utf-8")

        self.assertEqual(read_runtime_status(self.path), record)
        self.assertNotIn(private_trigger, raw_text)
        self.assertNotIn(private_replacement, raw_text)

    def test_missing_dead_or_reused_process_is_not_running(self) -> None:
        bindings = {"/fi": "φ"}
        record = RuntimeStatusRecord(
            pid=42,
            started_at=123456,
            config_hash=configuration_hash(bindings),
        )
        write_runtime_status(record, self.path)

        dead = inspect_runtime_status(
            bindings,
            path=self.path,
            process_start_lookup=lambda _pid: None,
            instance_probe=lambda: False,
        )
        reused = inspect_runtime_status(
            bindings,
            path=self.path,
            process_start_lookup=lambda _pid: 999999,
            instance_probe=lambda: False,
        )
        replacement_backend = inspect_runtime_status(
            bindings,
            path=self.path,
            process_start_lookup=lambda _pid: None,
            instance_probe=lambda: True,
        )

        self.assertIs(dead.state, RuntimeApplicationState.NOT_RUNNING)
        self.assertIs(reused.state, RuntimeApplicationState.NOT_RUNNING)
        self.assertIs(
            replacement_backend.state,
            RuntimeApplicationState.RUNNING_UNVERIFIED,
        )

    def test_live_process_distinguishes_applied_and_restart_required(self) -> None:
        loaded = {"/fi": "φ"}
        record = RuntimeStatusRecord(
            pid=42,
            started_at=123456,
            config_hash=configuration_hash(loaded),
        )
        write_runtime_status(record, self.path)
        lookup = lambda _pid: 123456

        applied = inspect_runtime_status(
            loaded,
            path=self.path,
            process_start_lookup=lookup,
            instance_probe=lambda: False,
        )
        stale = inspect_runtime_status(
            {"/fi": "Φ"},
            path=self.path,
            process_start_lookup=lookup,
            instance_probe=lambda: False,
        )

        self.assertIs(
            applied.state,
            RuntimeApplicationState.RUNNING_APPLIED,
        )
        self.assertIs(
            stale.state,
            RuntimeApplicationState.RUNNING_RESTART_REQUIRED,
        )

    def test_missing_or_corrupt_status_uses_nonintrusive_instance_probe(
        self,
    ) -> None:
        missing_running = inspect_runtime_status(
            {},
            path=self.path,
            instance_probe=lambda: True,
        )
        missing_stopped = inspect_runtime_status(
            {},
            path=self.path,
            instance_probe=lambda: False,
        )
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{broken", encoding="utf-8")
        corrupt_running = inspect_runtime_status(
            {},
            path=self.path,
            instance_probe=lambda: True,
        )

        self.assertIs(
            missing_running.state,
            RuntimeApplicationState.RUNNING_UNVERIFIED,
        )
        self.assertIs(
            missing_stopped.state,
            RuntimeApplicationState.NOT_RUNNING,
        )
        self.assertIs(
            corrupt_running.state,
            RuntimeApplicationState.RUNNING_UNVERIFIED,
        )

    def test_effective_hash_is_order_independent_and_content_sensitive(
        self,
    ) -> None:
        first = {"/a": "甲", "/b": "乙"}
        second = {"/b": "乙", "/a": "甲"}

        self.assertEqual(
            effective_bindings_hash(first),
            effective_bindings_hash(second),
        )
        self.assertNotEqual(
            effective_bindings_hash(first),
            effective_bindings_hash({"/a": "甲", "/b": "变化"}),
        )
        self.assertNotEqual(
            effective_bindings_hash(first),
            effective_bindings_hash({"/a": "甲"}),
        )

    def test_clear_only_removes_the_expected_process_record(self) -> None:
        first = RuntimeStatusRecord(
            pid=1,
            started_at=10,
            config_hash=configuration_hash({}),
        )
        replacement = RuntimeStatusRecord(
            pid=2,
            started_at=20,
            config_hash=configuration_hash({"/a": "甲"}),
        )
        write_runtime_status(replacement, self.path)

        clear_runtime_status(self.path, expected_record=first)
        self.assertEqual(read_runtime_status(self.path), replacement)

        clear_runtime_status(self.path, expected_record=replacement)
        self.assertFalse(self.path.exists())

    def test_published_status_is_removed_on_normal_and_exception_exit(self) -> None:
        bindings = {"/fi": "φ"}
        with published_runtime_status(
            bindings,
            path=self.path,
            pid=42,
            started_at=123456,
        ):
            self.assertTrue(self.path.is_file())
        self.assertFalse(self.path.exists())

        with self.assertRaisesRegex(RuntimeError, "simulated"):
            with published_runtime_status(
                bindings,
                path=self.path,
                pid=42,
                started_at=123456,
            ):
                self.assertTrue(self.path.is_file())
                raise RuntimeError("simulated")
        self.assertFalse(self.path.exists())

    def test_status_write_failure_does_not_block_backend_scope(self) -> None:
        entered = False

        with patch(
            "scitype.runtime_status.write_runtime_status",
            side_effect=RuntimeStatusError("simulated"),
        ):
            with published_runtime_status(
                {"/fi": "φ"},
                path=self.path,
                pid=42,
                started_at=123456,
            ):
                entered = True

        self.assertTrue(entered)


if __name__ == "__main__":
    unittest.main()
