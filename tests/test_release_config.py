"""Tests for the reproducible SciType Windows release configuration."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import tomllib
import unittest
import zipfile

from scripts.validate_windows_release import (
    ReleaseValidationError,
    validate_release_directory,
    validate_release_zip,
)


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_VERSION = "0.4.0"
_RELEASE_NAME = f"SciType-{_VERSION}-windows-x64"


class ReleaseConfigurationTests(unittest.TestCase):
    def test_build_dependency_does_not_become_runtime_dependency(self) -> None:
        pyproject = tomllib.loads(
            (_PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"),
        )

        self.assertEqual(pyproject["project"]["version"], _VERSION)
        self.assertEqual(pyproject["project"]["dependencies"], [])
        self.assertEqual(
            pyproject["project"]["optional-dependencies"]["build"],
            ["PyInstaller==6.21.0"],
        )

    def test_spec_is_windowed_onedir_without_upx(self) -> None:
        spec = (_PROJECT_ROOT / "SciType.spec").read_text(encoding="utf-8")

        self.assertIn('"src" / "scitype" / "app.py"', spec)
        self.assertIn("collect_data_files(", spec)
        self.assertIn('includes=["data/*.json"]', spec)
        self.assertIn('PROJECT_ROOT / "LICENSE"', spec)
        self.assertIn("console=False", spec)
        self.assertGreaterEqual(spec.count("upx=False"), 2)
        self.assertIn("COLLECT(", spec)
        self.assertNotIn("D:\\R_Srf", spec)

    def test_version_resource_contains_required_public_metadata(self) -> None:
        version_info = (
            _PROJECT_ROOT / "packaging/windows_version_info.txt"
        ).read_text(encoding="utf-8")

        self.assertIn("filevers=(0, 4, 0, 0)", version_info)
        self.assertIn("prodvers=(0, 4, 0, 0)", version_info)
        self.assertIn('"ProductName", "SciType"', version_info)
        self.assertIn('"FileVersion", "0.4.0"', version_info)
        self.assertIn('"ProductVersion", "0.4.0"', version_info)
        self.assertIn("Copyright (c) 2026 Y1n1N1", version_info)

    def test_build_script_has_required_fail_fast_stages(self) -> None:
        script = (
            _PROJECT_ROOT / "scripts/build_windows_release.ps1"
        ).read_text(encoding="utf-8-sig")

        clean_position = script.index("Remove-ValidatedProjectDirectory $buildPath")
        test_position = script.index('"unittest", "discover"')
        build_position = script.index('"-m",\n            "PyInstaller"')
        self.assertLess(clean_position, test_position)
        self.assertLess(test_position, build_position)
        self.assertIn('"--verify-resources"', script)
        self.assertIn("Compress-Archive", script)
        self.assertIn("Get-FileHash", script)
        self.assertIn("SHA256SUMS.txt", script)
        self.assertNotIn("Invoke-WebRequest", script)
        self.assertNotIn("Start-BitsTransfer", script)

    def test_release_readme_explains_runtime_and_security_boundary(self) -> None:
        readme = (_PROJECT_ROOT / "packaging/README.txt").read_text(
            encoding="utf-8",
        )

        self.assertIn("不需要预先安装 Python", readme)
        self.assertIn("Ctrl + Alt + Q", readme)
        self.assertIn("%LOCALAPPDATA%\\SciType\\scitype.log", readme)
        self.assertIn("不要关闭或绕过", readme)
        self.assertIn("官方 GitHub Release", readme)
        self.assertIn("SHA256SUMS.txt", readme)

    def test_log_folder_helper_only_opens_local_log_directory(self) -> None:
        helper = (_PROJECT_ROOT / "packaging/open_log_folder.bat").read_text(
            encoding="utf-8",
        )
        lowered = helper.casefold()

        self.assertIn("%localappdata%\\scitype", lowered)
        self.assertIn("explorer.exe", lowered)
        for forbidden in ("curl ", "http://", "https://", "del ", "rmdir "):
            self.assertNotIn(forbidden, lowered)


class ReleaseValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.temporary_root = Path(self.temporary_directory.name)
        self.release_directory = self.temporary_root / _RELEASE_NAME
        data_directory = (
            self.release_directory / "_internal/scitype/data"
        )
        data_directory.mkdir(parents=True)

        (self.release_directory / "SciType.exe").write_bytes(b"MZ-fake")
        license_bytes = (_PROJECT_ROOT / "LICENSE").read_bytes()
        (self.release_directory / "LICENSE").write_bytes(license_bytes)
        (self.release_directory / "_internal/LICENSE").write_bytes(
            license_bytes,
        )
        for filename, value in (
            ("symbols.json", [{"id": "greek.phi", "output": "φ"}]),
            (
                "default_bindings.json",
                [{"trigger": "/fi", "symbol_id": "greek.phi"}],
            ),
        ):
            (data_directory / filename).write_text(
                json.dumps(value, ensure_ascii=False),
                encoding="utf-8",
            )
        for filename in ("README.txt", "symbols.md", "open_log_folder.bat"):
            (self.release_directory / filename).write_text(
                filename,
                encoding="utf-8",
            )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _create_zip(self) -> Path:
        zip_path = self.temporary_root / f"{_RELEASE_NAME}.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            for item in self.release_directory.rglob("*"):
                if item.is_file():
                    archive.write(
                        item,
                        (
                            Path(self.release_directory.name)
                            / item.relative_to(self.release_directory)
                        ).as_posix(),
                    )
        return zip_path

    def test_valid_release_directory_passes(self) -> None:
        validate_release_directory(
            self.release_directory,
            project_root=_PROJECT_ROOT,
            version=_VERSION,
        )

    def test_license_mismatch_is_rejected(self) -> None:
        (self.release_directory / "LICENSE").write_text(
            "changed",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            ReleaseValidationError,
            "LICENSE.*不一致",
        ):
            validate_release_directory(
                self.release_directory,
                project_root=_PROJECT_ROOT,
                version=_VERSION,
            )

    def test_log_or_personal_config_is_rejected(self) -> None:
        (self.release_directory / "scitype.log").write_text(
            "must not ship",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            ReleaseValidationError,
            "日志或个人配置",
        ):
            validate_release_directory(
                self.release_directory,
                project_root=_PROJECT_ROOT,
                version=_VERSION,
            )

    def test_valid_zip_is_readable_and_contains_executable(self) -> None:
        validate_release_zip(
            self._create_zip(),
            release_directory_name=_RELEASE_NAME,
        )

    def test_zip_without_release_root_is_rejected(self) -> None:
        zip_path = self.temporary_root / "invalid.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("SciType.exe", b"MZ-fake")

        with self.assertRaisesRegex(
            ReleaseValidationError,
            "缺少.*SciType.exe",
        ):
            validate_release_zip(
                zip_path,
                release_directory_name=_RELEASE_NAME,
            )


if __name__ == "__main__":
    unittest.main()
