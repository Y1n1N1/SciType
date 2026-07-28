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

if (-not (Test-Path -LiteralPath $venvDirectory -PathType Container)) {
    Stop-WithChineseError "未找到 .venv，请先在项目根目录创建虚拟环境。"
}
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    Stop-WithChineseError "未找到 .venv\Scripts\python.exe，虚拟环境不完整。"
}

& $pythonPath -c "import scitype" *> $null
if ($LASTEXITCODE -ne 0) {
    Stop-WithChineseError "当前虚拟环境无法导入 scitype，请先执行可编辑安装。"
}

Push-Location $projectRoot
try {
    & $pythonPath -m scitype.windows_demo
    $exitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

exit $exitCode
