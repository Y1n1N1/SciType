[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = [System.IO.Path]::GetFullPath(
    (Join-Path $PSScriptRoot "..")
)
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$specPath = Join-Path $projectRoot "SciType.spec"
$buildPath = Join-Path $projectRoot "build"
$distPath = Join-Path $projectRoot "dist"
$releaseRoot = Join-Path $projectRoot "release"
$expectedVersion = "0.4.0"
$releaseName = "SciType-$expectedVersion-windows-x64"
$releaseDirectory = Join-Path $releaseRoot $releaseName
$zipPath = Join-Path $releaseRoot "$releaseName.zip"
$hashPath = Join-Path $releaseRoot "SHA256SUMS.txt"

function Invoke-CheckedPython {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [Parameter(Mandatory = $true)]
        [string]$FailureMessage
    )

    & $pythonPath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw $FailureMessage
    }
}

function Remove-ValidatedProjectDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$TargetPath
    )

    $resolvedTarget = [System.IO.Path]::GetFullPath($TargetPath)
    $projectPrefix = $projectRoot.TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar
    ) + [System.IO.Path]::DirectorySeparatorChar

    if (
        $resolvedTarget -eq $projectRoot -or
        -not $resolvedTarget.StartsWith(
            $projectPrefix,
            [System.StringComparison]::OrdinalIgnoreCase
        )
    ) {
        throw "拒绝清理项目目录之外的路径：$resolvedTarget"
    }

    if (Test-Path -LiteralPath $resolvedTarget) {
        Remove-Item -LiteralPath $resolvedTarget -Recurse -Force
    }
}

if (
    [System.Environment]::OSVersion.Platform -ne
    [System.PlatformID]::Win32NT
) {
    throw "SciType Windows 发布包只能在 Windows 上构建。"
}
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "缺少项目虚拟环境 Python：$pythonPath"
}
if (-not (Test-Path -LiteralPath $specPath -PathType Leaf)) {
    throw "缺少 PyInstaller 配置：$specPath"
}

Push-Location $projectRoot
try {
    $pythonBits = (
        & $pythonPath -c "import struct; print(struct.calcsize('P') * 8)"
    ).Trim()
    if ($LASTEXITCODE -ne 0 -or $pythonBits -ne "64") {
        throw "必须使用 64 位 Python 构建 windows-x64 发布包。"
    }

    $projectVersion = (
        & $pythonPath -c (
            "import pathlib,tomllib;" +
            "print(tomllib.loads(pathlib.Path('pyproject.toml')" +
            ".read_text(encoding='utf-8'))['project']['version'])"
        )
    ).Trim()
    if ($LASTEXITCODE -ne 0 -or $projectVersion -ne $expectedVersion) {
        throw (
            "pyproject.toml 版本应为 $expectedVersion，" +
            "实际为 $projectVersion。"
        )
    }

    Invoke-CheckedPython `
        -Arguments @("-c", "import scitype; import scitype.app") `
        -FailureMessage (
            "当前 .venv 未正确安装 SciType；请先执行 " +
            "'.\.venv\Scripts\python.exe -m pip install --editable "".[build]""'。"
        )

    $pyInstallerVersion = (
        & $pythonPath -m PyInstaller --version
    ).Trim()
    if (
        $LASTEXITCODE -ne 0 -or
        $pyInstallerVersion -ne "6.21.0"
    ) {
        throw (
            "需要 PyInstaller 6.21.0，实际为 " +
            "'$pyInstallerVersion'；请安装项目 build 可选依赖。"
        )
    }

    Remove-ValidatedProjectDirectory $buildPath
    Remove-ValidatedProjectDirectory $distPath
    Remove-ValidatedProjectDirectory $releaseRoot

    Write-Host "运行全部自动测试..."
    Invoke-CheckedPython `
        -Arguments @("-m", "unittest", "discover", "-s", "tests", "-v") `
        -FailureMessage "自动测试失败，发布构建已停止。"

    Write-Host "构建 PyInstaller onedir 发布目录..."
    Invoke-CheckedPython `
        -Arguments @(
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--workpath",
            $buildPath,
            "--distpath",
            $distPath,
            $specPath
        ) `
        -FailureMessage "PyInstaller 构建失败。"

    $distDirectory = Join-Path $distPath "SciType"
    $distExecutable = Join-Path $distDirectory "SciType.exe"
    if (-not (Test-Path -LiteralPath $distExecutable -PathType Leaf)) {
        throw "PyInstaller 未生成预期 EXE：$distExecutable"
    }

    Write-Host "运行冻结程序的只读资源自检..."
    $resourceCheck = Start-Process `
        -FilePath $distExecutable `
        -ArgumentList "--verify-resources" `
        -WindowStyle Hidden `
        -Wait `
        -PassThru
    if ($resourceCheck.ExitCode -ne 0) {
        throw "冻结程序无法读取随包 JSON 或 LICENSE 资源。"
    }

    New-Item -ItemType Directory -Path $releaseDirectory -Force | Out-Null
    Get-ChildItem -LiteralPath $distDirectory -Force |
        Copy-Item -Destination $releaseDirectory -Recurse -Force

    Copy-Item `
        -LiteralPath (Join-Path $projectRoot "LICENSE") `
        -Destination (Join-Path $releaseDirectory "LICENSE")
    Copy-Item `
        -LiteralPath (Join-Path $projectRoot "packaging\README.txt") `
        -Destination (Join-Path $releaseDirectory "README.txt")
    Copy-Item `
        -LiteralPath (Join-Path $projectRoot "docs\symbols.md") `
        -Destination (Join-Path $releaseDirectory "symbols.md")
    Copy-Item `
        -LiteralPath (Join-Path $projectRoot "packaging\open_log_folder.bat") `
        -Destination (Join-Path $releaseDirectory "open_log_folder.bat")

    $releaseExecutable = Join-Path $releaseDirectory "SciType.exe"
    $versionInfo = [System.Diagnostics.FileVersionInfo]::GetVersionInfo(
        $releaseExecutable
    )
    if (
        $versionInfo.ProductName -ne "SciType" -or
        $versionInfo.FileDescription -ne "SciType 理科符号快捷输入工具" -or
        $versionInfo.FileVersion -ne $expectedVersion -or
        $versionInfo.ProductVersion -ne $expectedVersion -or
        $versionInfo.LegalCopyright -ne "Copyright (c) 2026 Y1n1N1"
    ) {
        throw (
            "SciType.exe 版本资源不符合 0.4.0 发布要求：" +
            "`n$($versionInfo | Format-List | Out-String)"
        )
    }

    Compress-Archive `
        -LiteralPath $releaseDirectory `
        -DestinationPath $zipPath `
        -CompressionLevel Optimal `
        -Force

    Write-Host "验证发布目录和 ZIP..."
    Invoke-CheckedPython `
        -Arguments @(
            (Join-Path $projectRoot "scripts\validate_windows_release.py"),
            "--release-dir",
            $releaseDirectory,
            "--zip",
            $zipPath,
            "--project-root",
            $projectRoot,
            "--version",
            $expectedVersion
        ) `
        -FailureMessage "发布包结构或内容验证失败。"

    $exeHash = (
        Get-FileHash -LiteralPath $releaseExecutable -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    $zipHash = (
        Get-FileHash -LiteralPath $zipPath -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    $hashLines = @(
        "$exeHash  $releaseName/SciType.exe",
        "$zipHash  $releaseName.zip"
    )
    [System.IO.File]::WriteAllLines(
        $hashPath,
        $hashLines,
        [System.Text.UTF8Encoding]::new($false)
    )

    Write-Host ""
    Write-Host "SciType Windows 发布包构建完成："
    Write-Host ([System.IO.Path]::GetFullPath($releaseDirectory))
    Write-Host ([System.IO.Path]::GetFullPath($zipPath))
    Write-Host ([System.IO.Path]::GetFullPath($hashPath))
}
finally {
    Pop-Location
}
