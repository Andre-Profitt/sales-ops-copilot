<#
Office Deployment Tool (ODT) -- proper version-pinned rollback via setup.exe.

Steps:
  1. Download latest ODT installer from MS (~3MB)
  2. Self-extract to get setup.exe + sample XMLs
  3. Generate Configuration.xml pinning Version=16.0.19822.20182
  4. Run elevated setup.exe /configure Configuration.xml
     -- this triggers a UAC prompt on the user's desktop
     -- user clicks Yes
     -- ODT downloads + installs the pinned version (10-15 min)
  5. Verify version flipped
#>
$ErrorActionPreference = "Continue"
Start-Transcript -Path "$env:USERPROFILE\odt_rollback.log" -Force | Out-Null

$workDir = "$env:USERPROFILE\odt_work"
New-Item -ItemType Directory -Path $workDir -Force | Out-Null

# 1. Download ODT
# Microsoft provides a stable download alias that always returns the latest ODT installer
Write-Host "[1] Downloading ODT installer..."
$odtInstallerUrl = "https://officecdn.microsoft.com/db/492350F6-3A01-4F97-B9C0-C7C6DDF67D60/media/en-us/Setup.X64.exe"
$alternativeUrls = @(
    # The ODT download URL - typically a fwlink redirect
    "https://download.microsoft.com/download/2/7/A/27AF1BE6-DD20-4CB4-B154-EBAB8A7D4A7E/officedeploymenttool_18526-20144.exe",
    "https://download.microsoft.com/download/officedeploymenttool/officedeploymenttool.exe"
)

# Actually the simplest path: we already have setup.exe shipped with ClickToRun
# It's at C:\Program Files\Common Files\Microsoft Shared\ClickToRun\OfficeC2RClient.exe
# But for ODT-style /configure we need the standalone setup.exe.
# Let's check if it's in the install or download fresh.
$existingSetup = "C:\Program Files\Common Files\Microsoft Shared\ClickToRun\OfficeClickToRun.exe"
$setupExe = "$workDir\setup.exe"

# Try direct fwlink for ODT
$fwlink = "https://www.microsoft.com/en-us/download/confirmation.aspx?id=49117"
Write-Host "  trying fwlink..."

# Easier approach: pull the latest known ODT setup.exe from MS download
# The current stable URL pattern (May 2026): fwlink id=2253930 redirects to the latest
$urls = @(
    "https://go.microsoft.com/fwlink/p/?LinkID=626065",  # Office Deployment Tool fwlink
    "https://download.microsoft.com/download/2/7/A/27AF1BE6-DD20-4CB4-B154-EBAB8A7D4A7E/officedeploymenttool_18526-20144.exe"
)

$installerPath = "$workDir\OfficeDeploymentTool.exe"
$downloaded = $false
foreach ($u in $urls) {
    try {
        Write-Host "  trying: $u"
        Invoke-WebRequest -Uri $u -OutFile $installerPath -UseBasicParsing -TimeoutSec 60 -ErrorAction Stop
        if ((Get-Item $installerPath).Length -gt 100000) {
            $downloaded = $true
            Write-Host "  downloaded $((Get-Item $installerPath).Length) bytes"
            break
        }
    } catch {
        Write-Host "  failed: $($_.Exception.Message)"
    }
}

if (-not $downloaded) {
    Write-Host "[!] Could not download ODT installer from any URL"
    Stop-Transcript | Out-Null
    exit 1
}

# 2. Self-extract ODT to get setup.exe
Write-Host "[2] Extracting ODT installer..."
$extractDir = "$workDir\extracted"
New-Item -ItemType Directory -Path $extractDir -Force | Out-Null
& $installerPath /quiet /extract:$extractDir
Start-Sleep -Seconds 5

if (-not (Test-Path "$extractDir\setup.exe")) {
    Write-Host "[!] setup.exe not found after extract. Listing $extractDir :"
    Get-ChildItem $extractDir -Recurse | Select-Object Name, Length, FullName | Format-Table -AutoSize
    Stop-Transcript | Out-Null
    exit 2
}
$setupExe = "$extractDir\setup.exe"
Write-Host "  setup.exe at: $setupExe ($((Get-Item $setupExe).Length) bytes)"

# 3. Generate Configuration.xml pinning version
$configXml = @"
<Configuration>
  <Updates Enabled="FALSE" />
  <Add OfficeClientEdition="64" Channel="Current" Version="16.0.19822.20182" SourcePath="">
    <Product ID="O365ProPlusRetail">
      <Language ID="en-us" />
    </Product>
  </Add>
  <Display Level="Full" AcceptEULA="TRUE" />
  <Property Name="FORCEAPPSHUTDOWN" Value="TRUE" />
  <Property Name="SharedComputerLicensing" Value="0" />
  <RemoveMSI />
</Configuration>
"@
$configPath = "$workDir\Configuration.xml"
Set-Content -LiteralPath $configPath -Value $configXml -Force
Write-Host "[3] Wrote config: $configPath"

# 4. Run setup.exe /configure ELEVATED
# Start-Process -Verb RunAs triggers UAC prompt on user's desktop
Write-Host "[4] Launching setup.exe /configure (UAC prompt will appear on your desktop)..."
Write-Host "    Click YES on the UAC prompt to continue."

# Stop Office apps first
Get-Process POWERPNT, EXCEL, WINWORD, OUTLOOK, ONENOTE -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 3

try {
    # -Wait makes us block until setup.exe completes
    # -Verb RunAs triggers UAC prompt
    # -PassThru returns process info
    $proc = Start-Process -FilePath $setupExe `
        -ArgumentList "/configure", "`"$configPath`"" `
        -Verb RunAs `
        -Wait `
        -PassThru `
        -ErrorAction Stop
    Write-Host "[5] setup.exe exited with code: $($proc.ExitCode)"
} catch {
    Write-Host "[!] setup.exe launch failed: $($_.Exception.Message)" -ForegroundColor Red
    Stop-Transcript | Out-Null
    exit 3
}

# 5. Verify version
$reg = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Office\ClickToRun\Configuration" -ErrorAction SilentlyContinue
$final = $reg.VersionToReport
$ppExe = "C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE"
$ppVer = if (Test-Path $ppExe) { (Get-Item $ppExe).VersionInfo.FileVersion } else { "(missing)" }

Write-Host ""
Write-Host "========================================"
Write-Host " ODT ROLLBACK RESULT"
Write-Host "========================================"
Write-Host "  registry VersionToReport: $final"
Write-Host "  POWERPNT.EXE FileVersion: $ppVer"

if ($final -eq "16.0.19822.20182") {
    Write-Host "  STATUS: SUCCESS" -ForegroundColor Green
} else {
    Write-Host "  STATUS: did not flip to 19822.20182" -ForegroundColor Yellow
}
Stop-Transcript | Out-Null
