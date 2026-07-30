"""Small factual settings/about page with no speculative controls."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .design_tokens import SPACING


class SettingsPage(QWidget):
    """Expose only directories and information that already exist."""

    openConfigRequested = Signal()
    openLogsRequested = Signal()
    openLicensesRequested = Signal()
    refreshStatusRequested = Signal()

    def __init__(
        self,
        *,
        version: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("settingsPage")

        title = QLabel("设置")
        title.setObjectName("pageTitle")
        subtitle = QLabel("本地文件与程序信息")
        subtitle.setObjectName("secondaryText")

        surface = QWidget()
        surface.setObjectName("settingsSurface")
        surface_layout = QVBoxLayout(surface)
        surface_layout.setContentsMargins(
            SPACING.xl,
            SPACING.xl,
            SPACING.xl,
            SPACING.xl,
        )
        surface_layout.setSpacing(SPACING.lg)

        surface_layout.addLayout(
            self._info_row("当前版本", version),
        )
        surface_layout.addWidget(self._divider())
        surface_layout.addLayout(
            self._info_row("退出快捷键", "Ctrl + Alt + Q"),
        )
        surface_layout.addWidget(self._divider())
        self.runtime_status_value = QLabel()
        self.runtime_status_value.setObjectName("detailValue")
        self.runtime_status_value.setWordWrap(True)
        self.runtime_status_value.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse,
        )
        self.refresh_status_button = QPushButton("刷新状态")
        self.refresh_status_button.setObjectName("quietButton")
        surface_layout.addLayout(self._runtime_status_row())
        surface_layout.addWidget(self._divider())

        privacy_title = QLabel("隐私")
        privacy_title.setObjectName("sectionTitle")
        privacy = QLabel(
            "SciType 不记录触发词、输出内容、搜索词、剪贴板、"
            "窗口标题或普通键盘输入，也不发送网络请求。",
        )
        privacy.setObjectName("settingsDescription")
        privacy.setWordWrap(True)
        surface_layout.addWidget(privacy_title)
        surface_layout.addWidget(privacy)
        surface_layout.addWidget(self._divider())

        directory_title = QLabel("本地文件")
        directory_title.setObjectName("sectionTitle")
        surface_layout.addWidget(directory_title)

        self.open_config_button = QPushButton("打开用户配置文件夹")
        self.open_logs_button = QPushButton("打开日志文件夹")
        self.open_licenses_button = QPushButton("查看第三方许可证")

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(SPACING.sm)
        buttons.addWidget(self.open_config_button)
        buttons.addWidget(self.open_logs_button)
        buttons.addWidget(self.open_licenses_button)
        buttons.addStretch(1)
        surface_layout.addLayout(buttons)
        surface_layout.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            SPACING.xl,
            SPACING.xl,
            SPACING.xl,
            SPACING.xl,
        )
        layout.setSpacing(SPACING.xl)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(surface, 1)

        self.open_config_button.clicked.connect(self.openConfigRequested)
        self.open_logs_button.clicked.connect(self.openLogsRequested)
        self.open_licenses_button.clicked.connect(
            self.openLicensesRequested,
        )
        self.refresh_status_button.clicked.connect(
            self.refreshStatusRequested,
        )

    def set_runtime_status(self, message: str) -> None:
        """Show the latest verified backend/configuration relationship."""
        self.runtime_status_value.setText(message)

    def _runtime_status_row(self) -> QHBoxLayout:
        label = QLabel("运行状态")
        label.setObjectName("detailLabel")
        label.setMinimumWidth(100)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(SPACING.lg)
        row.addWidget(label)
        row.addWidget(self.runtime_status_value, 1)
        row.addWidget(self.refresh_status_button)
        return row

    @staticmethod
    def _info_row(label_text: str, value_text: str) -> QHBoxLayout:
        label = QLabel(label_text)
        label.setObjectName("detailLabel")
        label.setMinimumWidth(100)
        value = QLabel(value_text)
        value.setObjectName("detailValue")
        value.setWordWrap(True)
        value.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse,
        )
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(SPACING.lg)
        row.addWidget(label)
        row.addWidget(value, 1)
        return row

    @staticmethod
    def _divider() -> QFrame:
        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFrameShape(QFrame.Shape.HLine)
        return divider
