"""Tests for the formal Windows app without a real Hook or mutex."""

from __future__ import annotations

import io
import logging
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import json

import scitype.app as app
import scitype.windows_demo as windows_demo
from scitype.catalog_masks import (
    create_catalog_mask_document,
    save_catalog_masks,
)
from scitype.app import (
    ApplicationStatus,
    _console_message,
    load_runtime_dictionary,
    run_windows_application,
    verify_packaged_resources,
)
from scitype.user_bindings import (
    UserBinding,
    create_user_binding_document,
    save_user_bindings,
)


class _FakeInstanceLock:
    def __init__(self, *, is_primary: bool, events: list[str]) -> None:
        self.is_primary = is_primary
        self.events = events

    def __enter__(self) -> _FakeInstanceLock:
        self.events.append("instance_enter")
        return self

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        self.events.append("instance_exit")


class _FakeHook:
    def __init__(self, events: list[str], *, should_fail: bool = False) -> None:
        self.events = events
        self.should_fail = should_fail

    def run(self) -> None:
        self.events.append("hook_run")
        if self.should_fail:
            raise RuntimeError("simulated hook failure")


class _FakeRuntimeStatus:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def __enter__(self) -> None:
        self.events.append("status_enter")

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        self.events.append("status_exit")


class WindowsStartupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.logger = logging.getLogger(f"scitype.startup.{id(self)}")
        self.logger.handlers = [logging.NullHandler()]
        self.logger.propagate = False

    def test_existing_instance_never_loads_dictionary_or_creates_hook(
        self,
    ) -> None:
        events: list[str] = []

        status = run_windows_application(
            instance_lock=_FakeInstanceLock(
                is_primary=False,
                events=events,
            ),
            dictionary_loader=lambda: (
                events.append("dictionary") or {"/fi": "φ"}
            ),
            hook_factory=lambda _dictionary: _FakeHook(events),
            logger=self.logger,
        )

        self.assertIs(status, ApplicationStatus.ALREADY_RUNNING)
        self.assertEqual(events, ["instance_enter", "instance_exit"])

    def test_pythonw_without_console_streams_does_not_fail(self) -> None:
        with (
            patch("scitype.app.sys.stdout", None),
            patch("scitype.app.sys.stderr", None),
        ):
            _console_message("foreground")
            _console_message("error", is_error=True)

    def test_primary_then_rejected_second_instance_creates_only_one_hook(
        self,
    ) -> None:
        events: list[str] = []
        hook_creation_count = 0

        def create_hook(_dictionary: object) -> _FakeHook:
            nonlocal hook_creation_count
            hook_creation_count += 1
            events.append("hook_factory")
            return _FakeHook(events)

        first_status = run_windows_application(
            instance_lock=_FakeInstanceLock(
                is_primary=True,
                events=events,
            ),
            dictionary_loader=lambda: (
                events.append("dictionary") or {"/fi": "φ"}
            ),
            hook_factory=create_hook,
            logger=self.logger,
        )
        second_status = run_windows_application(
            instance_lock=_FakeInstanceLock(
                is_primary=False,
                events=events,
            ),
            dictionary_loader=lambda: (
                events.append("unexpected_dictionary") or {"/fi": "φ"}
            ),
            hook_factory=create_hook,
            logger=self.logger,
        )

        self.assertIs(first_status, ApplicationStatus.STOPPED)
        self.assertIs(second_status, ApplicationStatus.ALREADY_RUNNING)
        self.assertEqual(hook_creation_count, 1)
        self.assertEqual(
            events,
            [
                "instance_enter",
                "dictionary",
                "hook_factory",
                "hook_run",
                "instance_exit",
                "instance_enter",
                "instance_exit",
            ],
        )

    def test_instance_resource_is_released_after_hook_failure(self) -> None:
        events: list[str] = []

        with self.assertRaisesRegex(RuntimeError, "hook failure"):
            run_windows_application(
                instance_lock=_FakeInstanceLock(
                    is_primary=True,
                    events=events,
                ),
                dictionary_loader=lambda: (
                    events.append("dictionary") or {"/fi": "φ"}
                ),
                hook_factory=lambda _dictionary: _FakeHook(
                    events,
                    should_fail=True,
                ),
                logger=self.logger,
            )

        self.assertEqual(events[-1], "instance_exit")

    def test_active_dictionary_is_passed_to_hook_factory(self) -> None:
        events: list[str] = []
        active_dictionary = {"/mine": "自定义"}
        received_dictionary: object | None = None

        def create_hook(dictionary: object) -> _FakeHook:
            nonlocal received_dictionary
            received_dictionary = dictionary
            return _FakeHook(events)

        status = run_windows_application(
            instance_lock=_FakeInstanceLock(
                is_primary=True,
                events=events,
            ),
            dictionary_loader=lambda: active_dictionary,
            hook_factory=create_hook,
            logger=self.logger,
        )

        self.assertIs(status, ApplicationStatus.STOPPED)
        self.assertIs(received_dictionary, active_dictionary)

    def test_runtime_status_wraps_hook_and_cleans_after_failure(self) -> None:
        events: list[str] = []

        with self.assertRaisesRegex(RuntimeError, "hook failure"):
            run_windows_application(
                instance_lock=_FakeInstanceLock(
                    is_primary=True,
                    events=events,
                ),
                dictionary_loader=lambda: (
                    events.append("dictionary") or {"/fi": "φ"}
                ),
                hook_factory=lambda _dictionary: _FakeHook(
                    events,
                    should_fail=True,
                ),
                runtime_status_factory=lambda _dictionary: (
                    _FakeRuntimeStatus(events)
                ),
                logger=self.logger,
            )

        self.assertEqual(
            events,
            [
                "instance_enter",
                "dictionary",
                "status_enter",
                "hook_run",
                "status_exit",
                "instance_exit",
            ],
        )

    def test_default_dictionary_failure_prevents_hook_and_releases_instance(
        self,
    ) -> None:
        events: list[str] = []

        def fail_dictionary_load() -> dict[str, str]:
            events.append("dictionary")
            raise RuntimeError("invalid default dictionary")

        def forbidden_hook_factory(_dictionary: object) -> _FakeHook:
            events.append("unexpected_hook")
            return _FakeHook(events)

        with self.assertRaisesRegex(RuntimeError, "invalid default dictionary"):
            run_windows_application(
                instance_lock=_FakeInstanceLock(
                    is_primary=True,
                    events=events,
                ),
                dictionary_loader=fail_dictionary_load,
                hook_factory=forbidden_hook_factory,
                logger=self.logger,
            )

        self.assertEqual(
            events,
            ["instance_enter", "dictionary", "instance_exit"],
        )

    def test_invalid_user_config_uses_defaults_and_still_runs_hook(
        self,
    ) -> None:
        events: list[str] = []
        log_stream = io.StringIO()
        logger = logging.getLogger(f"scitype.safe-config.{id(self)}")
        logger.handlers = [logging.StreamHandler(log_stream)]
        logger.setLevel(logging.INFO)
        logger.propagate = False
        private_trigger = "/ceshiyinsi"
        private_replacement = "虚构内容${cursor}${cursor}"

        with tempfile.TemporaryDirectory() as temporary_directory:
            config_directory = Path(temporary_directory, "SciType")
            config_directory.mkdir()
            config_path = config_directory / "user_bindings.json"
            original_text = (
                '{"schema_version":1,"bindings":['
                f'{{"trigger":"{private_trigger}",'
                f'"replacement":"{private_replacement}",'
                '"enabled":true}]}'
            )
            config_path.write_text(original_text, encoding="utf-8")

            def create_hook(dictionary: object) -> _FakeHook:
                self.assertIn("/fi", dictionary)
                events.append("hook_factory")
                return _FakeHook(events)

            with patch.dict(
                os.environ,
                {"LOCALAPPDATA": temporary_directory},
            ):
                status = run_windows_application(
                    instance_lock=_FakeInstanceLock(
                        is_primary=True,
                        events=events,
                    ),
                    dictionary_loader=lambda: load_runtime_dictionary(
                        logger,
                    ),
                    hook_factory=create_hook,
                    logger=logger,
                )

            self.assertEqual(
                config_path.read_text(encoding="utf-8"),
                original_text,
            )

        self.assertIs(status, ApplicationStatus.STOPPED)
        self.assertIn("hook_run", events)
        logged = log_stream.getvalue()
        self.assertIn("用户配置加载失败", logged)
        self.assertNotIn(private_trigger, logged)
        self.assertNotIn(private_replacement, logged)

    def test_runtime_dictionary_applies_user_priority_over_local_pack(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            scitype_directory = Path(temporary_directory, "SciType")
            packs_directory = scitype_directory / "packs"
            packs_directory.mkdir(parents=True)
            (packs_directory / "local.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "pack": {
                            "id": "test.runtime",
                            "name": "运行时包",
                            "version": "1.0.0",
                        },
                        "entries": [
                            {
                                "name": "本地符号",
                                "category": "其他",
                                "trigger": "/local",
                                "replacement": "扩展值",
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            config_path = scitype_directory / "user_bindings.json"
            save_user_bindings(
                create_user_binding_document(
                    [UserBinding("/local", "用户值", True)],
                ),
                config_path,
            )

            with patch.dict(
                os.environ,
                {"LOCALAPPDATA": temporary_directory},
            ):
                enabled = load_runtime_dictionary(self.logger)
            self.assertEqual(enabled["/local"], "用户值")

            save_user_bindings(
                create_user_binding_document(
                    [UserBinding("/local", "停用说明", False)],
                ),
                config_path,
            )
            with patch.dict(
                os.environ,
                {"LOCALAPPDATA": temporary_directory},
            ):
                disabled = load_runtime_dictionary(self.logger)
            self.assertNotIn("/local", disabled)

    def test_runtime_dictionary_applies_catalog_masks_last(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            scitype_directory = Path(temporary_directory, "SciType")
            user_path = scitype_directory / "user_bindings.json"
            mask_path = scitype_directory / "catalog_masks.json"
            save_user_bindings(
                create_user_binding_document(
                    [UserBinding("/jf", "用户积分", True)],
                ),
                user_path,
            )
            save_catalog_masks(
                create_catalog_mask_document(("/jf",)),
                mask_path,
            )

            with patch.dict(
                os.environ,
                {"LOCALAPPDATA": temporary_directory},
            ):
                dictionary = load_runtime_dictionary(self.logger)

        self.assertNotIn("/jf", dictionary)

    def test_packaged_resource_check_loads_dictionary_and_license(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            Path(temporary_directory, "LICENSE").write_text(
                "license",
                encoding="utf-8",
            )
            with patch(
                "scitype.app.load_dictionary",
                return_value={"/fi": "φ"},
            ) as dictionary_loader:
                verify_packaged_resources(license_root=temporary_directory)

        dictionary_loader.assert_called_once_with()

    def test_packaged_resource_check_rejects_missing_license(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary_directory,
            patch(
                "scitype.app.load_dictionary",
                return_value={"/fi": "φ"},
            ),
            self.assertRaisesRegex(RuntimeError, "LICENSE 缺失"),
        ):
            verify_packaged_resources(license_root=temporary_directory)

    def test_windows_demo_is_a_compatibility_wrapper(self) -> None:
        self.assertIs(windows_demo.main, app.main)
        self.assertIs(
            windows_demo.run_windows_application,
            app.run_windows_application,
        )


if __name__ == "__main__":
    unittest.main()
