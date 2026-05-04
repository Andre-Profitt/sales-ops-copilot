#requires -Version 5.1
<#
install_openxml.ps1 - bootstrap DocumentFormat.OpenXml SDK on the VM.

Pinned to 2.20.0 - the last self-contained release that loads cleanly into
.NET Framework 4.x (PS5.1) without needing System.IO.Packaging or
System.Memory side-installs. 3.x is modularized with transitive deps that
do not load under PS5.1's CLR.

Idempotent: skips work if package already installed at the pinned version.

Usage (on VM, called by run_xlsx_canary.py before first gate-2 run):
  pwsh -File scripts\vm\install_openxml.ps1
#>

$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'

Write-Host "PowerShell: $($PSVersionTable.PSVersion)  bits=$([IntPtr]::Size * 8)"

# Ensure NuGet provider is registered (required for Install-Package on PS5.1)
$prov = Get-PackageProvider -Name NuGet -ErrorAction SilentlyContinue
if (-not $prov) {
    Write-Host "Bootstrapping NuGet provider..."
    Install-PackageProvider -Name NuGet -MinimumVersion 2.8.5.201 -Force -Scope CurrentUser | Out-Null
}

# Make sure nuget.org is a registered package source
$src = Get-PackageSource -ErrorAction SilentlyContinue | Where-Object { $_.Location -like '*nuget.org*' }
if (-not $src) {
    Write-Host "Registering nuget.org source..."
    Register-PackageSource -Name nugetorg -Location 'https://www.nuget.org/api/v2' -ProviderName NuGet -Trusted -Force | Out-Null
} else {
    Set-PackageSource -Name $src.Name -Trusted -Force | Out-Null
}

# Pin to 2.20.0 - last self-contained release.
$targetVersion = '2.20.0'
$pkg = Get-Package -Name DocumentFormat.OpenXml -RequiredVersion $targetVersion -ErrorAction SilentlyContinue
if (-not $pkg) {
    Write-Host "Installing DocumentFormat.OpenXml v$targetVersion..."
    Install-Package -Name DocumentFormat.OpenXml -RequiredVersion $targetVersion -Source nugetorg -Force -Scope CurrentUser | Out-Null
    $pkg = Get-Package -Name DocumentFormat.OpenXml -RequiredVersion $targetVersion
}
Write-Host "DocumentFormat.OpenXml: $($pkg.Version)"

# Sanity-check that the net35 DLL loads cleanly.
$dllPath = "$env:LOCALAPPDATA\PackageManagement\NuGet\Packages\DocumentFormat.OpenXml.$targetVersion\lib\net35\DocumentFormat.OpenXml.dll"
if (-not (Test-Path -LiteralPath $dllPath)) {
    Write-Host "FAIL: DLL not at expected path: $dllPath"
    exit 1
}
try {
    Add-Type -Path $dllPath -ErrorAction Stop
    $v = [System.Reflection.Assembly]::GetAssembly([DocumentFormat.OpenXml.Packaging.SpreadsheetDocument]).GetName().Version
    Write-Host "Loaded $dllPath  Assembly v$v"
} catch {
    Write-Host "FAIL: could not Add-Type: $($_.Exception.Message)"
    exit 1
}

Write-Host "OK"
