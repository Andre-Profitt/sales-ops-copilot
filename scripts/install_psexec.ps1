$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$dest = "$env:LOCALAPPDATA\PsTools"
$exe = "$dest\PsExec64.exe"

if (Test-Path -LiteralPath $exe) {
    Write-Host "PsExec already installed at $exe"
    exit 0
}

# Download PSTools from Microsoft Sysinternals (signed, free, single-zip distribution)
$url = "https://download.sysinternals.com/files/PSTools.zip"
$zip = "$env:TEMP\PSTools.zip"
Write-Host "Downloading $url"
Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing

New-Item -ItemType Directory -Path $dest -Force | Out-Null
Expand-Archive -Path $zip -DestinationPath $dest -Force
Remove-Item $zip -Force

if (-not (Test-Path -LiteralPath $exe)) {
    Write-Host "PsExec64.exe missing after extract; contents:"
    Get-ChildItem -LiteralPath $dest | Select-Object Name | Format-Table | Out-String | Write-Host
    exit 1
}
Write-Host "PsExec installed: $exe"
& $exe -accepteula -nobanner 2>&1 | Out-Null
Write-Host "EULA accepted"
