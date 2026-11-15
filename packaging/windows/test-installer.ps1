# Tests a built installer for real: installs it silently into a scratch folder under build/ with the desktop
# shortcut on, checks the exe, the installed-apps record, both shortcuts and that `vitralis.exe --version`
# says the version the record shows, installs again over itself, then uninstalls and fails if anything is
# left: files, shortcuts, the record or the installer's own registry key. The release workflow runs it before
# uploading the installer.
# It refuses to run over a real installation or its shortcuts. With Vitralis installed, build and test an
# installer with an identity of its own, the same four options to both scripts:
#   -AppId <new GUID> -AppName "Vitralis Installer Test" -AppKey "Software\Vitralis Installer Test" -AppMutex VitralisInstallerTest
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Installer,
    # What the installer was built with; the defaults are a release installer's.
    [string]$AppId = 'AB080C02-6AA8-4842-973A-AA93F9C4E128',
    [string]$AppName = 'Vitralis',
    [string]$AppKey = 'Software\Vitralis'
)

$ErrorActionPreference = 'Stop'
$Installer = (Resolve-Path -LiteralPath $Installer).Path
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$registryPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{' + $AppId + '}_is1'
$appKeyPath = 'HKCU:\' + $AppKey
$startShortcut = Join-Path ([Environment]::GetFolderPath('Programs')) "$AppName.lnk"
$desktopShortcut = Join-Path ([Environment]::GetFolderPath('DesktopDirectory')) "$AppName.lnk"
foreach ($existing in @($registryPath, $appKeyPath, $startShortcut, $desktopShortcut)) {
    if (Test-Path -LiteralPath $existing) {
        throw "An existing $AppName installation or shortcut prevents this test: $existing. Build and test with -AppId, -AppName, -AppKey and -AppMutex of their own to run beside it."
    }
}
$buildDirectory = Join-Path $projectRoot 'build'
New-Item -ItemType Directory -Force -Path $buildDirectory | Out-Null
$buildDirectory = (Resolve-Path -LiteralPath $buildDirectory).Path
$scratch = Join-Path $buildDirectory ('installer-test-' + [guid]::NewGuid().ToString('N'))
$appDirectory = Join-Path $scratch 'app'
New-Item -ItemType Directory -Path $scratch | Out-Null

function Invoke-SetupProcess([string]$Program, [string[]]$Options) {
    $process = Start-Process -FilePath $Program -ArgumentList $Options -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "$Program failed with exit code $($process.ExitCode)." }
}

try {
    $arguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/LANG=en', '/TASKS=desktopicon', ('/DIR="' + $appDirectory + '"'))
    Invoke-SetupProcess $Installer $arguments
    $app = Join-Path $appDirectory 'vitralis.exe'
    if (!(Test-Path -LiteralPath $app)) { throw 'The installed exe is missing.' }
    $registration = Get-ItemProperty -LiteralPath $registryPath
    if ($registration.DisplayName -ne $AppName) { throw "The installed-apps record is named '$($registration.DisplayName)', not '$AppName'." }
    if ($registration.Publisher -ne 'Breren') { throw "The installed-apps record's publisher is '$($registration.Publisher)'." }
    $shell = New-Object -ComObject WScript.Shell
    foreach ($shortcut in @($startShortcut, $desktopShortcut)) {
        if (!(Test-Path -LiteralPath $shortcut)) { throw "A shortcut is missing: $shortcut" }
        if ($shell.CreateShortcut($shortcut).TargetPath -ne $app) { throw "A shortcut points elsewhere: $shortcut" }
    }
    $output = Join-Path $scratch 'version.txt'
    $process = Start-Process -FilePath $app -ArgumentList '--version' -RedirectStandardOutput $output -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "The installed exe failed with exit code $($process.ExitCode)." }
    $said = (Get-Content -LiteralPath $output -Raw)
    if ($null -eq $said -or $said.Trim() -ne "Vitralis $($registration.DisplayVersion)") {
        throw "The installer says $($registration.DisplayVersion) and the installed exe says '$said'."
    }
    Invoke-SetupProcess $Installer $arguments
    if (!(Test-Path -LiteralPath $app)) { throw 'Installing again over itself lost the exe.' }
    Write-Output 'PASS: install, both shortcuts, installed-apps record, installed version, reinstall'
}
finally {
    $uninstaller = Join-Path $appDirectory 'unins000.exe'
    if (Test-Path -LiteralPath $uninstaller) {
        Invoke-SetupProcess $uninstaller @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART')
    }
    foreach ($remaining in @($registryPath, $appKeyPath, $startShortcut, $desktopShortcut, $appDirectory)) {
        if (Test-Path -LiteralPath $remaining) { throw "Uninstalling left this behind: $remaining" }
    }
    $resolvedScratch = (Resolve-Path -LiteralPath $scratch).Path
    if ([IO.Path]::GetDirectoryName($resolvedScratch) -ne $buildDirectory) {
        throw "Refusing to delete a scratch folder outside this project's build folder: $resolvedScratch"
    }
    Remove-Item -LiteralPath $resolvedScratch -Recurse -Force
}
Write-Output 'PASS: uninstall removed the files, both shortcuts, the record and the registry key'
