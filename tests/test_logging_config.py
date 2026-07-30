"""Tests for SciType's minimal rotating background log."""

from logging.handlers import RotatingFileHandler
from pathlib import Path
import tempfile
import unittest

from scitype.logging_config import (
    close_logging,
    configure_logging,
    get_log_path,
)
from scitype.windows_input import (
    InsertionOutcome,
    VK_OEM_2,
    VK_SPACE,
    VK_TAB,
    WindowsInputAdapter,
    WindowsKeyEvent,
)


_TEST_DIRECTORY = Path(__file__).resolve().parent


class LoggingConfigurationTests(unittest.TestCase):
    def test_log_path_is_under_local_app_data_scitype(self) -> None:
        base_directory = Path("D:/example/LocalAppData")

        self.assertEqual(
            get_log_path(base_directory),
            base_directory / "SciType" / "scitype.log",
        )

    def test_logger_uses_utf8_rotating_file_handler(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=_TEST_DIRECTORY,
        ) as temporary_directory:
            log_path = Path(temporary_directory, "SciType", "scitype.log")
            logger = configure_logging(
                log_path,
                logger_name=f"scitype.test.{id(self)}",
                max_bytes=1024,
                backup_count=2,
            )
            try:
                self.assertEqual(len(logger.handlers), 1)
                handler = logger.handlers[0]
                self.assertIsInstance(handler, RotatingFileHandler)
                self.assertEqual(handler.maxBytes, 1024)
                self.assertEqual(handler.backupCount, 2)
                self.assertEqual(
                    Path(handler.baseFilename),
                    log_path.resolve(),
                )
            finally:
                close_logging(logger)

    def test_simulated_keys_and_command_buffer_are_not_logged(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=_TEST_DIRECTORY,
        ) as temporary_directory:
            log_path = Path(temporary_directory, "scitype.log")
            logger = configure_logging(
                log_path,
                logger_name=f"scitype.privacy.{id(self)}",
            )
            try:
                logger.info("程序启动")
                adapter = WindowsInputAdapter()
                for vk_code in (VK_OEM_2, 0x58, 0x57, VK_SPACE):
                    adapter.handle_event(
                        WindowsKeyEvent(vk_code, is_key_down=True),
                    )
                    adapter.handle_event(
                        WindowsKeyEvent(vk_code, is_key_down=False),
                    )
                logger.info("程序退出")
                for handler in logger.handlers:
                    handler.flush()

                log_text = log_path.read_text(encoding="utf-8")
            finally:
                close_logging(logger)

        self.assertIn("程序启动", log_text)
        self.assertIn("程序退出", log_text)
        self.assertNotIn("/xw", log_text)
        self.assertNotIn("命令缓冲", log_text)
        self.assertNotIn("vk_code", log_text)

    def test_log_file_rotates_instead_of_growing_without_limit(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=_TEST_DIRECTORY,
        ) as temporary_directory:
            log_path = Path(temporary_directory, "scitype.log")
            logger = configure_logging(
                log_path,
                logger_name=f"scitype.rotation.{id(self)}",
                max_bytes=120,
                backup_count=1,
            )
            try:
                for _ in range(10):
                    logger.info("程序启动")
                for handler in logger.handlers:
                    handler.flush()
            finally:
                close_logging(logger)

            self.assertTrue(log_path.exists())
            self.assertTrue(Path(f"{log_path}.1").exists())

    def test_fraction_session_does_not_log_formula_or_window_data(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=_TEST_DIRECTORY,
        ) as temporary_directory:
            log_path = Path(temporary_directory, "scitype.log")
            logger = configure_logging(
                log_path,
                logger_name=f"scitype.fraction.privacy.{id(self)}",
            )
            try:
                logger.info("程序启动")
                adapter = WindowsInputAdapter()
                window = 8123
                decision = None
                for vk_code in (VK_OEM_2, 0x46, 0x53, VK_SPACE):
                    decision = adapter.handle_event(
                        WindowsKeyEvent(
                            vk_code,
                            is_key_down=True,
                            foreground_window=window,
                        ),
                    )
                    adapter.handle_event(
                        WindowsKeyEvent(
                            vk_code,
                            is_key_down=False,
                            foreground_window=window,
                        ),
                    )

                assert decision is not None
                adapter.complete_insertion(
                    decision,
                    InsertionOutcome.PRIMARY,
                )
                for _ in range(2):
                    adapter.handle_event(
                        WindowsKeyEvent(
                            VK_TAB,
                            is_key_down=True,
                            foreground_window=window,
                        ),
                    )
                    adapter.handle_event(
                        WindowsKeyEvent(
                            VK_TAB,
                            is_key_down=False,
                            foreground_window=window,
                        ),
                    )
                logger.info("程序退出")
                for handler in logger.handlers:
                    handler.flush()

                log_text = log_path.read_text(encoding="utf-8")
            finally:
                close_logging(logger)

        self.assertNotIn("/fs", log_text)
        self.assertNotIn("()/()", log_text)
        self.assertNotIn("8123", log_text)
        self.assertNotIn("Tab", log_text)


if __name__ == "__main__":
    unittest.main()
