"""Reproducible PyInstaller onedir configuration for SciType."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files


PROJECT_ROOT = Path(SPECPATH).resolve()
ICON_PATH = PROJECT_ROOT / "packaging" / "SciType.ico"

datas = collect_data_files(
    "scitype",
    includes=["data/*.json"],
)
datas.append((str(PROJECT_ROOT / "LICENSE"), "."))

analysis = Analysis(
    [str(PROJECT_ROOT / "src" / "scitype" / "app.py")],
    pathex=[str(PROJECT_ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
python_archive = PYZ(analysis.pure)

executable = EXE(
    python_archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="SciType",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(ICON_PATH) if ICON_PATH.is_file() else None,
    version=str(PROJECT_ROOT / "packaging" / "windows_version_info.txt"),
)

collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="SciType",
)
