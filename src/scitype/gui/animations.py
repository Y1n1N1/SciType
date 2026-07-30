"""Central, optional micro-animation helpers for the settings window."""

from __future__ import annotations

import os

from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QPropertyAnimation,
    QTimer,
    QVariantAnimation,
)
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QLabel,
    QListView,
    QStackedWidget,
    QWidget,
)

from .design_tokens import (
    FIELD_ERROR_FADE_MS,
    LIST_SELECTION_TRANSITION_MS,
    PAGE_TRANSITION_MS,
    TOAST_FADE_MS,
    TOAST_VISIBLE_MS,
)


def animations_enabled_by_default() -> bool:
    """Allow deterministic tests and accessibility setups to disable motion."""
    value = os.environ.get("SCITYPE_DISABLE_ANIMATIONS", "").strip()
    return value not in {"1", "true", "yes"}


class PageTransitionController(QObject):
    """Fade stacked pages without keeping graphics effects attached."""

    def __init__(
        self,
        stack: QStackedWidget,
        *,
        enabled: bool | None = None,
    ) -> None:
        super().__init__(stack)
        self._stack = stack
        self.enabled = (
            animations_enabled_by_default()
            if enabled is None
            else enabled
        )
        self._animation: QPropertyAnimation | None = None
        self._effect_widget: QWidget | None = None
        self._target_index: int | None = None

    @property
    def is_running(self) -> bool:
        return self._animation is not None

    def show(self, index: int) -> None:
        """Show one page immediately or with a 168 ms two-stage fade."""
        if not 0 <= index < self._stack.count():
            raise IndexError(index)
        self._stop_and_cleanup()
        if not self.enabled or index == self._stack.currentIndex():
            self._stack.setCurrentIndex(index)
            return

        self._target_index = index
        current = self._stack.currentWidget()
        if current is None:
            self._stack.setCurrentIndex(index)
            return
        self._animate(
            current,
            start=1.0,
            end=0.82,
            duration=PAGE_TRANSITION_MS // 2,
            finished=self._begin_fade_in,
        )

    def _begin_fade_in(self) -> None:
        target_index = self._target_index
        self._clear_effect()
        self._animation = None
        if target_index is None:
            return
        self._stack.setCurrentIndex(target_index)
        target = self._stack.currentWidget()
        if target is None:
            self._target_index = None
            return
        self._animate(
            target,
            start=0.82,
            end=1.0,
            duration=PAGE_TRANSITION_MS - PAGE_TRANSITION_MS // 2,
            finished=self._finish,
        )

    def _finish(self) -> None:
        self._clear_effect()
        self._animation = None
        self._target_index = None

    def _animate(
        self,
        widget: QWidget,
        *,
        start: float,
        end: float,
        duration: int,
        finished: object,
    ) -> None:
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(start)
        widget.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(duration)
        animation.setStartValue(start)
        animation.setEndValue(end)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(finished)
        self._effect_widget = widget
        self._animation = animation
        animation.start()

    def _stop_and_cleanup(self) -> None:
        if self._animation is not None:
            self._animation.stop()
            self._animation.deleteLater()
            self._animation = None
        self._clear_effect()
        self._target_index = None

    def _clear_effect(self) -> None:
        widget = self._effect_widget
        self._effect_widget = None
        if widget is not None:
            try:
                widget.setGraphicsEffect(None)
            except RuntimeError:
                pass


class ToastController(QObject):
    """Show non-modal status text with a short fade and no persistent effect."""

    def __init__(
        self,
        label: QLabel,
        *,
        enabled: bool | None = None,
    ) -> None:
        super().__init__(label)
        self._label = label
        self.enabled = (
            animations_enabled_by_default()
            if enabled is None
            else enabled
        )
        self._animation: QPropertyAnimation | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)
        self._effect: QGraphicsOpacityEffect | None = None

    def show(self, message: str, *, success: bool = True) -> None:
        """Display one content-safe operation result without a modal."""
        self._cancel()
        self._label.setText(message)
        self._label.setProperty("success", success)
        self._label.style().unpolish(self._label)
        self._label.style().polish(self._label)
        self._label.show()
        if not self.enabled:
            self._timer.start(TOAST_VISIBLE_MS)
            return
        self._effect = QGraphicsOpacityEffect(self._label)
        self._label.setGraphicsEffect(self._effect)
        self._animate(0.0, 1.0, self._hold)

    def _hold(self) -> None:
        self._clear_animation()
        self._timer.start(TOAST_VISIBLE_MS)

    def _fade_out(self) -> None:
        if not self.enabled:
            self._label.hide()
            return
        self._animate(1.0, 0.0, self._finish)

    def _finish(self) -> None:
        self._clear_animation()
        self._clear_effect()
        self._label.hide()

    def _animate(
        self,
        start: float,
        end: float,
        finished: object,
    ) -> None:
        if self._effect is None:
            self._effect = QGraphicsOpacityEffect(self._label)
            self._label.setGraphicsEffect(self._effect)
        animation = QPropertyAnimation(self._effect, b"opacity", self)
        animation.setDuration(TOAST_FADE_MS)
        animation.setStartValue(start)
        animation.setEndValue(end)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(finished)
        self._animation = animation
        animation.start()

    def _cancel(self) -> None:
        self._timer.stop()
        self._clear_animation()
        self._clear_effect()

    def _clear_animation(self) -> None:
        if self._animation is not None:
            self._animation.stop()
            self._animation.deleteLater()
            self._animation = None

    def _clear_effect(self) -> None:
        if self._effect is not None:
            self._label.setGraphicsEffect(None)
            self._effect = None


class SelectionTransitionController(QObject):
    """Expose a short selection-color progress value to list delegates."""

    PROPERTY_NAME = "scitypeSelectionProgress"

    def __init__(
        self,
        view: QListView,
        *,
        enabled: bool | None = None,
    ) -> None:
        super().__init__(view)
        self._view = view
        self.enabled = (
            animations_enabled_by_default()
            if enabled is None
            else enabled
        )
        self._animation: QVariantAnimation | None = None
        self._view.setProperty(self.PROPERTY_NAME, 1.0)
        view.selectionModel().currentChanged.connect(self._start)

    def _start(self, *_args: object) -> None:
        if self._animation is not None:
            self._animation.stop()
            self._animation.deleteLater()
            self._animation = None
        if not self.enabled:
            self._view.setProperty(self.PROPERTY_NAME, 1.0)
            self._view.viewport().update()
            return

        animation = QVariantAnimation(self)
        animation.setDuration(LIST_SELECTION_TRANSITION_MS)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.valueChanged.connect(self._set_progress)
        animation.finished.connect(self._finish)
        self._animation = animation
        animation.start()

    def _set_progress(self, value: object) -> None:
        self._view.setProperty(self.PROPERTY_NAME, float(value))
        self._view.viewport().update()

    def _finish(self) -> None:
        self._view.setProperty(self.PROPERTY_NAME, 1.0)
        self._view.viewport().update()
        if self._animation is not None:
            self._animation.deleteLater()
            self._animation = None


class RevealController(QObject):
    """Fade one inline message in, then immediately release its effect."""

    def __init__(
        self,
        widget: QWidget,
        *,
        enabled: bool | None = None,
    ) -> None:
        super().__init__(widget)
        self._widget = widget
        self.enabled = (
            animations_enabled_by_default()
            if enabled is None
            else enabled
        )
        self._animation: QPropertyAnimation | None = None
        self._effect: QGraphicsOpacityEffect | None = None

    def set_visible(self, visible: bool) -> None:
        if not visible:
            self._cleanup()
            self._widget.hide()
            return
        if self._widget.isVisible() and self._effect is None:
            return
        self._cleanup()
        self._widget.show()
        if not self.enabled:
            return
        effect = QGraphicsOpacityEffect(self._widget)
        effect.setOpacity(0.0)
        self._widget.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(FIELD_ERROR_FADE_MS)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(self._cleanup)
        self._effect = effect
        self._animation = animation
        animation.start()

    def _cleanup(self) -> None:
        if self._animation is not None:
            self._animation.stop()
            self._animation.deleteLater()
            self._animation = None
        if self._effect is not None:
            self._widget.setGraphicsEffect(None)
            self._effect = None
