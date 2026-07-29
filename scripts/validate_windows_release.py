"""Validate a SciType Windows onedir release using only the standard library."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import sys
import zipfile


REQUIRED_TOP_LEVEL = (
    "SciType.exe",
    "_internal",
    "LICENSE",
    "README.txt",
    "symbols.md",
    "open_log_folder.bat",
)
PACKAGED_RESOURCES = (
    Path("_internal/scitype/data/symbols.json"),
    Path("_internal/scitype/data/default_bindings.json"),
    Path("_internal/LICENSE"),
)
FORBIDDEN_COMPONENTS = {
    ".git",
    ".venv",
    ".pytest_cache",
    "__pycache__",
    "build",
    "dist",
    "release",
    "tests",
}
FORBIDDEN_FILENAMES = {
    "scitype.log",
    "user_bindings.json",
    "user_config.json",
}
PROXY_VARIABLES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
)


class ReleaseValidationError(RuntimeError):
    """Raised when a release artifact violates the packaging contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseValidationError(message)


def _validate_path_components(relative_path: Path | PurePosixPath) -> None:
    lowered_parts = {part.casefold() for part in relative_path.parts}
    forbidden = lowered_parts.intersection(FORBIDDEN_COMPONENTS)
    _require(
        not forbidden,
        f"发布包包含禁止目录：{relative_path}（{sorted(forbidden)}）",
    )
    _require(
        relative_path.name.casefold() not in FORBIDDEN_FILENAMES,
        f"发布包包含日志或个人配置：{relative_path}",
    )


def _sensitive_values(project_root: Path) -> list[str]:
    values = {
        str(project_root.resolve()),
        str(Path.home().resolve()),
        Path.home().name,
    }
    for variable in PROXY_VARIABLES:
        value = os.environ.get(variable)
        if value:
            values.add(value)
    return sorted(value for value in values if len(value) >= 3)


def _encoded_needles(values: list[str]) -> list[tuple[str, bytes]]:
    needles: list[tuple[str, bytes]] = []
    for value in values:
        for variant in {value, value.replace("\\", "/")}:
            needles.append((value, variant.encode("utf-8")))
            needles.append((value, variant.encode("utf-16-le")))
    return needles


def validate_release_directory(
    release_directory: Path,
    *,
    project_root: Path,
    version: str,
) -> None:
    """Validate required files, package resources and private-data exclusions."""
    expected_name = f"SciType-{version}-windows-x64"
    _require(
        release_directory.name == expected_name,
        f"发布目录名称应为 {expected_name}",
    )
    _require(release_directory.is_dir(), f"发布目录不存在：{release_directory}")

    for item_name in REQUIRED_TOP_LEVEL:
        item = release_directory / item_name
        _require(item.exists(), f"发布目录缺少：{item_name}")
    _require(
        (release_directory / "SciType.exe").stat().st_size > 0,
        "SciType.exe 为空",
    )

    source_license = (project_root / "LICENSE").read_bytes()
    _require(
        (release_directory / "LICENSE").read_bytes() == source_license,
        "发布目录 LICENSE 与项目 LICENSE 不一致",
    )

    for relative_path in PACKAGED_RESOURCES:
        resource = release_directory / relative_path
        _require(resource.is_file(), f"冻结包缺少资源：{relative_path}")
        _require(resource.stat().st_size > 0, f"冻结包资源为空：{relative_path}")
    _require(
        (release_directory / "_internal/LICENSE").read_bytes()
        == source_license,
        "冻结包内部 LICENSE 与项目 LICENSE 不一致",
    )

    for resource_name in ("symbols.json", "default_bindings.json"):
        resource_path = (
            release_directory / "_internal/scitype/data" / resource_name
        )
        with resource_path.open("r", encoding="utf-8") as file:
            parsed = json.load(file)
        _require(isinstance(parsed, list), f"{resource_name} 顶层不是 JSON 数组")
        _require(bool(parsed), f"{resource_name} 不能为空")

    needles = _encoded_needles(_sensitive_values(project_root))
    for item in release_directory.rglob("*"):
        relative_path = item.relative_to(release_directory)
        _validate_path_components(relative_path)
        if not item.is_file():
            continue

        content = item.read_bytes()
        for label, needle in needles:
            _require(
                needle not in content,
                f"发布文件 {relative_path} 泄漏敏感值：{label}",
            )


def validate_release_zip(
    zip_path: Path,
    *,
    release_directory_name: str,
) -> None:
    """Validate ZIP readability, root structure and forbidden paths."""
    _require(zip_path.is_file(), f"ZIP 不存在：{zip_path}")
    _require(zip_path.stat().st_size > 0, f"ZIP 为空：{zip_path}")

    expected_root = f"{release_directory_name}/"
    expected_executable = f"{expected_root}SciType.exe"
    with zipfile.ZipFile(zip_path, "r") as archive:
        _require(archive.testzip() is None, "ZIP CRC 校验失败")
        names = [name.replace("\\", "/") for name in archive.namelist()]
        _require(
            expected_executable in names,
            f"ZIP 缺少 {expected_executable}",
        )
        for name in names:
            path = PurePosixPath(name)
            _require(
                name.startswith(expected_root),
                f"ZIP 条目不在发布根目录内：{name}",
            )
            relative_parts = path.parts[1:]
            if relative_parts:
                _validate_path_components(PurePosixPath(*relative_parts))


def validate_windows_release(
    release_directory: Path,
    zip_path: Path,
    *,
    project_root: Path,
    version: str,
) -> None:
    """Run all platform-independent release artifact checks."""
    validate_release_directory(
        release_directory,
        project_root=project_root,
        version=version,
    )
    validate_release_zip(
        zip_path,
        release_directory_name=release_directory.name,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-dir", required=True, type=Path)
    parser.add_argument("--zip", required=True, dest="zip_path", type=Path)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--version", required=True)
    return parser.parse_args()


def main() -> int:
    arguments = _parse_args()
    try:
        validate_windows_release(
            arguments.release_dir.resolve(),
            arguments.zip_path.resolve(),
            project_root=arguments.project_root.resolve(),
            version=arguments.version,
        )
    except (OSError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as error:
        print(f"发布包验证失败：{error}", file=sys.stderr)
        return 1
    except ReleaseValidationError as error:
        print(f"发布包验证失败：{error}", file=sys.stderr)
        return 1

    print(f"发布包验证通过：{arguments.release_dir.resolve()}")
    print(f"ZIP 验证通过：{arguments.zip_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
