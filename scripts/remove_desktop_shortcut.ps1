Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$desktopDirectory = [Environment]::GetFolderPath(
    [Environment+SpecialFolder]::Desktop
)
if ([string]::IsNullOrWhiteSpace($desktopDirectory)) {
    Write-Error "SciType：无法确定当前用户桌面位置。"
    exit 1
}

$shortcutPath = Join-Path $desktopDirectory "SciType.lnk"
if (Test-Path -LiteralPath $shortcutPath -PathType Leaf) {
    Remove-Item -LiteralPath $shortcutPath -Force
    Write-Host "SciType 桌面快捷方式已删除：$shortcutPath"
}
else {
    Write-Host "SciType 桌面快捷方式不存在，无需删除。"
}
