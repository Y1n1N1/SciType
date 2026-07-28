"""Static contract tests for the user-run PowerShell launcher scripts."""

from pathlib import Path
import unittest


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIRECTORY = _PROJECT_ROOT / "scripts"


class LauncherScriptTests(unittest.TestCase):
    def test_desktop_shortcut_uses_project_pythonw_and_module(self) -> None:
        script = (
            _SCRIPTS_DIRECTORY / "create_desktop_shortcut.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn('"Scripts\\pythonw.exe"', script)
        self.assertIn('$shortcut.TargetPath = $pythonwPath', script)
        self.assertIn(
            '$shortcut.Arguments = "-m scitype.windows_demo"',
            script,
        )
        self.assertIn(
            "$shortcut.WorkingDirectory = $projectRoot",
            script,
        )
        self.assertIn(
            '$shortcut.Description = "SciType 理科符号快捷输入工具"',
            script,
        )

    def test_create_script_validates_environment_before_saving(self) -> None:
        script = (
            _SCRIPTS_DIRECTORY / "create_desktop_shortcut.ps1"
        ).read_text(encoding="utf-8")

        validation_end = script.index("$desktopDirectory")
        save_position = script.index("$shortcut.Save()")
        validation_text = script[:validation_end]

        self.assertIn("Test-Path -LiteralPath $venvDirectory", validation_text)
        self.assertIn("Test-Path -LiteralPath $pythonwPath", validation_text)
        self.assertIn('-c "import scitype"', validation_text)
        self.assertGreater(save_position, validation_end)

    def test_debug_script_uses_console_python(self) -> None:
        script = (
            _SCRIPTS_DIRECTORY / "start_scitype_debug.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn('"Scripts\\python.exe"', script)
        self.assertIn(
            "& $pythonPath -m scitype.windows_demo",
            script,
        )
        self.assertNotIn("pythonw.exe", script)

    def test_remove_script_only_targets_current_desktop_shortcut(self) -> None:
        script = (
            _SCRIPTS_DIRECTORY / "remove_desktop_shortcut.ps1"
        ).read_text(encoding="utf-8")
        remove_line = next(
            line.strip()
            for line in script.splitlines()
            if line.strip().startswith("Remove-Item")
        )

        self.assertIn('$shortcutPath', remove_line)
        self.assertNotIn(".venv", remove_line)
        self.assertNotIn("scitype.log", script)


if __name__ == "__main__":
    unittest.main()
