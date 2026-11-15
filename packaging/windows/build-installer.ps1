# Builds Vitralis's Windows installer around the portable exe: dist/vitralis-<version>-windows-x86_64-setup.exe.
# `uv run build` runs it after PyInstaller; on its own it takes the exe `uv run build` left in dist/.
# The version is read from pyproject.toml, never typed in. The installer test passes -AppId, -AppName,
# -AppKey and -AppMutex of its own; never release an installer built with them.
[CmdletBinding()]
param(
    [string]$Binary,
    [string]$OutputDirectory,
    [string]$Icon,
    [string]$Compiler,
    [string]$AppId,
    [string]$AppName,
    [string]$AppKey,
    [string]$AppMutex
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path

$manifest = Get-Content -LiteralPath (Join-Path $projectRoot 'pyproject.toml') -Raw
if ($manifest -notmatch '(?m)^version\s*=\s*"([^"]+)"') { throw 'pyproject.toml has no version.' }
$version = $Matches[1]

if (!$Binary) { $Binary = Join-Path $projectRoot "dist/vitralis-$version-windows-x86_64.exe" }
if (!$OutputDirectory) { $OutputDirectory = Join-Path $projectRoot 'dist' }
if (!$Icon) { $Icon = Join-Path $projectRoot 'build/vitralis.ico' }
foreach ($needed in @($Binary, $Icon)) {
    if (!(Test-Path -LiteralPath $needed)) { throw "$needed is missing: build the exe first with ``uv run build``." }
}
$Binary = (Resolve-Path -LiteralPath $Binary).Path
$Icon = (Resolve-Path -LiteralPath $Icon).Path
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)

if (!$Compiler -and $env:ISCC) { $Compiler = $env:ISCC }
if (!$Compiler) {
    $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($command) { $Compiler = $command.Source }
    else {
        $locations = @(
            "$env:LOCALAPPDATA/Programs/Inno Setup 6/ISCC.exe",
            "${env:ProgramFiles(x86)}/Inno Setup 6/ISCC.exe",
            "$env:ProgramFiles/Inno Setup 6/ISCC.exe"
        )
        $Compiler = $locations | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
}
if (!$Compiler -or !(Test-Path -LiteralPath $Compiler)) {
    throw 'Inno Setup 6 is missing: winget install JRSoftware.InnoSetup, or pass -Compiler (or set ISCC) with the path to ISCC.exe.'
}

$defines = @(
    '/Q',
    "/DAppVersion=$version",
    "/DAppBinary=$Binary",
    "/DIconFile=$Icon",
    "/DLicenseFile=$(Join-Path $projectRoot 'LICENSE')",
    "/DDistDir=$OutputDirectory"
)
if ($AppId) { $defines += "/DAppId={{$AppId}" }
if ($AppName) { $defines += "/DAppName=$AppName" }
if ($AppKey) { $defines += "/DAppKey=$AppKey" }
if ($AppMutex) { $defines += "/DAppMutex=$AppMutex" }
& $Compiler @defines (Join-Path $PSScriptRoot 'vitralis.iss')
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed with exit code $LASTEXITCODE." }
$installer = Join-Path $OutputDirectory "vitralis-$version-windows-x86_64-setup.exe"
if (!(Test-Path -LiteralPath $installer)) { throw "The installer wasn't produced: $installer" }
Write-Output $installer
