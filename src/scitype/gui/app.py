"""Standalone Qt Widgets entry point for SciType settings."""

from __future__ import annotations

from collections.abc import Sequence
import logging
from pathlib import Path
import sys

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QMessageBox

from scitype.dictionary import load_dictionary
from scitype.gui.main_window import MainWindow
from scitype.gui.styles import APP_STYLE
from scitype.gui.view_model import BindingSettingsViewModel
from scitype.logging_config import (
    close_logging,
    configure_logging,
    get_log_path,
)


SETTINGS_LOG_FILE_NAME = "scitype-settings.log"


def _frozen_resource_root() -> Path | None:
    resource_root = getattr(sys, "_MEIPASS", None)
    return Path(resource_root) if resource_root is not None else None


def verify_settings_resources() -> None:
    """Verify settings resources without opening a Qt window."""
    if not load_dictionary():
        raise RuntimeError("随包快捷绑定为空")
    resource_root = _frozen_resource_root()
    if resource_root is None:
        return
    for filename in ("LICENSE", "THIRD_PARTY_NOTICES.txt"):
        path = resource_root / filename
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"随包资源缺失：{filename}")


def _configure_settings_logger() -> logging.Logger:
    log_path = get_log_path().with_name(SETTINGS_LOG_FILE_NAME)
    return configure_logging(
        log_path,
        logger_name="scitype.settings",
    )


def create_application(
    argv: Sequence[str] | None = None,
) -> QApplication:
    """Create or return the process-wide QApplication."""
    existing = QApplication.instance()
    if isinstance(existing, QApplication):
        return existing
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough,
    )
    application = QApplication(
        list(sys.argv if argv is None else argv),
    )
    QCoreApplication.setOrganizationName("SciType")
    QCoreApplication.setApplicationName("SciTypeSettings")
    application.setStyleSheet(APP_STYLE)
    return application


def run_settings_application(
    *,
    argv: Sequence[str] | None = None,
    config_path: str | Path | None = None,
    logger: logging.Logger | None = None,
) -> int:
    """Run the standalone settings window and return Qt's exit code."""
    application = create_application(argv)
    active_logger = logger or _configure_settings_logger()
    owns_logger = logger is None
    try:
        active_logger.info("设置程序启动")
        view_model = BindingSettingsViewModel(
            config_path=config_path,
            logger=active_logger,
        )
        window = MainWindow(view_model)
        window.show()
        return application.exec()
    except Exception as error:
        active_logger.error(
            "设置程序启动失败 exception=%s",
            type(error).__name__,
        )
        QMessageBox.critical(
            None,
            "SciType 设置",
            "设置程序无法启动。原配置未被修改，请查看日志。",
        )
        return 1
    finally:
        active_logger.info("设置程序退出")
        if owns_logger:
            close_logging(active_logger)


def main(argv: Sequence[str] | None = None) -> int:
    """Run verification mode or open the SciType settings program."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments == ["--verify-resources"]:
        try:
            verify_settings_resources()
        except Exception:
            return 1
        return 0
    if arguments:
        return 2
    return run_settings_application(argv=[sys.argv[0]])


if __name__ == "__main__":
    raise SystemExit(main())
