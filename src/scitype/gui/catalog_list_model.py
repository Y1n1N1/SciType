"""Qt list model over the read-only catalog service snapshot."""

from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt

from scitype.catalog import (
    CatalogEntry,
    CatalogSnapshot,
    CatalogUserState,
    catalog_preview,
    query_catalog,
)


def catalog_status_text(entry: CatalogEntry) -> str:
    """Return a concise, user-facing precedence or conflict state."""
    if entry.conflict is not None:
        return "因触发词冲突，当前不可用于输入"
    if entry.user_state is CatalogUserState.DISABLED:
        return "已被用户禁用"
    if entry.user_state is CatalogUserState.OVERRIDDEN:
        return "已被用户绑定覆盖"
    return ""


class CatalogListModel(QAbstractListModel):
    """Filter immutable catalog rows without touching source files."""

    NameRole = Qt.ItemDataRole.UserRole + 1
    TriggerRole = Qt.ItemDataRole.UserRole + 2
    PreviewRole = Qt.ItemDataRole.UserRole + 3
    CategoryRole = Qt.ItemDataRole.UserRole + 4
    SourceRole = Qt.ItemDataRole.UserRole + 5
    StatusRole = Qt.ItemDataRole.UserRole + 6
    EntryRole = Qt.ItemDataRole.UserRole + 7

    def __init__(
        self,
        snapshot: CatalogSnapshot,
        parent: object | None = None,
    ) -> None:
        super().__init__(parent)
        self._snapshot = snapshot
        self._query = ""
        self._category: str | None = None
        self._source_id: str | None = None
        self._entries = query_catalog(snapshot)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._entries)

    def data(
        self,
        index: QModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object | None:
        if not index.isValid() or not 0 <= index.row() < len(self._entries):
            return None
        entry = self._entries[index.row()]
        if role in (Qt.ItemDataRole.DisplayRole, self.NameRole):
            return entry.name
        if role == self.TriggerRole:
            return entry.trigger
        if role == self.PreviewRole:
            return catalog_preview(entry.replacement)
        if role == self.CategoryRole:
            return entry.category
        if role == self.SourceRole:
            return entry.source_name
        if role == self.StatusRole:
            return catalog_status_text(entry)
        if role == self.EntryRole:
            return entry
        if role == Qt.ItemDataRole.ToolTipRole:
            status = catalog_status_text(entry)
            parts = (
                entry.name,
                entry.trigger,
                catalog_preview(entry.replacement),
                entry.source_name,
            )
            return "\n".join((*parts, status) if status else parts)
        if role == Qt.ItemDataRole.AccessibleTextRole:
            return f"{entry.name}，{entry.trigger}，{entry.source_name}"
        return None

    def set_snapshot(self, snapshot: CatalogSnapshot) -> None:
        self.beginResetModel()
        self._snapshot = snapshot
        self._entries = self._filtered()
        self.endResetModel()

    def set_filters(
        self,
        *,
        query: str | None = None,
        category: str | None | object = ...,
        source_id: str | None | object = ...,
    ) -> None:
        """Update one or more filters and reset the small read-only model."""
        if query is not None:
            self._query = query
        if category is not ...:
            self._category = category
        if source_id is not ...:
            self._source_id = source_id
        self.beginResetModel()
        self._entries = self._filtered()
        self.endResetModel()

    def entry_at(self, row: int) -> CatalogEntry | None:
        if not 0 <= row < len(self._entries):
            return None
        return self._entries[row]

    @property
    def snapshot(self) -> CatalogSnapshot:
        return self._snapshot

    def _filtered(self) -> tuple[CatalogEntry, ...]:
        return query_catalog(
            self._snapshot,
            query=self._query,
            category=self._category,
            source_id=self._source_id,
        )
