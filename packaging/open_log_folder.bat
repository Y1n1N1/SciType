@echo off
setlocal
set "SCITYPE_LOG_DIR=%LOCALAPPDATA%\SciType"

if not exist "%SCITYPE_LOG_DIR%" (
    echo SciType log folder has not been created yet:
    echo %SCITYPE_LOG_DIR%
    pause
    exit /b 0
)

start "" explorer.exe "%SCITYPE_LOG_DIR%"
endlocal
