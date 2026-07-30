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
_VERSION = "0.6.0"
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
            [
                "PyInstaller==6.21.0",
                "PySide6-Essentials==6.11.1",
            ],
        )
        self.assertEqual(
            pyproject["project"]["optional-dependencies"]["gui"],
            ["PySide6-Essentials==6.11.1"],
        )

    def test_spec_is_windowed_onedir_without_upx(self) -> None:
        spec = (_PROJECT_ROOT / "SciType.spec").read_text(encoding="utf-8")

        self.assertIn('"src" / "scitype" / "app.py"', spec)
        self.assertIn('"src" / "scitype" / "settings_app.py"', spec)
        self.assertIn("collect_data_files(", spec)
        self.assertIn('includes=["data/*.json"]', spec)
        self.assertIn('PROJECT_ROOT / "LICENSE"', spec)
        self.assertIn("console=False", spec)
        self.assertGreaterEqual(spec.count("upx=False"), 3)
        self.assertEqual(spec.count("console=False"), 2)
        self.assertIn('name="SciTypeSettings"', spec)
        self.assertIn("settings_analysis.binaries", spec)
        self.assertIn('"PySide6.QtNetwork"', spec)
        self.assertIn('"PySide6.QtWebEngineCore"', spec)
        self.assertIn("keep_settings_binary", spec)
        self.assertIn('"opengl32sw.dll"', spec)
        self.assertIn("/pyside6/translations/", spec)
        self.assertIn("qwindows.dll", spec)
        self.assertIn("COLLECT(", spec)
        self.assertNotIn(str(_PROJECT_ROOT), spec)

    def test_version_resource_contains_required_public_metadata(self) -> None:
        version_info = (
            _PROJECT_ROOT / "packaging/windows_version_info.txt"
        ).read_text(encoding="utf-8")

        self.assertIn("filevers=(0, 6, 0, 0)", version_info)
        self.assertIn("prodvers=(0, 6, 0, 0)", version_info)
        self.assertIn('"ProductName", "SciType"', version_info)
        self.assertIn('"FileVersion", "0.6.0"', version_info)
        self.assertIn('"ProductVersion", "0.6.0"', version_info)
        self.assertIn("Copyright (c) 2026 Y1n1N1", version_info)

        settings_version_info = (
            _PROJECT_ROOT / "packaging/windows_settings_version_info.txt"
        ).read_text(encoding="utf-8")
        self.assertIn('"InternalName", "SciTypeSettings"', settings_version_info)
        self.assertIn('"OriginalFilename", "SciTypeSettings.exe"', settings_version_info)
        self.assertIn('"FileVersion", "0.6.0"', settings_version_info)

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
        self.assertIn("SciTypeSettings.exe", script)
        self.assertIn("THIRD_PARTY_NOTICES.txt", script)
        self.assertIn("third_party_licenses", script)
        self.assertIn("extension-packs.md", script)
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
        self.assertIn("SciTypeSettings.exe", readme)
        self.assertIn("THIRD_PARTY_NOTICES.txt", readme)
        self.assertIn("%LOCALAPPDATA%\\SciType\\packs\\", readme)

    def test_third_party_notice_names_exact_qt_dependencies(self) -> None:
        notice = (
            _PROJECT_ROOT / "packaging/THIRD_PARTY_NOTICES.txt"
        ).read_text(encoding="utf-8")

        self.assertIn("PySide6 Essentials 6.11.1", notice)
        self.assertIn("Shiboken6 6.11.1", notice)
        self.assertIn("Qt 6.11.1", notice)
        self.assertIn("LGPL-3.0-only", notice)
        self.assertIn("动态链接", notice)
        self.assertIn("不导入 QML", notice)
        for license_name in ("LGPL-3.0.txt", "GPL-3.0.txt"):
            path = (
                _PROJECT_ROOT
                / "packaging/third_party_licenses"
                / license_name
            )
            self.assertTrue(path.is_file())
            self.assertGreater(path.stat().st_size, 5000)

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
        (self.release_directory / "SciTypeSettings.exe").write_bytes(
            b"MZ-fake-settings",
        )
        license_bytes = (_PROJECT_ROOT / "LICENSE").read_bytes()
        notice_bytes = (
            _PROJECT_ROOT / "packaging/THIRD_PARTY_NOTICES.txt"
        ).read_bytes()
        (self.release_directory / "LICENSE").write_bytes(license_bytes)
        (self.release_directory / "_internal/LICENSE").write_bytes(
            license_bytes,
        )
        (
            self.release_directory / "THIRD_PARTY_NOTICES.txt"
        ).write_bytes(notice_bytes)
        (
            self.release_directory / "_internal/THIRD_PARTY_NOTICES.txt"
        ).write_bytes(notice_bytes)
        third_party_directory = (
            self.release_directory / "third_party_licenses"
        )
        third_party_directory.mkdir()
        for license_name in ("LGPL-3.0.txt", "GPL-3.0.txt"):
            source = (
                _PROJECT_ROOT
                / "packaging/third_party_licenses"
                / license_name
            )
            (third_party_directory / license_name).write_bytes(
                source.read_bytes(),
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
        for filename in (
            "README.txt",
            "symbols.md",
            "extension-packs.md",
            "open_log_folder.bat",
        ):
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
        for filename in (
            "scitype.log",
            "scitype-settings.log",
            "scitype.log.1",
            "user_bindings.json",
        ):
            with self.subTest(filename=filename):
                path = self.release_directory / filename
                path.write_text("must not ship", encoding="utf-8")
                with self.assertRaisesRegex(
                    ReleaseValidationError,
                    "日志或个人配置",
                ):
                    validate_release_directory(
                        self.release_directory,
                        project_root=_PROJECT_ROOT,
                        version=_VERSION,
                    )
                path.unlink()

    def test_out_of_scope_qt_module_is_rejected(self) -> None:
        qt_directory = self.release_directory / "_internal/PySide6"
        qt_directory.mkdir()
        (qt_directory / "Qt6Network.dll").write_bytes(b"not-required")

        with self.assertRaisesRegex(
            ReleaseValidationError,
            "范围外的 Qt 动态库",
        ):
            validate_release_directory(
                self.release_directory,
                project_root=_PROJECT_ROOT,
                version=_VERSION,
            )

    def test_local_pack_directory_is_not_shipped(self) -> None:
        packs = self.release_directory / "packs"
        packs.mkdir()
        (packs / "personal.json").write_text("{}", encoding="utf-8")

        with self.assertRaisesRegex(
            ReleaseValidationError,
            "禁止目录",
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

    def test_zip_missing_license_is_rejected(self) -> None:
        zip_path = self._create_zip()
        rewritten_path = self.temporary_root / "missing-license.zip"
        with (
            zipfile.ZipFile(zip_path, "r") as source,
            zipfile.ZipFile(rewritten_path, "w") as destination,
        ):
            for item in source.infolist():
                if item.filename.endswith("/LICENSE"):
                    continue
                destination.writestr(item, source.read(item.filename))

        with self.assertRaisesRegex(
            ReleaseValidationError,
            "ZIP 缺少.*LICENSE",
        ):
            validate_release_zip(
                rewritten_path,
                release_directory_name=_RELEASE_NAME,
            )


if __name__ == "__main__":
    unittest.main()
