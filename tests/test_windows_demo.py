"""Tests for the formal Windows app without a real Hook or mutex."""

from __future__ import annotations

import logging
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import scitype.app as app
import scitype.windows_demo as windows_demo
from scitype.app import (
    ApplicationStatus,
    _console_message,
    run_windows_application,
    verify_packaged_resources,
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
            dictionary_loader=lambda: events.append("dictionary"),
            hook_factory=lambda: _FakeHook(events),
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

        def create_hook() -> _FakeHook:
            nonlocal hook_creation_count
            hook_creation_count += 1
            events.append("hook_factory")
            return _FakeHook(events)

        first_status = run_windows_application(
            instance_lock=_FakeInstanceLock(
                is_primary=True,
                events=events,
            ),
            dictionary_loader=lambda: events.append("dictionary"),
            hook_factory=create_hook,
            logger=self.logger,
        )
        second_status = run_windows_application(
            instance_lock=_FakeInstanceLock(
                is_primary=False,
                events=events,
            ),
            dictionary_loader=lambda: events.append("unexpected_dictionary"),
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
                dictionary_loader=lambda: events.append("dictionary"),
                hook_factory=lambda: _FakeHook(
                    events,
                    should_fail=True,
                ),
                logger=self.logger,
            )

        self.assertEqual(events[-1], "instance_exit")

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
