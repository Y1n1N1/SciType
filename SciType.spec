"""Reproducible two-program PyInstaller onedir configuration for SciType."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files


PROJECT_ROOT = Path(SPECPATH).resolve()
ICON_PATH = PROJECT_ROOT / "packaging" / "SciType.ico"

shared_datas = collect_data_files(
    "scitype",
    includes=["data/*.json"],
)
shared_datas.extend(
    [
        (str(PROJECT_ROOT / "LICENSE"), "."),
        (
            str(PROJECT_ROOT / "packaging" / "THIRD_PARTY_NOTICES.txt"),
            ".",
        ),
    ],
)

background_analysis = Analysis(
    [str(PROJECT_ROOT / "src" / "scitype" / "app.py")],
    pathex=[str(PROJECT_ROOT / "src")],
    binaries=[],
    datas=shared_datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
background_archive = PYZ(background_analysis.pure)

background_executable = EXE(
    background_archive,
    background_analysis.scripts,
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

settings_analysis = Analysis(
    [str(PROJECT_ROOT / "src" / "scitype" / "settings_app.py")],
    pathex=[str(PROJECT_ROOT / "src")],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide6.QtNetwork",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineQuick",
        "PySide6.QtWebEngineWidgets",
    ],
    noarchive=False,
    optimize=0,
)


def keep_settings_binary(entry):
    """Keep only the Qt DLLs and plugins used by this Widgets-only UI."""
    destination = entry[0].replace("\\", "/").casefold()
    filename = Path(destination).name
    if "/pyside6/plugins/" in f"/{destination}":
        return destination.endswith(
            "pyside6/plugins/platforms/qwindows.dll"
        ) or destination.endswith(
            "pyside6/plugins/styles/qmodernwindowsstyle.dll"
        )
    return filename not in {
        "opengl32sw.dll",
        "qt6network.dll",
        "qtnetwork.pyd",
        "qt6svg.dll",
        "qtsvg.pyd",
    }


settings_analysis.binaries = [
    entry
    for entry in settings_analysis.binaries
    if keep_settings_binary(entry)
]
settings_analysis.datas = [
    entry
    for entry in settings_analysis.datas
    if "/pyside6/translations/"
    not in f"/{entry[0].replace('\\', '/').casefold()}"
]
settings_archive = PYZ(settings_analysis.pure)

settings_executable = EXE(
    settings_archive,
    settings_analysis.scripts,
    [],
    exclude_binaries=True,
    name="SciTypeSettings",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(ICON_PATH) if ICON_PATH.is_file() else None,
    version=str(
        PROJECT_ROOT / "packaging" / "windows_settings_version_info.txt"
    ),
)

collection = COLLECT(
    background_executable,
    settings_executable,
    background_analysis.binaries,
    background_analysis.datas,
    settings_analysis.binaries,
    settings_analysis.datas,
    strip=False,
    upx=False,
    name="SciType",
)
