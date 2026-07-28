Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Stop-WithChineseError {
    param([Parameter(Mandatory = $true)][string]$Message)

    Write-Error "SciType：$Message"
    exit 1
}

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venvDirectory = Join-Path $projectRoot ".venv"
$pythonPath = Join-Path $venvDirectory "Scripts\python.exe"
$pythonwPath = Join-Path $venvDirectory "Scripts\pythonw.exe"

if (-not (Test-Path -LiteralPath $venvDirectory -PathType Container)) {
    Stop-WithChineseError "未找到 .venv，请先在项目根目录创建虚拟环境。"
}
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    Stop-WithChineseError "未找到 .venv\Scripts\python.exe，虚拟环境不完整。"
}
if (-not (Test-Path -LiteralPath $pythonwPath -PathType Leaf)) {
    Stop-WithChineseError "未找到 .venv\Scripts\pythonw.exe，无法创建后台启动快捷方式。"
}

& $pythonPath -c "import scitype" *> $null
if ($LASTEXITCODE -ne 0) {
    Stop-WithChineseError "当前虚拟环境无法导入 scitype，请先执行可编辑安装。"
}

$desktopDirectory = [Environment]::GetFolderPath(
    [Environment+SpecialFolder]::Desktop
)
if ([string]::IsNullOrWhiteSpace($desktopDirectory)) {
    Stop-WithChineseError "无法确定当前用户桌面位置。"
}

$shortcutPath = Join-Path $desktopDirectory "SciType.lnk"
$shell = New-Object -ComObject WScript.Shell
try {
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $pythonwPath
    $shortcut.Arguments = "-m scitype.windows_demo"
    $shortcut.WorkingDirectory = $projectRoot
    $shortcut.Description = "SciType 理科符号快捷输入工具"
    $shortcut.Save()
}
catch {
    Stop-WithChineseError "创建桌面快捷方式失败：$($_.Exception.Message)"
}
finally {
    if ($null -ne $shell) {
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)
    }
}

Write-Host "SciType 桌面快捷方式已创建或更新：$shortcutPath"
