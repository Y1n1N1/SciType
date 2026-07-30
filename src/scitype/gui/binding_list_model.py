"""Qt list model for the filtered user-binding list."""

from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt

from scitype.gui.view_model import BindingSettingsViewModel


class BindingListModel(QAbstractListModel):
    """Expose ViewModel rows without owning or persisting binding data."""

    TriggerRole = Qt.ItemDataRole.UserRole + 1
    PreviewRole = Qt.ItemDataRole.UserRole + 2
    EnabledRole = Qt.ItemDataRole.UserRole + 3
    SourceIndexRole = Qt.ItemDataRole.UserRole + 4

    def __init__(
        self,
        view_model: BindingSettingsViewModel,
        parent: object | None = None,
    ) -> None:
        super().__init__(parent)
        self._view_model = view_model
        self._query = ""
        self._source_indices = view_model.filtered_indices("")

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._source_indices)

    def data(
        self,
        index: QModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object | None:
        if not index.isValid() or not 0 <= index.row() < self.rowCount():
            return None

        source_index = self._source_indices[index.row()]
        binding = self._view_model.bindings[source_index]
        if role in (
            Qt.ItemDataRole.DisplayRole,
            self.TriggerRole,
        ):
            return binding.trigger
        if role == self.PreviewRole:
            return self._view_model.short_replacement_preview(
                binding.replacement,
            )
        if role == self.EnabledRole:
            return binding.enabled
        if role == self.SourceIndexRole:
            return source_index
        if role == Qt.ItemDataRole.ToolTipRole:
            status = "已启用" if binding.enabled else "已停用"
            return (
                f"{binding.trigger}\n"
                f"{self._view_model.short_replacement_preview(binding.replacement)}"
                f"\n{status}"
            )
        if role == Qt.ItemDataRole.AccessibleTextRole:
            status = "已启用" if binding.enabled else "已停用"
            return f"{binding.trigger}，{status}"
        return None

    def roleNames(self) -> dict[int, bytes]:
        roles = super().roleNames()
        roles.update(
            {
                self.TriggerRole: b"trigger",
                self.PreviewRole: b"preview",
                self.EnabledRole: b"enabled",
                self.SourceIndexRole: b"sourceIndex",
            },
        )
        return roles

    @property
    def query(self) -> str:
        return self._query

    def set_query(self, query: str) -> None:
        """Reset rows to the ViewModel's current filtered indices."""
        if query == self._query:
            return
        self._query = query
        self.refresh()

    def refresh(self) -> None:
        """Rebuild row mapping after a save, delete, or search."""
        self.beginResetModel()
        self._source_indices = self._view_model.filtered_indices(self._query)
        self.endResetModel()

    def source_index_for_row(self, row: int) -> int | None:
        if not 0 <= row < len(self._source_indices):
            return None
        return self._source_indices[row]

    def row_for_source_index(self, source_index: int) -> int | None:
        try:
            return self._source_indices.index(source_index)
        except ValueError:
            return None
