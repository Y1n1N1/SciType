"""Pure-Python state and operations for the SciType settings window."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import logging
import os
from pathlib import Path

from scitype.catalog import (
    CatalogEntry,
    CatalogSnapshot,
    PackErrorCode,
    PackImportPlan,
    PackValidationError,
    apply_user_states,
    execute_pack_import,
    load_catalog,
    prepare_pack_import,
)
from scitype.catalog_masks import (
    CATALOG_MASKS_FILE_NAME,
    CatalogMaskLoadStatus,
    CatalogMasksError,
    create_catalog_mask_document,
    save_catalog_masks,
)
from scitype.template import CURSOR_PLACEHOLDER
from scitype.runtime_status import (
    RUNTIME_STATUS_FILE_NAME,
    RuntimeApplicationState,
    RuntimeApplicationStatus,
    inspect_runtime_status,
)
from scitype.user_bindings import (
    ActiveBindingsSnapshot,
    ReloadStatus,
    UserBinding,
    UserBindingErrorCode,
    UserBindingLoadStatus,
    UserBindingsError,
    create_user_binding_document,
    get_user_bindings_path,
    has_trigger_conflict,
    load_active_bindings,
    reload_user_bindings,
    save_user_bindings,
    validate_replacement,
    validate_trigger,
)


CURSOR_PREVIEW = "⟨光标位置⟩"


@dataclass(frozen=True, slots=True)
class BindingDraft:
    """Editable fields for one new or existing user binding."""

    trigger: str
    replacement: str
    enabled: bool


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Field-level validation messages suitable for direct display."""

    field_errors: dict[str, str] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        return not self.field_errors


@dataclass(frozen=True, slots=True)
class OperationResult:
    """Outcome of a save or delete request."""

    success: bool
    message: str
    field_errors: dict[str, str] = field(default_factory=dict)
    restart_required: bool = False


_TRIGGER_ERROR_MESSAGES = {
    UserBindingErrorCode.INVALID_TRIGGER_TYPE: "触发词必须是文本。",
    UserBindingErrorCode.EMPTY_TRIGGER: "触发词不能为空。",
    UserBindingErrorCode.MISSING_TRIGGER_SLASH: "触发词必须以 / 开头。",
    UserBindingErrorCode.INVALID_TRIGGER_CHARACTERS: (
        "触发词只能包含小写英文字母和数字。"
    ),
}

_REPLACEMENT_ERROR_MESSAGES = {
    UserBindingErrorCode.INVALID_REPLACEMENT_TYPE: "输出内容必须是文本。",
    UserBindingErrorCode.EMPTY_REPLACEMENT: "输出内容不能为空。",
    UserBindingErrorCode.MULTIPLE_CURSOR_PLACEHOLDERS: (
        "最多只能设置一个光标位置。"
    ),
    UserBindingErrorCode.UNSUPPORTED_PLACEHOLDER: (
        "多槽位模板尚未支持。"
    ),
}


class BindingSettingsViewModel:
    """Own user-list state while delegating all persistence rules."""

    def __init__(
        self,
        *,
        config_path: str | os.PathLike[str] | None = None,
        default_bindings: dict[str, str] | None = None,
        packs_directory: str | os.PathLike[str] | None = None,
        catalog_masks_path: str | os.PathLike[str] | None = None,
        runtime_status_path: str | os.PathLike[str] | None = None,
        process_start_lookup: Callable[[int], int | None] | None = None,
        instance_probe: Callable[[], bool | None] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or logging.getLogger("scitype.settings")
        self._default_bindings_override = default_bindings
        resolved_packs_directory = self._resolve_packs_directory(
            config_path,
            packs_directory,
        )
        self._catalog = load_catalog(resolved_packs_directory)
        active_defaults = (
            self._catalog.catalog_bindings
            if default_bindings is None
            else default_bindings
        )
        self._snapshot = load_active_bindings(
            config_path,
            default_bindings=active_defaults,
            catalog_masks_path=catalog_masks_path,
        )
        self._catalog = apply_user_states(
            self._catalog,
            self._snapshot.user_document.bindings,
            self._snapshot.catalog_mask_document.disabled_triggers,
        )
        self._config_path = self._resolve_config_path(config_path)
        self._catalog_masks_path = (
            Path(catalog_masks_path)
            if catalog_masks_path is not None
            else (
                self._snapshot.catalog_mask_load_result.path
                if self._snapshot.catalog_mask_load_result.path is not None
                else (
                    self._config_path.parent / CATALOG_MASKS_FILE_NAME
                    if self._config_path is not None
                    else None
                )
            )
        )
        self._runtime_status_path = (
            Path(runtime_status_path)
            if runtime_status_path is not None
            else (
                self._config_path.parent / RUNTIME_STATUS_FILE_NAME
                if self._config_path is not None
                else None
            )
        )
        self._process_start_lookup = process_start_lookup
        self._instance_probe = instance_probe
        self._bindings = list(self._snapshot.user_document.bindings)
        self._selected_index: int | None = None
        self._draft: BindingDraft | None = None
        self._baseline: BindingDraft | None = None
        self._log_load_status(self._snapshot)
        self._log_catalog_status()

    @property
    def snapshot(self) -> ActiveBindingsSnapshot:
        return self._snapshot

    @property
    def catalog(self) -> CatalogSnapshot:
        return self._catalog

    @property
    def config_path(self) -> Path | None:
        return self._config_path

    @property
    def bindings(self) -> tuple[UserBinding, ...]:
        return tuple(self._bindings)

    @property
    def selected_index(self) -> int | None:
        return self._selected_index

    @property
    def draft(self) -> BindingDraft | None:
        return self._draft

    @property
    def has_load_error(self) -> bool:
        return self._snapshot.migration_error is not None or (
            self._snapshot.load_result.status
            is UserBindingLoadStatus.FAILED
        )

    @property
    def load_error_code(self) -> UserBindingErrorCode | None:
        if self._snapshot.migration_error is not None:
            return self._snapshot.migration_error.code
        error = self._snapshot.load_result.error
        return error.code if error is not None else None

    @property
    def load_error_message(self) -> str:
        """Return a content-safe message for the current load error."""
        if not self.has_load_error:
            return ""
        if (
            self.load_error_code
            is UserBindingErrorCode.UNSUPPORTED_SCHEMA_VERSION
        ):
            return "当前配置版本暂不支持，原文件已保留。"
        if (
            self.load_error_code
            is UserBindingErrorCode.LEGACY_MIGRATION_FAILED
        ):
            return "开发版词典屏蔽配置迁移失败，原文件已保留。"
        return "用户配置文件无法读取，原文件已保留。"

    @property
    def catalog_masks_error_message(self) -> str:
        """Return a non-content warning without blocking user bindings."""
        if (
            self._snapshot.catalog_mask_load_result.status
            is CatalogMaskLoadStatus.FAILED
        ):
            return (
                "词典屏蔽配置无法读取，原文件已保留；"
                "基础词典、扩展包和用户绑定仍可使用。"
            )
        return ""

    @property
    def config_directory(self) -> Path | None:
        """Return the folder a user may open to inspect the configuration."""
        if self._config_path is None:
            return None
        return self._config_path.parent

    @property
    def can_edit(self) -> bool:
        return not self.has_load_error and self._config_path is not None

    @property
    def runtime_status_path(self) -> Path | None:
        return self._runtime_status_path

    @property
    def catalog_masks_path(self) -> Path | None:
        return self._catalog_masks_path

    @property
    def is_dirty(self) -> bool:
        return self._draft != self._baseline

    @property
    def is_new(self) -> bool:
        return self._draft is not None and self._selected_index is None

    def begin_new(
        self,
        *,
        trigger: str = "",
        replacement: str = "",
        enabled: bool = True,
    ) -> None:
        """Start one unsaved item, optionally copied from the catalog."""
        self._selected_index = None
        self._baseline = None
        self._draft = BindingDraft(
            trigger=trigger,
            replacement=replacement,
            enabled=enabled,
        )

    def refresh_catalog(self) -> CatalogSnapshot:
        """Reload read-only sources and recompute the final effective mapping."""
        refreshed_catalog = load_catalog(self._catalog.packs_directory)
        active_defaults = (
            refreshed_catalog.catalog_bindings
            if self._default_bindings_override is None
            else self._default_bindings_override
        )
        refreshed_snapshot = load_active_bindings(
            self._config_path,
            default_bindings=active_defaults,
            catalog_masks_path=self._catalog_masks_path,
        )
        self._catalog = refreshed_catalog
        self._apply_snapshot(refreshed_snapshot)
        self._log_catalog_status()
        return self._catalog

    def prepare_pack_import(
        self,
        source_path: str | os.PathLike[str],
    ) -> PackImportPlan:
        """Validate an import without copying it yet."""
        if self._catalog.packs_directory is None:
            raise PackValidationError(
                "无法确定扩展包目录。",
                code=PackErrorCode.PATH_UNAVAILABLE,
            )
        return prepare_pack_import(
            source_path,
            self._catalog.packs_directory,
        )

    def import_pack(
        self,
        plan: PackImportPlan,
        *,
        allow_replace: bool = False,
    ) -> Path:
        """Safely import a validated local JSON pack and refresh the catalog."""
        try:
            destination = execute_pack_import(
                plan,
                allow_replace=allow_replace,
            )
        except PackValidationError as error:
            self._logger.warning(
                "扩展包导入失败 code=%s exception=%s",
                error.code.name,
                error.exception_type or "NONE",
            )
            raise
        self._logger.info("扩展包导入成功")
        self.refresh_catalog()
        return destination

    def runtime_application_status(self) -> RuntimeApplicationStatus:
        """Compare a fresh final mapping with a verified live backend."""
        current_bindings = self._current_effective_bindings()
        return inspect_runtime_status(
            current_bindings,
            path=self._runtime_status_path,
            process_start_lookup=self._process_start_lookup,
            instance_probe=self._instance_probe,
        )

    def runtime_status_message(self, *, saved: bool = False) -> str:
        """Return persistent, factual text for the settings application."""
        state = self.runtime_application_status().state
        prefix = "保存成功：绑定已保存到本地。" if saved else ""
        if state is RuntimeApplicationState.NOT_RUNNING:
            detail = "SciType 后台当前未运行；配置将在下次启动时应用。"
        elif state is RuntimeApplicationState.RUNNING_APPLIED:
            detail = "SciType 正在运行，当前配置已应用。"
        elif state is RuntimeApplicationState.RUNNING_RESTART_REQUIRED:
            detail = (
                "当前运行中的 SciType 尚未应用此次修改，"
                "需要重启后生效。"
            )
        else:
            detail = (
                "检测到 SciType 后台正在运行，但无法确认其是否已加载"
                "当前配置。可能正在运行旧版本，建议退出后台后启动当前版本。"
            )
        warning = self.catalog_masks_error_message
        if self._snapshot.migration_error is not None:
            warning = self.load_error_message
        suffix = f" {warning}" if warning else ""
        return f"{prefix}{detail}{suffix}"

    def _current_effective_bindings(self) -> dict[str, str]:
        """Re-read every source used by a fresh backend without changing UI."""
        current_catalog = load_catalog(self._catalog.packs_directory)
        active_defaults = (
            current_catalog.catalog_bindings
            if self._default_bindings_override is None
            else self._default_bindings_override
        )
        current_snapshot = load_active_bindings(
            self._config_path,
            default_bindings=active_defaults,
            catalog_masks_path=self._catalog_masks_path,
        )
        return dict(current_snapshot.effective_bindings)

    def set_catalog_entry_enabled(
        self,
        entry: CatalogEntry,
        *,
        enabled: bool,
    ) -> OperationResult:
        """Toggle a user override or the independent catalog-mask file."""
        blocked = self._editing_blocked_result()
        if blocked is not None:
            return blocked
        if entry.conflict is not None:
            return OperationResult(
                False,
                "因触发词冲突，当前不可用于输入。",
            )
        assert self._config_path is not None

        candidate = list(self._bindings)
        binding_index = next(
            (
                index
                for index, binding in enumerate(candidate)
                if binding.trigger == entry.trigger
            ),
            None,
        )
        existing = (
            candidate[binding_index]
            if binding_index is not None
            else None
        )
        if existing is not None:
            if existing.enabled is enabled:
                state_text = "启用" if enabled else "停用"
                return OperationResult(True, f"该词条当前已{state_text}。")
            assert binding_index is not None
            candidate[binding_index] = UserBinding(
                trigger=existing.trigger,
                replacement=existing.replacement,
                enabled=enabled,
            )
            try:
                candidate_document = create_user_binding_document(candidate)
                save_user_bindings(candidate_document, self._config_path)
            except UserBindingsError as error:
                self._log_operation_failure("修改启用状态", error)
                return OperationResult(
                    False,
                    "启用状态保存失败，原配置未被修改。",
                )
        else:
            if (
                self._snapshot.catalog_mask_load_result.status
                is CatalogMaskLoadStatus.FAILED
                or self._catalog_masks_path is None
            ):
                return OperationResult(
                    False,
                    "词典屏蔽配置无法读取，原文件未被修改。",
                )
            disabled = set(
                self._snapshot.catalog_mask_document.disabled_triggers,
            )
            currently_disabled = entry.trigger in disabled
            if enabled and not currently_disabled:
                return OperationResult(True, "该词条当前已启用。")
            if not enabled and currently_disabled:
                return OperationResult(True, "该词条当前已停用。")
            if enabled:
                disabled.discard(entry.trigger)
            else:
                disabled.add(entry.trigger)
            try:
                mask_document = create_catalog_mask_document(disabled)
                save_catalog_masks(
                    mask_document,
                    self._catalog_masks_path,
                )
            except CatalogMasksError as error:
                self._logger.warning(
                    "词典屏蔽状态保存失败 code=%s exception=%s",
                    error.code.name,
                    error.exception_type or "NONE",
                )
                return OperationResult(
                    False,
                    "启用状态保存失败，原配置未被修改。",
                )

        reload_result = reload_user_bindings(
            self._snapshot,
            self._config_path,
            catalog_masks_path=self._catalog_masks_path,
        )
        if reload_result.status is not ReloadStatus.APPLIED:
            self._log_reload_failure(reload_result.load_result.error)
            return OperationResult(
                True,
                "启用状态已保存，但重新读取失败；请重启 SciType。",
                restart_required=True,
            )

        self._apply_snapshot(reload_result.snapshot)
        self.clear_selection()
        self._logger.info("词典启用状态保存成功")
        status = self.runtime_application_status()
        return OperationResult(
            True,
            self.runtime_status_message(saved=True),
            restart_required=(
                status.state
                is RuntimeApplicationState.RUNNING_RESTART_REQUIRED
            ),
        )

    def select_binding(self, index: int) -> None:
        """Select an existing item; the view handles dirty confirmation."""
        binding = self._bindings[index]
        draft = BindingDraft(
            trigger=binding.trigger,
            replacement=binding.replacement,
            enabled=binding.enabled,
        )
        self._selected_index = index
        self._baseline = draft
        self._draft = draft

    def clear_selection(self) -> None:
        self._selected_index = None
        self._baseline = None
        self._draft = None

    def update_draft(
        self,
        *,
        trigger: str,
        replacement: str,
        enabled: bool,
    ) -> None:
        """Replace draft fields without writing configuration."""
        if self._draft is None:
            return
        self._draft = BindingDraft(
            trigger=trigger,
            replacement=replacement,
            enabled=enabled,
        )

    def cancel_changes(self) -> None:
        """Restore the selected item or discard a blank new item."""
        if self._selected_index is None:
            self.clear_selection()
            return
        self.select_binding(self._selected_index)

    def validate_current_draft(self) -> ValidationResult:
        """Run service-layer field and user-conflict validation."""
        draft = self._draft
        if draft is None:
            return ValidationResult(
                {"general": "请先选择或新建一个绑定。"},
            )

        errors: dict[str, str] = {}
        try:
            validate_trigger(draft.trigger)
        except UserBindingsError as error:
            errors["trigger"] = _TRIGGER_ERROR_MESSAGES.get(
                error.code,
                "触发词格式无效。",
            )

        try:
            validate_replacement(draft.replacement)
        except UserBindingsError as error:
            errors["replacement"] = _REPLACEMENT_ERROR_MESSAGES.get(
                error.code,
                "输出内容无效。",
            )

        if (
            "trigger" not in errors
            and has_trigger_conflict(
                self._bindings,
                draft.trigger,
                exclude_index=self._selected_index,
            )
        ):
            errors["trigger"] = "该触发词已经存在。"

        return ValidationResult(errors)

    def save_current(self) -> OperationResult:
        """Validate and atomically persist the current draft."""
        blocked = self._editing_blocked_result()
        if blocked is not None:
            return blocked

        validation = self.validate_current_draft()
        if not validation.is_valid:
            return OperationResult(
                success=False,
                message="请修正标出的内容。",
                field_errors=validation.field_errors,
            )

        assert self._draft is not None
        assert self._config_path is not None
        candidate = list(self._bindings)
        saved_binding = UserBinding(
            trigger=self._draft.trigger,
            replacement=self._draft.replacement,
            enabled=self._draft.enabled,
        )
        if self._selected_index is None:
            candidate.append(saved_binding)
            selected_index = len(candidate) - 1
        else:
            candidate[self._selected_index] = saved_binding
            selected_index = self._selected_index

        try:
            candidate_document = create_user_binding_document(candidate)
            save_user_bindings(candidate_document, self._config_path)
        except UserBindingsError as error:
            self._log_operation_failure("保存", error)
            return OperationResult(
                success=False,
                message="保存失败，原配置未被修改。",
            )

        reload_result = reload_user_bindings(
            self._snapshot,
            self._config_path,
            catalog_masks_path=self._catalog_masks_path,
        )
        if reload_result.status is not ReloadStatus.APPLIED:
            self._log_reload_failure(reload_result.load_result.error)
            return OperationResult(
                success=True,
                message="保存成功，但重新读取失败；请重启 SciType。",
                restart_required=True,
            )

        self._apply_snapshot(reload_result.snapshot)
        self.select_binding(selected_index)
        self._logger.info("用户绑定保存成功")
        self._logger.info("用户绑定 reload 成功")
        status = self.runtime_application_status()
        return OperationResult(
            success=True,
            message=self.runtime_status_message(saved=True),
            restart_required=(
                status.state
                is RuntimeApplicationState.RUNNING_RESTART_REQUIRED
            ),
        )

    def delete_selected(self) -> OperationResult:
        """Atomically delete the selected user item."""
        blocked = self._editing_blocked_result()
        if blocked is not None:
            return blocked
        if self._selected_index is None or self._config_path is None:
            return OperationResult(False, "请先选择要删除的绑定。")

        candidate = list(self._bindings)
        del candidate[self._selected_index]
        try:
            candidate_document = create_user_binding_document(candidate)
            save_user_bindings(candidate_document, self._config_path)
        except UserBindingsError as error:
            self._log_operation_failure("删除", error)
            return OperationResult(
                success=False,
                message="删除失败，原配置未被修改。",
            )

        reload_result = reload_user_bindings(
            self._snapshot,
            self._config_path,
            catalog_masks_path=self._catalog_masks_path,
        )
        if reload_result.status is not ReloadStatus.APPLIED:
            self._log_reload_failure(reload_result.load_result.error)
            return OperationResult(
                success=True,
                message="删除已保存，但重新读取失败；请重启 SciType。",
                restart_required=True,
            )

        self._apply_snapshot(reload_result.snapshot)
        self.clear_selection()
        self._logger.info("用户绑定删除成功")
        self._logger.info("用户绑定 reload 成功")
        status = self.runtime_application_status()
        return OperationResult(
            success=True,
            message=self.runtime_status_message(saved=True),
            restart_required=(
                status.state
                is RuntimeApplicationState.RUNNING_RESTART_REQUIRED
            ),
        )

    def filtered_indices(self, query: str) -> tuple[int, ...]:
        """Return source indices matching trigger or short replacement."""
        needle = query.casefold().strip()
        if not needle:
            return tuple(range(len(self._bindings)))
        return tuple(
            index
            for index, binding in enumerate(self._bindings)
            if needle in binding.trigger.casefold()
            or needle in binding.replacement.casefold()
        )

    def preview_text(self) -> str:
        """Return a plain-text A-to-B preview without rendering HTML."""
        if self._draft is None:
            return ""
        replacement = self._draft.replacement.replace(
            CURSOR_PLACEHOLDER,
            CURSOR_PREVIEW,
        )
        return f"{self._draft.trigger} → {replacement}"

    @staticmethod
    def short_replacement_preview(
        replacement: str,
        *,
        limit: int = 44,
    ) -> str:
        normalized = replacement.replace("\r\n", "\n").replace(
            "\n",
            " ↵ ",
        )
        if len(normalized) <= limit:
            return normalized
        return f"{normalized[: limit - 1]}…"

    def _resolve_config_path(
        self,
        explicit_path: str | os.PathLike[str] | None,
    ) -> Path | None:
        if explicit_path is not None:
            return Path(explicit_path)
        if self._snapshot.load_result.path is not None:
            return self._snapshot.load_result.path
        try:
            return get_user_bindings_path()
        except UserBindingsError:
            return None

    def _editing_blocked_result(self) -> OperationResult | None:
        if self.has_load_error:
            return OperationResult(
                success=False,
                message=self.load_error_message,
            )
        if self._config_path is None:
            return OperationResult(
                success=False,
                message="无法确定用户配置目录。",
            )
        return None

    def _apply_snapshot(self, snapshot: ActiveBindingsSnapshot) -> None:
        self._snapshot = snapshot
        self._bindings = list(snapshot.user_document.bindings)
        self._catalog = apply_user_states(
            self._catalog,
            self._bindings,
            snapshot.catalog_mask_document.disabled_triggers,
        )

    @staticmethod
    def _resolve_packs_directory(
        config_path: str | os.PathLike[str] | None,
        packs_directory: str | os.PathLike[str] | None,
    ) -> Path | None:
        if packs_directory is not None:
            return Path(packs_directory)
        if config_path is not None:
            return Path(config_path).parent / "packs"
        return None

    def _log_catalog_status(self) -> None:
        pack_count = sum(
            source.kind.name == "LOCAL_PACK"
            for source in self._catalog.sources
        )
        self._logger.info(
            "词典加载成功 pack_count=%d failure_count=%d",
            pack_count,
            len(self._catalog.failures),
        )
        for failure in self._catalog.failures:
            self._logger.warning(
                "扩展包加载失败 code=%s exception=%s",
                failure.code.name,
                failure.exception_type or "NONE",
            )

    def _log_load_status(self, snapshot: ActiveBindingsSnapshot) -> None:
        load_result = snapshot.load_result
        if load_result.status is UserBindingLoadStatus.MISSING:
            self._logger.info("设置界面：用户配置不存在")
        elif load_result.status is UserBindingLoadStatus.LOADED:
            self._logger.info("设置界面：用户配置加载成功")
        else:
            self._log_reload_failure(load_result.error, prefix="加载")
        mask_result = snapshot.catalog_mask_load_result
        if mask_result.status is CatalogMaskLoadStatus.MISSING:
            self._logger.info("设置界面：词典屏蔽配置不存在")
        elif mask_result.status is CatalogMaskLoadStatus.LOADED:
            self._logger.info("设置界面：词典屏蔽配置加载成功")
        else:
            error = mask_result.error
            self._logger.warning(
                "词典屏蔽配置加载失败 code=%s exception=%s",
                error.code.name if error is not None else "UNKNOWN",
                (
                    error.exception_type
                    if error is not None
                    and error.exception_type is not None
                    else "NONE"
                ),
            )
        if snapshot.migration_error is not None:
            self._logger.warning(
                "开发版词典屏蔽配置迁移失败 code=%s exception=%s",
                snapshot.migration_error.code.name,
                snapshot.migration_error.exception_type or "NONE",
            )

    def _log_operation_failure(
        self,
        operation: str,
        error: UserBindingsError,
    ) -> None:
        self._logger.warning(
            "用户绑定%s失败 code=%s exception=%s",
            operation,
            error.code.name,
            error.exception_type or "NONE",
        )

    def _log_reload_failure(
        self,
        error: UserBindingsError | None,
        *,
        prefix: str = "reload",
    ) -> None:
        code = error.code.name if error is not None else "UNKNOWN"
        exception_type = (
            error.exception_type
            if error is not None and error.exception_type is not None
            else "NONE"
        )
        self._logger.warning(
            "用户绑定%s失败 code=%s exception=%s",
            prefix,
            code,
            exception_type,
        )
